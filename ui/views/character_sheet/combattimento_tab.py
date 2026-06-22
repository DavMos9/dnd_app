"""
Tab Combattimento della scheda personaggio.

Struttura (ListView scrollabile):
  - HP Tracker        — barra HP colorata, danno/cura, HP temp,
                        tiri salvezza morte (sempre visibili)
  - Statistiche       — CA, Velocità, Iniziativa (calcolata), Ispirazione toggle
  - Azioni Turno      — Azione / Azione Bonus / Reazione + tracker movimento
                        Nuovo Turno (snapshot per undo) + Annulla
  - Tiri Salvezza & Abilità — riferimento rapido con competenze evidenziate
  - Armi Equipaggiate — nome, danno, bonus al tiro, proprietà, note magiche
  - Magia             — caratteristica, CD, bonus attacco, slot BG3-style,
                        incantesimi preparati per livello
  - Dadi Vita         — cerchietti + Riposo Breve
  - Riposo Lungo      — ripristina tutto

Nota movimento: stored come int (metri interi). Il passo 1.5m usa delta=2.
"""

import flet as ft
import json
import logging
from typing import cast
from config.settings import *
from data.models import Character, SpellSlot, CharacterProficiency, Weapon, KnownSpell
import data.repositories.character_repo as character_repo
from ui.theme import section_header

logger = logging.getLogger(__name__)

# Nomi ordinali per i livelli slot
_SLOT_NAMES = ["1°", "2°", "3°", "4°", "5°", "6°", "7°", "8°", "9°"]


