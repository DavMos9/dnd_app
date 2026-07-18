"""
Tab Esplorazione della scheda personaggio.

Struttura (ListView scrollabile):
  - Percezione Passiva   — valore calcolato (10 + mod SAG + eventuale competenza)
  - Sensi                — scurovisione, altri sensi speciali da razza
  - Velocità             — base + nuoto / scalata / volo (se presenti)
  - Lingue               — dalla scheda proficiencies (type="language"), sola
                        lettura (editing centralizzato in ProfiloTab dal
                        2026-07-17, vedi ProfiloTab._section_altre_competenze)
  - Strumenti            — dalla scheda proficiencies (type="tool"), sola
                        lettura, stesso motivo di Lingue
  - Tiri Salvezza        — griglia compatta 6 valori con indicatore competenza
  - Abilità              — griglia compatta 18 abilità con modificatore calcolato
"""

import flet as ft
import logging
from typing import Any, Callable, cast
from config.settings import *
from data.models import Character, CharacterProficiency, CustomAbility
import data.repositories.character_repo as character_repo
from data.game_data.game_data_loader import game_data
from ui.theme import section_header, muted_text, label_text, show_error_dialog

logger = logging.getLogger(__name__)

_STAT_LABEL: dict[str, str] = {
    "str": "Forza",
    "dex": "Destrezza",
    "con": "Costituzione",
    "int": "Intelligenza",
    "wis": "Saggezza",
    "cha": "Carisma",
}


