"""
Sezione Diario — vista principale accessibile dalla sidebar (key="diary").

Layout:
  Pannello sinistro (200px):
    ┌───────────────────────┐
    │  SEZIONI              │  ← 7 categorie cliccabili
    │  ▶ Cronaca            │
    │    PNG Incontrati     │
    │    PNG da Cercare     │
    │    Luoghi Visitati    │
    │    Da Esplorare       │
    │    Missioni           │
    │    Fazioni            │
    ├───────────────────────┤
    │  CAPITOLI / VOCI      │  ← lista elementi categoria attiva
    │  ● Cap. 1             │
    │  ▶ Cap. 2  ◀          │
    └───────────────────────┘

  Pannello destro (flex):
    Cronaca  → pagina lettura stile pergamena + editor inline
    Altre    → card dettaglio nota + form modifica inline

Flet 0.85.3: nessun expand=True su Column dentro Row dentro ListView,
              cast(list[ft.Control], [...]) per actions=, Any per handler.
"""

from __future__ import annotations

import flet as ft
import logging
from typing import Any, cast

from data.models import Character, DiaryEntry, CampaignNote, MasterCampaignNote
import data.repositories.character_repo as character_repo
from data.repositories import master_repo, world_repo
from core import world_sync
from core.world_backend import LocalBackend, RemoteBackend
from ui import design
from ui.components.background_sync import BackgroundSyncLoop
from ui.device_identity import resolve_device_id
from ui.widgets import wrap_dialog_actions

logger = logging.getLogger(__name__)

#: Stesso intervallo già validato altrove (`sheet_view.py::_SHEET_SYNC_INTERVAL_S`)
#: — bug segnalato da Davide (2026-08-16): le note condivise non si
#: aggiornavano da sole in questa sezione (di primo livello nella sidebar,
#: non un tab di `SheetView`), che non aveva mai avuto un ciclo di sync in
#: background — una sola risoluzione di `device_id` al mount, mai più
#: ripetuta.
_DIARY_SYNC_INTERVAL_S = 2.0

# ── Costanti visive ────────────────────────────────────────────────────────────

# Colori badge stato

# ── Definizioni categorie ──────────────────────────────────────────────────────
CATEGORIES: list[dict[str, Any]] = [
    {
        "key":        "diary",
        "label":      "Cronaca",
        "icon_off":   ft.Icons.MENU_BOOK_OUTLINED,
        "icon_on":    ft.Icons.MENU_BOOK,
        "list_label": "CAPITOLI",
        "add_label":  "Nuova Voce",
        "empty_msg":  "Nessuna voce ancora.\nPremi «Nuova Voce» per iniziare.",
    },
    {
        "key":        "npc",
        "label":      "PNG Incontrati",
        "icon_off":   ft.Icons.PEOPLE_OUTLINE,
        "icon_on":    ft.Icons.PEOPLE,
        "list_label": "PERSONAGGI",
        "add_label":  "Aggiungi PNG",
        "empty_msg":  "Nessun personaggio registrato.\nAggiungi i PNG che hai incontrato.",
    },
    {
        "key":        "npc_todo",
        "label":      "PNG da Cercare",
        "icon_off":   ft.Icons.PERSON_SEARCH_OUTLINED,
        "icon_on":    ft.Icons.PERSON_SEARCH,
        "list_label": "DA TROVARE",
        "add_label":  "Aggiungi PNG",
        "empty_msg":  "Nessun personaggio da cercare.\nAggiungi chi devi ancora incontrare.",
    },
    {
        "key":        "place",
        "label":      "Luoghi Visitati",
        "icon_off":   ft.Icons.PLACE_OUTLINED,
        "icon_on":    ft.Icons.PLACE,
        "list_label": "LUOGHI",
        "add_label":  "Aggiungi Luogo",
        "empty_msg":  "Nessun luogo registrato.\nAggiungi i luoghi che hai esplorato.",
    },
    {
        "key":        "place_todo",
        "label":      "Da Esplorare",
        "icon_off":   ft.Icons.EXPLORE_OUTLINED,
        "icon_on":    ft.Icons.EXPLORE,
        "list_label": "OBIETTIVI",
        "add_label":  "Aggiungi Luogo",
        "empty_msg":  "Nessun obiettivo segnato.\nAggiungi i luoghi che vuoi esplorare.",
    },
    {
        "key":        "quest",
        "label":      "Missioni",
        "icon_off":   ft.Icons.ASSIGNMENT_OUTLINED,
        "icon_on":    ft.Icons.ASSIGNMENT,
        "list_label": "MISSIONI",
        "add_label":  "Aggiungi Missione",
        "empty_msg":  "Nessuna missione registrata.\nTieni traccia delle tue quest.",
    },
    {
        "key":        "faction",
        "label":      "Fazioni",
        "icon_off":   ft.Icons.FLAG_OUTLINED,
        "icon_on":    ft.Icons.FLAG,
        "list_label": "FAZIONI",
        "add_label":  "Aggiungi Fazione",
        "empty_msg":  "Nessuna fazione registrata.\nTieni traccia delle organizzazioni.",
    },
    # "event"/"secret" (2026-08-16): categorie di `MasterCampaignNote` non
    # presenti finora tra quelle del giocatore — aggiunte qui perché una
    # nota condivisa dal master in queste categorie deve poter comparire
    # in una scheda "già esistente" (richiesta di Davide: niente più un
    # riquadro "condiviso" separato), non solo nelle 6 categorie storiche.
    {
        "key":        "event",
        "label":      "Eventi",
        "icon_off":   ft.Icons.EVENT_OUTLINED,
        "icon_on":    ft.Icons.EVENT,
        "list_label": "EVENTI",
        "add_label":  "Aggiungi Evento",
        "empty_msg":  "Nessun evento registrato.",
    },
    {
        "key":        "secret",
        "label":      "Segreti",
        "icon_off":   ft.Icons.LOCK_OUTLINE,
        "icon_on":    ft.Icons.LOCK,
        "list_label": "SEGRETI",
        "add_label":  "Aggiungi Segreto",
        "empty_msg":  "Nessun segreto registrato.",
    },
]