class CombattimentoTab(ft.ListView):
    """
    Tab combattimento: HP, azioni turno, slot, dadi vita, riposi.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.
    """

    def __init__(self, character: Character):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._page: ft.Page | None = None
        self._slots: list[SpellSlot] = character_repo.get_spell_slots(character.id)
        self._profs: list[CharacterProficiency] = character_repo.get_proficiencies(character.id)
        self._weapons: list[Weapon] = character_repo.get_weapons(character.id)
        self._prepared: list[KnownSpell] = character_repo.get_prepared_spells(character.id)
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        c = self.character
        self.controls = [
            self._section_hp(c),
            section_header("Statistiche di Combattimento"),
            self._section_stats(c),
            section_header("Azioni Turno"),
            self._section_turn(c),
            section_header("Tiri Salvezza e Abilità"),
            self._section_saves_skills(c),
            section_header("Armi Equipaggiate"),
            self._section_weapons(),
            section_header("Magia"),
            self._section_spell_slots(c),
            section_header("Dadi Vita"),
            self._section_hit_dice(c),
            self._section_riposo_lungo(c),
        ]

    # ------------------------------------------------------------------
    # Sezione HP
    # ------------------------------------------------------------------

    def _section_hp(self, c: Character) -> ft.Container:
        hp_ratio = (c.hp_current / c.hp_max) if c.hp_max > 0 else 0.0
        hp_ratio = max(0.0, min(1.0, hp_ratio))

        if hp_ratio > 0.5:
            hp_color = COLOR_HP_FULL
        elif hp_ratio > 0.25:
            hp_color = COLOR_HP_MID
        else:
            hp_color = COLOR_HP_LOW

        hp_label = ft.Row(
            [
                ft.Text(str(c.hp_current), size=38, weight=ft.FontWeight.BOLD,
                        color=hp_color, font_family=FONT_MONO),
                ft.Text(f" / {c.hp_max}", size=18, color=COLOR_TEXT_MUTED,
                        font_family=FONT_MONO),
                ft.Container(expand=True),
                ft.Column(
                    [
                        ft.Text("HP TEMP", size=9, color=COLOR_TEXT_MUTED,
                                weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"+{c.hp_temp}" if c.hp_temp else "—",
                            size=14, font_family=FONT_MONO,
                            color=COLOR_ACCENT_BLUE if c.hp_temp else COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=1,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.END,
            spacing=0,
        )

        bar = ft.ProgressBar(
            value=hp_ratio,
            color=hp_color,
            bgcolor=COLOR_BG_SECONDARY,
            height=12,
            border_radius=6,
        )

        btn_damage = ft.ElevatedButton(
            "− Danno",
            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
            on_click=self._on_damage_click,
            expand=True,
            style=ft.ButtonStyle(
                bgcolor=COLOR_HP_LOW, color="#ffffff",
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )
        btn_heal = ft.ElevatedButton(
            "+ Cura",
            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
            on_click=self._on_heal_click,
            expand=True,
            style=ft.ButtonStyle(
                bgcolor=COLOR_HP_FULL, color="#ffffff",
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )
        edit_btn = ft.TextButton(
            "✎ HP Max / Temp",
            on_click=self._on_edit_hp_click,
            style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
        )

        rows: list[ft.Control] = [
            hp_label,
            ft.Container(height=6),
            bar,
            ft.Container(height=10),
            ft.Row([btn_damage, ft.Container(width=8), btn_heal], spacing=0),
            ft.Row([edit_btn], alignment=ft.MainAxisAlignment.END),
            ft.Divider(color=COLOR_BORDER),
            self._build_death_saves(c),
        ]

        return ft.Container(
            content=ft.Column(rows, spacing=4),
            bgcolor=COLOR_BG_CARD,
            padding=16,
            border=ft.Border(
                top=ft.BorderSide(3, hp_color),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _build_death_saves(self, c: Character) -> ft.Column:
        """
        Tiri salvezza contro morte — sempre visibili.
        Grigi e inattivi quando HP > 0; colorati e interattivi quando HP = 0.
        """
        active = (c.hp_current <= 0)
        succ_color = COLOR_HP_FULL if active else COLOR_TEXT_MUTED
        fail_color = COLOR_HP_LOW  if active else COLOR_TEXT_MUTED
        label_color = COLOR_TEXT_MUTED

        def _circles(filled: int, color: str, on_click_fn) -> ft.Row:
            chips = []
            for i in range(3):
                is_filled = i < filled
                chips.append(ft.Container(
                    content=ft.Text(
                        "●" if is_filled else "○",
                        size=20,
                        color=color if is_filled else COLOR_BG_SECONDARY,
                    ),
                    on_click=(lambda e, n=i + 1: on_click_fn(n)) if active else None,
                    tooltip=(f"Imposta a {i + 1}" if active else "Attivo solo a 0 HP"),
                    border_radius=12,
                    ink=active,
                    padding=ft.Padding.all(2),
                ))
            return ft.Row(chips, spacing=4)

        def set_success(n: int):
            c.death_saves_success = n if c.death_saves_success != n else n - 1
            character_repo.update_death_saves(c.id, c.death_saves_success, c.death_saves_failure)
            self._refresh()

        def set_failure(n: int):
            c.death_saves_failure = n if c.death_saves_failure != n else n - 1
            character_repo.update_death_saves(c.id, c.death_saves_success, c.death_saves_failure)
            self._refresh()

        status_label = (
            ft.Text("PERSONAGGIO INCONSCIO", size=9, color=COLOR_HP_LOW,
                    weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
            if active else
            ft.Text("TIRI SALVEZZA MORTE", size=9, color=label_color,
                    weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
        )

        return ft.Column(
            [
                status_label,
                ft.Row([
                    ft.Text("Successi:", size=12, color=succ_color, width=80),
                    _circles(c.death_saves_success, succ_color, set_success),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Text("Fallimenti:", size=12, color=fail_color, width=80),
                    _circles(c.death_saves_failure, fail_color, set_failure),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            spacing=4,
        )

    # ------------------------------------------------------------------
    # HP dialogs
    # ------------------------------------------------------------------

    def _on_damage_click(self, e):
        if not self._page:
            return
        page = self._page
        field = ft.TextField(
            label="Quantità danno", keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True, text_align=ft.TextAlign.CENTER,
            text_style=ft.TextStyle(size=16, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_HP_LOW,
            bgcolor=COLOR_BG_CARD,
        )

        def apply(ev):
            if page is None:
                return
            try:
                amt = max(0, int(field.value or 0))
            except ValueError:
                return
            c = self.character
            # Il danno assorbe prima gli HP temporanei
            if c.hp_temp and c.hp_temp > 0:
                absorbed = min(c.hp_temp, amt)
                c.hp_temp -= absorbed
                amt -= absorbed
            c.hp_current = max(0, c.hp_current - amt)
            character_repo.update_hp(c.id, c.hp_current, c.hp_temp)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Applica Danno", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_HP_LOW),
            content=ft.Column([field], width=240, spacing=0),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Applica", on_click=apply,
                                  style=ft.ButtonStyle(bgcolor=COLOR_HP_LOW, color="#ffffff",
                                                       shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    def _on_heal_click(self, e):
        if not self._page:
            return
        page = self._page
        field = ft.TextField(
            label="Quantità cura", keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True, text_align=ft.TextAlign.CENTER,
            text_style=ft.TextStyle(size=16, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_HP_FULL,
            bgcolor=COLOR_BG_CARD,
        )

        def apply(ev):
            if page is None:
                return
            try:
                amt = max(0, int(field.value or 0))
            except ValueError:
                return
            c = self.character
            c.hp_current = min(c.hp_max, c.hp_current + amt)
            character_repo.update_hp(c.id, c.hp_current, c.hp_temp)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Applica Cura", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_HP_FULL),
            content=ft.Column([field], width=240, spacing=0),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Cura", on_click=apply,
                                  style=ft.ButtonStyle(bgcolor=COLOR_HP_FULL, color="#ffffff",
                                                       shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    def _on_edit_hp_click(self, e):
        page = self._page
        if page is None:
            return
        c = self.character

        def _num_field(label: str, value: int) -> ft.TextField:
            return ft.TextField(
                label=label, value=str(value),
                keyboard_type=ft.KeyboardType.NUMBER,
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
                bgcolor=COLOR_BG_CARD,
            )

        f_max  = _num_field("HP Max", c.hp_max)
        f_curr = _num_field("HP Attuali", c.hp_current)
        f_temp = _num_field("HP Temporanei", c.hp_temp or 0)

        def save(ev):
            if page is None:
                return
            try:
                c.hp_max     = max(1, int(f_max.value or c.hp_max))
                c.hp_current = max(0, min(c.hp_max, int(f_curr.value or c.hp_current)))
                c.hp_temp    = max(0, int(f_temp.value or 0))
            except ValueError:
                return
            character_repo.update_hp(c.id, c.hp_current, c.hp_temp)
            character_repo.update(c)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Modifica HP", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_TEXT_TITLE),
            content=ft.Column([f_max, f_curr, f_temp], spacing=10, width=300),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Salva", on_click=save,
                                  style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                                       shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Statistiche di combattimento
    # ------------------------------------------------------------------

    def _section_stats(self, c: Character) -> ft.Container:
        initiative = get_modifier(c.dex_score)
        init_str = f"+{initiative}" if initiative >= 0 else str(initiative)

        def _stat_box(label: str, value: str, accent: str = COLOR_TEXT_PRIMARY) -> ft.Container:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(label, size=9, color=COLOR_TEXT_MUTED,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                        ft.Text(value, size=22, color=accent,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER,
                                font_family=FONT_MONO),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=COLOR_BG_CARD,
                padding=ft.Padding.symmetric(vertical=10, horizontal=8),
                border=ft.Border.all(1, COLOR_BORDER),
                border_radius=6,
                expand=True,
            )

        ispir_active = bool(c.inspiration)
        ispir_color  = COLOR_ACCENT_AMBER if ispir_active else COLOR_TEXT_MUTED
        ispir_icon   = ft.Icons.STAR if ispir_active else ft.Icons.STAR_BORDER
        ispir_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text("ISPIR.", size=9, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Icon(ispir_icon, size=22, color=ispir_color),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(vertical=10, horizontal=8),
            border=ft.Border.all(1, ispir_color),
            border_radius=6,
            expand=True,
            on_click=self._toggle_inspiration,
            ink=True,
            tooltip="Attiva / disattiva ispirazione",
        )

        # Box CA cliccabile — mostra bonus temporaneo se attivo
        ca_bonus = c.ca_bonus
        ca_total = c.ac + ca_bonus
        ca_label = "CA" if ca_bonus == 0 else f"CA (+{ca_bonus})" if ca_bonus > 0 else f"CA ({ca_bonus})"
        ca_color = COLOR_ACCENT_BLUE if ca_bonus > 0 else (COLOR_ACCENT_CRIMSON if ca_bonus < 0 else COLOR_TEXT_PRIMARY)
        ca_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text(ca_label, size=9, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text(str(ca_total), size=22, color=ca_color,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                            font_family=FONT_MONO),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(vertical=10, horizontal=8),
            border=ft.Border.all(2 if ca_bonus != 0 else 1,
                                 ca_color if ca_bonus != 0 else COLOR_BORDER),
            border_radius=6,
            expand=True,
            on_click=self._on_ca_bonus_click,
            ink=True,
            tooltip="Clicca per aggiungere/rimuovere bonus CA temporaneo",
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ca_box,
                            _stat_box("VELOCITÀ", f"{c.speed}m"),
                            _stat_box("INIZIAT.", init_str, COLOR_ACCENT_BLUE),
                            ispir_box,
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            ft.TextButton(
                                "✎ Modifica CA / Velocità",
                                on_click=self._on_edit_stats_click,
                                style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                            )
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=6,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=12,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _toggle_inspiration(self, e):
        self.character.inspiration = not self.character.inspiration
        character_repo.update(self.character)
        self._refresh()

    def _on_edit_stats_click(self, e):
        page = self._page
        if not page:
            return
        c = self.character
        f_ac    = ft.TextField(label="Classe Armatura (CA)", value=str(c.ac),
                               keyboard_type=ft.KeyboardType.NUMBER,
                               text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                               border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
                               bgcolor=COLOR_BG_CARD)
        f_speed = ft.TextField(label="Velocità (m)", value=str(c.speed),
                               keyboard_type=ft.KeyboardType.NUMBER,
                               text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                               border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
                               bgcolor=COLOR_BG_CARD)

        def save(ev):
            if page is None:
                return
            try:
                c.ac    = max(0, int(f_ac.value or c.ac))
                c.speed = max(0, int(f_speed.value or c.speed))
            except ValueError:
                return
            character_repo.update(c)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Modifica Statistiche", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_TEXT_TITLE),
            content=ft.Column([f_ac, f_speed], spacing=10, width=280),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Salva", on_click=save,
                                  style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                                       shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    def _on_ca_bonus_click(self, e):
        """Dialog per aggiungere/modificare/rimuovere il bonus CA temporaneo."""
        page = self._page
        if not page:
            return
        c = self.character
        cur_bonus = c.ca_bonus

        f_bonus = ft.TextField(
            label="Bonus CA temporaneo (positivo o negativo)",
            value=str(cur_bonus),
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=16, color=COLOR_TEXT_PRIMARY,
                                    font_family=FONT_MONO),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            autofocus=True,
        )

        info_text = ft.Text(
            f"CA base (armatura): {c.ac}   |   CA totale con bonus: {c.ac + cur_bonus}",
            size=11, color=COLOR_TEXT_MUTED,
        )

        def save(ev):
            if page is None:
                return
            try:
                new_bonus = int(f_bonus.value or 0)
            except ValueError:
                new_bonus = 0
            character_repo.update_ca_bonus(c.id, new_bonus)
            c.ca_bonus = new_bonus
            page.pop_dialog()
            self._refresh()

        def reset(ev):
            if page is None:
                return
            character_repo.update_ca_bonus(c.id, 0)
            c.ca_bonus = 0
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Bonus CA Temporaneo", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column([
                info_text,
                f_bonus,
                ft.Text(
                    "Usato per incantesimi (es. Scudo), reazioni o condizioni temporanee.\n"
                    "Resetta a 0 a fine round o quando l'effetto termina.",
                    size=11, color=COLOR_TEXT_MUTED,
                ),
            ], spacing=8, width=300),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton("Reset a 0", on_click=reset,
                              style=ft.ButtonStyle(color=COLOR_TEXT_MUTED)),
                ft.ElevatedButton("Applica", on_click=save,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Azioni Turno
    # ------------------------------------------------------------------

    def _section_turn(self, c: Character) -> ft.Container:

        def _action_chip(label: str, used: bool, on_click) -> ft.Container:
            """Chip colorato: rosso = disponibile, grigio = usato."""
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if not used else ft.Icons.CANCEL,
                            size=20,
                            color="#ffffff" if not used else "#ffffff60",
                        ),
                        ft.Text(
                            label, size=10, text_align=ft.TextAlign.CENTER,
                            color="#ffffff" if not used else "#ffffff60",
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=3,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=COLOR_ACCENT_CRIMSON if not used else COLOR_TEXT_MUTED,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=8,
                on_click=on_click,
                ink=True,
                expand=True,
                tooltip="Segna come usato" if not used else "Libera",
            )

        def _save_turn():
            character_repo.update_turn_state(
                c.id, c.action_used, c.bonus_action_used,
                c.reaction_used, c.movement_used,
                c.previous_turn_state or "",
            )

        def toggle_action(e):
            c.action_used = not c.action_used
            _save_turn()
            self._refresh()

        def toggle_bonus(e):
            c.bonus_action_used = not c.bonus_action_used
            _save_turn()
            self._refresh()

        def toggle_reaction(e):
            c.reaction_used = not c.reaction_used
            _save_turn()
            self._refresh()

        # --- Tracker movimento ---
        speed = c.speed or 9
        used_m = c.movement_used or 0
        remaining_m = max(0, speed - used_m)
        move_ratio = min(1.0, used_m / speed) if speed > 0 else 0.0

        def use_movement(delta: int):
            """Aggiunge delta metri al movimento usato (positivo = usa, negativo = recupera)."""
            c.movement_used = max(0, min(speed, used_m + delta))
            character_repo.update_turn_state(
                c.id, c.action_used, c.bonus_action_used,
                c.reaction_used, c.movement_used,
                c.previous_turn_state or "",
            )
            self._refresh()

        move_bar = ft.ProgressBar(
            value=move_ratio, color=COLOR_ACCENT_AMBER,
            bgcolor=COLOR_BG_SECONDARY, height=8, border_radius=4,
        )
        movement_section = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("MOVIMENTO", size=9, color=COLOR_TEXT_MUTED,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.Text(
                            f"{remaining_m} / {speed} m rimanenti",
                            size=12, color=COLOR_TEXT_PRIMARY,
                        ),
                    ],
                    spacing=4,
                ),
                move_bar,
                ft.Row(
                    [
                        ft.TextButton("−1m", on_click=lambda e: use_movement(1),
                                      style=ft.ButtonStyle(color=COLOR_ACCENT_AMBER)),
                        ft.TextButton("−2m", on_click=lambda e: use_movement(2),
                                      style=ft.ButtonStyle(color=COLOR_ACCENT_AMBER)),
                        ft.TextButton("−3m", on_click=lambda e: use_movement(3),
                                      style=ft.ButtonStyle(color=COLOR_ACCENT_AMBER)),
                        ft.TextButton("−6m", on_click=lambda e: use_movement(6),
                                      style=ft.ButtonStyle(color=COLOR_ACCENT_AMBER)),
                        ft.Container(expand=True),
                        ft.TextButton("↩ Reset", on_click=lambda e: use_movement(-used_m),
                                      style=ft.ButtonStyle(color=COLOR_TEXT_MUTED)),
                    ],
                    spacing=0,
                ),
            ],
            spacing=4,
        )

        # --- Nuovo Turno / Annulla ---
        def nuovo_turno(e):
            snap = json.dumps({
                "action_used": c.action_used,
                "bonus_action_used": c.bonus_action_used,
                "reaction_used": c.reaction_used,
                "movement_used": c.movement_used,
            })
            character_repo.update_turn_state(c.id, False, False, False, 0, snap)
            self._refresh()

        def annulla_turno(e):
            prev = c.previous_turn_state
            if not prev:
                return
            try:
                snap = json.loads(prev)
                character_repo.update_turn_state(
                    c.id,
                    snap.get("action_used", False),
                    snap.get("bonus_action_used", False),
                    snap.get("reaction_used", False),
                    snap.get("movement_used", 0),
                    "",
                )
                self._refresh()
            except (json.JSONDecodeError, KeyError) as ex:
                logger.warning(f"Errore ripristino turno: {ex}")

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            _action_chip("AZIONE", c.action_used, toggle_action),
                            ft.Container(width=6),
                            _action_chip("BONUS", c.bonus_action_used, toggle_bonus),
                            ft.Container(width=6),
                            _action_chip("REAZIONE", c.reaction_used, toggle_reaction),
                        ],
                        spacing=0,
                    ),
                    ft.Container(height=8),
                    movement_section,
                    ft.Container(height=4),
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "↺ Nuovo Turno", on_click=nuovo_turno,
                                expand=True,
                                style=ft.ButtonStyle(
                                    bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                            ),
                            ft.Container(width=8),
                            ft.OutlinedButton(
                                "↩ Annulla", on_click=annulla_turno,
                                disabled=not bool(c.previous_turn_state),
                                style=ft.ButtonStyle(
                                    color=COLOR_TEXT_SECONDARY,
                                    side=ft.BorderSide(1, COLOR_BORDER),
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                            ),
                        ],
                        spacing=0,
                    ),
                ],
                spacing=4,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Tiri Salvezza & Abilità — riferimento rapido
    # ------------------------------------------------------------------

    def _section_saves_skills(self, c: Character) -> ft.Container:
        """
        Griglia compatta: 6 tiri salvezza + 18 abilità con modificatori.
        ✦ = competente, ★ = maestria (doppio bonus competenza).
        """
        pb = char_prof_bonus(c)
        scores = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        # Indici competenze dal DB
        save_profs: set[str] = {
            p.name for p in self._profs if p.proficiency_type == "save"
        }
        skill_profs: dict[str, bool] = {
            p.name: p.is_expert
            for p in self._profs if p.proficiency_type == "skill"
        }

        def _mod_str(val: int) -> str:
            return f"+{val}" if val >= 0 else str(val)

        def _save_row(stat_name: str, key: str) -> ft.Row:
            base = get_modifier(scores[key])
            prof = stat_name in save_profs
            total = base + (pb if prof else 0)
            marker = " ✦" if prof else ""
            color = COLOR_TEXT_PRIMARY if prof else COLOR_TEXT_MUTED
            return ft.Row([
                ft.Text(f"{_mod_str(total)}{marker}", size=12,
                        color=color, weight=ft.FontWeight.W_600,
                        font_family=FONT_MONO, width=48),
                ft.Text(stat_name, size=12, color=color),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        def _skill_row(skill_name: str, stat_key: str) -> ft.Row:
            base = get_modifier(scores[stat_key])
            expert = skill_profs.get(skill_name, None)
            if expert is True:
                total = base + pb * 2
                marker, color = " ★", COLOR_ACCENT_BLUE
            elif expert is False:
                total = base + pb
                marker, color = " ✦", COLOR_TEXT_PRIMARY
            else:
                total, marker, color = base, "", COLOR_TEXT_MUTED
            return ft.Row([
                ft.Text(f"{_mod_str(total)}{marker}", size=12,
                        color=color, weight=ft.FontWeight.W_600,
                        font_family=FONT_MONO, width=48),
                ft.Text(skill_name, size=12, color=color),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # --- Tiri Salvezza ---
        save_pairs = list(zip(ABILITY_SCORES, ABILITY_KEYS))
        save_controls: list[ft.Control] = [
            ft.Text("TIRI SALVEZZA", size=9, color=COLOR_TEXT_MUTED,
                    weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
        ]
        save_controls.extend(_save_row(name, key) for name, key in save_pairs)
        saves_col = ft.Column(controls=save_controls, spacing=3)

        # --- Abilità — due colonne da 9 ---
        skill_items = list(SKILLS.items())
        half = len(skill_items) // 2
        col_a = ft.Column(
            [_skill_row(n, k) for n, k in skill_items[:half]], spacing=3
        )
        col_b = ft.Column(
            [_skill_row(n, k) for n, k in skill_items[half:]], spacing=3
        )

        return ft.Container(
            content=ft.Column([
                saves_col,
                ft.Divider(color=COLOR_BORDER),
                ft.Text("ABILITÀ", size=9, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8)),
                ft.Row([col_a, ft.Container(width=20), col_b], spacing=0),
                ft.Text("✦ competente  ★ maestria", size=10, color=COLOR_TEXT_MUTED,
                        italic=True),
            ], spacing=8),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Armi Equipaggiate
    # ------------------------------------------------------------------

    def _section_weapons(self) -> ft.Container:
        """Armi is_equipped=True con bonus attacco, danno, proprietà."""

        def _atk_str(w: Weapon) -> str:
            return f"+{w.attack_bonus}" if w.attack_bonus >= 0 else str(w.attack_bonus)

        def _dmg_str(w: Weapon) -> str:
            s = w.damage_dice or "—"
            if w.damage_bonus > 0:
                s += f"+{w.damage_bonus}"
            elif w.damage_bonus < 0:
                s += str(w.damage_bonus)
            if w.damage_type:
                s += f"  {w.damage_type}"
            return s

        def _range_str(w: Weapon) -> str:
            if w.range_normal and w.range_normal > 0:
                if w.range_max:
                    return f"{w.range_normal}/{w.range_max} m"
                return f"{w.range_normal} m"
            return "mischia"

        def _weapon_card(w: Weapon) -> ft.Container:
            props = w.properties.strip() if w.properties else ""

            # Descrizione magica (testo libero)
            magic_row = (
                ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=12, color=COLOR_ACCENT_AMBER),
                    ft.Text(w.magic_description, size=11, color=COLOR_ACCENT_AMBER,
                            expand=True),
                ], spacing=4)
                if w.is_magical and w.magic_description else None
            )

            # Danni magici aggiuntivi (JSON array: [{dice, type, note}])
            extra_damage_rows: list[ft.Control] = []
            try:
                magic_dmgs = json.loads(w.magic_damages or "[]")
                for md in magic_dmgs:
                    dice = md.get("dice", "")
                    typ  = md.get("type", "")
                    note = md.get("note", "")
                    if not dice:
                        continue
                    label = f"+ {dice}  {typ}"
                    if note:
                        label += f"  ({note})"
                    extra_damage_rows.append(
                        ft.Row([
                            ft.Icon(ft.Icons.WHATSHOT, size=11, color=COLOR_ACCENT_AMBER),
                            ft.Text(label, size=11, color=COLOR_ACCENT_AMBER,
                                    font_family=FONT_MONO),
                        ], spacing=4)
                    )
            except (json.JSONDecodeError, AttributeError):
                pass

            rows: list[ft.Control] = [
                ft.Row([
                    ft.Text(w.name, size=14, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE, expand=True),
                    ft.Container(
                        content=ft.Text(_range_str(w), size=10, color=COLOR_TEXT_MUTED),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                        border=ft.Border.all(1, COLOR_BORDER),
                        border_radius=4,
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("ATT", size=9, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER),
                            ft.Text(_atk_str(w), size=16, color=COLOR_ACCENT_CRIMSON,
                                    weight=ft.FontWeight.BOLD, font_family=FONT_MONO,
                                    text_align=ft.TextAlign.CENTER),
                        ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor=COLOR_BG_SECONDARY,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=6,
                        width=58,
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("DANNO", size=9, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER),
                            ft.Text(_dmg_str(w), size=13, color=COLOR_TEXT_PRIMARY,
                                    weight=ft.FontWeight.BOLD, font_family=FONT_MONO,
                                    text_align=ft.TextAlign.CENTER),
                        ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor=COLOR_BG_SECONDARY,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=6,
                        expand=True,
                    ),
                ], spacing=8),
            ]
            if props:
                rows.append(ft.Text(props, size=11, color=COLOR_TEXT_MUTED, italic=True))
            if magic_row:
                rows.append(magic_row)
            rows.extend(extra_damage_rows)

            return ft.Container(
                content=ft.Column(rows, spacing=6),
                bgcolor=COLOR_BG_SECONDARY,
                padding=10,
                border_radius=6,
                border=ft.Border.all(1, COLOR_BORDER),
            )

        if not self._weapons:
            body = ft.Column([
                ft.Text("Nessuna arma equipaggiata.", size=12, color=COLOR_TEXT_MUTED),
                ft.Text("Aggiungi armi dalla scheda Inventario (prossimamente).",
                        size=11, color=COLOR_TEXT_MUTED),
            ], spacing=4)
        else:
            body = ft.Column(
                [_weapon_card(w) for w in self._weapons], spacing=8
            )

        return ft.Container(
            content=body,
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Slot Incantesimo BG3-style
    # ------------------------------------------------------------------

    def _section_spell_slots(self, c: Character) -> ft.Container:
        """
        Sezione Magia completa:
          - header: caratteristica, CD tiro salvezza, bonus attacco incantesimo
          - slot BG3-style cliccabili
          - incantesimi preparati raggruppati per livello
        """
        # --- Mapping chiave → nome italiano ---
        _KEY_TO_NAME = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
        _KEY_TO_ABBR = dict(zip(ABILITY_KEYS, ABILITY_ABBR))
        _KEY_TO_SCORE = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        pb = char_prof_bonus(c)
        sp_key = c.spellcasting_ability or ""
        is_caster = bool(sp_key and sp_key in _KEY_TO_SCORE)

        sections: list[ft.Control] = []

        # --- Header statistiche magia ---
        if is_caster:
            sp_mod  = get_modifier(_KEY_TO_SCORE[sp_key])
            save_dc = 8 + pb + sp_mod
            atk_bon = pb + sp_mod
            atk_str = f"+{atk_bon}" if atk_bon >= 0 else str(atk_bon)
            sp_name = _KEY_TO_NAME[sp_key]
            sp_abbr = _KEY_TO_ABBR[sp_key]

            def _magic_stat(label: str, value: str) -> ft.Container:
                return ft.Container(
                    content=ft.Column([
                        ft.Text(label, size=9, color=COLOR_TEXT_MUTED,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                        ft.Text(value, size=18, color=COLOR_ACCENT_BLUE,
                                weight=ft.FontWeight.BOLD, font_family=FONT_MONO,
                                text_align=ft.TextAlign.CENTER),
                    ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=COLOR_BG_SECONDARY,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    border_radius=6,
                    expand=True,
                )

            sections += [
                ft.Row([
                    _magic_stat(f"CARATTERISTICA\n({sp_abbr})", sp_name),
                    _magic_stat("CD TIRO SALVEZZA", str(save_dc)),
                    _magic_stat("BONUS ATTACCO", atk_str),
                ], spacing=8),
                ft.Divider(color=COLOR_BORDER),
            ]
        else:
            sections.append(
                ft.Text("Nessuna caratteristica da incantatore.",
                        size=12, color=COLOR_TEXT_MUTED)
            )

        # --- Slot BG3-style ---
        active_slots = [s for s in self._slots if s.total > 0]
        configure_btn = ft.TextButton(
            "✎ Configura slot",
            on_click=self._on_configure_slots_click,
            style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
        )

        if not active_slots:
            sections += [
                ft.Text("Nessuno slot configurato.", size=12, color=COLOR_TEXT_MUTED),
                ft.Row([configure_btn], alignment=ft.MainAxisAlignment.END),
            ]
        else:
            slot_rows = []
            for slot in sorted(active_slots, key=lambda s: s.slot_level):
                avail = slot.total - slot.used
                circles = []
                for i in range(slot.total):
                    is_avail = i < avail
                    circles.append(ft.Container(
                        content=ft.Text(
                            "●" if is_avail else "○",
                            size=22,
                            color=COLOR_SLOT_FULL if is_avail else COLOR_TEXT_MUTED,
                        ),
                        on_click=lambda e, lv=slot.slot_level, use=is_avail:
                            self._toggle_slot(lv, use=use),
                        tooltip="Usa slot" if is_avail else "Recupera slot",
                        border_radius=14,
                        ink=True,
                        padding=ft.Padding.all(2),
                    ))
                slot_rows.append(ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                _SLOT_NAMES[slot.slot_level - 1],
                                size=12, color=COLOR_TEXT_SECONDARY,
                                weight=ft.FontWeight.W_600,
                            ),
                            width=28,
                        ),
                        ft.Row(circles, spacing=2),
                        ft.Container(expand=True),
                        ft.Text(f"{avail}/{slot.total}", size=11, color=COLOR_TEXT_MUTED),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ))
            sections += slot_rows + [
                ft.Row([configure_btn], alignment=ft.MainAxisAlignment.END),
            ]

        # --- Incantesimi preparati ---
        if self._prepared:
            sections.append(ft.Divider(color=COLOR_BORDER))
            sections.append(
                ft.Text("INCANTESIMI PREPARATI", size=9, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
            )
            # Raggruppa per livello
            by_level: dict[int, list[KnownSpell]] = {}
            for sp in self._prepared:
                by_level.setdefault(sp.spell_level, []).append(sp)

            for lv in sorted(by_level.keys()):
                level_label = "Trucchetti" if lv == 0 else f"{_SLOT_NAMES[lv - 1]} livello"
                spell_names = "  ·  ".join(sp.name for sp in by_level[lv])
                sections.append(ft.Row([
                    ft.Container(
                        content=ft.Text(level_label, size=10, color=COLOR_ACCENT_BLUE,
                                        weight=ft.FontWeight.BOLD),
                        width=80,
                    ),
                    ft.Text(spell_names, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START))

        return ft.Container(
            content=ft.Column(sections, spacing=8),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_BLUE),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _toggle_slot(self, slot_level: int, use: bool):
        for slot in self._slots:
            if slot.slot_level == slot_level:
                if use:
                    slot.used = min(slot.total, slot.used + 1)
                else:
                    slot.used = max(0, slot.used - 1)
                character_repo.update_spell_slot(self.character.id, slot_level, slot.used)
                self._refresh()
                return

    def _on_configure_slots_click(self, e):
        page = self._page
        if page is None:
            return
        slot_map = {s.slot_level: s for s in self._slots}
        fields: dict[int, ft.TextField] = {}

        for lv in range(1, 10):
            s = slot_map.get(lv)
            fields[lv] = ft.TextField(
                label=f"{_SLOT_NAMES[lv - 1]} livello",
                value=str(s.total if s else 0),
                keyboard_type=ft.KeyboardType.NUMBER,
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_BLUE,
                bgcolor=COLOR_BG_CARD,
            )

        # Layout 3×3
        grid = ft.Row(
            [
                ft.Column([fields[1], fields[4], fields[7]], spacing=8, expand=True),
                ft.Column([fields[2], fields[5], fields[8]], spacing=8, expand=True),
                ft.Column([fields[3], fields[6], fields[9]], spacing=8, expand=True),
            ],
            spacing=12,
        )

        def save(ev):
            if page is None:
                return
            for lv, field in fields.items():
                try:
                    total = max(0, min(9, int(field.value or 0)))
                except ValueError:
                    total = 0
                character_repo.update_spell_slot_total(self.character.id, lv, total)
            self._slots = character_repo.get_spell_slots(self.character.id)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Configura Slot Incantesimo", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [
                    ft.Text(
                        "Numero massimo di slot per livello (0 = non disponibile).",
                        size=12, color=COLOR_TEXT_SECONDARY,
                    ),
                    ft.Container(height=6),
                    grid,
                ],
                width=380,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Salva", on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Dadi Vita
    # ------------------------------------------------------------------

    def _section_hit_dice(self, c: Character) -> ft.Container:
        die        = c.hit_dice_type or 8
        total      = c.hit_dice_total or c.level
        remaining  = c.hit_dice_remaining if c.hit_dice_remaining is not None else total
        con_mod    = get_modifier(c.con_score)
        con_str    = f"+{con_mod}" if con_mod >= 0 else str(con_mod)

        # Cerchietti ◆ disponibili / ◇ usati
        dice_circles: list[ft.Control] = []
        for i in range(total):
            avail = i < remaining
            dice_circles.append(ft.Container(
                content=ft.Text(
                    "◆" if avail else "◇", size=18,
                    color=COLOR_ACCENT_CRIMSON if avail else COLOR_TEXT_MUTED,
                ),
                tooltip=f"d{die} disponibile" if avail else "usato",
                padding=ft.Padding.all(1),
            ))

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"d{die}", size=28, weight=ft.FontWeight.BOLD,
                                    color=COLOR_ACCENT_CRIMSON, font_family=FONT_MONO),
                            ft.Container(width=10),
                            ft.Column(
                                [
                                    ft.Text(f"{remaining} / {total} rimanenti",
                                            size=13, color=COLOR_TEXT_PRIMARY),
                                    ft.Text(f"Cura per dado: 1–{die} {con_str} CON",
                                            size=11, color=COLOR_TEXT_MUTED),
                                ],
                                spacing=1,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Row(dice_circles, spacing=4, wrap=True),
                        padding=ft.Padding.symmetric(vertical=4),
                    ),
                    ft.ElevatedButton(
                        "Riposo Breve",
                        icon=ft.Icons.COFFEE,
                        on_click=self._on_short_rest_click,
                        disabled=(remaining == 0),
                        expand=True,
                        style=ft.ButtonStyle(
                            bgcolor=COLOR_ACCENT_AMBER, color="#ffffff",
                            shape=ft.RoundedRectangleBorder(radius=6),
                        ),
                    ),
                ],
                spacing=8,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_AMBER),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _on_short_rest_click(self, e):
        page = self._page
        if page is None:
            return
        c = self.character
        die       = c.hit_dice_type or 8
        total     = c.hit_dice_total or c.level
        remaining = c.hit_dice_remaining if c.hit_dice_remaining is not None else total
        con_mod   = get_modifier(c.con_score)

        f_dice = ft.TextField(
            label=f"Dadi da spendere (max {remaining})", value="1",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_AMBER,
            bgcolor=COLOR_BG_CARD, width=300,
        )
        f_roll = ft.TextField(
            label=f"Totale dadi tirati (escluso CON)",
            hint_text=f"es. {die // 2} per un dado",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_AMBER,
            bgcolor=COLOR_BG_CARD, width=300,
        )

        def apply(ev):
            if page is None:
                return
            try:
                n = max(1, min(remaining, int(f_dice.value or 1)))
                roll = max(n, int(f_roll.value or n))
            except ValueError:
                return
            recovered = max(1, roll + con_mod * n)
            c.hp_current = min(c.hp_max, c.hp_current + recovered)
            c.hit_dice_remaining = max(0, remaining - n)
            character_repo.update_hp(c.id, c.hp_current)
            character_repo.update_hit_dice(c.id, c.hit_dice_remaining)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Riposo Breve", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_ACCENT_AMBER),
            content=ft.Column(
                [
                    ft.Text(
                        f"Lancia i dadi vita (d{die}) e aggiungi {con_mod:+d} CON per dado.",
                        size=12, color=COLOR_TEXT_SECONDARY,
                    ),
                    ft.Container(height=4),
                    f_dice,
                    f_roll,
                ],
                spacing=8, width=320,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Applica Riposo", on_click=apply,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_AMBER, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Riposo Lungo
    # ------------------------------------------------------------------

    def _section_riposo_lungo(self, c: Character) -> ft.Container:

        def do_rest(ev):
            page = self._page
            if page is None:
                return
            # HP e HP temp
            c.hp_current = c.hp_max
            c.hp_temp = 0
            # Recupera metà dei dadi vita (minimo 1) — PHB p.186
            total = c.hit_dice_total or c.level
            recovered_dice = max(1, total // 2)
            c.hit_dice_remaining = min(
                total,
                (c.hit_dice_remaining or 0) + recovered_dice,
            )
            # Azzera stato turno e death saves
            c.action_used = False
            c.bonus_action_used = False
            c.reaction_used = False
            c.movement_used = 0
            c.previous_turn_state = ""
            c.death_saves_success = 0
            c.death_saves_failure = 0
            # Ripristina tutti gli slot
            for slot in self._slots:
                if slot.total > 0:
                    character_repo.update_spell_slot(c.id, slot.slot_level, 0)
            # Salva tutto
            character_repo.update(c)
            character_repo.update_hp(c.id, c.hp_max, 0)
            page.pop_dialog()
            self._refresh()

        def confirm(e):
            page = self._page
            if page is None:
                return
            total = c.hit_dice_total or c.level
            recovered = max(1, total // 2)
            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Riposo Lungo", size=14, weight=ft.FontWeight.BOLD,
                              color=COLOR_TEXT_TITLE),
                content=ft.Text(
                    f"Effettuare un riposo lungo?\n\n"
                    f"  ❤  HP ripristinati ({c.hp_current} → {c.hp_max})\n"
                    f"  ◆  Dadi vita recuperati (+{recovered})\n"
                    f"  ●  Slot incantesimo ripristinati\n"
                    f"  ↺  Azioni turno azzerate\n"
                    f"  ☠  Tiri salvezza morte azzerati",
                    size=13, color=COLOR_TEXT_PRIMARY,
                ),
                actions=[
                    ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                    ft.ElevatedButton(
                        "Riposa",
                        on_click=do_rest,
                        style=ft.ButtonStyle(
                            bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                            shape=ft.RoundedRectangleBorder(radius=4),
                        ),
                    ),
                ],
                bgcolor=COLOR_BG_CARD,
            ))

        return ft.Container(
            content=ft.ElevatedButton(
                "Riposo Lungo",
                icon=ft.Icons.BEDTIME,
                on_click=confirm,
                expand=True,
                style=ft.ButtonStyle(
                    bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                    shape=ft.RoundedRectangleBorder(radius=6),
                    padding=ft.Padding.symmetric(vertical=14, horizontal=20),
                ),
            ),
            padding=ft.Padding.only(bottom=24),
        )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        self._slots    = character_repo.get_spell_slots(self.character.id)
        self._profs    = character_repo.get_proficiencies(self.character.id)
        self._weapons  = character_repo.get_weapons(self.character.id)
        self._prepared = character_repo.get_prepared_spells(self.character.id)
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
