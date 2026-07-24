"""
Vista "Note di Campagna" della Modalità Master — terza tab di `MasterView`,
insieme a "Rubrica NPC" e "Incontri". Vedi `dnd_app/docs/master_section_design.md`
sezione "5. Note di Campagna del Master" per il design completo.

Nessuna fonte DMG coinvolta — è un puro strumento organizzativo per il
Master (PNG da tenere d'occhio, luoghi, missioni, fazioni, eventi, segreti),
indipendente da ogni personaggio giocante (a differenza di `campaign_notes`/
`DiaryView`, che sono per-personaggio).

Layout a due pannelli, stesso pattern già collaudato in `DiaryView` (mai
`expand=True` su Column dentro Row dentro ListView, `cast(list[ft.Control], [...])`
per `actions=`, `Any` per gli handler):

  Pannello sinistro (200px): 8 categorie cliccabili + lista voci categoria attiva
  Pannello destro (flex):    pagina di lettura stile pergamena + editor inline
"""

from __future__ import annotations

import logging
from typing import Any, cast

import flet as ft

from config.settings import (
    COLOR_TEXT_TITLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_BORDER, COLOR_BG_CARD,
    COLOR_ACCENT_CRIMSON,
)
from data.models import MasterCampaignNote, MasterNpc
from data.repositories import master_repo

logger = logging.getLogger(__name__)

# ── Costanti visive (stesse di DiaryView, per coerenza) ─────────────────────
_PARCHMENT  = "#fffef6"
_LIST_BG    = "#f7f2e8"
_NAV_SEL_BG = COLOR_ACCENT_CRIMSON + "1a"

_STATUS_GREEN  = "#2e7d32"
_STATUS_ORANGE = "#e65100"
_STATUS_RED    = COLOR_ACCENT_CRIMSON
_STATUS_GRAY   = COLOR_TEXT_MUTED

# ── Definizioni categorie ────────────────────────────────────────────────────
CATEGORIES: list[dict[str, Any]] = [
    {
        "key": "npc", "label": "PNG Incontrati",
        "icon_off": ft.Icons.PEOPLE_OUTLINE, "icon_on": ft.Icons.PEOPLE,
        "list_label": "PERSONAGGI", "add_label": "Aggiungi PNG",
        "empty_msg": "Nessun personaggio registrato.\nAggiungi i PNG che vuoi tenere d'occhio.",
    },
    {
        "key": "npc_todo", "label": "PNG da Cercare",
        "icon_off": ft.Icons.PERSON_SEARCH_OUTLINED, "icon_on": ft.Icons.PERSON_SEARCH,
        "list_label": "DA TROVARE", "add_label": "Aggiungi PNG",
        "empty_msg": "Nessun personaggio da cercare.\nAggiungi chi il gruppo deve ancora incontrare.",
    },
    {
        "key": "place", "label": "Luoghi",
        "icon_off": ft.Icons.PLACE_OUTLINED, "icon_on": ft.Icons.PLACE,
        "list_label": "LUOGHI", "add_label": "Aggiungi Luogo",
        "empty_msg": "Nessun luogo registrato.\nAggiungi i luoghi della tua campagna.",
    },
    {
        "key": "place_todo", "label": "Da Esplorare",
        "icon_off": ft.Icons.EXPLORE_OUTLINED, "icon_on": ft.Icons.EXPLORE,
        "list_label": "OBIETTIVI", "add_label": "Aggiungi Luogo",
        "empty_msg": "Nessun obiettivo segnato.\nAggiungi i luoghi che il gruppo non ha ancora esplorato.",
    },
    {
        "key": "quest", "label": "Missioni",
        "icon_off": ft.Icons.ASSIGNMENT_OUTLINED, "icon_on": ft.Icons.ASSIGNMENT,
        "list_label": "MISSIONI", "add_label": "Aggiungi Missione",
        "empty_msg": "Nessuna missione registrata.\nTieni traccia delle quest della campagna.",
    },
    {
        "key": "faction", "label": "Fazioni",
        "icon_off": ft.Icons.FLAG_OUTLINED, "icon_on": ft.Icons.FLAG,
        "list_label": "FAZIONI", "add_label": "Aggiungi Fazione",
        "empty_msg": "Nessuna fazione registrata.\nTieni traccia delle organizzazioni della campagna.",
    },
    {
        "key": "event", "label": "Eventi",
        "icon_off": ft.Icons.EVENT_OUTLINED, "icon_on": ft.Icons.EVENT,
        "list_label": "EVENTI", "add_label": "Aggiungi Evento",
        "empty_msg": "Nessun evento registrato.\nTieni traccia di eventi in corso o pianificati.",
    },
    {
        "key": "secret", "label": "Segreti",
        "icon_off": ft.Icons.LOCK_OUTLINE, "icon_on": ft.Icons.LOCK,
        "list_label": "SEGRETI", "add_label": "Aggiungi Segreto",
        "empty_msg": "Nessun segreto registrato.\nAppunti riservati al solo Master.",
    },
]

