"""
Tracker di combattimento a schermo intero per un singolo incontro della
Modalità Master — round/turno, lista combattenti ordinata per iniziativa
(evidenziato quello di turno), aggiunta di Personaggio Giocante/NPC dalla
Rubrica/Mostro dal Bestiario/Creazione Rapida, gestione PF (solo per
npc/adhoc — i PG restano sempre gestiti dal giocatore sulla propria
scheda), Calcolatore Difficoltà Incontro. Vedi
`dnd_app/docs/master_section_design.md` per il design completo e
`core/encounter_calculator.py` per la logica pura del calcolo.

Instanziata da `MasterEncounterListView` quando il Master apre un
incontro — non gestisce da sola la navigazione verso la lista, delega a
`on_back_to_list()`.
"""

import logging
from typing import Any

import flet as ft

from config.settings import (
    COLOR_ACCENT_BLUE, COLOR_ACCENT_CRIMSON, COLOR_ACCENT_RED,
    COLOR_BG_CARD, COLOR_BG_SECONDARY, COLOR_BORDER,
    COLOR_TEXT_MUTED, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_TITLE,
)
from core.encounter_calculator import calculate_difficulty, DIFFICULTY_LABELS
from data.game_data.game_data_loader import parse_monster_xp
from data.models import MasterEncounter
from data.repositories import character_repo, master_repo
from ui.components.monster_picker import load_monsters, show_monster_picker, monster_display_name
from ui.theme import title_text, muted_text, primary_button
from ui import design

logger = logging.getLogger(__name__)



def _int_or(text: str | None, default: int) -> int:
    if text is None:
        return default
    t = text.strip()
    if not t:
        return default
    try:
        return int(t)
    except ValueError:
        try:
            return int(float(t))
        except ValueError:
            return default


