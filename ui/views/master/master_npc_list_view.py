"""
Vista "Rubrica NPC" della Modalità Master. Lista/ricerca degli NPC salvati
in `master_npcs`, con dialog di dettaglio (stat block completo se
`has_stat_block`), creazione (due percorsi: "Nuovo dal Bestiario"/"Nuovo
Manuale"), modifica ed eliminazione. Vedi
`dnd_app/docs/master_section_design.md` per il design completo.

Indipendente da ogni personaggio giocante — nessuna dipendenza da
`character_repo`, solo da `master_repo` (le 3 tabelle Master) e dal
bestiario condiviso (`ui.components.monster_picker`).
"""

import logging
from typing import Any

import flet as ft

from config import settings
from core import npc_generator as ng
from data.game_data.game_data_loader import GameDataLoader, parse_monster_xp
from data.models import MasterNpc
from data.repositories import master_repo
from ui.components.monster_picker import (
    creature_entry_dict, load_monsters, show_monster_picker,
    build_stat_block_column, monster_display_name,
)
from ui.theme import title_text, body_text, muted_text, primary_button
from ui.widgets import DropdownAltro, MultiSelectAltro, wrap_dialog_actions, responsive_dialog_width
from ui import design

logger = logging.getLogger(__name__)
_loader = GameDataLoader()


def _int_or(text: str | None, default: int) -> int:
    """Parsing tollerante di un TextField numerico — mai un'eccezione per
    testo vuoto/non numerico, ricade sul default invece di bloccare il
    salvataggio dell'NPC."""
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


def _csv_to_list(csv: str) -> list[str]:
    return [s.strip() for s in (csv or "").split(",") if s.strip()]


def _list_to_csv(values: list[str]) -> str:
    return ", ".join(values)