STATUS_OPTIONS: dict[str, list[str]] = {
    "npc":        ["alleato", "neutrale", "ostile", "sconosciuto"],
    "npc_todo":   ["cercato", "sentito nominare", "leggenda"],
    "place":      ["esplorato", "parzialmente esplorato"],
    "place_todo": ["da esplorare", "sentito nominare", "leggenda/rumor"],
    "quest":      ["attiva", "completata", "fallita", "in pausa"],
    "faction":    ["alleata", "neutrale", "ostile", "sconosciuta"],
    "event":      ["pianificato", "in corso", "concluso"],
    "secret":     ["nascosto", "parzialmente svelato", "svelato"],
}

_STATUS_COLOR_MAP: dict[str, str] = {
    "alleato": _STATUS_GREEN, "esplorato": _STATUS_GREEN,
    "completata": _STATUS_GREEN, "alleata": _STATUS_GREEN,
    "concluso": _STATUS_GREEN, "svelato": _STATUS_GREEN,
    "neutrale": _STATUS_ORANGE, "parzialmente esplorato": _STATUS_ORANGE,
    "in pausa": _STATUS_ORANGE, "cercato": _STATUS_ORANGE,
    "in corso": _STATUS_ORANGE, "parzialmente svelato": _STATUS_ORANGE,
    "ostile": _STATUS_RED, "fallita": _STATUS_RED,
}


def _status_color(status: str) -> str:
    return _STATUS_COLOR_MAP.get(status, _STATUS_GRAY)


def _cat_meta(key: str) -> dict[str, Any]:
    for c in CATEGORIES:
        if c["key"] == key:
            return c
    return CATEGORIES[0]


# ══════════════════════════════════════════════════════════════════════════
# MasterNotesView
# ══════════════════════════════════════════════════════════════════════════