STATUS_OPTIONS: dict[str, list[str]] = {
    "npc":        ["alleato", "neutrale", "ostile", "sconosciuto"],
    "npc_todo":   ["cercato", "sentito nominare", "leggenda"],
    "place":      ["esplorato", "parzialmente esplorato"],
    "place_todo": ["da esplorare", "sentito nominare", "leggenda/rumor"],
    "quest":      ["attiva", "completata", "fallita", "in pausa"],
    "faction":    ["alleata", "neutrale", "ostile", "sconosciuta"],
    "event":      ["in corso", "concluso", "futuro"],
    "secret":     ["non rivelato", "parzialmente noto", "rivelato"],
}

_STATUS_TONES: dict[str, str] = {
    "alleato": "success", "esplorato": "success",
    "completata": "success", "alleata": "success",
    "neutrale": "warning", "parzialmente esplorato": "warning",
    "in pausa": "warning", "cercato": "warning",
    "ostile": "danger", "fallita": "danger",
}


def _status_color(status: str) -> str:
    return getattr(design.T(), _STATUS_TONES.get(status, "text_3"))


def _cat_meta(key: str) -> dict[str, Any]:
    for c in CATEGORIES:
        if c["key"] == key:
            return c
    return CATEGORIES[0]


# ══════════════════════════════════════════════════════════════════════════════
# DiaryView
# ══════════════════════════════════════════════════════════════════════════════