class MasterNpcListView(ft.Column):
    """Lista/ricerca NPC di rubrica + creazione/modifica/eliminazione."""

    def __init__(self, world_id: str = ""):
        super().__init__(expand=True, spacing=0, scroll=ft.ScrollMode.AUTO)
        self._page: ft.Page | None = None
        #: Mondo correntemente selezionato in `MasterView` (2026-08-12, bug
        #: report Davide: "in Master... npc... tutto deve essere dipendente
        #: dal mondo") — "" per la modalità locale. Stesso principio già in
        #: uso per Incontri/Note/Bottino: un mondo è un container, la
        #: rubrica NPC ne mostra/crea solo il contenuto.
        self._world_id = world_id
        self._npcs: list[MasterNpc] = []
        self._search_query: str = ""
        self._list_col = ft.Column(spacing=10)
        self._build()
        self.refresh()

    def did_mount(self):
        self._page = self.page

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    def _build(self):
        self.controls.clear()
        header = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            title_text("Rubrica NPC", size=18),
                            ft.Container(expand=True),
                            primary_button("+ Nuovo NPC", on_click=self._on_new_click),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.TextField(
                        hint_text="Cerca per nome, ruolo o tag...",
                        prefix_icon=ft.Icons.SEARCH,
                        dense=True,
                        border_radius=8,
                        on_change=self._on_search_change,
                        border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style']),
                ],
                spacing=10,
            ),
            padding=ft.Padding.all(16),
        )
        body = ft.Container(
            content=self._list_col,
            padding=ft.Padding.only(left=16, right=16, bottom=16),
        )
        self.controls.append(header)
        self.controls.append(body)

    def refresh(self):
        self._npcs = master_repo.get_npcs(self._search_query, self._world_id)
        self._populate_list()
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_search_change(self, e: Any):
        self._search_query = e.control.value or ""
        self.refresh()

    def _populate_list(self):
        self._list_col.controls.clear()
        if not self._npcs:
            self._list_col.controls.append(self._empty_state())
            return
        for npc in self._npcs:
            self._list_col.controls.append(self._npc_card(npc))

    def _empty_state(self) -> ft.Control:
        msg = (
            "Nessun NPC trovato per questa ricerca."
            if self._search_query
            else "Nessun NPC ancora salvato. Creane uno dal Bestiario o manualmente."
        )
        return design.empty_state(ft.Icons.GROUPS_OUTLINED, "Rubrica vuota", msg)

    def _npc_card(self, npc: MasterNpc) -> ft.Control:
        chips: list[ft.Control] = []
        if npc.role:
            chips.append(self._chip(npc.role, design.T().magic))
        for tag in [t.strip() for t in npc.tags.split(",") if t.strip()]:
            chips.append(self._chip(tag, design.T().text_3))

        subtitle_parts: list[str] = []
        if npc.has_stat_block:
            subtitle_parts.append(f"CA {npc.ac} · PF {npc.hp_max}")
            if npc.cr:
                subtitle_parts.append(f"GS {npc.cr}")
            if npc.xp:
                subtitle_parts.append(f"{npc.xp} PE")
        subtitle = " · ".join(subtitle_parts)

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.SHIELD if npc.has_stat_block else ft.Icons.PERSON_OUTLINE,
                            color=design.T().primary if npc.has_stat_block else design.T().text_3,
                            size=22,
                        ),
                        width=44, height=44,
                        alignment=ft.Alignment.CENTER,
                        bgcolor=ft.Colors.with_opacity(
                            0.12, design.T().primary_fill if npc.has_stat_block else design.T().text_3),
                        border_radius=design.Radius.PILL,
                    ),
                    ft.Container(width=design.Space.MD),
                    ft.Column(
                        [
                            ft.Text(npc.name or "(senza nome)", size=15,
                                     weight=ft.FontWeight.BOLD,
                                     color=design.T().text,
                                     font_family=design.Font.DISPLAY,
                                     no_wrap=True, max_lines=1,
                                     overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Row(chips, spacing=6, wrap=True) if chips else ft.Container(height=0),
                            ft.Text(subtitle, size=11, color=design.T().text_3) if subtitle else ft.Container(height=0),
                        ],
                        spacing=3, expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=design.T().text_3, size=18),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(design.Space.MD),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
            border=ft.Border.only(left=ft.BorderSide(
                3, design.T().primary if npc.has_stat_block else design.T().magic)),
            on_click=lambda e, n=npc: self._open_detail(n),
            ink=True,
            animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
        )

    @staticmethod
    def _chip(text: str, color: str) -> ft.Container:
        """Chip dalla primitiva condivisa: il colore passato sceglie il tono."""
        p = design.T()
        tone = {p.primary: "primary", p.magic: "magic", p.success: "success",
                p.warning: "warning", p.danger: "danger"}.get(color, "neutral")
        return design.chip(text, tone)

    # ------------------------------------------------------------------
    # Dettaglio NPC
    # ------------------------------------------------------------------

    def _open_detail(self, npc: MasterNpc):
        if not self._page:
            return
        page = self._page

        content_col: ft.Control
        if npc.has_stat_block:
            content_col = build_stat_block_column(creature_entry_dict(npc))
        else:
            content_col = ft.Column(
                [ft.Text("Nessuna statistica di combattimento — solo scheda di ruolo.",
                         size=12, color=design.T().text_3, italic=True)]
            )

        info_rows: list[ft.Control] = []
        if npc.role:
            info_rows.append(body_text(f"Ruolo: {npc.role}", size=12, color=design.T().text_2))
        if npc.tags:
            info_rows.append(body_text(f"Tag: {npc.tags}", size=12, color=design.T().text_3))
        if npc.notes:
            info_rows.append(ft.Container(height=6))
            # Note lunghe (>~3-4 righe) dietro un collassabile — stesso
            # principio della scheda mostro: ridurre lo spazio occupato
            # senza nascondere l'informazione (chiusa di default solo se
            # abbastanza lunga da valerne la pena). Nessuno stato su `self`:
            # basta sopravvivere alla vita di questo dialog, stesso pattern
            # a `ft.Ref` locale già usato in `monster_picker.py`.
            notes_text = npc.notes
            if len(notes_text) > 180 or notes_text.count("\n") >= 3:
                notes_ref: ft.Ref[ft.Container] = ft.Ref()

                def _render_notes(exp: bool) -> ft.Control:
                    return design.collapsible_section(
                        "Note", lambda: body_text(notes_text, size=13, color=design.T().text),
                        expanded=exp, on_toggle=_on_notes_toggle,
                    )

                def _on_notes_toggle(new_state: bool) -> None:
                    notes_ref.current.content = _render_notes(new_state)
                    try:
                        notes_ref.current.update()
                    except Exception:
                        pass

                info_rows.append(ft.Container(content=_render_notes(False), ref=notes_ref))
            else:
                info_rows.append(body_text(notes_text, size=13, color=design.T().text))

        dlg = ft.AlertDialog(
            title=design.dialog_title(npc.name or "(senza nome)"),
            content=ft.Container(
                content=ft.Column(
                    [*info_rows, ft.Divider(height=14, color=design.T().border) if info_rows else ft.Container(height=0),
                     content_col],
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=responsive_dialog_width(page, 340), height=480,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton(
                    "Aggiungi a Incontro...", icon=ft.Icons.PLAYLIST_ADD,
                    on_click=lambda e, n=npc: self._open_add_to_encounter(n),
                ),
                ft.TextButton(
                    "Modifica", icon=ft.Icons.EDIT,
                    on_click=lambda e, n=npc: (page.pop_dialog(), self._open_npc_form(npc=n)),
                ),
                ft.TextButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE,
                    style=ft.ButtonStyle(color=design.T().danger),
                    on_click=lambda e, n=npc: (page.pop_dialog(), self._confirm_delete(n)),
                ),
                ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
            ]),
        )
        page.show_dialog(dlg)

    def _confirm_delete(self, npc: MasterNpc):
        if not self._page:
            return
        page = self._page

        def _do_delete(e: Any):
            master_repo.delete_npc(npc.id)
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Elimina NPC?"),
            content=ft.Text(
                f"\"{npc.name}\" verrà rimosso dalla rubrica. Se è già presente in un incontro "
                "salvato, il suo nome/CA/PF restano comunque nello storico di quell'incontro.",
                size=12, color=design.T().text_2,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=_do_delete,
                    style=ft.ButtonStyle(bgcolor=design.T().danger_fill, color=design.T().on_primary_fill),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _open_add_to_encounter(self, npc: MasterNpc):
        if not self._page:
            return
        page = self._page
        page.pop_dialog()
        encounters = master_repo.get_encounters(include_archived=False)

        if not encounters:
            info_dlg = ft.AlertDialog(
                title=design.dialog_title("Nessun incontro attivo"),
                content=ft.Text(
                    "Crea prima un incontro dalla tab \"Incontri\", poi torna qui per aggiungerci questo NPC.",
                    size=12, color=design.T().text_2,
                ),
                actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
            )
            page.show_dialog(info_dlg)
            return

        enc_dd = ft.Dropdown(
            label="Incontro",
            options=[ft.DropdownOption(key=enc.id, text=enc.name or "(senza nome)") for enc in encounters],
            value=encounters[0].id, dense=True, border_radius=design.Radius.SM,
            border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=100,
                                keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())

        def _do_add(e: Any):
            enc_id = enc_dd.value or encounters[0].id
            master_repo.add_member(
                encounter_id=enc_id, kind="npc", npc_id=npc.id,
                display_name=npc.name, ac=npc.ac, hp_current=npc.hp_max, hp_max=npc.hp_max,
                xp=npc.xp, initiative=_int_or(init_tf.value, 10),
            )
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=design.dialog_title(f"Aggiungi \"{npc.name}\" a un incontro"),
            content=ft.Container(
                content=ft.Column([enc_dd, ft.Container(height=8), init_tf], tight=True),
                width=responsive_dialog_width(page, 300),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Aggiungi", icon=ft.Icons.ADD, on_click=_do_add,
                    style=ft.ButtonStyle(bgcolor=design.T().magic, color=design.T().on_accent),
                ),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Creazione — scelta tra i due percorsi
    # ------------------------------------------------------------------

    def _on_new_click(self, e: Any):
        if not self._page:
            return
        page = self._page

        def _from_bestiary(_e: Any):
            page.pop_dialog()
            self._open_bestiary_picker()

        def _manual(_e: Any):
            page.pop_dialog()
            self._open_npc_form(npc=None, prefill_monster=None)

        def _generate(_e: Any):
            page.pop_dialog()
            from ui.views.master.master_npc_generator_dialog import show_npc_generator_dialog
            show_npc_generator_dialog(page, on_saved=self.refresh, world_id=self._world_id)

        dlg = ft.AlertDialog(
            title=design.dialog_title("Nuovo NPC"),
            content=ft.Column(
                [
                    ft.Text("Come vuoi crearlo?", size=12, color=design.T().text_2),
                    ft.Container(height=10),
                    ft.OutlinedButton(
                        "Nuovo dal Bestiario", icon=ft.Icons.MENU_BOOK_OUTLINED,
                        on_click=_from_bestiary,
                        style=ft.ButtonStyle(color=design.T().primary,
                                             side=ft.BorderSide(1, design.T().primary)),
                    ),
                    ft.Container(height=8),
                    ft.OutlinedButton(
                        "Nuovo Manuale", icon=ft.Icons.EDIT_OUTLINED,
                        on_click=_manual,
                        style=ft.ButtonStyle(color=design.T().magic,
                                             side=ft.BorderSide(1, design.T().magic)),
                    ),
                    ft.Container(height=8),
                    ft.OutlinedButton(
                        "Genera Casuale", icon=ft.Icons.AUTO_AWESOME,
                        on_click=_generate,
                        style=ft.ButtonStyle(color=design.T().magic,
                                             side=ft.BorderSide(1, design.T().magic)),
                    ),
                ],
                tight=True,
            ),
            actions=[ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog())],
        )
        page.show_dialog(dlg)

    def _open_bestiary_picker(self):
        if not self._page:
            return
        pool = load_monsters()

        def _on_select(m: dict):
            self._page.pop_dialog()  # type: ignore[union-attr]
            self._open_npc_form(npc=None, prefill_monster=m)

        show_monster_picker(
            self._page, "Nuovo NPC dal Bestiario", pool,
            existing_names=set(), on_select=_on_select,
            select_label="Usa questo mostro", select_color=design.T().magic,
        )

    # ------------------------------------------------------------------
    # Form Nuovo Manuale / Modifica / atterraggio dal Bestiario
    # ------------------------------------------------------------------

    def _open_npc_form(self, npc: MasterNpc | None, prefill_monster: dict | None = None):
        """
        Un unico form per tutti e 3 gli scenari:
          - `npc` valorizzato            → modifica di un NPC esistente
          - `prefill_monster` valorizzato → creazione "dal Bestiario", form
            precompilato con l'intero stat block del mostro scelto, per gli
            ultimi ritocchi (nome/ruolo/note/tag ed eventuali correzioni ai
            campi numerici) prima del salvataggio effettivo in `master_npcs`
          - nessuno dei due              → creazione "Nuovo Manuale", form vuoto

        I campi complessi (Tratti/Azioni/Reazioni/Azioni Leggendarie) non sono
        editabili riga per riga in questo form — restano quelli già presenti
        sull'NPC in modifica, o quelli importati dal mostro scelto in
        creazione; per cambiarli davvero conviene ricreare l'NPC dal
        Bestiario. Mostrati qui solo come conteggio di sola lettura.
        """
        if not self._page:
            return
        page = self._page
        is_edit = npc is not None

        # Sorgente dei valori di partenza: npc esistente > mostro scelto > default vuoti
        if npc is not None:
            src: dict[str, Any] = {
                "name": npc.name, "role": npc.role, "notes": npc.notes, "tags": npc.tags,
                "has_stat_block": npc.has_stat_block, "creature_type": npc.creature_type,
                "size": npc.size, "alignment": npc.alignment, "ac": npc.ac, "ac_note": npc.ac_note,
                "hp_max": npc.hp_max, "hp_formula": npc.hp_formula, "speed": npc.speed,
                "str_score": npc.str_score, "dex_score": npc.dex_score, "con_score": npc.con_score,
                "int_score": npc.int_score, "wis_score": npc.wis_score, "cha_score": npc.cha_score,
                "damage_vulnerabilities": npc.damage_vulnerabilities,
                "damage_resistances": npc.damage_resistances,
                "damage_immunities": npc.damage_immunities,
                "condition_immunities": npc.condition_immunities,
                "senses": npc.senses, "languages": npc.languages, "cr": npc.cr, "xp": npc.xp,
                "saving_throws": npc.saving_throws, "skills": npc.skills,
                "traits": npc.traits, "actions": npc.actions,
                "reactions": npc.reactions, "legendary_actions": npc.legendary_actions,
                "source_page": npc.source_page,
                "race": npc.race or ng.resolve_race_from_tags(npc.tags),
            }
        elif prefill_monster is not None:
            m = prefill_monster
            import json as _json
            src = {
                "name": monster_display_name(m.get("name", "")), "role": "", "notes": "", "tags": "",
                "has_stat_block": True, "creature_type": m.get("type", ""),
                "size": m.get("size", ""), "alignment": m.get("alignment", ""),
                "ac": int(m.get("ac", 10)), "ac_note": m.get("ac_note", ""),
                "hp_max": int(m.get("hp_max", 1)), "hp_formula": m.get("hp_formula", ""),
                "speed": m.get("speed", ""),
                "str_score": int(m.get("str_score", 10)), "dex_score": int(m.get("dex_score", 10)),
                "con_score": int(m.get("con_score", 10)), "int_score": int(m.get("int_score", 10)),
                "wis_score": int(m.get("wis_score", 10)), "cha_score": int(m.get("cha_score", 10)),
                "damage_vulnerabilities": m.get("damage_vulnerabilities", ""),
                "damage_resistances": m.get("damage_resistances", ""),
                "damage_immunities": m.get("damage_immunities", ""),
                "condition_immunities": m.get("condition_immunities", ""),
                "senses": m.get("senses", ""), "languages": m.get("languages", ""),
                "cr": str(m.get("cr", "")), "xp": parse_monster_xp(m.get("xp", 0)),
                "saving_throws": _json.dumps(m.get("saving_throws", {})),
                "skills": _json.dumps(m.get("skills", {})),
                "traits": _json.dumps(m.get("traits", [])),
                "actions": _json.dumps(m.get("actions", [])),
                "reactions": _json.dumps(m.get("reactions", [])),
                "legendary_actions": _json.dumps(m.get("legendary_actions", [])),
                "source_page": (
                    f"da Bestiario: {m.get('name', '')} (p.{m['source_page']})"
                    if m.get("source_page") else f"da Bestiario: {m.get('name', '')}"
                ),
                "race": "",
            }
        else:
            src = {
                "name": "", "role": "", "notes": "", "tags": "",
                "has_stat_block": False, "creature_type": "", "size": "", "alignment": "",
                "ac": 10, "ac_note": "", "hp_max": 1, "hp_formula": "", "speed": "9 m",
                "str_score": 10, "dex_score": 10, "con_score": 10,
                "int_score": 10, "wis_score": 10, "cha_score": 10,
                "damage_vulnerabilities": "", "damage_resistances": "",
                "damage_immunities": "", "condition_immunities": "",
                "senses": "", "languages": "", "cr": "", "xp": 0,
                "saving_throws": "{}", "skills": "{}",
                "traits": "[]", "actions": "[]", "reactions": "[]", "legendary_actions": "[]",
                "source_page": "",
                "race": "",
            }

        # --- campi anagrafici, sempre visibili ---
        name_tf = ft.TextField(label="Nome *", value=src["name"], dense=True, border_radius=design.Radius.SM, autofocus=True, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        role_tf = ft.TextField(label="Ruolo (es. Alleato, Antagonista, Comune)", value=src["role"],
                                dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        tags_tf = ft.TextField(label="Tag (separati da virgola)", value=src["tags"], dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        notes_tf = ft.TextField(label="Note di ruolo / backstory", value=src["notes"],
                                 multiline=True, min_lines=2, max_lines=6, dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        # Razza (2026-08-12, bug report Davide) — fuori da stat_fields_col:
        # ha senso anche per un NPC "solo ruolo" senza stat block, e serve
        # da fonte per l'auto-riempimento di Tipo creatura/Taglia sotto.
        race_picker = DropdownAltro("Razza", ng.get_race_options(), src["race"], width=180)
        error_text = ft.Text("", size=12, color=design.T().danger)

        # --- toggle + campi statistiche ---
        stat_cb = ft.Checkbox(label="Ha statistiche di combattimento", value=src["has_stat_block"])

        type_picker = DropdownAltro("Tipo creatura", settings.CREATURE_TYPES, src["creature_type"], width=160)
        size_picker = DropdownAltro("Taglia", settings.SIZES, src["size"], width=110)
        align_picker = DropdownAltro("Allineamento", settings.ALIGNMENTS, src["alignment"])
        ac_tf = ft.TextField(label="CA", value=str(src["ac"]), dense=True, border_radius=design.Radius.SM, width=80,
                              keyboard_type=ft.KeyboardType.NUMBER, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        ac_note_tf = ft.TextField(label="Nota CA", value=src["ac_note"], dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        hp_tf = ft.TextField(label="PF Massimi", value=str(src["hp_max"]), dense=True, border_radius=design.Radius.SM,
                              width=100, keyboard_type=ft.KeyboardType.NUMBER, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        hp_formula_tf = ft.TextField(label="Formula PF (es. 2d8+2)", value=src["hp_formula"],
                                      dense=True, border_radius=design.Radius.SM, width=160, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        speed_tf = ft.TextField(label="Velocità", value=src["speed"], dense=True, border_radius=design.Radius.SM, width=110, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        cr_picker = DropdownAltro("GS", settings.CR_OPTIONS, src["cr"], width=80)
        xp_tf = ft.TextField(label="PE (per Calcolatore Difficoltà)", value=str(src["xp"]), dense=True,
                              border_radius=design.Radius.SM, width=180, keyboard_type=ft.KeyboardType.NUMBER, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])

        def _score_field(label: str, key: str) -> ft.TextField:
            return ft.TextField(label=label, value=str(src[key]), dense=True, border_radius=design.Radius.SM,
                                 width=70, keyboard_type=ft.KeyboardType.NUMBER, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])

        str_tf, dex_tf, con_tf = _score_field("FOR", "str_score"), _score_field("DES", "dex_score"), _score_field("COS", "con_score")
        int_tf, wis_tf, cha_tf = _score_field("INT", "int_score"), _score_field("SAG", "wis_score"), _score_field("CAR", "cha_score")

        senses_tf = ft.TextField(label="Sensi", value=src["senses"], dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        languages_tf = ft.TextField(label="Linguaggi", value=src["languages"], dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        _damage_options = list(settings.DAMAGE_TYPES_IT.values())
        vuln_picker = MultiSelectAltro(_damage_options, _csv_to_list(src["damage_vulnerabilities"]))
        res_picker = MultiSelectAltro(_damage_options, _csv_to_list(src["damage_resistances"]))
        imm_picker = MultiSelectAltro(_damage_options, _csv_to_list(src["damage_immunities"]))
        _conditions = _loader.get_conditions()
        cond_picker = MultiSelectAltro(
            [c["name"] for c in _conditions],
            _csv_to_list(src["condition_immunities"]),
            base_option_bodies={c["name"]: c.get("description", "") for c in _conditions},
        )

        import json as _json2

        def _feat_count(key: str) -> int:
            try:
                return len(_json2.loads(src[key]) or [])
            except Exception:
                return 0

        complex_note = muted_text(
            "Tratti {t} · Azioni {a} · Reazioni {r} · Azioni Leggendarie {l}"
            " — importati dal Bestiario, non modificabili da qui: per cambiarli ricrea l'NPC dal Bestiario.".format(
                t=_feat_count("traits"), a=_feat_count("actions"),
                r=_feat_count("reactions"), l=_feat_count("legendary_actions"),
            ),
            size=11,
        ) if any(_feat_count(k) for k in ("traits", "actions", "reactions", "legendary_actions")) else ft.Container(height=0)

        def _picker_label(text: str) -> ft.Text:
            return ft.Text(text, size=11, weight=ft.FontWeight.BOLD, color=design.T().text_2)

        stat_fields_col = ft.Column(
            [
                ft.Divider(height=14, color=design.T().border),
                # wrap=True (2026-08-15, bug report Davide: campi tagliati a
                # destra) — la somma delle larghezze fisse dei campi supera
                # quella del dialog su schermi stretti; qui è sicuro perché
                # il contenitore del dialog ha una width esplicita
                # (responsive_dialog_width) e nessun Row non-expand si
                # frappone sopra, quindi il vincolo di larghezza arriva
                # bounded fino a questi Row (vedi regole_flet_api.md, sezione
                # "WRAP=True DENTRO UNA ROW NON-EXPAND").
                ft.Row([type_picker.control, size_picker.control], spacing=8, run_spacing=8, wrap=True),
                align_picker.control,
                ft.Row([ac_tf, hp_tf, hp_formula_tf], spacing=8, run_spacing=8, wrap=True),
                ac_note_tf,
                ft.Row([speed_tf, cr_picker.control, xp_tf], spacing=8, run_spacing=8, wrap=True),
                ft.Row([str_tf, dex_tf, con_tf, int_tf, wis_tf, cha_tf], spacing=6, run_spacing=6, wrap=True),
                senses_tf, languages_tf,
                _picker_label("Vulnerabilità ai danni"), vuln_picker.control,
                _picker_label("Resistenze ai danni"), res_picker.control,
                _picker_label("Immunità ai danni"), imm_picker.control,
                _picker_label("Immunità alle condizioni"), cond_picker.control,
                complex_note,
            ],
            spacing=8,
            visible=src["has_stat_block"],
        )

        def _apply_race_autofill() -> None:
            """
            Auto-riempimento di Tipo creatura/Taglia dalla Razza scelta
            (2026-08-12, bug report Davide) — scrive SOLO se i campi sono
            attualmente vuoti, non sovrascrive mai un valore che il Master
            ha già impostato a mano o da un salvataggio precedente.
            """
            if not stat_cb.value:
                return
            ctype, size = ng.resolve_creature_type_and_size(race_picker.value)
            if not (type_picker.value or "").strip():
                type_picker.value = ctype
            if not (size_picker.value or "").strip():
                size_picker.value = size

        def _on_stat_toggle(e: Any):
            stat_fields_col.visible = bool(stat_cb.value)
            _apply_race_autofill()
            try:
                stat_fields_col.update()
            except RuntimeError:
                pass

        stat_cb.on_change = _on_stat_toggle
        race_picker.on_change = lambda e: _apply_race_autofill()
        if stat_cb.value:  # form aperto già con la spunta attiva (es. modifica)
            _apply_race_autofill()

        def _do_save(e: Any):
            name = (name_tf.value or "").strip()
            if not name:
                error_text.value = "Il nome è obbligatorio."
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return

            kwargs = dict(
                name=name, role=(role_tf.value or "").strip(), notes=notes_tf.value or "",
                tags=(tags_tf.value or "").strip(), has_stat_block=bool(stat_cb.value),
                creature_type=type_picker.value or "", size=size_picker.value or "",
                alignment=align_picker.value or "",
                ac=_int_or(ac_tf.value, 10), ac_note=ac_note_tf.value or "",
                hp_max=_int_or(hp_tf.value, 1), hp_formula=hp_formula_tf.value or "",
                speed=speed_tf.value or "",
                str_score=_int_or(str_tf.value, 10), dex_score=_int_or(dex_tf.value, 10),
                con_score=_int_or(con_tf.value, 10), int_score=_int_or(int_tf.value, 10),
                wis_score=_int_or(wis_tf.value, 10), cha_score=_int_or(cha_tf.value, 10),
                saving_throws=src["saving_throws"], skills=src["skills"],
                damage_vulnerabilities=_list_to_csv(vuln_picker.values),
                damage_resistances=_list_to_csv(res_picker.values),
                damage_immunities=_list_to_csv(imm_picker.values),
                condition_immunities=_list_to_csv(cond_picker.values),
                senses=senses_tf.value or "", languages=languages_tf.value or "", cr=cr_picker.value or "",
                xp=_int_or(xp_tf.value, 0),
                traits=src["traits"], actions=src["actions"],
                reactions=src["reactions"], legendary_actions=src["legendary_actions"],
                source_page=src["source_page"],
                world_id=self._world_id,
                race=race_picker.value or "",
            )

            if is_edit and npc is not None:
                npc.name = kwargs["name"]; npc.role = kwargs["role"]; npc.notes = kwargs["notes"]
                npc.tags = kwargs["tags"]; npc.has_stat_block = kwargs["has_stat_block"]
                npc.creature_type = kwargs["creature_type"]; npc.size = kwargs["size"]
                npc.alignment = kwargs["alignment"]; npc.ac = kwargs["ac"]; npc.ac_note = kwargs["ac_note"]
                npc.hp_max = kwargs["hp_max"]; npc.hp_formula = kwargs["hp_formula"]; npc.speed = kwargs["speed"]
                npc.str_score = kwargs["str_score"]; npc.dex_score = kwargs["dex_score"]
                npc.con_score = kwargs["con_score"]; npc.int_score = kwargs["int_score"]
                npc.wis_score = kwargs["wis_score"]; npc.cha_score = kwargs["cha_score"]
                npc.damage_vulnerabilities = kwargs["damage_vulnerabilities"]
                npc.damage_resistances = kwargs["damage_resistances"]
                npc.damage_immunities = kwargs["damage_immunities"]
                npc.condition_immunities = kwargs["condition_immunities"]
                npc.senses = kwargs["senses"]; npc.languages = kwargs["languages"]; npc.cr = kwargs["cr"]
                npc.xp = kwargs["xp"]
                npc.race = kwargs["race"]
                ok = master_repo.update_npc(npc)
            else:
                ok = master_repo.create_npc(**kwargs) is not None

            if not ok:
                error_text.value = "Errore durante il salvataggio. Riprova."
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return

            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Modifica NPC" if is_edit else "Nuovo NPC"),
            content=ft.Container(
                content=ft.Column(
                    [
                        name_tf, role_tf, race_picker.control, tags_tf, notes_tf,
                        ft.Container(height=6),
                        stat_cb,
                        stat_fields_col,
                        error_text,
                    ],
                    scroll=ft.ScrollMode.AUTO, spacing=8,
                ),
                width=responsive_dialog_width(page, 340), height=480,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Salva" if is_edit else "Crea NPC", icon=ft.Icons.SAVE, on_click=_do_save,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ]),
        )
        page.show_dialog(dlg)