class MasterNotesView(ft.Column):
    """Vista Note di Campagna del Master, due pannelli — stesso layout di
    `DiaryView` ma senza Cronaca e senza `character_id` (indipendente da ogni
    personaggio)."""

    def __init__(self):
        super().__init__(expand=True, spacing=0)
        self._page: ft.Page | None = None

        self._active_cat: str = "npc"
        self._notes: dict[str, list[MasterCampaignNote]] = {}
        self._npcs: list[MasterNpc] = []
        self._sel_note_id: str | None = None
        self._note_edit: bool = False

        # campi editor nota (impostati in _build_note_edit_panel)
        self._nf_name:   ft.TextField = ft.TextField()
        self._nf_status: ft.Dropdown = ft.Dropdown()
        self._nf_tags:   ft.TextField = ft.TextField()
        self._nf_desc:   ft.TextField = ft.TextField()
        self._nf_npc:    ft.Dropdown = ft.Dropdown()

        self._detail_container: ft.Container = ft.Container(expand=True)
        self._left_list_lv: ft.ListView = ft.ListView(expand=True, spacing=2,
                                                        padding=ft.Padding.only(bottom=8))

        self._load_all()
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    # ──────────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        for cat in CATEGORIES:
            self._notes[cat["key"]] = master_repo.get_master_campaign_notes(cat["key"])
        self._npcs = master_repo.get_npcs()

    def _load_notes(self, cat: str) -> None:
        self._notes[cat] = master_repo.get_master_campaign_notes(cat)

    def _npc_name(self, npc_id: str) -> str:
        for n in self._npcs:
            if n.id == npc_id:
                return n.name or "(senza nome)"
        return ""

    # ──────────────────────────────────────────────────────────────────────
    # Build principale
    # ──────────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.controls.clear()

        notes = self._notes.get(self._active_cat, [])
        if notes and self._sel_note_id is None:
            self._sel_note_id = notes[0].id

        self._detail_container = ft.Container(expand=True, content=self._build_detail_panel())

        body = ft.Row(
            [
                self._build_left_panel(),
                ft.VerticalDivider(width=1, color=COLOR_BORDER),
                self._detail_container,
            ],
            expand=True, spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        self.controls.append(self._build_header())
        self.controls.append(ft.Divider(height=1, color=COLOR_BORDER))
        self.controls.append(body)

    # ──────────────────────────────────────────────────────────────────────
    # Header
    # ──────────────────────────────────────────────────────────────────────

    def _build_header(self) -> ft.Container:
        meta = _cat_meta(self._active_cat)
        total = len(self._notes.get(self._active_cat, []))
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(meta["icon_on"], color=COLOR_ACCENT_CRIMSON, size=20),
                    ft.Container(width=10),
                    ft.Column(
                        [
                            ft.Text("Note di Campagna", size=15, weight=ft.FontWeight.BOLD,
                                    color=COLOR_TEXT_TITLE),
                            ft.Text(
                                f"{meta['label']} · {total} {'voce' if total == 1 else 'voci'}",
                                size=11, color=COLOR_TEXT_MUTED,
                            ),
                        ],
                        spacing=1, expand=True,
                    ),
                    ft.ElevatedButton(
                        meta["add_label"], icon=ft.Icons.ADD,
                        on_click=lambda e: self._open_new_note_dialog(),
                        style=ft.ButtonStyle(
                            bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                            shape=ft.RoundedRectangleBorder(radius=4),
                            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=18, vertical=10),
            border=ft.Border(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Pannello sinistro
    # ──────────────────────────────────────────────────────────────────────

    def _build_left_panel(self) -> ft.Container:
        meta = _cat_meta(self._active_cat)

        cat_nav = ft.Column(
            [
                ft.Container(
                    content=ft.Text("SEZIONI", size=9, weight=ft.FontWeight.BOLD,
                                     color=COLOR_TEXT_MUTED,
                                     style=ft.TextStyle(letter_spacing=2)),
                    padding=ft.Padding.only(left=12, top=10, bottom=4),
                ),
                *[self._cat_button(c) for c in CATEGORIES],
            ],
            spacing=1,
        )

        list_label = ft.Container(
            content=ft.Text(meta["list_label"], size=9, weight=ft.FontWeight.BOLD,
                             color=COLOR_TEXT_MUTED,
                             style=ft.TextStyle(letter_spacing=2)),
            padding=ft.Padding.only(left=12, top=8, bottom=4),
        )

        items = self._build_note_list_items()
        self._left_list_lv = ft.ListView(
            controls=items, expand=True, spacing=2,
            padding=ft.Padding.only(left=4, right=4, bottom=12),
        )

        return ft.Container(
            content=ft.Column(
                [cat_nav, ft.Divider(height=1, color=COLOR_BORDER), list_label, self._left_list_lv],
                expand=True, spacing=0,
            ),
            width=200, bgcolor=_LIST_BG,
        )

    def _cat_button(self, cat: dict[str, Any]) -> ft.Container:
        is_sel = cat["key"] == self._active_cat
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(cat["icon_on"] if is_sel else cat["icon_off"], size=16,
                            color="#ffffff" if is_sel else COLOR_TEXT_SECONDARY),
                    ft.Container(width=8),
                    ft.Text(cat["label"], size=12,
                            color="#ffffff" if is_sel else COLOR_TEXT_PRIMARY,
                            weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                            expand=True),
                    self._count_badge(cat["key"]),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            bgcolor=COLOR_ACCENT_CRIMSON if is_sel else "transparent",
            border_radius=6,
            margin=ft.Margin.only(left=6, right=6),
            on_click=lambda e, k=cat["key"]: self._on_cat_click(k),
            ink=True,
        )

    def _count_badge(self, key: str) -> ft.Container:
        n = len(self._notes.get(key, []))
        if n == 0:
            return ft.Container(width=0)
        return ft.Container(
            content=ft.Text(str(n), size=9, color=COLOR_TEXT_MUTED,
                             text_align=ft.TextAlign.CENTER),
            bgcolor=COLOR_BORDER, border_radius=8,
            padding=ft.Padding.symmetric(horizontal=5, vertical=1),
        )

    def _build_note_list_items(self) -> list[ft.Control]:
        notes = self._notes.get(self._active_cat, [])
        meta = _cat_meta(self._active_cat)
        if not notes:
            return [self._left_empty(meta["empty_msg"])]
        return [self._note_list_item(n) for n in notes]

    def _note_list_item(self, note: MasterCampaignNote) -> ft.Container:
        is_sel = note.id == self._sel_note_id
        sc = _status_color(note.status)

        status_chip = ft.Container(
            content=ft.Text(note.status or "—", size=9, color="#ffffff",
                             weight=ft.FontWeight.BOLD),
            bgcolor=sc, border_radius=8,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        ) if note.status else ft.Container(height=0)

        preview = (note.description or "").replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "…"

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(note.name or "Senza nome", size=12,
                            weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                            color=COLOR_TEXT_TITLE if is_sel else COLOR_TEXT_PRIMARY,
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ft.Row([status_chip], spacing=4) if note.status else ft.Container(height=0),
                    ft.Text(preview, size=10, color=COLOR_TEXT_MUTED,
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1) if preview else ft.Container(height=0),
                ],
                spacing=3,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            bgcolor=_NAV_SEL_BG if is_sel else "transparent",
            border_radius=6,
            border=ft.Border.all(1, COLOR_ACCENT_CRIMSON) if is_sel else None,
            on_click=lambda e, nid=note.id: self._on_sel_note(nid),
            ink=True,
        )

    def _left_empty(self, msg: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(msg, size=11, color=COLOR_TEXT_MUTED, text_align=ft.TextAlign.CENTER),
            padding=ft.Padding.symmetric(horizontal=10, vertical=16),
            alignment=ft.Alignment.CENTER,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Pannello destro
    # ──────────────────────────────────────────────────────────────────────

    def _build_detail_panel(self) -> ft.Control:
        note = self._get_sel_note()
        meta = _cat_meta(self._active_cat)
        if note is None:
            return self._full_empty_state(
                meta["icon_on"], f"Nessuna {meta['label'].lower()} selezionata", meta["empty_msg"],
            )
        if self._note_edit:
            return self._build_note_edit_panel(note)
        return self._build_note_reading_panel(note)

    def _build_note_reading_panel(self, note: MasterCampaignNote) -> ft.Column:
        sc = _status_color(note.status)

        status_row: list[ft.Control] = []
        if note.status:
            status_row.append(
                ft.Container(
                    content=ft.Text(note.status, size=11, color="#ffffff", weight=ft.FontWeight.BOLD),
                    bgcolor=sc, border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                )
            )

        tag_chips: list[ft.Control] = []
        if note.tags:
            for tag in [t.strip() for t in note.tags.split(",") if t.strip()]:
                tag_chips.append(
                    ft.Container(
                        content=ft.Text(f"#{tag}", size=10, color=COLOR_TEXT_SECONDARY),
                        bgcolor=COLOR_BORDER + "80", border_radius=8,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    )
                )

        ornament = ft.Row(
            [
                ft.Container(expand=True, height=1, bgcolor=COLOR_BORDER),
                ft.Container(content=ft.Icon(ft.Icons.STAR, size=11, color=COLOR_ACCENT_CRIMSON),
                             padding=ft.Padding.symmetric(horizontal=10)),
                ft.Container(expand=True, height=1, bgcolor=COLOR_BORDER),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        page_content_items: list[ft.Control] = []
        if status_row:
            page_content_items.append(ft.Row(status_row, alignment=ft.MainAxisAlignment.CENTER))
            page_content_items.append(ft.Container(height=10))

        page_content_items += [
            ft.Text(note.name or "Senza nome", size=22, weight=ft.FontWeight.BOLD,
                    color=COLOR_TEXT_TITLE, text_align=ft.TextAlign.CENTER, italic=True),
            ft.Container(height=14),
            ornament,
            ft.Container(height=18),
        ]

        if note.description:
            page_content_items.append(
                ft.Text(note.description, size=14, color=COLOR_TEXT_PRIMARY, selectable=True)
            )

        npc_name = self._npc_name(note.linked_npc_id) if note.linked_npc_id else ""
        if npc_name:
            page_content_items += [
                ft.Container(height=14),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.PERSON, size=14, color=COLOR_TEXT_MUTED),
                        ft.Container(width=6),
                        ft.Text(f"PNG collegato: {npc_name}", size=12,
                                color=COLOR_TEXT_SECONDARY, italic=True),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ]

        if tag_chips:
            page_content_items += [
                ft.Container(height=20),
                ft.Divider(height=1, color=COLOR_BORDER),
                ft.Container(height=8),
                ft.Row(tag_chips, wrap=True, spacing=6, run_spacing=6),
            ]

        page_content_items.append(ft.Container(height=32))

        page_content = ft.Column(page_content_items, scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.OutlinedButton("Modifica", icon=ft.Icons.EDIT_OUTLINED,
                                       on_click=lambda e: self._on_note_start_edit()),
                    ft.Container(width=8),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=COLOR_ACCENT_CRIMSON,
                                  icon_size=18, tooltip="Elimina",
                                  on_click=lambda e: self._on_note_delete()),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border(top=ft.BorderSide(1, COLOR_BORDER)),
        )

        return ft.Column(
            [
                ft.Container(content=page_content, expand=True, bgcolor=_PARCHMENT,
                             padding=ft.Padding.symmetric(horizontal=56, vertical=32)),
                action_bar,
            ],
            spacing=0, expand=True,
        )

    def _build_note_edit_panel(self, note: MasterCampaignNote) -> ft.Column:
        opts = STATUS_OPTIONS.get(self._active_cat, [])
        self._nf_name = ft.TextField(
            value=note.name or "", label="Nome", autofocus=True,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor="transparent", label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=11),
        )
        self._nf_status = ft.Dropdown(
            label="Stato",
            value=note.status or (opts[0] if opts else ""),
            options=[ft.DropdownOption(key=s, text=s) for s in opts],
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor="transparent", label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=11),
        )
        self._nf_tags = ft.TextField(
            value=note.tags or "",
            label="Tag (separati da virgola — es. corte, waterdeep, alleanza)",
            text_style=ft.TextStyle(size=12, color=COLOR_TEXT_SECONDARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor="transparent", label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=11),
        )
        npc_opts = [ft.DropdownOption(key="", text="— nessuno —")] + [
            ft.DropdownOption(key=n.id, text=n.name or "(senza nome)") for n in self._npcs
        ]
        self._nf_npc = ft.Dropdown(
            label="PNG collegato (opzionale)",
            value=note.linked_npc_id or "",
            options=npc_opts,
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor="transparent", label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=11),
        )
        self._nf_desc = ft.TextField(
            value=note.description or "", label="Descrizione / Note",
            multiline=True, min_lines=10, max_lines=30,
            text_style=ft.TextStyle(size=14, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor="transparent", label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=11),
        )

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.TextButton("Annulla", on_click=lambda e: self._on_note_cancel_edit(),
                                  style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY)),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Salva", icon=ft.Icons.SAVE_OUTLINED,
                        on_click=lambda e: self._on_note_save_edit(note),
                        style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                              shape=ft.RoundedRectangleBorder(radius=4)),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border(top=ft.BorderSide(1, COLOR_BORDER)),
        )

        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [self._nf_name, self._nf_status, self._nf_npc, self._nf_tags, self._nf_desc],
                        spacing=14, scroll=ft.ScrollMode.AUTO,
                    ),
                    expand=True, bgcolor=_PARCHMENT,
                    padding=ft.Padding.symmetric(horizontal=48, vertical=28),
                ),
                action_bar,
            ],
            spacing=0, expand=True,
        )

    def _full_empty_state(self, icon: Any, title: str, msg: str) -> ft.Container:
        return ft.Container(
            expand=True, bgcolor=_PARCHMENT,
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, color=COLOR_BORDER),
                    ft.Container(height=16),
                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_SECONDARY,
                            italic=True, text_align=ft.TextAlign.CENTER),
                    ft.Container(height=8),
                    ft.Text(msg, size=13, color=COLOR_TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Helper
    # ──────────────────────────────────────────────────────────────────────

    def _get_sel_note(self) -> MasterCampaignNote | None:
        if not self._sel_note_id:
            return None
        for n in self._notes.get(self._active_cat, []):
            if n.id == self._sel_note_id:
                return n
        return None

    # ──────────────────────────────────────────────────────────────────────
    # Event handlers — navigazione categorie
    # ──────────────────────────────────────────────────────────────────────

    def _on_cat_click(self, key: str) -> None:
        if key == self._active_cat:
            return
        self._active_cat = key
        self._note_edit = False
        # Non resettare la selezione per categoria → ricorda l'ultima voce vista
        if self._notes.get(key) and not any(
            n.id == self._sel_note_id for n in self._notes.get(key, [])
        ):
            self._sel_note_id = None
        self._refresh()

    # ──────────────────────────────────────────────────────────────────────
    # Event handlers — note
    # ──────────────────────────────────────────────────────────────────────

    def _on_sel_note(self, note_id: str) -> None:
        if note_id == self._sel_note_id and not self._note_edit:
            return
        self._sel_note_id = note_id
        self._note_edit = False
        self._refresh()

    def _on_note_start_edit(self) -> None:
        self._note_edit = True
        self._update_detail()

    def _on_note_cancel_edit(self) -> None:
        self._note_edit = False
        self._update_detail()

    def _on_note_save_edit(self, note: MasterCampaignNote) -> None:
        name   = (self._nf_name.value or "").strip() or "Senza nome"
        status = (self._nf_status.value or "").strip()
        tags   = (self._nf_tags.value or "").strip()
        desc   = (self._nf_desc.value or "").strip()
        npc_id = (self._nf_npc.value or "").strip()
        master_repo.update_master_campaign_note(note.id, name, desc, status, tags, npc_id)
        logger.info("Master campaign note aggiornata: %s", note.id)
        self._note_edit = False
        self._load_notes(self._active_cat)
        self._refresh()

    def _on_note_delete(self) -> None:
        page = self._page
        if page is None:
            return
        note = self._get_sel_note()
        if note is None:
            return

        def do_delete(ev: Any) -> None:
            if page is None:
                return
            master_repo.delete_master_campaign_note(note.id)
            page.pop_dialog()
            self._load_notes(self._active_cat)
            notes = self._notes.get(self._active_cat, [])
            self._sel_note_id = notes[0].id if notes else None
            self._note_edit = False
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Elimina voce", size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Text(
                f"Eliminare «{note.name or 'Senza nome'}»?\nL'azione non è reversibile.",
                size=13, color=COLOR_TEXT_PRIMARY,
            ),
            actions=cast(list[ft.Control], [
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=do_delete,
                    style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                          shape=ft.RoundedRectangleBorder(radius=4)),
                ),
            ]),
            bgcolor=COLOR_BG_CARD,
        ))

    def _open_new_note_dialog(self) -> None:
        page = self._page
        if page is None:
            return
        cat  = self._active_cat
        meta = _cat_meta(cat)
        opts = STATUS_OPTIONS.get(cat, [])

        f_name = ft.TextField(
            label="Nome", autofocus=True,
            text_style=ft.TextStyle(size=14, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        f_status = ft.Dropdown(
            label="Stato", value=opts[0] if opts else "",
            options=[ft.DropdownOption(key=s, text=s) for s in opts],
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        npc_opts = [ft.DropdownOption(key="", text="— nessuno —")] + [
            ft.DropdownOption(key=n.id, text=n.name or "(senza nome)") for n in self._npcs
        ]
        f_npc = ft.Dropdown(
            label="PNG collegato (opzionale)", value="",
            options=npc_opts,
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        f_desc = ft.TextField(
            label="Descrizione / Note", multiline=True, min_lines=3, max_lines=8,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )

        def save(ev: Any) -> None:
            if page is None:
                return
            name   = (f_name.value or "").strip() or "Senza nome"
            status = (f_status.value or "").strip()
            desc   = (f_desc.value or "").strip()
            npc_id = (f_npc.value or "").strip()
            master_repo.create_master_campaign_note(cat, name, desc, status, "", npc_id)
            page.pop_dialog()
            self._load_notes(cat)
            notes = self._notes.get(cat, [])
            if notes:
                self._sel_note_id = notes[-1].id
            self._note_edit = False
            self._refresh()

        fields: list[ft.Control] = [f_name]
        if opts:
            fields.append(f_status)
        if self._npcs:
            fields.append(f_npc)
        fields.append(f_desc)

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(meta["add_label"], size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(fields, spacing=10, scroll=ft.ScrollMode.AUTO, width=400),
            actions=cast(list[ft.Control], [
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Crea", icon=ft.Icons.ADD, on_click=save,
                    style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                          shape=ft.RoundedRectangleBorder(radius=4)),
                ),
            ]),
            bgcolor=COLOR_BG_CARD,
        ))

    # ──────────────────────────────────────────────────────────────────────
    # Refresh
    # ──────────────────────────────────────────────────────────────────────

    def _update_detail(self) -> None:
        self._detail_container.content = self._build_detail_panel()
        try:
            self._detail_container.update()
        except RuntimeError:
            pass

    def _refresh(self) -> None:
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