class EsplorazioneTab(ft.ListView):
    """
    Tab esplorazione: sensi, velocità, lingue (CRUD), strumenti (CRUD),
    tiri salvezza compatti, abilità compatte.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.
    """

    def __init__(self, character: Character, on_refresh: Callable[[], None] | None = None):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None
        # Competenze base di classe (armor_proficiencies/weapon_proficiencies) —
        # self-healing ad ogni apertura tab, stesso principio già usato per
        # sync_borrowed_spellcasting_ability/init_class_resources altrove nel
        # progetto: backfilla i personaggi creati prima di questo fix
        # (2026-07-16), idempotente (dedup per proficiency_type+name).
        if character.class_name:
            character_repo.apply_class_base_proficiencies(character.id, character.class_name)
        self._profs: list[CharacterProficiency] = character_repo.get_proficiencies(character.id)
        # Abilità Speciali custom di esplorazione (2026-07-16, richiesta
        # Davide: abilità concesse dal master o annotazioni aggiuntive —
        # puramente additivo, mai in sostituzione dei tratti razziali/PHB
        # già mostrati sopra in "Sensi e Velocità").
        self._custom_abilities: list[CustomAbility] = character_repo.get_custom_abilities(
            character.id, "esplorazione"
        )
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        c = self.character
        pb = char_prof_bonus(c)

        self._skill_profs: dict[str, bool] = {}
        self._save_profs: set[str] = set()

        for p in self._profs:
            if p.proficiency_type == "skill":
                self._skill_profs[p.name] = p.is_expert
            elif p.proficiency_type in ("save", "saving_throw"):
                self._save_profs.add(p.name)

        # Bonus passivi da talenti (feats.json -> "passive_bonuses", es.
        # Osservatore: +5 Percezione Passiva e Indagare Passivo) — sommati
        # su TUTTI i talenti posseduti che hanno questo campo (dato-driven,
        # nessun nome di talento hardcoded), stesso principio già usato per
        # get_feats_permanent_hp_bonus(). Mai persistiti: ricalcolati sempre
        # a display, stesso pattern di get_effective_speed().
        self._feat_passive_perception_bonus = 0
        self._feat_passive_investigation_bonus = 0
        for p in self._profs:
            if p.proficiency_type != "feat":
                continue
            fd = game_data.get_feat(p.name)
            if not fd:
                continue
            pbo = fd.get("passive_bonuses", {}) or {}
            self._feat_passive_perception_bonus += int(pbo.get("perception", 0) or 0)
            self._feat_passive_investigation_bonus += int(pbo.get("investigation", 0) or 0)

        # IMPORTANTE: modifica in-place — NON riassegnare self.controls
        self.controls.clear()
        self.controls.append(self._section_percezione(c, pb))
        self.controls.append(self._section_indagare_passiva(c, pb))
        self.controls.append(section_header("Sensi e Velocità"))
        self.controls.append(self._section_sensi(c))
        self.controls.append(self._section_lingue_header())
        self.controls.append(self._section_lingue())
        self.controls.append(self._section_strumenti_header())
        self.controls.append(self._section_strumenti())
        self.controls.append(self._section_custom_abilities_header())
        self.controls.append(self._section_custom_abilities())
        self.controls.append(section_header("Tiri Salvezza"))
        self.controls.append(self._section_saves(c, pb))
        self.controls.append(section_header("Abilità"))
        self.controls.append(self._section_skills(c, pb))
        self.controls.append(section_header("Appunti di Sessione"))
        self.controls.append(self._section_notes(c))

    # ------------------------------------------------------------------
    # Percezione passiva
    # ------------------------------------------------------------------

    def _section_percezione(self, c: Character, pb: int) -> ft.Container:
        wis_mod = get_modifier(c.wis_score)
        has_perc = "Percezione" in self._skill_profs
        is_expert = self._skill_profs.get("Percezione", False)

        bonus = pb * (2 if is_expert else 1) if has_perc else 0
        feat_bonus = self._feat_passive_perception_bonus
        calculated = 10 + wis_mod + bonus + feat_bonus
        override = c.passive_perception_override or 0
        passive = override if override > 0 else calculated

        if passive >= 18:
            color = COLOR_ACCENT_GREEN
        elif passive >= 14:
            color = COLOR_ACCENT_BLUE
        else:
            color = COLOR_TEXT_PRIMARY

        indicator = ""
        if is_expert:
            indicator = "★ maestria"
        elif has_perc:
            indicator = "● competente"

        detail = (
            f"Override manuale (calcolato: {calculated})"
            if override > 0
            else (
                f"10 + {wis_mod:+d} SAG"
                + (f" + {bonus} comp." if bonus else "")
                + (f" + {feat_bonus} talento" if feat_bonus else "")
                + (f"  {indicator}" if indicator else "")
            )
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    label_text("Percezione Passiva", 9),
                                    ft.Icon(ft.Icons.EDIT, size=11, color=COLOR_TEXT_MUTED),
                                ],
                                spacing=4,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                str(passive),
                                size=42,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE if override > 0 else color,
                                font_family=FONT_MONO,
                            ),
                            muted_text(detail, size=11, text_align=ft.TextAlign.CENTER),
                        ],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=16, vertical=20),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
            ink=True,
            on_click=lambda e: self._on_edit_passive_perception(calculated),
            tooltip="Modifica Percezione Passiva",
        )

    def _on_edit_passive_perception(self, calculated: int) -> None:
        page = self._page
        if page is None:
            return
        c = self.character
        current_override = c.passive_perception_override or 0

        tf = ft.TextField(
            label="Percezione Passiva (override)",
            value=str(current_override) if current_override > 0 else "",
            hint_text=f"Vuoto = calcolato automaticamente ({calculated})",
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
        )

        def _save(e):
            raw = (tf.value or "").strip()
            if not raw:
                value = 0
            else:
                try:
                    value = max(0, int(raw))
                except ValueError:
                    cast(Any, tf).error_text = "Inserisci un numero intero"
                    tf.update()
                    return
            if not character_repo.update_passive_perception_override(c.id, value):
                show_error_dialog(page, "Errore nel salvataggio della Percezione Passiva.")
                return
            c.passive_perception_override = value
            page.pop_dialog()
            self._refresh()

        def _reset(e):
            if not character_repo.update_passive_perception_override(c.id, 0):
                show_error_dialog(page, "Errore nel salvataggio della Percezione Passiva.")
                return
            c.passive_perception_override = 0
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text("Percezione Passiva"),
            content=ft.Column(
                [
                    muted_text(f"Valore calcolato dal PHB: {calculated}", 12),
                    tf,
                ],
                spacing=12,
                tight=True,
            ),
            actions=[
                ft.TextButton("Ripristina calcolato", on_click=_reset),
                ft.TextButton("Annulla", on_click=_cancel),
                ft.ElevatedButton("Applica", on_click=_save),
            ],
        )
        page.show_dialog(dlg)

    def _section_indagare_passiva(self, c: Character, pb: int) -> ft.Container:
        """
        Indagare Passivo (10 + mod INT + eventuale competenza + bonus da
        talenti, es. Osservatore: +5) — sola lettura, nessun override
        manuale (a differenza della Percezione Passiva): aggiunta insieme al
        fix del talento Osservatore (2026-07-16), che è il primo e unico
        caso PHB in cui questo valore serve davvero in questa app. Se in
        futuro servisse un override anche qui, andrebbe aggiunta una nuova
        colonna dedicata (stesso pattern di passive_perception_override).
        """
        int_mod = get_modifier(c.int_score)
        has_ind = "Indagare" in self._skill_profs
        is_expert = self._skill_profs.get("Indagare", False)

        bonus = pb * (2 if is_expert else 1) if has_ind else 0
        feat_bonus = self._feat_passive_investigation_bonus
        calculated = 10 + int_mod + bonus + feat_bonus

        indicator = ""
        if is_expert:
            indicator = "★ maestria"
        elif has_ind:
            indicator = "● competente"

        detail = (
            f"10 + {int_mod:+d} INT"
            + (f" + {bonus} comp." if bonus else "")
            + (f" + {feat_bonus} talento" if feat_bonus else "")
            + (f"  {indicator}" if indicator else "")
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            label_text("Indagare Passivo", 9),
                            ft.Text(
                                str(calculated),
                                size=30,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_PRIMARY,
                                font_family=FONT_MONO,
                            ),
                            muted_text(detail, size=11, text_align=ft.TextAlign.CENTER),
                        ],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            border=ft.Border(
                top=ft.BorderSide(2, COLOR_BORDER),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Sensi e Velocità
    # ------------------------------------------------------------------

    def _section_sensi(self, c: Character) -> ft.Container:
        race_info = game_data.get_resolved_race(c.race, c.subrace)
        darkvision = race_info.get("darkvision", 0)

        rows: list[ft.Control] = []

        # Velocità a piedi effettiva: include il bonus dinamico di classe
        # non equipaggiato (Monaco Movimento Senza Armatura, Barbaro
        # Movimento Veloce — Categoria B, audit 2026-07-09). Le velocità
        # speciali sotto (Nuoto/Scalata/Volo) restano al valore base: il
        # PHB descrive entrambe le capacità come bonus alla velocità di
        # movimento a piedi, non alle velocità speciali di razza.
        effective_walk_speed = character_repo.get_effective_speed(c)
        speed_note = "" if effective_walk_speed == (c.speed or 9) else f" (base {c.speed or 9:g} m)"
        rows.append(self._editable_info_row(
            "Camminata", f"{effective_walk_speed:g} m{speed_note}",
            on_click=self._on_edit_speed,
        ))
        for trait in race_info.get("traits", []):
            t_lower = (trait.get("name", "") + " " + trait.get("description", "")).lower()
            if "nuoto" in t_lower or "swim" in t_lower:
                rows.append(self._info_row("Nuoto", f"{c.speed or 9:g} m"))
            elif "scalat" in t_lower or "climb" in t_lower:
                rows.append(self._info_row("Scalata", f"{c.speed or 9:g} m"))
            elif "volo" in t_lower or "fly" in t_lower:
                rows.append(self._info_row("Volo", f"{c.speed or 9:g} m"))

        rows.append(ft.Container(height=8))

        if darkvision:
            rows.append(self._info_row("Scurovisione", f"{darkvision} m"))
        else:
            rows.append(self._info_row("Scurovisione", "Nessuna"))

        rows.append(
            muted_text(
                "Per sensi aggiuntivi concessi dal master, usa \"Abilità Speciali\" più sotto.",
                11,
            )
        )

        return self._compact_card(rows)

    def _on_edit_speed(self) -> None:
        page = self._page
        if page is None:
            return
        c = self.character

        tf = ft.TextField(
            label="Velocità base a piedi (metri)",
            value=f"{c.speed or 9:g}",
            hint_text="es. 9, 7.5, 10.5",
            autofocus=True,
        )

        def _save(e):
            raw = (tf.value or "").strip().replace(",", ".")
            try:
                value = max(0.0, float(raw))
            except ValueError:
                cast(Any, tf).error_text = "Inserisci un numero valido (es. 9 oppure 7.5)"
                tf.update()
                return
            if not character_repo.update_speed(c.id, value):
                from ui.theme import show_error_dialog
                show_error_dialog(page, "Errore nel salvataggio della velocità.")
                return
            c.speed = value
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text("Modifica Velocità"),
            content=ft.Column(
                [
                    muted_text(
                        "Velocità base standard di camminata (bonus di classe come "
                        "Movimento Veloce/Senza Armatura si applicano automaticamente sopra "
                        "a questo valore, quando attivi).",
                        11,
                    ),
                    tf,
                ],
                spacing=12,
                tight=True,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=_cancel),
                ft.ElevatedButton("Applica", on_click=_save),
            ],
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Lingue — sola lettura (editing centralizzato in ProfiloTab, vedi
    # ProfiloTab._section_altre_competenze — decisione Davide 2026-07-17:
    # "Tutto in Profilo")
    # ------------------------------------------------------------------

    def _section_lingue_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=3, height=14, bgcolor=COLOR_ACCENT_CRIMSON, border_radius=1),
                    ft.Container(width=8),
                    ft.Text(
                        "LINGUE",
                        size=10,
                        color=COLOR_TEXT_SECONDARY,
                        weight=ft.FontWeight.BOLD,
                        style=ft.TextStyle(letter_spacing=2),
                    ),
                    ft.Container(width=8),
                    ft.Container(expand=True, height=1, bgcolor=COLOR_BORDER),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            margin=ft.Margin.only(bottom=0, top=4),
        )

    def _section_lingue(self) -> ft.Container:
        lingue = [p for p in self._profs if p.proficiency_type == "language"]

        if not lingue:
            rows: list[ft.Control] = [muted_text("Nessuna lingua registrata — usa + Aggiungi", 12)]
        else:
            rows = []
            for p in sorted(lingue, key=lambda x: x.name):
                rows.append(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.LANGUAGE, size=14, color=COLOR_TEXT_MUTED),
                            ft.Text(
                                p.name,
                                size=13,
                                color=COLOR_TEXT_PRIMARY,
                                expand=True,
                            ),
                        ],
                        spacing=6,
                    )
                )

        return self._compact_card(rows)

    # ------------------------------------------------------------------
    # Strumenti — sola lettura (editing centralizzato in ProfiloTab, vedi
    # ProfiloTab._section_altre_competenze — decisione Davide 2026-07-17)
    # ------------------------------------------------------------------

    def _section_strumenti_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=3, height=14, bgcolor=COLOR_ACCENT_CRIMSON, border_radius=1),
                    ft.Container(width=8),
                    ft.Text(
                        "STRUMENTI",
                        size=10,
                        color=COLOR_TEXT_SECONDARY,
                        weight=ft.FontWeight.BOLD,
                        style=ft.TextStyle(letter_spacing=2),
                    ),
                    ft.Container(width=8),
                    ft.Container(expand=True, height=1, bgcolor=COLOR_BORDER),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            margin=ft.Margin.only(bottom=0, top=4),
        )

    def _section_strumenti(self) -> ft.Container:
        strumenti = [p for p in self._profs if p.proficiency_type == "tool"]

        if not strumenti:
            rows: list[ft.Control] = [muted_text("Nessuno strumento registrato — usa + Aggiungi", 12)]
        else:
            rows = []
            for s in sorted(strumenti, key=lambda x: x.name):
                indicator = "★" if s.is_expert else "●"
                ind_color = COLOR_ACCENT_BLUE if s.is_expert else COLOR_ACCENT_CRIMSON
                lvl_text = "maestria" if s.is_expert else "competenza"
                rows.append(
                    ft.Row(
                        [
                            ft.Text(indicator, size=12, color=ind_color, width=16),
                            ft.Text(
                                s.name,
                                size=13,
                                color=COLOR_TEXT_PRIMARY,
                                expand=True,
                            ),
                            muted_text(lvl_text, 11),
                        ],
                        spacing=6,
                    )
                )

        return self._compact_card(rows)

    # ------------------------------------------------------------------
    # Abilità Speciali custom (2026-07-16) — voci additive, es. concesse
    # dal master; non modificano mai i tratti razziali/PHB già mostrati
    # sopra in "Sensi e Velocità".
    # ------------------------------------------------------------------

    def _section_custom_abilities_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=3, height=14, bgcolor=COLOR_ACCENT_CRIMSON, border_radius=1),
                    ft.Container(width=8),
                    ft.Text(
                        "ABILITÀ SPECIALI",
                        size=10, color=COLOR_TEXT_SECONDARY, weight=ft.FontWeight.BOLD,
                        style=ft.TextStyle(letter_spacing=2),
                    ),
                    ft.Container(width=8),
                    ft.Container(expand=True, height=1, bgcolor=COLOR_BORDER),
                    ft.Container(width=8),
                    ft.TextButton(
                        "+ Aggiungi",
                        on_click=lambda e: self._on_add_custom_ability(),
                        style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            margin=ft.Margin.only(bottom=0, top=4),
        )

    def _section_custom_abilities(self) -> ft.Container:
        if not self._custom_abilities:
            rows: list[ft.Control] = [
                muted_text(
                    "Nessuna abilità speciale di esplorazione registrata — usa "
                    "«+ Aggiungi» per annotare capacità custom concesse dal master.",
                    12,
                )
            ]
        else:
            rows = [self._custom_ability_row(ab) for ab in self._custom_abilities]

        return self._compact_card(rows)

    def _custom_ability_row(self, ab: CustomAbility) -> ft.Container:
        # 2026-07-17, bug report Davide (punto 1, stesso fix gemello di
        # combattimento_tab.py): mostrata per intero, non più troncata.
        full_desc = ab.description.strip()
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(ab.name, size=13, color=COLOR_TEXT_PRIMARY,
                                    weight=ft.FontWeight.W_600),
                            muted_text(full_desc, 11) if full_desc else ft.Container(height=0),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.EDIT, icon_size=16, icon_color=COLOR_TEXT_MUTED,
                        tooltip="Modifica",
                        on_click=lambda e, a=ab: self._on_edit_custom_ability(a),
                        padding=ft.Padding.all(2),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=COLOR_ACCENT_CRIMSON,
                        tooltip="Elimina",
                        on_click=lambda e, a=ab: self._on_delete_custom_ability(a),
                        padding=ft.Padding.all(2),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=4,
            ),
            border=ft.Border(bottom=ft.BorderSide(1, COLOR_BORDER)),
            padding=ft.Padding.only(bottom=8),
        )

    def _on_add_custom_ability(self) -> None:
        self._open_custom_ability_dialog(None)

    def _on_edit_custom_ability(self, ab: CustomAbility) -> None:
        self._open_custom_ability_dialog(ab)

    def _open_custom_ability_dialog(self, ab: CustomAbility | None) -> None:
        page = self._page
        if page is None:
            return

        tf_name = ft.TextField(
            label="Nome", value=(ab.name if ab else ""), autofocus=True,
        )
        tf_desc = ft.TextField(
            label="Descrizione", value=(ab.description if ab else ""),
            multiline=True, min_lines=3, max_lines=8,
        )

        def _save(e):
            name = (tf_name.value or "").strip()
            if not name:
                cast(Any, tf_name).error_text = "Inserisci il nome dell'abilità"
                tf_name.update()
                return
            desc = tf_desc.value or ""
            if ab is None:
                new_id = character_repo.create_custom_ability(
                    self.character.id, "esplorazione", name, desc
                )
                if not new_id:
                    show_error_dialog(page, "Errore nel salvataggio dell'abilità.")
                    return
            else:
                if not character_repo.update_custom_ability(ab.id, name, desc):
                    show_error_dialog(page, "Errore nel salvataggio dell'abilità.")
                    return
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text("Modifica Abilità Speciale" if ab else "Nuova Abilità Speciale"),
            content=ft.Column([tf_name, tf_desc], spacing=12, tight=True, width=340),
            actions=[
                ft.TextButton("Annulla", on_click=_cancel),
                ft.ElevatedButton("Salva", on_click=_save),
            ],
        )
        page.show_dialog(dlg)

    def _on_delete_custom_ability(self, ab: CustomAbility) -> None:
        page = self._page
        if page is None:
            return

        def _confirm(e):
            if not character_repo.delete_custom_ability(ab.id):
                show_error_dialog(page, "Errore nell'eliminazione dell'abilità.")
                return
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text("Elimina Abilità Speciale"),
            content=ft.Text(f'Eliminare "{ab.name}" dalla scheda?'),
            actions=[
                ft.TextButton("Annulla", on_click=_cancel),
                ft.ElevatedButton(
                    "Elimina", on_click=_confirm,
                    style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff"),
                ),
            ],
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Tiri Salvezza (griglia compatta)
    # ------------------------------------------------------------------

    def _section_saves(self, c: Character, pb: int) -> ft.Container:
        scores = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        cells: list[ft.Control] = []
        for key, full_name, abbr in zip(ABILITY_KEYS, ABILITY_SCORES, ABILITY_ABBR):
            score = scores[key]
            base_mod = get_modifier(score)
            prof = full_name in self._save_profs
            total = base_mod + (pb if prof else 0)
            total_str = f"+{total}" if total >= 0 else str(total)

            indicator_color = COLOR_ACCENT_CRIMSON if prof else COLOR_BORDER
            text_color = COLOR_TEXT_PRIMARY if prof else COLOR_TEXT_MUTED

            cells.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=6, height=6,
                                        bgcolor=indicator_color,
                                        border_radius=3,
                                    ),
                                    ft.Text(
                                        abbr, size=9, color=COLOR_TEXT_SECONDARY,
                                        weight=ft.FontWeight.BOLD,
                                        style=ft.TextStyle(letter_spacing=1),
                                    ),
                                ],
                                spacing=4,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                total_str,
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=text_color,
                                font_family=FONT_MONO,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                    ),
                    expand=True,
                    bgcolor=COLOR_BG_SECONDARY if prof else COLOR_BG_CARD,
                    padding=ft.Padding.symmetric(horizontal=4, vertical=8),
                    border=ft.Border.all(1, COLOR_BORDER),
                    border_radius=4,
                )
            )

        return ft.Container(
            content=ft.Row(cells, spacing=4),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Abilità (griglia compatta 2 colonne)
    # ------------------------------------------------------------------

    def _section_skills(self, c: Character, pb: int) -> ft.Container:
        scores = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        skill_items: list[ft.Control] = []
        for skill_name, stat_key in sorted(SKILLS.items()):
            score = scores.get(stat_key, 10)
            base_mod = get_modifier(score)
            is_expert = self._skill_profs.get(skill_name, False) if skill_name in self._skill_profs else None
            is_prof = skill_name in self._skill_profs

            if is_expert:
                bonus = pb * 2
                indicator = "★"
                ind_color = COLOR_ACCENT_BLUE
            elif is_prof:
                bonus = pb
                indicator = "●"
                ind_color = COLOR_ACCENT_CRIMSON
            else:
                bonus = 0
                indicator = "○"
                ind_color = COLOR_BORDER

            total = base_mod + bonus
            total_str = f"+{total}" if total >= 0 else str(total)
            abbr = ABILITY_ABBR[ABILITY_KEYS.index(stat_key)]

            skill_items.append(
                ft.Row(
                    [
                        ft.Text(indicator, size=11, color=ind_color, width=14),
                        ft.Text(
                            total_str,
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY if is_prof else COLOR_TEXT_MUTED,
                            font_family=FONT_MONO,
                            width=32,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Text(
                            skill_name,
                            size=12,
                            color=COLOR_TEXT_PRIMARY if is_prof else COLOR_TEXT_SECONDARY,
                            expand=True,
                        ),
                        muted_text(abbr, 10),
                    ],
                    spacing=4,
                )
            )

        mid = (len(skill_items) + 1) // 2
        col_left = skill_items[:mid]
        col_right = skill_items[mid:]

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(cast(list[ft.Control], col_left), spacing=6, expand=True),
                    ft.Container(width=1, bgcolor=COLOR_BORDER),
                    ft.Column(cast(list[ft.Control], col_right), spacing=6, expand=True),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # NOTA: Lingue/Strumenti sono sola lettura da qui (2026-07-17) —
    # l'editing (aggiunta con autofill da catalogo, rimozione) vive ora in
    # ProfiloTab._open_add_competenza_dialog() / ProfiloTab._on_delete_
    # proficiency(), decisione di Davide "Tutto in Profilo". Il metodo
    # _on_delete_proficiency che viveva qui è stato rimosso (nessun
    # chiamante residuo in questo file).

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _info_row(self, label: str, value: str) -> ft.Row:
        return ft.Row(
            [
                muted_text(label, 12),
                ft.Text(
                    value, size=13, color=COLOR_TEXT_PRIMARY,
                    weight=ft.FontWeight.BOLD, font_family=FONT_BODY,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def _editable_info_row(self, label: str, value: str, on_click: Callable[[], None]) -> ft.Container:
        """Riga info con affordance di modifica (icona matita + tap)."""
        return ft.Container(
            content=ft.Row(
                [
                    muted_text(label, 12),
                    ft.Row(
                        [
                            ft.Text(
                                value, size=13, color=COLOR_TEXT_PRIMARY,
                                weight=ft.FontWeight.BOLD, font_family=FONT_BODY,
                            ),
                            ft.Icon(ft.Icons.EDIT, size=12, color=COLOR_TEXT_MUTED),
                        ],
                        spacing=4,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            on_click=lambda e: on_click(),
            ink=True,
            border_radius=4,
            tooltip=f"Modifica {label}",
        )

    def _compact_card(self, rows: list[ft.Control]) -> ft.Container:
        return ft.Container(
            content=ft.Column(rows, spacing=6),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Appunti di sessione
    # ------------------------------------------------------------------

    def _section_notes(self, c: Character) -> ft.Container:
        """
        Campo di testo libero per appunti al volo durante la sessione.
        Salva automaticamente quando il campo perde il focus.
        """
        notes_field = ft.TextField(
            value=c.session_notes or "",
            multiline=True,
            min_lines=4,
            max_lines=12,
            hint_text="Scrivi qui note veloci: tiri da ricordare, promemoria abilità, "
                      "effetti attivi, info ricevute dal DM…",
            hint_style=ft.TextStyle(size=12, color=COLOR_TEXT_MUTED),
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            expand=True,
        )

        def on_blur(ev: ft.Event[ft.TextField]) -> None:
            notes = notes_field.value or ""
            if notes != (c.session_notes or ""):
                character_repo.update_session_notes(c.id, notes)
                c.session_notes = notes

        notes_field.on_blur = on_blur

        return ft.Container(
            content=ft.Column(
                [
                    muted_text("Le note vengono salvate automaticamente quando esci dal campo.", 11),
                    notes_field,
                ],
                spacing=6,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.all(12),
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        if self.character.class_name:
            character_repo.apply_class_base_proficiencies(self.character.id, self.character.class_name)
        self._profs = character_repo.get_proficiencies(self.character.id)
        self._custom_abilities = character_repo.get_custom_abilities(self.character.id, "esplorazione")
        self._build()  # già chiama controls.clear() internamente
        try:
            self.update()
        except RuntimeError:
            pass
        if self._on_refresh:
            self._on_refresh()
