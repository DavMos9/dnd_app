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

from data.game_data.game_data_loader import parse_monster_xp
from data.models import MasterNpc
from data.repositories import master_repo
from ui.components.monster_picker import (
    creature_entry_dict, load_monsters, show_monster_picker,
    build_stat_block_column, monster_display_name,
)
from ui.theme import title_text, body_text, muted_text, primary_button
from ui.widgets import wrap_dialog_actions
from ui import design

logger = logging.getLogger(__name__)


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


class MasterNpcListView(ft.Column):
    """Lista/ricerca NPC di rubrica + creazione/modifica/eliminazione."""

    def __init__(self):
        super().__init__(expand=True, spacing=0)
        self._page: ft.Page | None = None
        self._npcs: list[MasterNpc] = []
        self._search_query: str = ""
        self._list_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
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
                    ),
                ],
                spacing=10,
            ),
            padding=ft.Padding.all(16),
        )
        body = ft.Container(
            content=self._list_col, expand=True,
            padding=ft.Padding.only(left=16, right=16, bottom=16),
        )
        self.controls.append(header)
        self.controls.append(body)

    def refresh(self):
        self._npcs = master_repo.get_npcs(self._search_query)
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
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.GROUPS_OUTLINED, size=48, color=design.T().border),
                    ft.Container(height=10),
                    muted_text(msg, size=13, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(32),
            alignment=ft.Alignment.CENTER,
        )

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
                    ft.Icon(
                        ft.Icons.SHIELD if npc.has_stat_block else ft.Icons.PERSON_OUTLINE,
                        color=design.T().primary if npc.has_stat_block else design.T().text_3,
                        size=22,
                    ),
                    ft.Container(width=10),
                    ft.Column(
                        [
                            ft.Text(npc.name or "(senza nome)", size=14, weight=ft.FontWeight.BOLD,
                                     color=design.T().text),
                            ft.Row(chips, spacing=6, wrap=True) if chips else ft.Container(height=0),
                            ft.Text(subtitle, size=11, color=design.T().text_3) if subtitle else ft.Container(height=0),
                        ],
                        spacing=3, expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=design.T().text_3, size=18),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(12),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
            border_radius=8,
            on_click=lambda e, n=npc: self._open_detail(n),
            ink=True,
        )

    def _chip(self, text: str, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(text, size=10, color=color, weight=ft.FontWeight.W_600),
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border=ft.Border.all(1, color),
            border_radius=10,
        )

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
            info_rows.append(body_text(npc.notes, size=13, color=design.T().text))

        dlg = ft.AlertDialog(
            title=ft.Text(npc.name or "(senza nome)", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [*info_rows, ft.Divider(height=14, color=design.T().border) if info_rows else ft.Container(height=0),
                     content_col],
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=340, height=480,
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
            title=ft.Text("Elimina NPC?", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Text(
                f"\"{npc.name}\" verrà rimosso dalla rubrica. Se è già presente in un incontro "
                "salvato, il suo nome/CA/PF restano comunque nello storico di quell'incontro.",
                size=12, color=design.T().text_2,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=_do_delete,
                    style=ft.ButtonStyle(bgcolor=design.T().danger, color=design.T().on_primary),
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
                title=ft.Text("Nessun incontro attivo", size=15, weight=ft.FontWeight.BOLD),
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
            value=encounters[0].id, dense=True, border_radius=6,
        )
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=100,
                                keyboard_type=ft.KeyboardType.NUMBER)

        def _do_add(e: Any):
            enc_id = enc_dd.value or encounters[0].id
            master_repo.add_member(
                encounter_id=enc_id, kind="npc", npc_id=npc.id,
                display_name=npc.name, ac=npc.ac, hp_current=npc.hp_max, hp_max=npc.hp_max,
                xp=npc.xp, initiative=_int_or(init_tf.value, 10),
            )
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text(f"Aggiungi \"{npc.name}\" a un incontro", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([enc_dd, ft.Container(height=8), init_tf], tight=True),
                width=300,
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
            show_npc_generator_dialog(page, on_saved=self.refresh)

        dlg = ft.AlertDialog(
            title=ft.Text("Nuovo NPC", size=16, weight=ft.FontWeight.BOLD),
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
            }

        # --- campi anagrafici, sempre visibili ---
        name_tf = ft.TextField(label="Nome *", value=src["name"], dense=True, border_radius=6, autofocus=True)
        role_tf = ft.TextField(label="Ruolo (es. Alleato, Antagonista, Comune)", value=src["role"],
                                dense=True, border_radius=6)
        tags_tf = ft.TextField(label="Tag (separati da virgola)", value=src["tags"], dense=True, border_radius=6)
        notes_tf = ft.TextField(label="Note di ruolo / backstory", value=src["notes"],
                                 multiline=True, min_lines=2, max_lines=6, dense=True, border_radius=6)
        error_text = ft.Text("", size=12, color=design.T().danger)

        # --- toggle + campi statistiche ---
        stat_cb = ft.Checkbox(label="Ha statistiche di combattimento", value=src["has_stat_block"])

        type_tf = ft.TextField(label="Tipo creatura", value=src["creature_type"], dense=True,
                                border_radius=6, width=160)
        size_tf = ft.TextField(label="Taglia", value=src["size"], dense=True, border_radius=6, width=110)
        align_tf = ft.TextField(label="Allineamento", value=src["alignment"], dense=True, border_radius=6)
        ac_tf = ft.TextField(label="CA", value=str(src["ac"]), dense=True, border_radius=6, width=80,
                              keyboard_type=ft.KeyboardType.NUMBER)
        ac_note_tf = ft.TextField(label="Nota CA", value=src["ac_note"], dense=True, border_radius=6)
        hp_tf = ft.TextField(label="PF Massimi", value=str(src["hp_max"]), dense=True, border_radius=6,
                              width=100, keyboard_type=ft.KeyboardType.NUMBER)
        hp_formula_tf = ft.TextField(label="Formula PF (es. 2d8+2)", value=src["hp_formula"],
                                      dense=True, border_radius=6, width=160)
        speed_tf = ft.TextField(label="Velocità", value=src["speed"], dense=True, border_radius=6, width=110)
        cr_tf = ft.TextField(label="GS", value=src["cr"], dense=True, border_radius=6, width=80)
        xp_tf = ft.TextField(label="PE (per Calcolatore Difficoltà)", value=str(src["xp"]), dense=True,
                              border_radius=6, width=180, keyboard_type=ft.KeyboardType.NUMBER)

        def _score_field(label: str, key: str) -> ft.TextField:
            return ft.TextField(label=label, value=str(src[key]), dense=True, border_radius=6,
                                 width=70, keyboard_type=ft.KeyboardType.NUMBER)

        str_tf, dex_tf, con_tf = _score_field("FOR", "str_score"), _score_field("DES", "dex_score"), _score_field("COS", "con_score")
        int_tf, wis_tf, cha_tf = _score_field("INT", "int_score"), _score_field("SAG", "wis_score"), _score_field("CAR", "cha_score")

        senses_tf = ft.TextField(label="Sensi", value=src["senses"], dense=True, border_radius=6)
        languages_tf = ft.TextField(label="Linguaggi", value=src["languages"], dense=True, border_radius=6)
        vuln_tf = ft.TextField(label="Vulnerabilità danni", value=src["damage_vulnerabilities"], dense=True, border_radius=6)
        res_tf = ft.TextField(label="Resistenze danni", value=src["damage_resistances"], dense=True, border_radius=6)
        imm_tf = ft.TextField(label="Immunità danni", value=src["damage_immunities"], dense=True, border_radius=6)
        cond_tf = ft.TextField(label="Immunità condizioni", value=src["condition_immunities"], dense=True, border_radius=6)

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

        stat_fields_col = ft.Column(
            [
                ft.Divider(height=14, color=design.T().border),
                ft.Row([type_tf, size_tf], spacing=8),
                align_tf,
                ft.Row([ac_tf, hp_tf, hp_formula_tf], spacing=8),
                ac_note_tf,
                ft.Row([speed_tf, cr_tf, xp_tf], spacing=8),
                ft.Row([str_tf, dex_tf, con_tf, int_tf, wis_tf, cha_tf], spacing=6),
                senses_tf, languages_tf, vuln_tf, res_tf, imm_tf, cond_tf,
                complex_note,
            ],
            spacing=8,
            visible=src["has_stat_block"],
        )

        def _on_stat_toggle(e: Any):
            stat_fields_col.visible = bool(stat_cb.value)
            try:
                stat_fields_col.update()
            except RuntimeError:
                pass

        stat_cb.on_change = _on_stat_toggle

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
                creature_type=type_tf.value or "", size=size_tf.value or "", alignment=align_tf.value or "",
                ac=_int_or(ac_tf.value, 10), ac_note=ac_note_tf.value or "",
                hp_max=_int_or(hp_tf.value, 1), hp_formula=hp_formula_tf.value or "",
                speed=speed_tf.value or "",
                str_score=_int_or(str_tf.value, 10), dex_score=_int_or(dex_tf.value, 10),
                con_score=_int_or(con_tf.value, 10), int_score=_int_or(int_tf.value, 10),
                wis_score=_int_or(wis_tf.value, 10), cha_score=_int_or(cha_tf.value, 10),
                saving_throws=src["saving_throws"], skills=src["skills"],
                damage_vulnerabilities=vuln_tf.value or "", damage_resistances=res_tf.value or "",
                damage_immunities=imm_tf.value or "", condition_immunities=cond_tf.value or "",
                senses=senses_tf.value or "", languages=languages_tf.value or "", cr=cr_tf.value or "",
                xp=_int_or(xp_tf.value, 0),
                traits=src["traits"], actions=src["actions"],
                reactions=src["reactions"], legendary_actions=src["legendary_actions"],
                source_page=src["source_page"],
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
            title=ft.Text("Modifica NPC" if is_edit else "Nuovo NPC", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [
                        name_tf, role_tf, tags_tf, notes_tf,
                        ft.Container(height=6),
                        stat_cb,
                        stat_fields_col,
                        error_text,
                    ],
                    scroll=ft.ScrollMode.AUTO, spacing=8,
                ),
                width=340, height=480,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Salva" if is_edit else "Crea NPC", icon=ft.Icons.SAVE, on_click=_do_save,
                    style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary),
                ),
            ]),
        )
        page.show_dialog(dlg)