class MasterEncounterView(ft.Column):
    def __init__(self, encounter_id: str, on_back_to_list):
        super().__init__(expand=True, spacing=0)
        self.encounter_id = encounter_id
        self.on_back_to_list = on_back_to_list
        self._page: ft.Page | None = None
        self.encounter: MasterEncounter | None = None
        self._members: list[dict] = []  # resolved, vedi master_repo.get_encounter_members_resolved
        self._header_area = ft.Container()
        self._list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self._build()
        self.refresh()

    def did_mount(self):
        self._page = self.page

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    def _build(self):
        self.controls.clear()
        self.controls.append(self._header_area)
        self.controls.append(
            ft.Container(content=self._list_col, expand=True, padding=ft.Padding.all(16))
        )
        self.controls.append(
            ft.Container(
                content=primary_button(
                    "+ Aggiungi Combattente", icon=ft.Icons.PERSON_ADD,
                    on_click=self._on_add_combatant_click,
                ),
                padding=ft.Padding.only(left=16, right=16, bottom=16),
            )
        )

    def refresh(self):
        self.encounter = master_repo.get_encounter_by_id(self.encounter_id)
        self._members = master_repo.get_encounter_members_resolved(self.encounter_id, active_only=True)
        self._header_area.content = self._build_header()
        self._populate_list()
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_header(self) -> ft.Control:
        enc = self.encounter
        if enc is None:
            return ft.Container(
                content=ft.Text("Incontro non trovato.", color=COLOR_TEXT_MUTED),
                padding=ft.Padding.all(16),
            )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK, icon_color=COLOR_TEXT_SECONDARY,
                                tooltip="Torna alla lista incontri",
                                on_click=lambda e: self.on_back_to_list(),
                            ),
                            ft.Column(
                                [
                                    title_text(enc.name or "(senza nome)", size=17),
                                    muted_text(f"Round {enc.round_number}", size=12),
                                ],
                                spacing=0,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # Azioni sempre visibili come pillole con etichetta, non più
                    # nascoste dietro un'icona MORE_VERT (2026-07-24, redesign su
                    # richiesta di Davide, stesso pattern di master_view.py).
                    # `wrap=True`: su schermi stretti (smartphone) vanno a capo
                    # invece di traboccare fuori dalla finestra.
                    ft.Row(
                        [
                            self._action_pill(
                                ft.Icons.ANALYTICS_OUTLINED, "Difficoltà", COLOR_ACCENT_BLUE,
                                self._on_difficulty_click,
                            ),
                            self._action_pill(
                                ft.Icons.FLAG_OUTLINED, "Termina Incontro", COLOR_TEXT_SECONDARY,
                                self._on_end_encounter_click,
                            ),
                            ft.ElevatedButton(
                                "Prossimo Turno", icon=ft.Icons.SKIP_NEXT,
                                on_click=self._on_next_turn_click,
                                style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color=design.T().on_primary),
                            ),
                        ],
                        spacing=8, wrap=True,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

    @staticmethod
    def _action_pill(icon, label: str, color: str, on_click) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=15, color=color),
                    ft.Container(width=6),
                    ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=color),
                ],
                tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, color),
            border_radius=16,
            on_click=on_click,
            ink=True,
        )

    def _populate_list(self):
        self._list_col.controls.clear()
        if not self._members:
            self._list_col.controls.append(self._empty_state())
            return
        current_idx = self.encounter.current_turn_index if self.encounter else 0
        for i, resolved in enumerate(self._members):
            self._list_col.controls.append(
                self._member_card(resolved, is_current=(i == current_idx))
            )

    def _empty_state(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.GROUPS_OUTLINED, size=48, color=COLOR_BORDER),
                    ft.Container(height=10),
                    muted_text(
                        "Nessun combattente ancora aggiunto a questo incontro.",
                        size=13, text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(32),
            alignment=ft.Alignment.CENTER,
        )

    def _member_card(self, resolved: dict, is_current: bool) -> ft.Control:
        m = resolved["member"]
        name = resolved["name"]
        ac = resolved["ac"]
        hp_current = resolved["hp_current"]
        hp_max = resolved["hp_max"]
        source = resolved["source"]

        icon = {
            "character": ft.Icons.PERSON,
            "npc": ft.Icons.SHIELD,
            "adhoc": ft.Icons.BOLT,
        }.get(source, ft.Icons.HELP_OUTLINE)
        icon_color = {
            "character": COLOR_ACCENT_BLUE,
            "npc": COLOR_ACCENT_CRIMSON,
            "adhoc": COLOR_TEXT_MUTED,
        }.get(source, COLOR_TEXT_MUTED)

        hp_ratio = (hp_current / hp_max) if hp_max else 0
        hp_color = COLOR_TEXT_PRIMARY
        if hp_max:
            if hp_ratio <= 0:
                hp_color = COLOR_ACCENT_RED
            elif hp_ratio < 0.5:
                hp_color = design.T().alert

        stats_row: list[ft.Control] = [
            ft.Text(f"CA {ac}", size=11, color=COLOR_TEXT_MUTED),
        ]
        if source == "character":
            stats_row.append(ft.Text(f"PF {hp_current}/{hp_max} (giocatore)", size=11, color=COLOR_TEXT_MUTED))
        else:
            stats_row.append(
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_size=16,
                                      icon_color=COLOR_TEXT_MUTED,
                                      on_click=lambda e, mm=m: self._on_hp_delta(mm, -1)),
                        ft.Text(f"PF {hp_current}/{hp_max}", size=12, color=hp_color, weight=ft.FontWeight.W_600),
                        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_size=16,
                                      icon_color=COLOR_TEXT_MUTED,
                                      on_click=lambda e, mm=m: self._on_hp_delta(mm, 1)),
                    ],
                    spacing=0, tight=True,
                )
            )
            if resolved.get("xp"):
                stats_row.append(ft.Text(f"{resolved['xp']} PE", size=11, color=COLOR_TEXT_MUTED))

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(str(m.initiative), size=15, weight=ft.FontWeight.BOLD,
                                         color=design.T().on_primary if is_current else COLOR_TEXT_PRIMARY,
                                         text_align=ft.TextAlign.CENTER),
                        width=34, height=34, alignment=ft.Alignment.CENTER,
                        bgcolor=COLOR_ACCENT_CRIMSON if is_current else COLOR_BG_SECONDARY,
                        border_radius=17,
                        on_click=lambda e, mm=m: self._on_edit_initiative(mm),
                        tooltip="Modifica iniziativa",
                        ink=True,
                    ),
                    ft.Container(width=10),
                    ft.Icon(icon, color=icon_color, size=20),
                    ft.Container(width=8),
                    ft.Column(
                        [
                            ft.Text(name, size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                            ft.Row(stats_row, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ],
                        spacing=3, expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE, icon_color=COLOR_TEXT_MUTED, icon_size=18,
                        tooltip="Rimuovi dall'incontro",
                        on_click=lambda e, mm=m: self._on_remove_member(mm),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(10),
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(2 if is_current else 1, COLOR_ACCENT_CRIMSON if is_current else COLOR_BORDER),
            border_radius=8,
        )

    # ------------------------------------------------------------------
    # Azioni header
    # ------------------------------------------------------------------

    def _on_next_turn_click(self, e: Any):
        master_repo.advance_turn(self.encounter_id)
        self.refresh()

    def _on_end_encounter_click(self, e: Any):
        if not self._page:
            return
        page = self._page

        def _do_end(_e: Any):
            master_repo.archive_encounter(self.encounter_id, archived=True)
            page.pop_dialog()
            self.on_back_to_list()

        dlg = ft.AlertDialog(
            title=ft.Text("Termina Incontro?", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Text(
                "L'incontro verrà archiviato e non comparirà più nella lista attiva "
                "(resta comunque conservato nello storico del database).",
                size=12, color=COLOR_TEXT_SECONDARY,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Termina", icon=ft.Icons.FLAG, on_click=_do_end,
                    style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color=design.T().on_primary),
                ),
            ],
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Calcolatore Difficoltà
    # ------------------------------------------------------------------

    def _on_difficulty_click(self, e: Any):
        if not self._page:
            return
        page = self._page

        party_levels: list[int] = []
        for resolved in self._members:
            if resolved["source"] != "character":
                continue
            m = resolved["member"]
            ch = character_repo.get_by_id(m.character_id) if m.character_id else None
            party_levels.append(ch.level if ch else 1)

        monster_xp = [
            int(resolved.get("xp", 0) or 0)
            for resolved in self._members
            if resolved["source"] in ("npc", "adhoc")
        ]

        ghost_levels: list[int] = []
        result_col = ft.Column([], spacing=6)
        ghost_row = ft.Row([], spacing=6, wrap=True)
        ghost_tf = ft.TextField(label="Livello PG fantasma", value="1", width=140, dense=True,
                                 border_radius=6, keyboard_type=ft.KeyboardType.NUMBER)

        def _recompute():
            levels = party_levels + ghost_levels
            res = calculate_difficulty(monster_xp, levels)
            diff_key = res["difficulty"]
            diff_label = DIFFICULTY_LABELS.get(diff_key, diff_key)
            diff_color = design.difficulty_color(diff_key)
            thr = res["thresholds"]
            result_col.controls.clear()
            result_col.controls.extend([
                ft.Text(
                    f"Gruppo: {res['party_size']} personaggi (livelli {', '.join(str(l) for l in levels) or '—'})",
                    size=12, color=COLOR_TEXT_SECONDARY,
                ),
                ft.Text(
                    f"Mostri/NPC: {res['monster_count']} · PE totali {res['monster_xp_total']} "
                    f"× {res['multiplier']:g} = PE modificato {res['adjusted_xp']}",
                    size=12, color=COLOR_TEXT_SECONDARY,
                ),
                ft.Container(height=6),
                ft.Container(
                    content=ft.Text(diff_label.upper(), size=16, weight=ft.FontWeight.BOLD, color=design.T().on_primary,
                                     text_align=ft.TextAlign.CENTER),
                    bgcolor=diff_color, border_radius=6, padding=ft.Padding.symmetric(vertical=8),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(height=6),
                ft.Text(
                    f"Soglie di gruppo — Facile {thr['facile']} · Medio {thr['medio']} · "
                    f"Difficile {thr['difficile']} · Letale {thr['letale']}",
                    size=11, color=COLOR_TEXT_MUTED,
                ),
            ])
            try:
                result_col.update()
            except RuntimeError:
                pass

        def _add_ghost(_e: Any):
            lvl = max(1, min(20, _int_or(ghost_tf.value, 1)))
            ghost_levels.append(lvl)
            _rebuild_ghost_row()
            _recompute()

        def _remove_ghost(idx: int):
            if 0 <= idx < len(ghost_levels):
                ghost_levels.pop(idx)
            _rebuild_ghost_row()
            _recompute()

        def _rebuild_ghost_row():
            ghost_row.controls.clear()
            for i, lvl in enumerate(ghost_levels):
                ghost_row.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(f"Lv.{lvl}", size=11, color=COLOR_TEXT_SECONDARY),
                                ft.IconButton(ft.Icons.CLOSE, icon_size=12, icon_color=COLOR_TEXT_MUTED,
                                              on_click=lambda e, ix=i: _remove_ghost(ix)),
                            ],
                            spacing=0, tight=True,
                        ),
                        padding=ft.Padding.symmetric(horizontal=6),
                        border=ft.Border.all(1, COLOR_BORDER), border_radius=12,
                    )
                )
            try:
                ghost_row.update()
            except RuntimeError:
                pass

        _recompute()

        dlg = ft.AlertDialog(
            title=ft.Text("Calcolatore Difficoltà Incontro", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [
                        muted_text(
                            "Aggiungi \"PG fantasma\" per pianificare con personaggi non ancora "
                            "presenti nell'incontro (i livelli non vengono salvati).", size=11,
                        ),
                        ft.Row([ghost_tf, ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=COLOR_ACCENT_BLUE,
                                                        on_click=_add_ghost)], spacing=6),
                        ghost_row,
                        ft.Divider(height=14, color=COLOR_BORDER),
                        result_col,
                    ],
                    spacing=6, scroll=ft.ScrollMode.AUTO, tight=True,
                ),
                width=340, height=420,
            ),
            actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # PF / Iniziativa / Rimozione membro
    # ------------------------------------------------------------------

    def _on_hp_delta(self, member, delta: int):
        new_hp = max(0, member.hp_current + delta)
        master_repo.update_member_hp(member.id, new_hp)
        self.refresh()

    def _on_edit_initiative(self, member):
        if not self._page:
            return
        page = self._page
        init_tf = ft.TextField(label="Iniziativa", value=str(member.initiative), dense=True,
                                border_radius=6, autofocus=True, keyboard_type=ft.KeyboardType.NUMBER)

        def _do_save(_e: Any):
            master_repo.update_member_initiative(member.id, _int_or(init_tf.value, member.initiative))
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Modifica Iniziativa", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=init_tf, width=200),
            actions=[
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Salva", icon=ft.Icons.SAVE, on_click=_do_save,
                                   style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color=design.T().on_primary)),
            ],
        )
        page.show_dialog(dlg)

    def _on_remove_member(self, member):
        master_repo.remove_member(member.id)
        self.refresh()

    # ------------------------------------------------------------------
    # Aggiungi Combattente — dialog a 4 scelte
    # ------------------------------------------------------------------

    def _next_order_index(self) -> int:
        existing = master_repo.get_encounter_members(self.encounter_id, active_only=False)
        return (max((m.order_index for m in existing), default=-1) + 1)

    def _on_add_combatant_click(self, e: Any):
        if not self._page:
            return
        page = self._page

        def _go(fn):
            def _inner(_e: Any):
                page.pop_dialog()
                fn()
            return _inner

        dlg = ft.AlertDialog(
            title=ft.Text("Aggiungi Combattente", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.OutlinedButton(
                        "Personaggio Giocante", icon=ft.Icons.PERSON_OUTLINE,
                        on_click=_go(self._open_add_character_dialog),
                        style=ft.ButtonStyle(color=COLOR_ACCENT_BLUE, side=ft.BorderSide(1, COLOR_ACCENT_BLUE)),
                    ),
                    ft.Container(height=6),
                    ft.OutlinedButton(
                        "NPC dalla Rubrica", icon=ft.Icons.GROUPS_OUTLINED,
                        on_click=_go(self._open_add_npc_dialog),
                        style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON, side=ft.BorderSide(1, COLOR_ACCENT_CRIMSON)),
                    ),
                    ft.Container(height=6),
                    ft.OutlinedButton(
                        "Mostro dal Bestiario", icon=ft.Icons.MENU_BOOK_OUTLINED,
                        on_click=_go(self._open_add_monster_dialog),
                        style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON, side=ft.BorderSide(1, COLOR_ACCENT_CRIMSON)),
                    ),
                    ft.Container(height=6),
                    ft.OutlinedButton(
                        "Creazione Rapida", icon=ft.Icons.BOLT,
                        on_click=_go(self._open_add_adhoc_dialog),
                        style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY, side=ft.BorderSide(1, COLOR_BORDER)),
                    ),
                ],
                tight=True,
            ),
            actions=[ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog())],
        )
        page.show_dialog(dlg)

    def _open_add_character_dialog(self):
        if not self._page:
            return
        page = self._page
        chars = character_repo.get_all()
        already_ids = {
            resolved["member"].character_id for resolved in
            master_repo.get_encounter_members_resolved(self.encounter_id, active_only=False)
            if resolved["source"] == "character"
        }
        available = [c for c in chars if c.id not in already_ids]

        if not available:
            dlg = ft.AlertDialog(
                title=ft.Text("Nessun personaggio disponibile", size=15, weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    "Tutti i personaggi esistenti sono già in questo incontro, oppure non ne hai ancora creato uno.",
                    size=12, color=COLOR_TEXT_SECONDARY,
                ),
                actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
            )
            page.show_dialog(dlg)
            return

        char_dd = ft.Dropdown(
            label="Personaggio",
            options=[ft.DropdownOption(key=c.id, text=f"{c.name} (Lv.{c.level} {c.class_name})") for c in available],
            value=available[0].id, dense=True, border_radius=6,
        )
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=120,
                                keyboard_type=ft.KeyboardType.NUMBER)

        def _do_add(_e: Any):
            ch = next((c for c in available if c.id == char_dd.value), available[0])
            master_repo.add_member(
                encounter_id=self.encounter_id, kind="character", character_id=ch.id,
                display_name=ch.name, initiative=_int_or(init_tf.value, 10),
                order_index=self._next_order_index(),
            )
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Aggiungi Personaggio Giocante", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([char_dd, ft.Container(height=8), init_tf], tight=True), width=300,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Aggiungi", icon=ft.Icons.ADD, on_click=_do_add,
                                   style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_BLUE, color=design.T().on_accent)),
            ],
        )
        page.show_dialog(dlg)

    def _open_add_npc_dialog(self):
        if not self._page:
            return
        page = self._page
        npcs = master_repo.get_npcs()

        if not npcs:
            dlg = ft.AlertDialog(
                title=ft.Text("Nessun NPC in rubrica", size=15, weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    "Crea prima un NPC dalla tab \"Rubrica NPC\", poi torna qui per aggiungerlo.",
                    size=12, color=COLOR_TEXT_SECONDARY,
                ),
                actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
            )
            page.show_dialog(dlg)
            return

        npc_dd = ft.Dropdown(
            label="NPC",
            options=[ft.DropdownOption(key=n.id, text=n.name or "(senza nome)") for n in npcs],
            value=npcs[0].id, dense=True, border_radius=6,
        )
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=100,
                                keyboard_type=ft.KeyboardType.NUMBER)
        qty_tf = ft.TextField(label="Quantità", value="1", dense=True, width=90,
                               keyboard_type=ft.KeyboardType.NUMBER)

        def _do_add(_e: Any):
            npc = next((n for n in npcs if n.id == npc_dd.value), npcs[0])
            qty = max(1, _int_or(qty_tf.value, 1))
            base_idx = self._next_order_index()
            for i in range(qty):
                name = f"{npc.name} {i + 1}" if qty > 1 else npc.name
                master_repo.add_member(
                    encounter_id=self.encounter_id, kind="npc", npc_id=npc.id,
                    display_name=name, ac=npc.ac, hp_current=npc.hp_max, hp_max=npc.hp_max,
                    xp=npc.xp, initiative=_int_or(init_tf.value, 10), order_index=base_idx + i,
                )
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Aggiungi NPC dalla Rubrica", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([npc_dd, ft.Row([init_tf, qty_tf], spacing=8)], spacing=8, tight=True),
                width=300,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Aggiungi", icon=ft.Icons.ADD, on_click=_do_add,
                                   style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color=design.T().on_primary)),
            ],
        )
        page.show_dialog(dlg)

    def _open_add_monster_dialog(self):
        if not self._page:
            return
        page = self._page
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=110,
                                keyboard_type=ft.KeyboardType.NUMBER)
        qty_tf = ft.TextField(label="Quantità", value="1", dense=True, width=90,
                               keyboard_type=ft.KeyboardType.NUMBER)
        save_cb = ft.Checkbox(label="Salva anche in Rubrica NPC", value=False)

        def _open_picker(_e: Any):
            page.pop_dialog()
            pool = load_monsters()

            def _on_select(m: dict):
                page.pop_dialog()
                qty = max(1, _int_or(qty_tf.value, 1))
                init_val = _int_or(init_tf.value, 10)
                base_idx = self._next_order_index()
                disp = monster_display_name(m.get("name", ""))
                for i in range(qty):
                    name = f"{disp} {i + 1}" if qty > 1 else disp
                    master_repo.add_member(
                        encounter_id=self.encounter_id, kind="adhoc",
                        display_name=name, ac=int(m.get("ac", 10)),
                        hp_current=int(m.get("hp_max", 1)), hp_max=int(m.get("hp_max", 1)),
                        xp=parse_monster_xp(m.get("xp", 0)), initiative=init_val, order_index=base_idx + i,
                    )
                if save_cb.value:
                    master_repo.create_npc_from_monster(m)
                self.refresh()

            show_monster_picker(
                page, "Mostro dal Bestiario", pool, existing_names=set(), on_select=_on_select,
                select_label="Aggiungi all'incontro", select_color=COLOR_ACCENT_CRIMSON,
            )

        dlg = ft.AlertDialog(
            title=ft.Text("Aggiungi Mostro dal Bestiario", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row([init_tf, qty_tf], spacing=8),
                        save_cb,
                        muted_text("Il nome, CA, PF e PE verranno importati automaticamente dal mostro scelto.",
                                   size=11),
                    ],
                    spacing=8, tight=True,
                ),
                width=300,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Scegli Mostro...", icon=ft.Icons.MENU_BOOK_OUTLINED, on_click=_open_picker,
                                   style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color=design.T().on_primary)),
            ],
        )
        page.show_dialog(dlg)

    def _open_add_adhoc_dialog(self):
        if not self._page:
            return
        page = self._page
        name_tf = ft.TextField(label="Nome *", dense=True, border_radius=6, autofocus=True)
        ac_tf = ft.TextField(label="CA", value="10", dense=True, width=90,
                              keyboard_type=ft.KeyboardType.NUMBER)
        hp_tf = ft.TextField(label="PF", value="10", dense=True, width=90,
                              keyboard_type=ft.KeyboardType.NUMBER)
        xp_tf = ft.TextField(label="PE", value="0", dense=True, width=90,
                              keyboard_type=ft.KeyboardType.NUMBER)
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=110,
                                keyboard_type=ft.KeyboardType.NUMBER)
        error_text = ft.Text("", size=12, color=COLOR_ACCENT_RED)

        def _do_add(_e: Any):
            name = (name_tf.value or "").strip()
            if not name:
                error_text.value = "Il nome è obbligatorio."
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return
            hp = _int_or(hp_tf.value, 10)
            master_repo.add_member(
                encounter_id=self.encounter_id, kind="adhoc", display_name=name,
                ac=_int_or(ac_tf.value, 10), hp_current=hp, hp_max=hp,
                xp=_int_or(xp_tf.value, 0), initiative=_int_or(init_tf.value, 10),
                order_index=self._next_order_index(),
            )
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Creazione Rapida", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [name_tf, ft.Row([ac_tf, hp_tf, xp_tf], spacing=8), init_tf, error_text],
                    spacing=8, tight=True,
                ),
                width=320,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Aggiungi", icon=ft.Icons.ADD, on_click=_do_add,
                                   style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color=design.T().on_primary)),
            ],
        )
        page.show_dialog(dlg)
