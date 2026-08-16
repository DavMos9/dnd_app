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

import json
import logging
from typing import Any, cast

import flet as ft

from core import world_permissions as perm
from core import world_sync
from core.world_backend import LocalBackend
from data.models import MasterCampaignNote, MasterNpc, WorldMember
from data.repositories import master_repo, world_repo
from ui.widgets import wrap_dialog_actions, responsive_dialog_width, show_snack
from ui import design

logger = logging.getLogger(__name__)

#: Opzioni del selettore "Visibilità" — significativo solo quando la vista è
#: legata a un mondo (`world_id` non vuoto), vedi il docstring della classe.
_VISIBILITY_OPTIONS: list[tuple[str, str]] = [
    ("private", "Privata (solo il Master)"),
    ("all", "Tutti i giocatori del mondo"),
    ("selected", "Solo i giocatori selezionati"),
]

# ── Costanti visive (stesse di DiaryView, per coerenza) ─────────────────────


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

_STATUS_TONES: dict[str, str] = {
    "alleato": "success", "esplorato": "success",
    "completata": "success", "alleata": "success",
    "concluso": "success", "svelato": "success",
    "neutrale": "warning", "parzialmente esplorato": "warning",
    "in pausa": "warning", "cercato": "warning",
    "in corso": "warning", "parzialmente svelato": "warning",
    "ostile": "danger", "fallita": "danger",
}