class DiaryView(ft.Column):
    """
    Vista diario a due pannelli per la navbar laterale (key="diary").
    Eredita da ft.Column (expand=True) — gestisce il proprio scroll internamente.
    """

    def __init__(self, character: Character):
        super().__init__(expand=True, spacing=0)
        self.character = character
        self._page: ft.Page | None = None

        # ── Stato navigazione ──────────────────────────────────────────────
        self._active_cat: str = "diary"

        # ── Stato Cronaca ──────────────────────────────────────────────────
        self._diary_entries: list[DiaryEntry] = []
        self._sel_diary_id: str | None = None
        self._diary_edit: bool = False
        # campi editor diario (impostati in _build_diary_edit_panel)
        self._ef_title:   ft.TextField = ft.TextField(**design.field_style())
        self._ef_date:    ft.TextField = ft.TextField(**design.field_style())
        self._ef_content: ft.TextField = ft.TextField(**design.field_style())

        # ── Stato Note di Campagna ─────────────────────────────────────────
        self._notes: dict[str, list[CampaignNote]] = {}
        self._sel_note_id: str | None = None
        self._note_edit: bool = False
        # campi editor nota (impostati in _build_note_edit_panel)
        self._nf_name:   ft.TextField = ft.TextField(**design.field_style())
        self._nf_status: ft.Dropdown = ft.Dropdown(**design.field_style())
        self._nf_tags:   ft.TextField = ft.TextField(**design.field_style())
        self._nf_desc:   ft.TextField = ft.TextField(**design.field_style())

        # ── Container riferimenti aggiornabili ────────────────────────────
        self._detail_container: ft.Container = ft.Container(expand=True)
        self._left_list_lv: ft.Column = ft.Column(spacing=2)
        self._left_list_label: ft.Text = ft.Text("", size=9,
                                                  weight=ft.FontWeight.BOLD,
                                                  color=design.T().text_3,
                                                  style=ft.TextStyle(letter_spacing=2))

        # Note condivise dal Master (2026-08-16, richiesta di Davide:
        # "voglio che le note condivise... vengano visualizzate... nella
        # sezione diario/note del giocatore già esistente", niente più un
        # riquadro "condiviso" separato) — SOLO se `character.world_id` è
        # valorizzato. Fuse direttamente in `self._notes[cat]` da
        # `_merge_shared_notes()`; `_shared_note_ids` distingue quelle non
        # modificabili da questo dispositivo (chip + pannello di sola
        # lettura, vedi `_note_list_item`/`_build_note_reading_panel`).
        self.device_id: str | None = None
        self._shared_note_ids: set[str] = set()
        self.backend = LocalBackend()
        self._remote_backends: dict[str, RemoteBackend] = {}
        self._sync_loop: BackgroundSyncLoop | None = None
        self._connection_state: str = "connected"

        self._load_all()
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)
        page = self.page
        if page is not None and self.character.world_id:
            page.run_task(self._init_shared_notes)

    def will_unmount(self) -> None:
        self._stop_world_sync()

    async def _init_shared_notes(self) -> None:
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        self._merge_shared_notes()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        self._start_world_sync()

    def _start_world_sync(self) -> None:
        """Ciclo periodico (2026-08-16, vedi `_DIARY_SYNC_INTERVAL_S`) —
        stesso pattern di `sheet_view.py::SheetView`/`spells_view.py::SpellsView`/
        `maps_view.py::MapsView`: finché la sezione Diario resta aperta,
        scarica gli eventi nuovi dall'host (note condivise dal master) e
        ridisegna, senza richiedere di uscire e rientrare nella sezione."""
        if self._sync_loop is not None or not self.character.world_id:
            return
        world_id = self.character.world_id

        def _apply() -> None:
            world = world_repo.get_world(world_id)
            if world is None or world.is_local_host:
                return
            backend = world_sync.resolve_backend_for_world(
                world, self.device_id or "", self.backend, self._remote_backends,
            )
            if backend is not None and isinstance(backend, RemoteBackend):
                self._connection_state = backend.connection_state()
                world_sync.sync_replica(backend, world_id)
            else:
                self._connection_state = "disconnected"

        def _signature() -> str | None:
            world = world_repo.get_world(world_id)
            seq = world.last_synced_seq if world is not None else 0
            return f"{self._connection_state}|{seq}"

        async def _redraw() -> None:
            self._merge_shared_notes()
            self._build()
            try:
                self.update()
            except RuntimeError:
                pass

        loop = BackgroundSyncLoop(
            get_page=lambda: self.page,
            signature_fn=_signature,
            async_redraw_fn=_redraw,
            apply_fn=_apply,
            interval_s=_DIARY_SYNC_INTERVAL_S,
            thread_name=f"diary-sync-{self.character.id[:8]}",
        )
        self._sync_loop = loop
        loop.start()

    def _stop_world_sync(self) -> None:
        if self._sync_loop is not None:
            self._sync_loop.stop()
        self._sync_loop = None

    # ──────────────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        self._load_diary()
        for cat in CATEGORIES:
            if cat["key"] != "diary":
                self._notes[cat["key"]] = character_repo.get_campaign_notes(
                    self.character.id, cat["key"]
                )
        self._merge_shared_notes()

    def _merge_shared_notes(self) -> None:
        """Aggiunge le note condivise dal master (già filtrate per
        visibilità, `master_repo.get_notes_visible_to`) in coda alla lista
        di ogni categoria — stessi campi di `CampaignNote`
        (`id/name/description/status/tags`), niente sezione separata. No-op
        finché `device_id` non è risolto (prima di `did_mount`) o se il
        personaggio non è in un mondo."""
        if not self.character.world_id or self.device_id is None:
            return
        shared = master_repo.get_notes_visible_to(self.character.world_id, self.device_id)
        self._shared_note_ids = {n.id for n in shared}
        by_cat: dict[str, list[MasterCampaignNote]] = {}
        for n in shared:
            by_cat.setdefault(n.category, []).append(n)
        for cat_key, shared_notes in by_cat.items():
            own = [n for n in self._notes.get(cat_key, []) if n.id not in self._shared_note_ids]
            self._notes[cat_key] = own + shared_notes

    def _load_diary(self) -> None:
        raw = character_repo.get_diary_entries(self.character.id)
        self._diary_entries = sorted(raw, key=lambda e: e.created_at or "")
        # Aggiusta la selezione se la voce è stata cancellata
        if self._sel_diary_id and not self._get_sel_diary():
            self._sel_diary_id = (self._diary_entries[0].id
                                  if self._diary_entries else None)

    def _load_notes(self, cat: str) -> None:
        if cat != "diary":
            self._notes[cat] = character_repo.get_campaign_notes(
                self.character.id, cat
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Build principale
    # ──────────────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.controls.clear()

        # Selezione automatica primo elemento se niente è selezionato
        if self._active_cat == "diary":
            if self._diary_entries and self._sel_diary_id is None:
                self._sel_diary_id = self._diary_entries[0].id
        else:
            notes = self._notes.get(self._active_cat, [])
            if notes and self._sel_note_id is None:
                self._sel_note_id = notes[0].id

        self._detail_container = ft.Container(
            expand=True,
            content=self._build_detail_panel(),
        )

        body = ft.Row(
            [
                self._build_left_panel(),
                ft.VerticalDivider(width=1, color=design.T().border),
                self._detail_container,
            ],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        self.controls.append(self._build_header())
        self.controls.append(ft.Divider(height=1, color=design.T().border))
        self.controls.append(body)

    # ──────────────────────────────────────────────────────────────────────────
    # Header
    # ──────────────────────────────────────────────────────────────────────────

    def _build_header(self) -> ft.Container:
        meta = _cat_meta(self._active_cat)
        total = self._item_count()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(meta["icon_on"], color=design.T().primary_icon, size=20),
                    ft.Container(width=10),
                    ft.Column(
                        [
                            ft.Text(
                                f"Cronaca di {self.character.name or 'Avventuriero'}",
                                size=15, weight=ft.FontWeight.BOLD, color=design.T().text,
                            ),
                            ft.Text(
                                f"{meta['label']} · {total} "
                                f"{'voce' if total == 1 else 'voci'}",
                                size=11, color=design.T().text_3,
                            ),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    ft.ElevatedButton(
                        meta["add_label"],
                        icon=ft.Icons.ADD,
                        on_click=lambda e: self._on_add(),
                        style=ft.ButtonStyle(
                            bgcolor=design.T().primary_fill,
                            color=design.T().on_primary_fill,
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

    def _item_count(self) -> int:
        if self._active_cat == "diary":
            return len(self._diary_entries)
        return len(self._notes.get(self._active_cat, []))

    # ──────────────────────────────────────────────────────────────────────────
    # Pannello sinistro
    # ──────────────────────────────────────────────────────────────────────────

    def _build_left_panel(self) -> ft.Container:
        meta = _cat_meta(self._active_cat)

        # Categoria nav
        cat_nav = ft.Column(
            [
                ft.Container(
                    content=ft.Text(
                        "SEZIONI", size=9, weight=ft.FontWeight.BOLD,
                        color=design.T().text_3,
                        style=ft.TextStyle(letter_spacing=2),
                    ),
                    padding=ft.Padding.only(left=12, top=10, bottom=4),
                ),
                *[self._cat_button(c) for c in CATEGORIES],
            ],
            spacing=1,
        )

        # Lista elementi
        list_label = ft.Container(
            content=ft.Text(
                meta["list_label"], size=9, weight=ft.FontWeight.BOLD,
                color=design.T().text_3,
                style=ft.TextStyle(letter_spacing=2),
            ),
            padding=ft.Padding.only(left=12, top=8, bottom=4),
        )

        items = self._build_item_controls()
        self._left_list_lv = ft.Column(controls=items, spacing=2)

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
            content=ft.Column(
                [
                    cat_nav,
                    ft.Divider(height=1, color=design.T().border),
                    list_label,
                    ft.Container(
                        content=self._left_list_lv,
                        padding=ft.Padding.only(left=4, right=4, bottom=12),
                    ),
                ],
                expand=True,
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=200,
            bgcolor=design.T().parchment_alt,
        )

    def _cat_button(self, cat: dict[str, Any]) -> ft.Container:
        is_sel = cat["key"] == self._active_cat
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        cat["icon_on"] if is_sel else cat["icon_off"],
                        size=16,
                        color=design.T().on_primary if is_sel else design.T().text_2,
                    ),
                    ft.Container(width=8),
                    ft.Text(
                        cat["label"], size=12,
                        color=design.T().on_primary if is_sel else design.T().text,
                        weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                        expand=True,
                    ),
                    # Badge contatore
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
        if key == "diary":
            n = len(self._diary_entries)
        else:
            n = len(self._notes.get(key, []))
        if n == 0:
            return ft.Container(width=0)
        return ft.Container(
            content=ft.Text(
                str(n), size=9, color=design.T().text_3,
                text_align=ft.TextAlign.CENTER,
            ),
            bgcolor=design.T().border,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=5, vertical=1),
        )

    def _build_item_controls(self) -> list[ft.Control]:
        if self._active_cat == "diary":
            return self._build_diary_list_items()
        return self._build_note_list_items()

    # ── Lista diario ───────────────────────────────────────────────────────────

    def _build_diary_list_items(self) -> list[ft.Control]:
        if not self._diary_entries:
            return [self._left_empty("Nessuna voce.\nPremi «Nuova Voce».")]
        return [
            self._diary_list_item(e, i + 1)
            for i, e in enumerate(self._diary_entries)
        ]

    def _diary_list_item(self, entry: DiaryEntry, number: int) -> ft.Container:
        is_sel = entry.id == self._sel_diary_id
        date_label = entry.session_date or (
            entry.created_at[:10] if entry.created_at else ""
        )
        badge = ft.Container(
            content=ft.Text(
                str(number), size=9, weight=ft.FontWeight.BOLD,
                color=design.T().on_primary if is_sel else design.T().primary,
                text_align=ft.TextAlign.CENTER,
            ),
            width=22, height=22,
            bgcolor=design.T().primary_fill if is_sel else "transparent",
            border=ft.Border.all(1, design.T().primary),
            border_radius=11,
            alignment=ft.Alignment.CENTER,
        )
        rows: list[ft.Control] = [
            ft.Row(
                [
                    badge,
                    ft.Container(width=7),
                    ft.Text(
                        entry.title or "Senza titolo", size=12,
                        weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                        color=design.T().text if is_sel else design.T().text,
                        overflow=ft.TextOverflow.ELLIPSIS, max_lines=2, expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        ]
        if date_label:
            rows.append(
                ft.Container(
                    content=ft.Text(date_label, size=10, color=design.T().text_3),
                    padding=ft.Padding.only(left=29),
                )
            )
        return ft.Container(
            content=ft.Column(rows, spacing=3),
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.10, design.T().primary_fill) if is_sel else "transparent",
            border_radius=design.Radius.MD,
            border=(ft.Border.only(left=ft.BorderSide(3, design.T().primary))
                    if is_sel else None),
            on_click=lambda e, eid=entry.id: self._on_sel_diary(eid),
            ink=True,
        )

    # ── Lista note ─────────────────────────────────────────────────────────────

    def _build_note_list_items(self) -> list[ft.Control]:
        notes = self._notes.get(self._active_cat, [])
        meta = _cat_meta(self._active_cat)
        if not notes:
            return [self._left_empty(meta["empty_msg"])]
        return [self._note_list_item(n) for n in notes]

    def _note_list_item(self, note: CampaignNote) -> ft.Container:
        is_sel = note.id == self._sel_note_id
        is_shared = note.id in self._shared_note_ids
        sc = _status_color(note.status)

        status_chip = ft.Container(
            content=ft.Text(
                note.status or "—", size=9, color=design.T().on_primary,
                weight=ft.FontWeight.BOLD,
            ),
            bgcolor=sc,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        ) if note.status else ft.Container(height=0)

        shared_chip = ft.Container(
            content=ft.Text(
                "Condivisa dal Master", size=9, color=design.T().on_primary,
                weight=ft.FontWeight.BOLD,
            ),
            bgcolor=design.T().primary,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        ) if is_shared else ft.Container(height=0)

        preview = (note.description or "").replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "…"

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        note.name or "Senza nome", size=12,
                        weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                        color=design.T().text if is_sel else design.T().text,
                        overflow=ft.TextOverflow.ELLIPSIS, max_lines=1,
                    ),
                    ft.Row([status_chip, shared_chip], spacing=4)
                        if (note.status or is_shared) else ft.Container(height=0),
                    ft.Text(
                        preview, size=10, color=design.T().text_3,
                        overflow=ft.TextOverflow.ELLIPSIS, max_lines=1,
                    ) if preview else ft.Container(height=0),
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
            content=ft.Text(
                msg, size=11, color=design.T().text_3,
                text_align=ft.TextAlign.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=16),
            alignment=ft.Alignment.CENTER,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Pannello destro (dispatch)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_detail_panel(self) -> ft.Control:
        if self._active_cat == "diary":
            return self._build_diary_detail()
        return self._build_note_detail()

    # ── Diario: dettaglio ──────────────────────────────────────────────────────

    def _build_diary_detail(self) -> ft.Control:
        entry = self._get_sel_diary()
        if entry is None:
            return self._full_empty_state(
                ft.Icons.MENU_BOOK_OUTLINED,
                "La tua cronaca ti aspetta",
                "Seleziona un capitolo a sinistra\no premi «Nuova Voce».",
            )
        if self._diary_edit:
            return self._build_diary_edit_panel(entry)
        return self._build_diary_reading_panel(entry)

    def _build_diary_reading_panel(self, entry: DiaryEntry) -> ft.Column:
        date_label = entry.session_date or (
            entry.created_at[:10] if entry.created_at else ""
        )
        idx = self._diary_index()

        ornament = ft.Row(
            [
                ft.Container(expand=True, height=1, bgcolor=design.T().border),
                ft.Container(
                    content=ft.Icon(ft.Icons.STAR, size=11, color=design.T().primary_icon),
                    padding=ft.Padding.symmetric(horizontal=10),
                ),
                ft.Container(expand=True, height=1, bgcolor=design.T().border),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        page_content = ft.Column(
            [
                ft.Text(
                    date_label.upper(), size=10, weight=ft.FontWeight.BOLD,
                    color=design.T().text_3, text_align=ft.TextAlign.CENTER,
                    style=ft.TextStyle(letter_spacing=2),
                ) if date_label else ft.Container(height=0),
                ft.Container(height=8),
                ft.Text(
                    entry.title or "Senza titolo", size=22,
                    weight=ft.FontWeight.BOLD, color=design.T().text,
                    text_align=ft.TextAlign.CENTER, italic=True,
                ),
                ft.Container(height=14),
                ornament,
                ft.Container(height=18),
                ft.Text(entry.content or "", size=14,
                        color=design.T().text, selectable=True),
                ft.Container(height=32),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=0,
        )

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        icon_color=design.T().text_2,
                        tooltip="Voce precedente",
                        disabled=(idx <= 0),
                        on_click=lambda e: self._on_prev(),
                    ),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Modifica", icon=ft.Icons.EDIT_OUTLINED,
                                on_click=lambda e: self._on_diary_start_edit(),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=design.T().primary_icon, icon_size=18,
                                tooltip="Elimina voce",
                                on_click=lambda e: self._on_diary_delete(),
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ARROW_FORWARD,
                        icon_color=design.T().text_2,
                        tooltip="Voce successiva",
                        disabled=(idx >= len(self._diary_entries) - 1),
                        on_click=lambda e: self._on_next(),
                    ),
                ],
                # niente più spacer expand=True tra i 3 gruppi (bug report Davide,
                # 2026-07-24: non si adattava a finestre strette/smartphone) —
                # SPACE_BETWEEN ottiene lo stesso effetto visivo "ai bordi" senza
                # bisogno di expand, e wrap=True fa scendere il gruppo centrale
                # su una riga propria se davvero non c'è spazio.
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border(top=ft.BorderSide(1, design.T().border)),
        )

        return ft.Column(
            [
                ft.Container(
                    content=page_content, expand=True,
                    bgcolor=design.T().parchment,
                    padding=ft.Padding.symmetric(horizontal=56, vertical=32),
                ),
                action_bar,
            ],
            spacing=0, expand=True,
        )

    def _build_diary_edit_panel(self, entry: DiaryEntry) -> ft.Column:
        self._ef_title = ft.TextField(
            value=entry.title or "", label="Titolo", autofocus=True,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD,
                                    color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent",
            label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])
        self._ef_date = ft.TextField(
            value=entry.session_date or "",
            label="Data / Sessione  (es. «Sessione 3»  ·  «15 Kythorn 1492»)",
            text_style=ft.TextStyle(size=12, color=design.T().text_2),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent",
            label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])
        self._ef_content = ft.TextField(
            value=entry.content or "",
            label="Scrivi qui la tua storia…",
            multiline=True, min_lines=14, max_lines=40,
            text_style=ft.TextStyle(size=14, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent",
            label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.TextButton(
                        "Annulla",
                        on_click=lambda e: self._on_diary_cancel_edit(),
                        style=ft.ButtonStyle(color=design.T().text_2),
                    ),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Salva", icon=ft.Icons.SAVE_OUTLINED,
                        on_click=lambda e: self._on_diary_save_edit(entry),
                        style=ft.ButtonStyle(
                            bgcolor=design.T().primary_fill, color=design.T().on_primary_fill,
                        ),
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
                        [self._ef_title, self._ef_date, self._ef_content],
                        spacing=14, scroll=ft.ScrollMode.AUTO,
                    ),
                    expand=True, bgcolor=design.T().parchment,
                    padding=ft.Padding.symmetric(horizontal=48, vertical=28),
                ),
                action_bar,
            ],
            spacing=0, expand=True,
        )

    # ── Note: dettaglio ────────────────────────────────────────────────────────

    def _build_note_detail(self) -> ft.Control:
        note = self._get_sel_note()
        meta = _cat_meta(self._active_cat)
        if note is None:
            return self._full_empty_state(
                meta["icon_on"],
                f"Nessuna {meta['label'].lower()} selezionata",
                meta["empty_msg"],
            )
        # Nota condivisa dal master (2026-08-16): sola lettura, modificarla
        # resta compito del master — mai il pannello di modifica, che
        # presume `character_repo.update_campaign_note` (scrittura su
        # `campaign_notes`, non su `master_campaign_notes`).
        if note.id in self._shared_note_ids:
            return self._build_note_reading_panel(note)
        if self._note_edit:
            return self._build_note_edit_panel(note)
        return self._build_note_reading_panel(note)

    def _build_note_reading_panel(self, note: CampaignNote) -> ft.Column:
        is_shared = note.id in self._shared_note_ids
        sc = _status_color(note.status)

        # Status badge
        status_row: list[ft.Control] = []
        if is_shared:
            # Icona PUBLIC rimossa (audit anti-AI-slop): il testo "Condivisa
            # dal Master" dice già esplicitamente lo stesso concetto — stesso
            # principio già applicato in home_view.py::_section_label.
            status_row.append(
                ft.Container(
                    content=ft.Text("Condivisa dal Master", size=11, color=design.T().on_primary,
                                     weight=ft.FontWeight.BOLD),
                    bgcolor=design.T().primary, border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                )
            )
        if note.status:
            status_row.append(
                ft.Container(
                    content=ft.Text(
                        note.status, size=11, color=design.T().on_primary,
                        weight=ft.FontWeight.BOLD,
                    ),
                    bgcolor=sc, border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                )
            )

        # Tags
        tag_chips: list[ft.Control] = []
        if note.tags:
            for tag in [t.strip() for t in note.tags.split(",") if t.strip()]:
                tag_chips.append(
                    ft.Container(
                        content=ft.Text(f"#{tag}", size=10, color=design.T().text_2),
                        bgcolor=design.T().border + "80",
                        border_radius=8,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    )
                )

        ornament = ft.Row(
            [
                ft.Container(expand=True, height=1, bgcolor=design.T().border),
                ft.Container(
                    content=ft.Icon(ft.Icons.STAR, size=11, color=design.T().primary_icon),
                    padding=ft.Padding.symmetric(horizontal=10),
                ),
                ft.Container(expand=True, height=1, bgcolor=design.T().border),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        page_content_items: list[ft.Control] = []
        if status_row:
            page_content_items.append(
                ft.Row(status_row, alignment=ft.MainAxisAlignment.CENTER)
            )
            page_content_items.append(ft.Container(height=10))

        page_content_items += [
            ft.Text(
                note.name or "Senza nome", size=22,
                weight=ft.FontWeight.BOLD, color=design.T().text,
                text_align=ft.TextAlign.CENTER, italic=True,
            ),
            ft.Container(height=14),
            ornament,
            ft.Container(height=18),
        ]

        if note.description:
            page_content_items.append(
                ft.Text(note.description, size=14,
                        color=design.T().text, selectable=True)
            )

        if tag_chips:
            page_content_items += [
                ft.Container(height=20),
                ft.Divider(height=1, color=design.T().border),
                ft.Container(height=8),
                ft.Row(tag_chips, wrap=True, spacing=6, run_spacing=6),
            ]

        page_content_items.append(ft.Container(height=32))

        page_content = ft.Column(
            page_content_items,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=0,
        )

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Text("Sola lettura — modificarla è compito del Master.",
                            size=11, italic=True, color=design.T().text_3),
                ] if is_shared else [
                    ft.OutlinedButton(
                        "Modifica", icon=ft.Icons.EDIT_OUTLINED,
                        on_click=lambda e: self._on_note_start_edit(),
                    ),
                    ft.Container(width=8),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=design.T().primary_icon, icon_size=18,
                        tooltip="Elimina",
                        on_click=lambda e: self._on_note_delete(),
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
                    content=page_content, expand=True,
                    bgcolor=design.T().parchment,
                    padding=ft.Padding.symmetric(horizontal=56, vertical=32),
                ),
                action_bar,
            ],
            spacing=0, expand=True,
        )

    def _build_note_edit_panel(self, note: CampaignNote) -> ft.Column:
        opts = STATUS_OPTIONS.get(self._active_cat, [])
        self._nf_name = ft.TextField(
            value=note.name or "", label="Nome", autofocus=True,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD,
                                    color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent",
            label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])
        self._nf_status = ft.Dropdown(
            label="Stato",
            value=note.status or (opts[0] if opts else ""),
            options=[ft.DropdownOption(key=s, text=s) for s in opts],
            border_color=design.T().border,
            focused_border_color=design.T().primary,
            # 2026-08-16: NON "transparent" — causa del menu a tendina
            # semitrasparente/nero (bug report Davide su `master_notes_view.py`,
            # stesso identico pattern qui): in questa versione di Flet il
            # riempimento del popup segue il `bgcolor` del campo stesso.
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        self._nf_tags = ft.TextField(
            value=note.tags or "",
            label="Tag (separati da virgola — es. mago, waterdeep, alleanza)",
            text_style=ft.TextStyle(size=12, color=design.T().text_2),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent",
            label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])
        self._nf_desc = ft.TextField(
            value=note.description or "",
            label="Descrizione / Note",
            multiline=True, min_lines=10, max_lines=30,
            text_style=ft.TextStyle(size=14, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor="transparent",
            label_style=ft.TextStyle(color=design.T().text_3, size=11),
            border_radius=design.field_style()['border_radius'])

        action_bar = ft.Container(
            content=ft.Row(
                [
                    ft.TextButton(
                        "Annulla",
                        on_click=lambda e: self._on_note_cancel_edit(),
                        style=ft.ButtonStyle(color=design.T().text_2),
                    ),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Salva", icon=ft.Icons.SAVE_OUTLINED,
                        on_click=lambda e: self._on_note_save_edit(note),
                        style=ft.ButtonStyle(
                            bgcolor=design.T().primary_fill, color=design.T().on_primary_fill,
                        ),
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
                        [self._nf_name, self._nf_status,
                         self._nf_tags, self._nf_desc],
                        spacing=14, scroll=ft.ScrollMode.AUTO,
                    ),
                    expand=True, bgcolor=design.T().parchment,
                    padding=ft.Padding.symmetric(horizontal=48, vertical=28),
                ),
                action_bar,
            ],
            spacing=0, expand=True,
        )

    # ── Stato vuoto pannello destro ────────────────────────────────────────────

    def _full_empty_state(self, icon: Any, title: str, msg: str) -> ft.Container:
        return ft.Container(
            expand=True, bgcolor=design.T().parchment,
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, color=design.T().border),
                    ft.Container(height=16),
                    ft.Text(
                        title, size=18, weight=ft.FontWeight.BOLD,
                        color=design.T().text_2, italic=True,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        msg, size=13, color=design.T().text_3,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Helper: recupero elementi selezionati
    # ──────────────────────────────────────────────────────────────────────────

    def _get_sel_diary(self) -> DiaryEntry | None:
        if not self._sel_diary_id:
            return None
        for e in self._diary_entries:
            if e.id == self._sel_diary_id:
                return e
        return None

    def _get_sel_note(self) -> CampaignNote | None:
        if not self._sel_note_id:
            return None
        for n in self._notes.get(self._active_cat, []):
            if n.id == self._sel_note_id:
                return n
        return None

    def _diary_index(self) -> int:
        for i, e in enumerate(self._diary_entries):
            if e.id == self._sel_diary_id:
                return i
        return -1

    # ──────────────────────────────────────────────────────────────────────────
    # Event handlers — navigazione categorie
    # ──────────────────────────────────────────────────────────────────────────

    def _on_cat_click(self, key: str) -> None:
        if key == self._active_cat:
            return
        self._active_cat = key
        self._note_edit = False
        self._diary_edit = False
        # Non resettare la selezione → ricorda l'ultima voce vista per categoria
        self._refresh()

    # ──────────────────────────────────────────────────────────────────────────
    # Event handlers — Cronaca
    # ──────────────────────────────────────────────────────────────────────────

    def _on_sel_diary(self, entry_id: str) -> None:
        if entry_id == self._sel_diary_id and not self._diary_edit:
            return
        self._sel_diary_id = entry_id
        self._diary_edit = False
        self._refresh()

    def _on_prev(self) -> None:
        idx = self._diary_index()
        if idx > 0:
            self._sel_diary_id = self._diary_entries[idx - 1].id
            self._diary_edit = False
            self._refresh()

    def _on_next(self) -> None:
        idx = self._diary_index()
        if idx < len(self._diary_entries) - 1:
            self._sel_diary_id = self._diary_entries[idx + 1].id
            self._diary_edit = False
            self._refresh()

    def _on_diary_start_edit(self) -> None:
        self._diary_edit = True
        self._update_detail()

    def _on_diary_cancel_edit(self) -> None:
        self._diary_edit = False
        self._update_detail()

    def _on_diary_save_edit(self, entry: DiaryEntry) -> None:
        title   = (self._ef_title.value or "").strip() or "Senza titolo"
        date    = (self._ef_date.value or "").strip()
        content = (self._ef_content.value or "").strip()
        character_repo.update_diary_entry(entry.id, title, content, date)
        logger.info("Voce diario aggiornata: %s", entry.id)
        self._diary_edit = False
        self._load_diary()
        self._refresh()

    def _on_diary_delete(self) -> None:
        page = self._page
        if page is None:
            return
        entry = self._get_sel_diary()
        if entry is None:
            return

        def do_delete(ev: Any) -> None:
            if page is None:
                return
            character_repo.delete_diary_entry(entry.id)
            page.pop_dialog()
            self._load_diary()
            self._sel_diary_id = (self._diary_entries[0].id
                                  if self._diary_entries else None)
            self._diary_edit = False
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Elimina voce", ft.Icons.DELETE_FOREVER, tone="danger"),
            content=ft.Text(
                f"Eliminare «{entry.title or 'Senza titolo'}»?\nL'azione non è reversibile.",
                size=13, color=design.T().text,
            ),
            actions=cast(list[ft.Control], wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=do_delete,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ])),
        ))

    # ──────────────────────────────────────────────────────────────────────────
    # Event handlers — Note di Campagna
    # ──────────────────────────────────────────────────────────────────────────

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

    def _on_note_save_edit(self, note: CampaignNote) -> None:
        name   = (self._nf_name.value or "").strip() or "Senza nome"
        status = (self._nf_status.value or "").strip()
        tags   = (self._nf_tags.value or "").strip()
        desc   = (self._nf_desc.value or "").strip()
        character_repo.update_campaign_note(note.id, name, desc, status, tags)
        logger.info("Campaign note aggiornata: %s", note.id)
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
            character_repo.delete_campaign_note(note.id)
            page.pop_dialog()
            self._load_notes(self._active_cat)
            notes = self._notes.get(self._active_cat, [])
            self._sel_note_id = notes[0].id if notes else None
            self._note_edit = False
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Elimina voce", ft.Icons.DELETE_FOREVER, tone="danger"),
            content=ft.Text(
                f"Eliminare «{note.name or 'Senza nome'}»?\nL'azione non è reversibile.",
                size=13, color=design.T().text,
            ),
            actions=cast(list[ft.Control], wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=do_delete,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ])),
        ))

    # ──────────────────────────────────────────────────────────────────────────
    # Event handler — pulsante "+ Aggiungi" (dispatcha per categoria)
    # ──────────────────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        if self._active_cat == "diary":
            self._open_new_diary_dialog()
        else:
            self._open_new_note_dialog()

    def _open_new_diary_dialog(self) -> None:
        page = self._page
        if page is None:
            return

        f_title = ft.TextField(
            label="Titolo", autofocus=True,
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])
        f_date = ft.TextField(
            label="Data / Sessione  (es. «Sessione 3»  ·  «15 Kythorn 1492»)",
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])
        f_content = ft.TextField(
            label="Contenuto (puoi ampliarlo in seguito)",
            multiline=True, min_lines=4, max_lines=10,
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])

        def save(ev: Any) -> None:
            if page is None:
                return
            title   = (f_title.value or "").strip() or "Senza titolo"
            date    = (f_date.value or "").strip()
            content = (f_content.value or "").strip()
            character_repo.create_diary_entry(self.character.id, title, content, date)
            page.pop_dialog()
            self._load_diary()
            if self._diary_entries:
                self._sel_diary_id = self._diary_entries[-1].id
            self._diary_edit = False
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Nuova Voce di Diario"),
            content=ft.Column(
                [f_title, f_date, f_content],
                spacing=10, scroll=ft.ScrollMode.AUTO, width=400,
            ),
            actions=cast(list[ft.Control], wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Crea", icon=ft.Icons.ADD, on_click=save,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ])),
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
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])
        f_status = ft.Dropdown(
            label="Stato",
            value=opts[0] if opts else "",
            options=[ft.DropdownOption(key=s, text=s) for s in opts],
            border_color=design.T().border,
            focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        f_desc = ft.TextField(
            label="Descrizione / Note",
            multiline=True, min_lines=3, max_lines=8,
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border, focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])

        def save(ev: Any) -> None:
            if page is None:
                return
            name   = (f_name.value or "").strip() or "Senza nome"
            status = (f_status.value or "").strip()
            desc   = (f_desc.value or "").strip()
            character_repo.create_campaign_note(
                self.character.id, cat, name, desc, status
            )
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
        fields.append(f_desc)

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(meta["add_label"]),
            content=ft.Column(
                fields, spacing=10, scroll=ft.ScrollMode.AUTO, width=400,
            ),
            actions=cast(list[ft.Control], wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Crea", icon=ft.Icons.ADD, on_click=save,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ])),
        ))

    # ──────────────────────────────────────────────────────────────────────────
    # Refresh
    # ──────────────────────────────────────────────────────────────────────────

    def _update_detail(self) -> None:
        """Aggiorna solo il pannello destro (più veloce di un rebuild completo)."""
        self._detail_container.content = self._build_detail_panel()
        try:
            self._detail_container.update()
        except RuntimeError:
            pass

    def _refresh(self) -> None:
        """Ricostruisce l'intera vista."""
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