def _status_color(status: str) -> str:
    return getattr(design.T(), _STATUS_TONES.get(status, "text_3"))


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
    personaggio).

    **`world_id` (2026-08-06)** — il mondo correntemente selezionato in
    `MasterView`, "" per la modalità locale. Determina:

    1. quali note sono visibili qui (`get_master_campaign_notes(world_id=...)`
       — una nota nasce legata al mondo attivo al momento della creazione e
       non lo cambia più, stessa scelta di `create_master_campaign_note()`);
    2. se il selettore "Visibilità" compare nell'editor — solo con un mondo
       selezionato ha senso scegliere chi tra i giocatori può vedere una
       nota (vedi `multiplayer_design.md` §7).

    **Nota onesta**: questo passo registra correttamente l'intenzione del
    Master (`visibility`/`visible_to_device_ids`, persistite nel DB), ma NON
    ancora la consegna effettiva ai dispositivi dei giocatori — serve un
    nuovo tipo di evento nel giornale del mondo più una schermata lato
    giocatore che oggi non esiste. Vedi CLAUDE.md.

    **`is_mobile` (2026-08-06, bug report Davide su smartphone reale —
    screenshot)**: il layout a due pannelli fissi ("SEZIONI" a 200px +
    pannello di lettura con 56px di padding orizzontale per lato) presumeva
    implicitamente una finestra larga almeno ~500-600px. Su uno smartphone
    stretto (~360-380px) il pannello di lettura restava con appena 40-50px
    utili — non "un po' stretto", davvero insufficiente a mostrare testo,
    da cui "le note vengono tagliate ed escono fuori dallo schermo" (parole
    di Davide). Fix: sotto il breakpoint mobile (`_MOBILE_BP = 600`,
    riusato da `MasterView._compact_tabs`, non un valore nuovo — stesso
    principio già seguito per la tab bar) i due pannelli non stanno più
    fianco a fianco ma si alternano a schermo intero (categorie+lista, poi
    il dettaglio di una nota, con un pulsante "← indietro" per tornare) —
    stesso pattern di drill-down già in uso per `MasterEncounterListView` ↔
    `MasterEncounterView`. Il padding generoso del pannello "pergamena"
    (56px orizzontali) resta invariato su schermi larghi, dove è
    un'intenzione estetica valida, e si riduce solo sotto il breakpoint."""

    def __init__(self, world_id: str = "", is_mobile: bool = False, device_id: str = ""):
        super().__init__(expand=True, spacing=0)
        self._page: ft.Page | None = None
        self._world_id = world_id
        self._device_id = device_id
        #: Cache di `RemoteBackend` per mondo (stesso pattern di
        #: `WorldsView._remote_backends`/`MasterEncounterView._remote_backends`),
        #: usata da `_send_note_share_command()` per raggiungere l'host
        #: anche quando questo dispositivo non lo ospita.
        self._remote_backends: dict = {}
        self._is_mobile = is_mobile
        #: Solo rilevante se `_is_mobile`: quale dei due pannelli mostrare
        #: (False = categorie+lista, True = dettaglio nota). Ignorato su
        #: desktop/tablet, dove sono sempre entrambi visibili fianco a fianco.
        self._mobile_show_detail: bool = False
        #: Membri del mondo attivo, per il selettore "Solo i giocatori
        #: selezionati" — vuoto se `world_id == ""` (modalità locale).
        self._world_members: list[WorldMember] = (
            world_repo.get_members(world_id) if world_id else []
        )

        self._active_cat: str = "npc"
        self._notes: dict[str, list[MasterCampaignNote]] = {}
        self._npcs: list[MasterNpc] = []
        self._sel_note_id: str | None = None
        self._note_edit: bool = False

        # campi editor nota (impostati in _build_note_edit_panel)
        self._nf_name:   ft.TextField = ft.TextField(**design.field_style())
        self._nf_status: ft.Dropdown = ft.Dropdown(**design.field_style())
        self._nf_tags:   ft.TextField = ft.TextField(**design.field_style())
        self._nf_desc:   ft.TextField = ft.TextField(**design.field_style())
        self._nf_npc:    ft.Dropdown = ft.Dropdown(**design.field_style())
        self._nf_visibility: ft.Dropdown = ft.Dropdown(**design.field_style())
        #: Checkbox per membro, ricostruite ad ogni apertura editor — solo
        #: se `_nf_visibility.value == "selected"`.
        self._nf_member_checks: dict[str, ft.Checkbox] = {}

        self._detail_container: ft.Container = ft.Container(expand=True)
        self._left_list_lv: ft.Column = ft.Column(spacing=2)

        self._load_all()
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    # ──────────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        for cat in CATEGORIES:
            self._notes[cat["key"]] = master_repo.get_master_campaign_notes(
                cat["key"], world_id=self._world_id,
            )
        self._npcs = master_repo.get_npcs(world_id=self._world_id)

    def _load_notes(self, cat: str) -> None:
        self._notes[cat] = master_repo.get_master_campaign_notes(cat, world_id=self._world_id)

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

        # Su mobile il pannello visibile non deve più espandersi/scrollare
        # per conto proprio: scorre l'intera `MasterNotesView` (header
        # incluso), stesso principio già applicato alle altre tab di
        # Modalità Master. Su desktop/tablet resta un layout master-detail a
        # due colonne, ciascuna con lo scroll indipendente di prima.
        self._detail_container = ft.Container(expand=(not self._is_mobile),
                                               content=self._build_detail_panel())
        self.scroll = ft.ScrollMode.AUTO if self._is_mobile else None

        if self._is_mobile:
            # Drill-down a schermo intero invece di due pannelli fissi
            # fianco a fianco — vedi il docstring della classe. Un solo
            # pannello alla volta, mai i due insieme: eviterebbe comunque
            # il vero problema (padding/larghezze pensate per uno spazio
            # condiviso con l'altro pannello, non per lo schermo intero).
            body: ft.Control = self._detail_container if self._mobile_show_detail \
                else self._build_left_panel()
        else:
            body = ft.Row(
                [
                    self._build_left_panel(),
                    ft.VerticalDivider(width=1, color=design.T().border),
                    self._detail_container,
                ],
                expand=True, spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )

        self.controls.append(self._build_header())
        self.controls.append(ft.Divider(height=1, color=design.T().border))
        self.controls.append(body)

    # ──────────────────────────────────────────────────────────────────────
    # Header
    # ──────────────────────────────────────────────────────────────────────

    def _build_header(self) -> ft.Container:
        meta = _cat_meta(self._active_cat)
        total = len(self._notes.get(self._active_cat, []))
        # Su mobile, mentre si legge/modifica una nota specifica, l'icona di
        # categoria lascia il posto a un pulsante "indietro" verso
        # categorie+lista (drill-down, vedi docstring della classe e
        # _build()) — su desktop/tablet i due pannelli sono sempre entrambi
        # visibili, l'icona di categoria resta sempre quella giusta.
        show_back = self._is_mobile and self._mobile_show_detail
        leading: list[ft.Control] = (
            [ft.IconButton(
                icon=ft.Icons.ARROW_BACK, icon_color=design.T().text_2, icon_size=20,
                tooltip="Torna alla lista",
                on_click=lambda e: self._on_mobile_back(),
            )]
            if show_back else
            [ft.Icon(meta["icon_on"], color=design.T().primary_icon, size=20),
             ft.Container(width=10)]
        )
        return ft.Container(
            content=ft.Row(
                [
                    *leading,
                    ft.Column(
                        [
                            ft.Text("Note di Campagna", size=15, weight=ft.FontWeight.BOLD,
                                    color=design.T().text),
                            ft.Text(
                                f"{meta['label']} · {total} {'voce' if total == 1 else 'voci'}",
                                size=11, color=design.T().text_3,
                            ),
                        ],
                        spacing=1, expand=True,
                    ),
                    ft.ElevatedButton(
                        meta["add_label"], icon=ft.Icons.ADD,
                        on_click=lambda e: self._open_new_note_dialog(),
                        style=ft.ButtonStyle(
                            bgcolor=design.T().primary_fill, color=design.T().on_primary_fill,
                            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=18, vertical=10),
            border=ft.Border(bottom=ft.BorderSide(1, design.T().border)),
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
                                     color=design.T().text_3,
                                     style=ft.TextStyle(letter_spacing=2)),
                    padding=ft.Padding.only(left=12, top=10, bottom=4),
                ),
                *[self._cat_button(c) for c in CATEGORIES],
            ],
            spacing=1,
        )

        list_label = ft.Container(
            content=ft.Text(meta["list_label"], size=9, weight=ft.FontWeight.BOLD,
                             color=design.T().text_3,
                             style=ft.TextStyle(letter_spacing=2)),
            padding=ft.Padding.only(left=12, top=8, bottom=4),
        )

        items = self._build_note_list_items()
        self._left_list_lv = ft.Column(
            controls=items, spacing=2,
        )

        return ft.Container(
            # Un'unica regione scrollabile per tutto il pannello (fix
            # 2026-07-30, bug report di Davide: con la finestra ridotta le
            # categorie in fondo — Fazioni, Eventi… — restavano fuori schermo
            # e non c'era modo di raggiungerle). Prima la lista era una
            # `ListView(expand=True)` dentro una Column NON scrollabile: le
            # voci sopra la occupavano tutta l'altezza e il resto veniva
            # semplicemente tagliato. Ora scorre l'intero pannello, e la lista
            # e' una Column normale — niente scroll annidato, stessa regola
            # gia' stabilita per il CardPicker.
            # Su mobile lo scroll di questo pannello è responsabilità della
            # `MasterNotesView` esterna (un solo pannello alla volta, header
            # incluso, scorrono insieme) — niente scroll annidato. Su
            # desktop/tablet resta un pannello indipendente nel layout a due
            # colonne (pattern master-detail), con scroll proprio invariato.
            content=ft.Column(
                [cat_nav, ft.Divider(height=1, color=design.T().border), list_label,
                 ft.Container(content=self._left_list_lv,
                              padding=ft.Padding.only(left=4, right=4, bottom=12))],
                expand=(not self._is_mobile), spacing=0,
                scroll=(None if self._is_mobile else ft.ScrollMode.AUTO),
            ),
            # Larghezza fissa 200px SOLO quando condivide la riga col
            # pannello di dettaglio (desktop/tablet, vedi _build()) — su
            # mobile questo pannello è l'unico visibile e deve prendersi
            # tutta la larghezza dello schermo, non restare bloccato a
            # 200px (bug report Davide, vedi docstring della classe).
            width=(None if self._is_mobile else 200),
            # Non più `expand=self._is_mobile`: su mobile questo pannello è
            # un figlio naturale della `MasterNotesView` scrollabile (vedi
            # `_build()`), non deve competere per lo spazio residuo — solo
            # su desktop/tablet vive dentro una Row a spazio fisso.
            bgcolor=design.T().parchment_alt,
        )

    def _cat_button(self, cat: dict[str, Any]) -> ft.Container:
        is_sel = cat["key"] == self._active_cat
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(cat["icon_on"] if is_sel else cat["icon_off"], size=16,
                            color=design.T().on_primary if is_sel else design.T().text_2),
                    ft.Container(width=8),
                    ft.Text(cat["label"], size=12,
                            color=design.T().on_primary if is_sel else design.T().text,
                            weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                            expand=True),
                    self._count_badge(cat["key"]),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                         vertical=design.Space.SM),
            bgcolor=design.T().primary_fill if is_sel else "transparent",
            border_radius=design.Radius.PILL,
            shadow=design.elevation(1) if is_sel else None,
            margin=ft.Margin.only(left=6, right=6),
            animate=ft.Animation(design.Duration.FAST, design.CURVE),
            on_click=lambda e, k=cat["key"]: self._on_cat_click(k),
            ink=True,
        )

    def _count_badge(self, key: str) -> ft.Container:
        n = len(self._notes.get(key, []))
        if n == 0:
            return ft.Container(width=0)
        return design.chip(str(n), "neutral")

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
            content=ft.Text(note.status or "—", size=9, color=design.T().on_primary,
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
                            color=design.T().text if is_sel else design.T().text,
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ft.Row([status_chip], spacing=4) if note.status else ft.Container(height=0),
                    ft.Text(preview, size=10, color=design.T().text_3,
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1) if preview else ft.Container(height=0),
                ],
                spacing=3,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.10, design.T().primary_fill) if is_sel else "transparent",
            border_radius=design.Radius.MD,
            border=(ft.Border.only(left=ft.BorderSide(3, design.T().primary))
                    if is_sel else None),
            on_click=lambda e, nid=note.id: self._on_sel_note(nid),
            ink=True,
        )

    def _left_empty(self, msg: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(msg, size=11, color=design.T().text_3, text_align=ft.TextAlign.CENTER),
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
                    content=ft.Text(note.status, size=11, color=design.T().on_primary, weight=ft.FontWeight.BOLD),
                    bgcolor=sc, border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                )
            )

        tag_chips: list[ft.Control] = []
        if note.tags:
            for tag in [t.strip() for t in note.tags.split(",") if t.strip()]:
                tag_chips.append(
                    ft.Container(
                        content=ft.Text(f"#{tag}", size=10, color=design.T().text_2),
                        bgcolor=design.T().border + "80", border_radius=8,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    )
                )

        ornament = ft.Row(
            [
                ft.Container(expand=True, height=1, bgcolor=design.T().border),
                ft.Container(content=ft.Icon(ft.Icons.STAR, size=11, color=design.T().primary_icon),
                             padding=ft.Padding.symmetric(horizontal=10)),
                ft.Container(expand=True, height=1, bgcolor=design.T().border),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        page_content_items: list[ft.Control] = []
        if status_row:
            page_content_items.append(ft.Row(status_row, alignment=ft.MainAxisAlignment.CENTER))
            page_content_items.append(ft.Container(height=10))

        # Indicatore di visibilità (2026-08-06) — solo se legata a un mondo:
        # senza, ogni nota è per definizione "solo locale", ridondante da
        # ripetere. Promemoria onesto: registra l'intenzione del Master, la
        # consegna ai giocatori non è ancora implementata (vedi CLAUDE.md).
        if self._world_id and note.visibility != "private":
            vis_label = ("Visibile a tutti i giocatori" if note.visibility == "all"
                         else "Visibile a giocatori selezionati")
            page_content_items.append(ft.Row(
                [
                    ft.Icon(ft.Icons.VISIBILITY_OUTLINED, size=12, color=design.T().magic),
                    ft.Container(width=4),
                    ft.Text(vis_label, size=11, color=design.T().magic, italic=True),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ))
            page_content_items.append(ft.Container(height=6))

        page_content_items += [
            ft.Text(note.name or "Senza nome", size=22, weight=ft.FontWeight.BOLD,
                    color=design.T().text, text_align=ft.TextAlign.CENTER, italic=True),
            ft.Container(height=14),
            ornament,
            ft.Container(height=18),
        ]

        if note.description:
            page_content_items.append(
                ft.Text(note.description, size=14, color=design.T().text, selectable=True)
            )

        npc_name = self._npc_name(note.linked_npc_id) if note.linked_npc_id else ""
        if npc_name:
            page_content_items += [
                ft.Container(height=14),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.PERSON, size=14, color=design.T().text_3),
                        ft.Container(width=6),
                        ft.Text(f"PNG collegato: {npc_name}", size=12,
                                color=design.T().text_2, italic=True),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ]

        if tag_chips:
            page_content_items += [
                ft.Container(height=20),
                ft.Divider(height=1, color=design.T().border),
                ft.Container(height=8),
                ft.Row(tag_chips, wrap=True, spacing=6, run_spacing=6),
            ]

        page_content_items.append(ft.Container(height=32))

        # Su mobile niente scroll/expand propri: scorre l'intera
        # `MasterNotesView` (vedi `_build()`). Su desktop resta un pannello
        # indipendente col proprio scroll, come prima.
        page_content = ft.Column(
            page_content_items, spacing=0,
            scroll=(None if self._is_mobile else ft.ScrollMode.AUTO),
            expand=(not self._is_mobile),
        )

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.OutlinedButton("Modifica", icon=ft.Icons.EDIT_OUTLINED,
                                       on_click=lambda e: self._on_note_start_edit()),
                    ft.Container(width=8),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=design.T().primary_icon,
                                  icon_size=18, tooltip="Elimina",
                                  on_click=lambda e: self._on_note_delete()),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border(top=ft.BorderSide(1, design.T().border)),
        )

        return ft.Column(
            [
                ft.Container(
                    content=page_content, expand=(not self._is_mobile),
                    bgcolor=design.T().parchment,
                    # 56/32px di margine "pergamena" è un'intenzione estetica
                    # valida quando il pannello condivide la finestra col
                    # riquadro categorie (desktop/tablet) — su mobile, dove
                    # questo pannello prende tutto lo schermo, lasciava
                    # appena 40-50px utili al testo su un telefono stretto:
                    # ridotto (bug report Davide, vedi docstring classe).
                    padding=ft.Padding.symmetric(
                        horizontal=(16 if self._is_mobile else 56),
                        vertical=(20 if self._is_mobile else 32)),
                ),
                action_bar,
            ],
            spacing=0, expand=(not self._is_mobile),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Visibilità (2026-08-06) — solo con un mondo selezionato
    # ──────────────────────────────────────────────────────────────────────

    def _build_visibility_section(self, current_visibility: str, current_ids_json: str) -> ft.Control:
        """
        Selettore "Visibilità" + elenco spuntabile dei giocatori del mondo
        attivo (solo se `value == 'selected'`). Ritorna un `ft.Container`
        vuoto se `self._world_id` è "" (modalità locale — non ha senso
        scegliere dei giocatori senza un mondo). Aggiorna
        `self._nf_visibility`/`self._nf_member_checks`, letti da
        `_collect_visibility_fields()` al salvataggio.
        """
        if not self._world_id:
            self._nf_visibility = ft.Dropdown(value="private")  # non mostrato, ma sempre presente
            self._nf_member_checks = {}
            return ft.Container(height=0)

        import json
        try:
            selected_ids = set(json.loads(current_ids_json) or [])
        except (ValueError, TypeError):
            selected_ids = set()

        players = [m for m in self._world_members if m.role == "player"]
        members_col = ft.Column(spacing=2)
        self._nf_member_checks = {}

        def _rebuild_members() -> None:
            members_col.controls.clear()
            if not players:
                members_col.controls.append(ft.Text(
                    "Nessun giocatore in questo mondo (solo owner/master).",
                    size=11, color=design.T().text_3, italic=True,
                ))
            for m in players:
                cb = ft.Checkbox(
                    label=m.display_name or "(senza nome)",
                    value=m.device_id in selected_ids,
                )
                self._nf_member_checks[m.device_id] = cb
                members_col.controls.append(cb)
            try:
                members_col.update()
            except RuntimeError:
                pass

        self._nf_visibility = ft.Dropdown(
            label="Visibilità",
            value=current_visibility or "private",
            options=[ft.DropdownOption(key=k, text=label) for k, label in _VISIBILITY_OPTIONS],
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent", label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'],
            # Fix difensivo (2026-08-16, bug report Davide: menu semitrasparente
            # nero) — il tema globale già imposta `dropdown_theme.menu_style`
            # per OGNI Dropdown (`ui/theme.py`, commit 2026-08-15), ma questo
            # dropdown vive in un dialog di condivisione nota aperto con
            # `page.show_dialog()`: se per qualunque motivo runtime non eredita
            # il tema di pagina, l'override esplicito qui sotto lo garantisce
            # comunque, stesso identico stile del tema globale.
            menu_style=ft.MenuStyle(
                bgcolor=design.T().surface, shadow_color=design.T().shadow,
                elevation=8, shape=ft.RoundedRectangleBorder(radius=design.Radius.SM),
                side=ft.BorderSide(1, design.T().border),
            ),
        )

        def _on_change(e: Any) -> None:
            members_container.visible = self._nf_visibility.value == "selected"
            try:
                members_container.update()
            except RuntimeError:
                pass

        self._nf_visibility.on_select = _on_change
        _rebuild_members()
        members_container = ft.Container(
            content=members_col, padding=ft.Padding.only(left=8, top=4),
            visible=(current_visibility == "selected"),
        )
        return ft.Column([self._nf_visibility, members_container], spacing=6)

    def _collect_visibility_fields(self) -> tuple[str, str]:
        """Legge lo stato corrente dei controlli di visibilità costruiti da
        `_build_visibility_section()`. Ritorna sempre `("private", "[]")` se
        `self._world_id` è vuoto (nessun mondo selezionato — coerenza
        difensiva anche se l'editor non mostra il selettore in quel caso)."""
        if not self._world_id:
            return "private", "[]"
        import json
        visibility = self._nf_visibility.value or "private"
        if visibility != "selected":
            return visibility, "[]"
        chosen = [device_id for device_id, cb in self._nf_member_checks.items() if cb.value]
        return visibility, json.dumps(chosen)

    def _build_note_edit_panel(self, note: MasterCampaignNote) -> ft.Column:
        opts = STATUS_OPTIONS.get(self._active_cat, [])
        self._nf_name = ft.TextField(
            value=note.name or "", label="Nome", autofocus=True,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent", label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])
        self._nf_status = ft.Dropdown(
            label="Stato",
            value=note.status or (opts[0] if opts else ""),
            options=[ft.DropdownOption(key=s, text=s) for s in opts],
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent", label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        self._nf_tags = ft.TextField(
            value=note.tags or "",
            label="Tag (separati da virgola — es. corte, waterdeep, alleanza)",
            text_style=ft.TextStyle(size=12, color=design.T().text_2),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent", label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])
        npc_opts = [ft.DropdownOption(key="", text="— nessuno —")] + [
            ft.DropdownOption(key=n.id, text=n.name or "(senza nome)") for n in self._npcs
        ]
        self._nf_npc = ft.Dropdown(
            label="PNG collegato (opzionale)",
            value=note.linked_npc_id or "",
            options=npc_opts,
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent", label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        self._nf_desc = ft.TextField(
            value=note.description or "", label="Descrizione / Note",
            multiline=True, min_lines=10, max_lines=30,
            text_style=ft.TextStyle(size=14, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent", label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])
        visibility_section = self._build_visibility_section(note.visibility, note.visible_to_device_ids)

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.TextButton("Annulla", on_click=lambda e: self._on_note_cancel_edit(),
                                  style=ft.ButtonStyle(color=design.T().text_2)),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Salva", icon=ft.Icons.SAVE_OUTLINED,
                        on_click=lambda e: self._on_note_save_edit(note),
                        style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border(top=ft.BorderSide(1, design.T().border)),
        )

        return ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [self._nf_name, self._nf_status, self._nf_npc, self._nf_tags,
                         visibility_section, self._nf_desc],
                        spacing=14,
                        scroll=(None if self._is_mobile else ft.ScrollMode.AUTO),
                        expand=(not self._is_mobile),
                    ),
                    expand=(not self._is_mobile), bgcolor=design.T().parchment,
                    # Stesso motivo del pannello di lettura sopra.
                    padding=ft.Padding.symmetric(
                        horizontal=(16 if self._is_mobile else 48),
                        vertical=(20 if self._is_mobile else 28)),
                ),
                action_bar,
            ],
            spacing=0, expand=(not self._is_mobile),
        )

    def _full_empty_state(self, icon: Any, title: str, msg: str) -> ft.Container:
        return ft.Container(
            expand=True, bgcolor=design.T().parchment,
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, color=design.T().border),
                    ft.Container(height=16),
                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=design.T().text_2,
                            italic=True, text_align=ft.TextAlign.CENTER),
                    ft.Container(height=8),
                    ft.Text(msg, size=13, color=design.T().text_3, text_align=ft.TextAlign.CENTER),
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
        # Su mobile, cambiare sezione riporta sempre alla lista della nuova
        # sezione (non ha senso restare sul dettaglio di una nota di una
        # categoria diversa da quella appena scelta).
        if self._is_mobile:
            self._mobile_show_detail = False
        self._refresh()

    def _on_mobile_back(self) -> None:
        """Solo mobile: dal dettaglio di una nota torna a categorie+lista."""
        self._mobile_show_detail = False
        self._note_edit = False
        self._refresh()

    # ──────────────────────────────────────────────────────────────────────
    # Event handlers — note
    # ──────────────────────────────────────────────────────────────────────

    def _on_sel_note(self, note_id: str) -> None:
        already_showing = note_id == self._sel_note_id and not self._note_edit
        # Su mobile va comunque fatto il drill-down al dettaglio anche se la
        # nota era già quella selezionata (es. preselezionata da _build()):
        # da fermi sulla lista, toccarla deve portare alla pagina di lettura.
        if already_showing and (not self._is_mobile or self._mobile_show_detail):
            return
        self._sel_note_id = note_id
        self._note_edit = False
        if self._is_mobile:
            self._mobile_show_detail = True
        self._refresh()

    def _on_note_start_edit(self) -> None:
        self._note_edit = True
        self._update_detail()

    def _on_note_cancel_edit(self) -> None:
        self._note_edit = False
        self._update_detail()

    def _send_note_share_command(self, payload: dict) -> bool:
        """
        Invia `CMD_NOTE_SHARE` per il mondo attivo — risolve l'host giusto
        (`LocalBackend` se questo dispositivo ospita, altrimenti un
        `RemoteBackend` in cache, stesso meccanismo già usato da
        `WorldsView`/`MasterEncounterView`) invece di scrivere direttamente
        su `master_repo`: è l'unico modo per cui condividere/aggiornare una
        nota finisce nel registro (§6.2, "cambiare la visibilità è
        un'azione registrata") e raggiunge davvero l'host anche quando il
        master gioca da un dispositivo che non lo ospita.
        """
        world = world_repo.get_world(self._world_id)
        if world is None:
            if self._page is not None:
                show_snack(self._page, "Mondo non trovato.", tone="danger")
            return False
        backend = world_sync.resolve_backend_for_world(
            world, self._device_id or "", LocalBackend(), self._remote_backends,
        )
        if backend is None:
            if self._page is not None:
                show_snack(self._page, "Impossibile raggiungere l'host del mondo — riprova.", tone="danger")
            return False
        result = backend.send_command(
            self._world_id, self._device_id or "", perm.CMD_NOTE_SHARE, payload,
            target_type="note", target_id=str(payload.get("note_id") or ""),
        )
        if not result.success:
            if self._page is not None:
                show_snack(self._page, result.error or "Condivisione della nota fallita.", tone="danger")
            return False
        return True

    def _on_note_save_edit(self, note: MasterCampaignNote) -> None:
        name   = (self._nf_name.value or "").strip() or "Senza nome"
        status = (self._nf_status.value or "").strip()
        tags   = (self._nf_tags.value or "").strip()
        desc   = (self._nf_desc.value or "").strip()
        npc_id = (self._nf_npc.value or "").strip()
        visibility, visible_ids_json = self._collect_visibility_fields()
        if self._world_id:
            ok = self._send_note_share_command({
                "note_id": note.id, "category": note.category,
                "name": name, "description": desc, "status": status,
                "tags": tags, "linked_npc_id": npc_id,
                "visibility": visibility,
                "visible_to_device_ids": json.loads(visible_ids_json or "[]"),
            })
            if not ok:
                return
        else:
            master_repo.update_master_campaign_note(
                note.id, name, desc, status, tags, npc_id,
                visibility=visibility, visible_to_device_ids=visible_ids_json,
            )
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
            # Su mobile, dopo l'eliminazione torna alla lista invece di
            # restare su un pannello di dettaglio ora vuoto o cambiato.
            if self._is_mobile:
                self._mobile_show_detail = False
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Elimina voce"),
            content=ft.Text(
                f"Eliminare «{note.name or 'Senza nome'}»?\nL'azione non è reversibile.",
                size=13, color=design.T().text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=do_delete,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ]),
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
            text_style=ft.TextStyle(size=14, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])
        f_status = ft.Dropdown(
            label="Stato", value=opts[0] if opts else "",
            options=[ft.DropdownOption(key=s, text=s) for s in opts],
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        npc_opts = [ft.DropdownOption(key="", text="— nessuno —")] + [
            ft.DropdownOption(key=n.id, text=n.name or "(senza nome)") for n in self._npcs
        ]
        f_npc = ft.Dropdown(
            label="PNG collegato (opzionale)", value="",
            options=npc_opts,
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        f_desc = ft.TextField(
            label="Descrizione / Note", multiline=True, min_lines=3, max_lines=8,
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])
        visibility_section = self._build_visibility_section("private", "[]")

        def save(ev: Any) -> None:
            if page is None:
                return
            name   = (f_name.value or "").strip() or "Senza nome"
            status = (f_status.value or "").strip()
            desc   = (f_desc.value or "").strip()
            npc_id = (f_npc.value or "").strip()
            visibility, visible_ids_json = self._collect_visibility_fields()
            if self._world_id:
                ok = self._send_note_share_command({
                    "category": cat, "name": name, "description": desc,
                    "status": status, "tags": "", "linked_npc_id": npc_id,
                    "visibility": visibility,
                    "visible_to_device_ids": json.loads(visible_ids_json or "[]"),
                })
                if not ok:
                    return
            else:
                master_repo.create_master_campaign_note(
                    cat, name, desc, status, "", npc_id,
                    world_id=self._world_id, visibility=visibility,
                    visible_to_device_ids=visible_ids_json,
                )
            page.pop_dialog()
            self._load_notes(cat)
            notes = self._notes.get(cat, [])
            if notes:
                self._sel_note_id = notes[-1].id
            self._note_edit = False
            # Su mobile, dopo la creazione mostra subito il dettaglio della
            # nuova nota invece di lasciare l'utente sulla lista.
            if self._is_mobile:
                self._mobile_show_detail = True
            self._refresh()

        fields: list[ft.Control] = [f_name]
        if opts:
            fields.append(f_status)
        if self._npcs:
            fields.append(f_npc)
        fields.append(visibility_section)
        fields.append(f_desc)

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(meta["add_label"]),
            content=ft.Column(fields, spacing=10, scroll=ft.ScrollMode.AUTO,
                              width=responsive_dialog_width(page, 400)),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Crea", icon=ft.Icons.ADD, on_click=save,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ]),
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

    def set_mobile(self, is_mobile: bool) -> None:
        """
        Aggiornamento "in place" quando la finestra viene ridimensionata
        MENTRE questa vista è già a video (2026-08-06, chiamato da
        `MasterView.set_mobile()` — vedi il suo docstring per il contesto
        completo del bug: prima d'ora il layout a due colonne fisse restava
        quello scelto all'apertura, quindi ridimensionare la finestra dal
        vivo non aveva alcun effetto e il testo del pannello di dettaglio
        poteva restare tagliato).

        Passa dal layout a due colonne al drill-down (o viceversa) SENZA
        perdere la categoria/nota correntemente selezionata (`_active_cat`/
        `_sel_note_id` non vengono toccate). L'unica cosa che si azzera è
        `_mobile_show_detail` — quale dei due pannelli mostrare in modalità
        mobile — perché non ha un significato da preservare quando si
        passa da un layout all'altro: si riparte sempre dalla lista.
        """
        if is_mobile == self._is_mobile:
            return
        self._is_mobile = is_mobile
        self._mobile_show_detail = False
        self._refresh()

    def _refresh(self) -> None:
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
