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
from typing import Any, Callable, cast
from config.settings import *
from config.settings import get_race_display_traits
from data.models import Character, SpellSlot, CharacterProficiency, Weapon, KnownSpell, ClassResource, CreatureEntry
import data.repositories.character_repo as character_repo
from data.game_data.game_data_loader import GameDataLoader
from ui.theme import section_header, muted_text

_loader = GameDataLoader()

logger = logging.getLogger(__name__)

# Nomi ordinali per i livelli slot
_SLOT_NAMES = ["1°", "2°", "3°", "4°", "5°", "6°", "7°", "8°", "9°"]


def monster_display_name(raw_name: str) -> str:
    """Converte il nome in MAIUSCOLO del bestiary in title case leggibile."""
    return raw_name.title()


class CombattimentoTab(ft.ListView):
    """
    Tab combattimento: HP, azioni turno, slot, dadi vita, riposi.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.
    """

    def __init__(self, character: Character, on_refresh: Callable[[], None] | None = None):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None
        self._slots: list[SpellSlot] = character_repo.get_spell_slots(character.id)
        # Auto-init slot PHB se il personaggio è un incantatore e non ha ancora slot configurati
        if character.spellcasting_ability and all(s.total == 0 for s in self._slots):
            character_repo.auto_init_spell_slots(
                character.id, character.class_name or "", character.level
            )
            self._slots = character_repo.get_spell_slots(character.id)
        self._profs: list[CharacterProficiency] = character_repo.get_proficiencies(character.id)
        self._weapons: list[Weapon] = character_repo.get_weapons(character.id)
        self._prepared: list[KnownSpell] = character_repo.get_prepared_spells(character.id)
        self._resources: list[ClassResource] = character_repo.get_class_resources(character.id)
        # Sync automatico a ogni apertura della tab: aggiunge risorse nuove, aggiorna
        # i pool massimi in base al livello corrente (es. Furia che scala nel tempo) e
        # rimuove risorse non più applicabili (es. sottoclasse cambiata) — idempotente,
        # non tocca current_value oltre al clamp al nuovo massimo.
        if character.class_name:
            character_repo.init_class_resources(
                character.id, character.class_name, character.level, character
            )
            self._resources = character_repo.get_class_resources(character.id)
        self._features: list[dict] = self._load_class_features(character)
        self._race_traits: dict = get_race_display_traits(
            character.race or "", character.subrace or ""
        )
        # Forme selvatiche e evocazioni
        self._forme: list[CreatureEntry] = character_repo.get_creature_entries(
            character.id, entry_type="forma"
        )
        self._evocazioni: list[CreatureEntry] = character_repo.get_creature_entries(
            character.id, entry_type="evocazione"
        )
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        c = self.character
        controls: list[ft.Control] = [
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
        ]
        if self._resources:
            controls += [
                section_header("Risorse di Classe"),
                self._section_class_resources(),
            ]
        if self._features:
            controls += [
                section_header("Abilità di Classe"),
                self._section_class_features(),
            ]
        _rt = self._race_traits
        if _rt["resistances"] or _rt["advantage_saves"]:
            controls += [
                section_header("Tratti di Razza"),
                self._section_racial_traits(),
            ]
        # Forme selvatiche — solo Druido
        if (c.class_name or "").lower() == "druido":
            controls += [
                section_header("Forme Selvatiche"),
                self._section_forme(),
            ]
        # Evocazioni — tutti i personaggi
        controls += [
            section_header("Evocazioni"),
            self._section_evocazioni(),
        ]
        controls += [
            section_header("Dadi Vita"),
            self._section_hit_dice(c),
            self._section_riposo_lungo(c),
        ]
        self.controls = controls

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
            content=ft.Column([f_max, f_curr, f_temp], spacing=10),
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
        initiative = get_modifier(c.dex_score) + (c.initiative_bonus or 0)
        init_str = f"+{initiative}" if initiative >= 0 else str(initiative)

        # Velocità effettiva: base (razza + override manuale + Talento Mobile)
        # + bonus dinamico di classe non equipaggiato (Monaco/Barbaro, Categoria B)
        effective_speed = character_repo.get_effective_speed(c)
        speed_bonus_active = effective_speed != (c.speed or 0)
        speed_label = "VELOCITÀ" if not speed_bonus_active else "VELOCITÀ ✦"

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
                            _stat_box(speed_label, f"{effective_speed:g}m",
                                     COLOR_ACCENT_BLUE if speed_bonus_active else COLOR_TEXT_PRIMARY),
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
            ], spacing=8),
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
        # Include il bonus dinamico di classe non equipaggiato (Monaco/Barbaro)
        # nel movimento realmente disponibile in combattimento
        speed = character_repo.get_effective_speed(c)
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
                            f"{remaining_m:g} / {speed:g} m rimanenti",
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
            sections.append(
                ft.Text("Clicca un incantesimo per la descrizione completa.",
                        size=10, color=COLOR_TEXT_MUTED, italic=True)
            )
            # Raggruppa per livello
            by_level: dict[int, list[KnownSpell]] = {}
            for sp in self._prepared:
                by_level.setdefault(sp.spell_level, []).append(sp)

            def _make_spell_btn(sp: KnownSpell) -> ft.TextButton:
                return ft.TextButton(
                    sp.name,
                    on_click=lambda e, s=sp: self._open_spell_dialog(s.name, s.spell_level),
                    style=ft.ButtonStyle(
                        color=COLOR_TEXT_PRIMARY,
                        padding=ft.Padding.symmetric(horizontal=2, vertical=0),
                        overlay_color=ft.Colors.with_opacity(0.08, COLOR_ACCENT_BLUE),
                    ),
                )

            for lv in sorted(by_level.keys()):
                level_label = "Trucchetti" if lv == 0 else f"{_SLOT_NAMES[lv - 1]} livello"
                spell_controls: list[ft.Control] = []
                for i, sp in enumerate(by_level[lv]):
                    spell_controls.append(_make_spell_btn(sp))
                    if i < len(by_level[lv]) - 1:
                        spell_controls.append(
                            ft.Text("·", size=12, color=COLOR_TEXT_MUTED)
                        )
                sections.append(ft.Row([
                    ft.Container(
                        content=ft.Text(level_label, size=10, color=COLOR_ACCENT_BLUE,
                                        weight=ft.FontWeight.BOLD),
                        width=80,
                    ),
                    ft.Row(spell_controls, spacing=0, wrap=True, expand=True),
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

    def _open_spell_dialog(self, spell_name: str, spell_level: int) -> None:
        """Apre un AlertDialog con la descrizione completa dell'incantesimo."""
        page = self._page
        if not page:
            return

        spell = _loader.get_spell_by_name(spell_name, self.character.class_name)

        if not spell:
            page.show_dialog(ft.AlertDialog(
                title=ft.Text(spell_name, size=14, weight=ft.FontWeight.BOLD,
                              color=COLOR_TEXT_TITLE),
                content=ft.Text(
                    "Trucchetto" if spell_level == 0 else f"{spell_level}° livello",
                    size=12, color=COLOR_TEXT_MUTED,
                ),
                actions=[
                    ft.TextButton("Chiudi",
                                  on_click=lambda ev: page.pop_dialog() if page else None),
                ],
                bgcolor=COLOR_BG_CARD,
            ))
            return

        level_str = "Trucchetto" if spell_level == 0 else f"{spell_level}° livello"
        school    = spell.get("school", "")
        header    = f"{level_str}  ·  {school}" if school else level_str

        def _info_row(label: str, value: str) -> ft.Row:
            return ft.Row([
                ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.W_600, width=110),
                ft.Text(value, size=11, color=COLOR_TEXT_PRIMARY, expand=True),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START)

        info_rows: list[ft.Control] = []
        for label, key in [
            ("Tempo di lancio", "casting_time"),
            ("Gittata",         "range"),
            ("Componenti",      "components"),
            ("Durata",          "duration"),
        ]:
            val = spell.get(key, "")
            if val:
                info_rows.append(_info_row(label, str(val)))

        tags: list[ft.Control] = []
        if spell.get("ritual"):
            tags.append(ft.Container(
                content=ft.Text("Rituale", size=10, color=COLOR_ACCENT_BLUE),
                border=ft.Border.all(1, COLOR_ACCENT_BLUE),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            ))
        if spell.get("concentration"):
            tags.append(ft.Container(
                content=ft.Text("Concentrazione", size=10, color=COLOR_ACCENT_AMBER),
                border=ft.Border.all(1, COLOR_ACCENT_AMBER),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            ))

        desc   = spell.get("description", "")
        higher = spell.get("higher_levels", "")

        content_items: list[ft.Control] = [
            ft.Text(header, size=11, color=COLOR_TEXT_MUTED, italic=True),
            ft.Container(height=4),
        ]
        if info_rows:
            content_items.extend(info_rows)
            content_items.append(ft.Container(height=4))
        if tags:
            content_items.append(ft.Row(tags, spacing=6, wrap=True))
            content_items.append(ft.Container(height=4))
        if desc:
            content_items.append(ft.Divider(color=COLOR_BORDER))
            content_items.append(
                ft.Text(desc, size=13, color=COLOR_TEXT_PRIMARY, selectable=True)
            )
        if higher:
            content_items.append(ft.Container(height=6))
            content_items.append(
                ft.Text("A livelli superiori:", size=11,
                        color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD)
            )
            content_items.append(
                ft.Text(higher, size=12, color=COLOR_TEXT_SECONDARY, italic=True)
            )

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(spell_name, size=15, weight=ft.FontWeight.BOLD,
                          color=COLOR_TEXT_TITLE),
            content=ft.Column(
                content_items,
                spacing=6,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Chiudi",
                              on_click=lambda ev: page.pop_dialog() if page else None),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

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
    # Risorse di Classe
    # ------------------------------------------------------------------

    def _section_class_resources(self) -> ft.Container:
        """
        Sezione risorse di classe (Furia, Ki, Incanalare Divinità, ecc.).
        - display_type "circles": cerchietti ● cliccabili (click = usa/recupera).
        - display_type "counter": etichetta numerica con bottoni − e +.
        """
        rows: list[ft.Control] = []
        for res in self._resources:
            if res.max_value < 0 or res.display_type == "unlimited":
                rows.append(self._resource_unlimited_row(res))
            elif res.display_type == "circles":
                rows.append(self._resource_circles_row(res))
            else:
                rows.append(self._resource_counter_row(res))

        # Incantesimi Flessibili (solo Stregone, dal momento in cui ha Punti Stregoneria)
        sp_res = next((r for r in self._resources if r.name == "Punti Stregoneria"), None)
        if (self.character.class_name or "").strip().lower() == "stregone" and sp_res:
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(self._section_flexible_casting(sp_res))

        return ft.Container(
            content=ft.Column(rows, spacing=10),
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

    def _section_flexible_casting(self, sp_res: ClassResource) -> ft.Column:
        """
        Incantesimi Flessibili (Stregone, PHB): converte Punti Stregoneria in slot
        incantesimo aggiuntivi (spariscono al riposo lungo) o viceversa.
        Costo di creazione letto da stregone.json ("spell_slot_creation_cost"),
        fonte unica condivisa con la scheda di classe.
        """
        class_data = _loader.get_class("Stregone") or {}
        cost_table: dict[int, int] = {
            row["slot_level"]: row["sorcery_points"]
            for row in class_data.get("spell_slot_creation_cost", [])
        } or {1: 2, 2: 3, 3: 5, 4: 6, 5: 7}  # fallback se il JSON non è disponibile

        create_dd = ft.Dropdown(
            label="Crea slot di livello",
            options=[
                ft.DropdownOption(key=str(lv), text=f"{lv}° — costo {cost} pt")
                for lv, cost in sorted(cost_table.items())
            ],
            value=str(min(cost_table.keys())) if cost_table else None,
            width=190,
            dense=True,
            text_size=12,
            border_radius=6,
        )

        available_slots = [s for s in self._slots if s.total > 0 and s.used < s.total]
        convert_dd = ft.Dropdown(
            label="Converti slot di livello",
            options=(
                [
                    ft.DropdownOption(key=str(s.slot_level),
                                       text=f"{s.slot_level}° — {s.total - s.used} liber{'o' if s.total - s.used == 1 else 'i'}")
                    for s in available_slots
                ] or [ft.DropdownOption(key="", text="Nessuno slot disponibile")]
            ),
            value=str(available_slots[0].slot_level) if available_slots else "",
            disabled=not available_slots,
            width=190,
            dense=True,
            text_size=12,
            border_radius=6,
        )

        def on_create(e: Any) -> None:
            if not create_dd.value:
                return
            lv = int(create_dd.value)
            cost = cost_table.get(lv, 0)
            if sp_res.current_value < cost:
                self._show_flex_cast_error(
                    f"Punti stregoneria insufficienti: servono {cost}, "
                    f"disponibili {sp_res.current_value}."
                )
                return
            sp_res.current_value -= cost
            character_repo.update_class_resource(sp_res.id, sp_res.current_value)
            slot = next((s for s in self._slots if s.slot_level == lv), None)
            new_total = (slot.total if slot else 0) + 1
            character_repo.update_spell_slot_total(self.character.id, lv, new_total)
            self._refresh()

        def on_convert(e: Any) -> None:
            if not convert_dd.value:
                return
            lv = int(convert_dd.value)
            slot = next((s for s in self._slots if s.slot_level == lv), None)
            if not slot or slot.used >= slot.total:
                self._show_flex_cast_error("Nessuno slot disponibile a quel livello.")
                return
            character_repo.update_spell_slot(self.character.id, lv, slot.used + 1)
            sp_res.current_value = min(sp_res.max_value, sp_res.current_value + lv)
            character_repo.update_class_resource(sp_res.id, sp_res.current_value)
            self._refresh()

        return ft.Column(
            [
                ft.Text("Incantesimi Flessibili", size=12, weight=ft.FontWeight.BOLD,
                        color=COLOR_ACCENT_CRIMSON),
                muted_text(
                    "Azione bonus: crea uno slot spendendo punti stregoneria (svanisce "
                    "al riposo lungo), oppure sacrifica uno slot per ottenere punti "
                    "pari al suo livello.",
                    size=11,
                ),
                ft.Row([create_dd, ft.ElevatedButton("Crea", on_click=on_create, height=36)],
                       spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([convert_dd, ft.ElevatedButton("Converti", on_click=on_convert, height=36,
                                                        disabled=not available_slots)],
                       spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            spacing=8,
        )

    def _show_flex_cast_error(self, message: str) -> None:
        page = self._page
        if page is None:
            return
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Operazione non valida", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_ACCENT_CRIMSON),
            content=ft.Text(message, size=13, color=COLOR_TEXT_PRIMARY),
            actions=[ft.TextButton("OK", on_click=lambda ev: page.pop_dialog() if page else None)],
            bgcolor=COLOR_BG_CARD,
        ))

    def _resource_unlimited_row(self, res: ClassResource) -> ft.Row:
        """Riga per risorse senza limite di utilizzi (es. Furia del Barbaro al 20° livello)."""
        reset_icon  = "☽" if res.reset_on == "short_rest" else "☀"
        reset_label = "Ripristino: riposo breve" if res.reset_on == "short_rest" else "Ripristino: riposo lungo"
        return ft.Row(
            [
                ft.Text(res.name, size=12, color=COLOR_TEXT_PRIMARY,
                        weight=ft.FontWeight.W_600, expand=True),
                ft.Text(reset_icon, size=14, color=COLOR_TEXT_MUTED, tooltip=reset_label),
                ft.Container(width=6),
                ft.Container(
                    content=ft.Text("∞ Illimitata", size=12, color=COLOR_ACCENT_CRIMSON,
                                     weight=ft.FontWeight.BOLD),
                    bgcolor=COLOR_BG_SECONDARY,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    border_radius=6,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        )

    def _resource_circles_row(self, res: ClassResource) -> ft.Row:
        """Riga con cerchietti BG3-style per risorse a pool piccolo (≤ 6)."""
        reset_icon  = "☽" if res.reset_on == "short_rest" else "☀"
        reset_label = "Ripristino: riposo breve" if res.reset_on == "short_rest" else "Ripristino: riposo lungo"

        circles: list[ft.Control] = []
        for i in range(res.max_value):
            is_avail = i < res.current_value
            circles.append(ft.Container(
                content=ft.Text(
                    "●" if is_avail else "○",
                    size=22,
                    color=COLOR_ACCENT_CRIMSON if is_avail else COLOR_TEXT_MUTED,
                ),
                on_click=lambda e, r=res, use=is_avail: self._toggle_resource(r, use),
                tooltip="Usa" if is_avail else "Recupera",
                border_radius=14,
                ink=True,
                padding=ft.Padding.all(2),
            ))

        return ft.Row(
            [
                ft.Text(res.name, size=12, color=COLOR_TEXT_PRIMARY,
                        weight=ft.FontWeight.W_600, expand=True),
                ft.Text(reset_icon, size=14, color=COLOR_TEXT_MUTED,
                        tooltip=reset_label),
                ft.Container(width=6),
                ft.Row(circles, spacing=2),
                ft.Container(width=4),
                ft.Text(f"{res.current_value}/{res.max_value}", size=11,
                        color=COLOR_TEXT_MUTED, font_family=FONT_MONO),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        )

    def _resource_counter_row(self, res: ClassResource) -> ft.Column:
        """Riga con counter −/+ per risorse a pool grande (Ki, Stregoneria, ecc.)."""
        reset_icon  = "☽" if res.reset_on == "short_rest" else "☀"
        reset_label = "Ripristino: riposo breve" if res.reset_on == "short_rest" else "Ripristino: riposo lungo"

        ratio = (res.current_value / res.max_value) if res.max_value > 0 else 0.0
        bar_color = COLOR_ACCENT_CRIMSON if ratio > 0.4 else COLOR_ACCENT_AMBER

        return ft.Column([
            ft.Row(
                [
                    ft.Text(res.name, size=12, color=COLOR_TEXT_PRIMARY,
                            weight=ft.FontWeight.W_600, expand=True),
                    ft.Text(reset_icon, size=14, color=COLOR_TEXT_MUTED,
                            tooltip=reset_label),
                    ft.Container(width=8),
                    ft.IconButton(
                        ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        icon_size=18,
                        icon_color=COLOR_ACCENT_CRIMSON,
                        on_click=lambda e, r=res: self._decrement_resource(r),
                        disabled=res.current_value <= 0,
                        tooltip="Usa 1",
                    ),
                    ft.Text(
                        f"{res.current_value}/{res.max_value}",
                        size=15, color=COLOR_TEXT_PRIMARY,
                        weight=ft.FontWeight.BOLD, font_family=FONT_MONO,
                        width=70, text_align=ft.TextAlign.CENTER,
                    ),
                    ft.IconButton(
                        ft.Icons.ADD_CIRCLE_OUTLINE,
                        icon_size=18,
                        icon_color=COLOR_HP_FULL,
                        on_click=lambda e, r=res: self._increment_resource(r),
                        disabled=res.current_value >= res.max_value,
                        tooltip="Recupera 1",
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            ft.Row([ft.ProgressBar(
                value=ratio, color=bar_color,
                bgcolor=COLOR_BG_SECONDARY, height=6,
                border_radius=3, expand=True,
            )]),
        ], spacing=4)

    def _toggle_resource(self, res: ClassResource, use: bool):
        """Click su cerchietto: usa (●→○) o recupera (○→●)."""
        if use:
            res.current_value = max(0, res.current_value - 1)
        else:
            res.current_value = min(res.max_value, res.current_value + 1)
        character_repo.update_class_resource(res.id, res.current_value)
        self._refresh()

    def _decrement_resource(self, res: ClassResource):
        res.current_value = max(0, res.current_value - 1)
        character_repo.update_class_resource(res.id, res.current_value)
        self._refresh()

    def _increment_resource(self, res: ClassResource):
        res.current_value = min(res.max_value, res.current_value + 1)
        character_repo.update_class_resource(res.id, res.current_value)
        self._refresh()

    # ------------------------------------------------------------------
    # Tratti di Razza
    # ------------------------------------------------------------------

    def _section_racial_traits(self) -> ft.Container:
        """
        Sezione di riferimento rapido: resistenze e vantaggi ai TS razziali.
        Puramente informativa, nessuna interazione.
        """
        rt = self._race_traits
        rows: list[ft.Control] = []

        def _chip(label: str, icon: str, color: str) -> ft.Container:
            return ft.Container(
                content=ft.Row([
                    ft.Text(icon, size=14),
                    ft.Text(label, size=12, color=color,
                            weight=ft.FontWeight.W_600),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=f"{color}18",
                border=ft.Border.all(1, f"{color}60"),
                border_radius=16,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            )

        if rt["resistances"]:
            rows.append(ft.Text(
                "RESISTENZE", size=9, color=COLOR_TEXT_MUTED,
                weight=ft.FontWeight.BOLD,
                style=ft.TextStyle(letter_spacing=0.8),
            ))
            rows.append(ft.Row(
                [_chip(r, "🛡", COLOR_ACCENT_BLUE) for r in rt["resistances"]],
                spacing=6, wrap=True,
            ))

        if rt["advantage_saves"] and rows:
            rows.append(ft.Container(height=4))

        if rt["advantage_saves"]:
            rows.append(ft.Text(
                "VANTAGGIO AI TIRI SALVEZZA", size=9, color=COLOR_TEXT_MUTED,
                weight=ft.FontWeight.BOLD,
                style=ft.TextStyle(letter_spacing=0.8),
            ))
            rows.append(ft.Row(
                [_chip(s, "↑", COLOR_ACCENT_AMBER) for s in rt["advantage_saves"]],
                spacing=6, wrap=True,
            ))

        race_label = self.character.race or ""
        if self.character.subrace:
            race_label += f" · {self.character.subrace}"

        rows.append(ft.Container(height=2))
        rows.append(ft.Text(
            race_label, size=10, color=COLOR_TEXT_MUTED, italic=True,
        ))

        return ft.Container(
            content=ft.Column(rows, spacing=6),
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

    # ------------------------------------------------------------------
    # Abilità di Classe
    # ------------------------------------------------------------------

    def _load_class_features(self, c: Character) -> list[dict]:
        """
        Carica le feature base + sottoclasse dalla classe JSON,
        filtrate per livello ≤ livello personaggio.
        Ordina per livello poi per nome.
        """
        if not c.class_name:
            return []

        cls_data = _loader.get_class(c.class_name)
        if not cls_data:
            return []

        features: list[dict] = []

        # Feature base della classe
        for feat in cls_data.get("features", []):
            if feat.get("level", 1) <= c.level:
                features.append({
                    "level": feat["level"],
                    "name": feat["name"],
                    "description": feat.get("description", ""),
                    "source": c.class_name,
                })

        # Feature della sottoclasse selezionata
        subclass_name = (c.subclass or "").strip()
        if subclass_name:
            for sc in cls_data.get("subclasses", []):
                if sc.get("name", "").lower() == subclass_name.lower():
                    for feat in sc.get("features", []):
                        if feat.get("level", 1) <= c.level:
                            features.append({
                                "level": feat["level"],
                                "name": feat["name"],
                                "description": feat.get("description", ""),
                                "source": subclass_name,
                            })
                    break

        features.sort(key=lambda f: (f["level"], f["name"]))
        return features

    def _section_class_features(self) -> ft.Container:
        """
        Lista compatta delle abilità di classe disponibili al livello attuale.
        Ogni riga: badge livello + nome + fonte (sottoclasse se diversa).
        Click → dialog con descrizione completa.
        """
        def _open_feature_dialog(feat: dict, e=None):
            # Usa self._page direttamente: la closure viene invocata DOPO did_mount()
            if not self._page:
                return
                return
            page = self._page
            source_label = (
                f"  ·  {feat['source']}"
                if feat["source"].lower() != (self.character.class_name or "").lower()
                else ""
            )
            page.show_dialog(ft.AlertDialog(
                title=ft.Row([
                    ft.Container(
                        content=ft.Text(
                            f"Lv {feat['level']}",
                            size=10, color="#ffffff",
                            weight=ft.FontWeight.BOLD,
                        ),
                        bgcolor=COLOR_ACCENT_CRIMSON,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                        border_radius=4,
                    ),
                    ft.Container(width=8),
                    ft.Text(feat["name"], size=14, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE, expand=True),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                content=ft.Column([
                    ft.Text(
                        feat["description"] or "Nessuna descrizione disponibile.",
                        size=13, color=COLOR_TEXT_PRIMARY,
                        selectable=True,
                    ),
                    ft.Text(
                        f"{self.character.class_name}{source_label}",
                        size=11, color=COLOR_TEXT_MUTED, italic=True,
                    ) if source_label else ft.Container(height=0),
                ], spacing=10, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Chiudi",
                                  on_click=lambda ev: page.pop_dialog() if page else None),
                ],
                bgcolor=COLOR_BG_CARD,
            ))

        rows: list[ft.Control] = []
        current_level = -1
        for feat in self._features:
            # Separatore di livello
            if feat["level"] != current_level:
                current_level = feat["level"]
                if rows:
                    rows.append(ft.Divider(color=COLOR_BORDER, height=1))

            is_subclass = feat["source"].lower() != (self.character.class_name or "").lower()
            badge_color = COLOR_ACCENT_BLUE if is_subclass else COLOR_ACCENT_CRIMSON

            row = ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(
                            f"Lv{feat['level']}",
                            size=9, color="#ffffff",
                            weight=ft.FontWeight.BOLD,
                        ),
                        bgcolor=badge_color,
                        padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                        border_radius=3,
                        width=32,
                    ),
                    ft.Container(width=8),
                    ft.Text(
                        feat["name"],
                        size=13, color=COLOR_TEXT_PRIMARY,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=COLOR_TEXT_MUTED),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                on_click=lambda e, f=feat: _open_feature_dialog(f),
                ink=True,
                border_radius=4,
                padding=ft.Padding.symmetric(vertical=6, horizontal=4),
            )
            rows.append(row)

        legend = ft.Row([
            ft.Container(width=10, height=10, bgcolor=COLOR_ACCENT_CRIMSON,
                         border_radius=2),
            ft.Text(" classe base  ", size=10, color=COLOR_TEXT_MUTED),
            ft.Container(width=10, height=10, bgcolor=COLOR_ACCENT_BLUE,
                         border_radius=2),
            ft.Text(" sottoclasse", size=10, color=COLOR_TEXT_MUTED),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        return ft.Container(
            content=ft.Column([*rows, ft.Divider(color=COLOR_BORDER), legend], spacing=2),
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
            bgcolor=COLOR_BG_CARD,
        )
        f_roll = ft.TextField(
            label=f"Totale dadi tirati (escluso CON)",
            hint_text=f"es. {die // 2} per un dado",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_AMBER,
            bgcolor=COLOR_BG_CARD,
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
            # Riposto breve: risorse short_rest + slot Warlock (PHB p.107)
            character_repo.reset_class_resources(c.id, "short_rest")
            if c.class_name.strip().lower() == "warlock":
                character_repo.reset_all_spell_slots(c.id)
            page.pop_dialog()
            self._refresh()

        # Note classe-specifiche per il riposo breve
        class_key = c.class_name.strip().lower()
        extra_notes: list[ft.Control] = []
        if class_key == "warlock":
            extra_notes.append(ft.Text(
                "✦ Warlock: tutti gli slot del Patto della Magia vengono ripristinati.",
                size=11, color=COLOR_ACCENT_BLUE, italic=True,
            ))
        if class_key == "mago" and c.level >= 1:
            max_rec = (c.level + 1) // 2  # metà livello arrotondata per eccesso
            extra_notes.append(ft.Text(
                f"✦ Mago: puoi usare Recupero Arcano (1/riposo lungo) per recuperare "
                f"slot incantesimo per un totale di {max_rec} livelli (max Lv5 ciascuno). "
                f"Aggiorna manualmente gli slot nella scheda degli incantesimi.",
                size=11, color=COLOR_ACCENT_BLUE, italic=True,
            ))

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
                    *extra_notes,
                ],
                spacing=8,
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
            # Ripristina tutti gli slot incantesimo (usato=0)
            character_repo.reset_all_spell_slots(c.id)
            # Ricalcola i totali PHB — rimuove eventuali slot temporanei creati
            # con Incantesimi Flessibili (Stregone), che svaniscono al riposo lungo
            character_repo.auto_init_spell_slots(c.id, c.class_name or "", c.level)
            # Ripristina tutte le risorse di classe (short_rest e long_rest)
            character_repo.reset_class_resources(c.id, "short_rest")
            character_repo.reset_class_resources(c.id, "long_rest")
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
                    f"  ⚡  Risorse di classe ripristinate\n"
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
    # Sezione Forme Selvatiche (solo Druido)
    # ------------------------------------------------------------------

    def _section_forme(self) -> ft.Container:
        """
        Bestiary personale delle forme selvatiche del Druido.
        - Banner "In forma" se una forma è attiva (hp tracker + Esci).
        - Lista forme conosciute con tasto Trasformati.
        - Tasto "+ Aggiungi Forma" (ricerca nel bestiary Bestia).
        - Spillover HP: quando la forma scende a 0 hp chiede il danno totale
          e lo trasferisce al Druido.
        """
        rows: list[ft.Control] = []

        # ── Forma attiva ────────────────────────────────────────────────
        active = next((f for f in self._forme if f.is_active), None)
        if active:
            rows.append(self._active_forma_banner(active))
            rows.append(ft.Divider(height=8, color="transparent"))

        # ── Forme conosciute ────────────────────────────────────────────
        if not self._forme:
            rows.append(ft.Text(
                "Nessuna forma conosciuta.\nAggiungi le bestie in cui puoi trasformarti.",
                size=12, color=COLOR_TEXT_MUTED, text_align=ft.TextAlign.CENTER,
            ))
        else:
            for forma in self._forme:
                rows.append(self._forma_row(forma, active))

        rows.append(ft.Container(height=6))
        rows.append(ft.TextButton(
            "+ Aggiungi Forma",
            icon=ft.Icons.ADD,
            on_click=lambda _: self._open_creature_search("forma"),
        ))

        return ft.Container(
            content=ft.Column(rows, spacing=8),
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

    def _active_forma_banner(self, forma: CreatureEntry) -> ft.Container:
        """Banner grande per la forma selvatica attiva con tracker HP."""
        ratio = (forma.hp_current / forma.hp_max) if forma.hp_max > 0 else 0.0
        ratio = max(0.0, min(1.0, ratio))
        hp_color = COLOR_HP_FULL if ratio > 0.5 else (COLOR_HP_MID if ratio > 0.25 else COLOR_HP_LOW)

        def apply_damage(_e: ft.ControlEvent) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Danno", keyboard_type=ft.KeyboardType.NUMBER, width=120)

            def confirm(_ev: Any) -> None:
                try:
                    dmg = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = forma.hp_current - dmg
                if new_hp <= 0:
                    # Spillover: danno eccede i PF della forma
                    spillover = abs(new_hp)
                    character_repo.update_creature_hp(forma.id, 0)
                    character_repo.set_creature_active(forma.id, False)
                    page.pop_dialog()
                    self._spillover_dialog(spillover)
                else:
                    character_repo.update_creature_hp(forma.id, new_hp)
                    page.pop_dialog()
                    self._refresh()

            dlg = ft.AlertDialog(
                title=ft.Text(f"Danno a {forma.name}"),
                content=tf,
                actions=cast(list[ft.Control], [
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ]),
            )
            page.show_dialog(dlg)

        def apply_heal(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Cura", keyboard_type=ft.KeyboardType.NUMBER, width=120)

            def confirm(_ev: Any) -> None:
                try:
                    heal = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = min(forma.hp_max, forma.hp_current + heal)
                character_repo.update_creature_hp(forma.id, new_hp)
                page.pop_dialog()
                self._refresh()

            dlg = ft.AlertDialog(
                title=ft.Text(f"Cura {forma.name}"),
                content=tf,
                actions=cast(list[ft.Control], [
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ]),
            )
            page.show_dialog(dlg)

        def exit_form(_e: Any) -> None:
            character_repo.set_creature_active(forma.id, False, reset_hp=True)
            self._refresh()

        def _on_apply_damage(_e: Any) -> None: apply_damage(_e)  # type: ignore[arg-type]
        def _on_apply_heal(_e: Any) -> None: apply_heal(_e)  # type: ignore[arg-type]

        return ft.Container(
            content=ft.Column(cast(list[ft.Control], [
                ft.Row(cast(list[ft.Control], [
                    ft.Text("🐺 IN FORMA:", size=10, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.W_600),
                    ft.Text(forma.name.title(), size=14, color=COLOR_TEXT_PRIMARY,
                            weight=ft.FontWeight.BOLD, expand=True),
                    ft.TextButton("Esci dalla Forma", on_click=exit_form,
                                  style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON)),
                ]), vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row(cast(list[ft.Control], [
                    ft.Text(str(forma.hp_current), size=30, weight=ft.FontWeight.BOLD,
                            color=hp_color, font_family=FONT_MONO),
                    ft.Text(f" / {forma.hp_max} PF", size=14, color=COLOR_TEXT_MUTED,
                            font_family=FONT_MONO),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.REMOVE, on_click=_on_apply_damage,
                                  icon_color=COLOR_ACCENT_CRIMSON,
                                  tooltip="Applica danno"),
                    ft.IconButton(ft.Icons.ADD, on_click=_on_apply_heal,
                                  icon_color=COLOR_HP_FULL,
                                  tooltip="Cura"),
                ]), vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.ProgressBar(
                        value=ratio, height=6,
                        color=hp_color, bgcolor=COLOR_BG_SECONDARY,
                        expand=True,
                    )
                ]),
                ft.Text(f"CA {forma.ac}{' (' + forma.ac_note + ')' if forma.ac_note else ''} · {forma.speed}",
                        size=11, color=COLOR_TEXT_MUTED),
            ]), spacing=4),
            bgcolor=COLOR_BG_SECONDARY,
            padding=12,
            border_radius=8,
            border=ft.Border.all(1, COLOR_ACCENT_CRIMSON),
        )

    def _forma_row(self, forma: CreatureEntry, active: "CreatureEntry | None") -> ft.Container:
        """Riga compatta per una forma selvatica nel bestiary."""
        is_active = forma.is_active

        def trasformati(_e: Any) -> None:
            # Disattiva eventuale forma precedente (non si può stare in due forme)
            for f in self._forme:
                if f.is_active:
                    character_repo.set_creature_active(f.id, False, reset_hp=True)
            character_repo.set_creature_active(forma.id, True)
            self._refresh()

        def show_sheet(_e: Any) -> None:
            self._show_creature_sheet(forma)

        def remove(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            def confirm(_ev: Any) -> None:
                character_repo.delete_creature_entry(forma.id)
                page.pop_dialog()
                self._refresh()
            dlg = ft.AlertDialog(
                title=ft.Text("Rimuovi forma?"),
                content=ft.Text(f"Rimuovere {forma.name.title()} dal bestiary?"),
                actions=cast(list[ft.Control], [
                    ft.TextButton("Rimuovi", on_click=confirm,
                                  style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON)),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ]),
            )
            page.show_dialog(dlg)

        cr_text = f"GS {forma.cr}" if forma.cr else "GS —"
        hp_text = f"{forma.hp_max} PF ({forma.hp_formula})" if forma.hp_formula else f"{forma.hp_max} PF"

        return ft.Container(
            content=ft.Row([
                ft.GestureDetector(
                    content=ft.Column([
                        ft.Text(forma.name.title(), size=13, weight=ft.FontWeight.W_600,
                                color=COLOR_TEXT_PRIMARY),
                        ft.Text(f"{cr_text} · {hp_text} · CA {forma.ac}",
                                size=11, color=COLOR_TEXT_MUTED),
                    ], spacing=2),
                    on_tap=show_sheet,
                    expand=True,
                ),
                ft.Container(width=8),
                ft.ElevatedButton(
                    "Trasformati",
                    on_click=trasformati,
                    disabled=is_active or (active is not None and not is_active),
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON if not (active and not is_active) else COLOR_BG_SECONDARY,
                        color="#ffffff" if not (active and not is_active) else COLOR_TEXT_MUTED,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    ),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_color=COLOR_TEXT_MUTED,
                    on_click=remove,
                    tooltip="Rimuovi dal bestiary",
                    icon_size=18,
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=6, horizontal=2),
            border=ft.Border(
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
        )

    def _spillover_dialog(self, spillover: int) -> None:
        """Dialog che informa del danno spillover al personaggio dopo la forma a 0 HP."""
        if not self._page:
            return
        page = self._page
        c = self.character
        new_hp = max(0, c.hp_current - spillover)

        def apply(_e: Any) -> None:
            character_repo.update_hp(c.id, new_hp)
            page.pop_dialog()
            self._refresh()

        def dismiss(_e: Any) -> None:
            page.pop_dialog()
            self._refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("⚠️ Forma a 0 PF!"),
            content=ft.Column([
                ft.Text("La forma selvatica ha esaurito i suoi Punti Ferita.", size=13),
                ft.Container(height=4),
                ft.Text(f"Danno spillover: {spillover} PF", size=13,
                        weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON),
                ft.Text(f"PF {c.name}: {c.hp_current} → {new_hp}", size=13),
                ft.Container(height=4),
                ft.Text("Se il danno spillover supera i tuoi PF massimi, cadi immediatamente privo di sensi.",
                        size=11, color=COLOR_TEXT_MUTED),
            ], spacing=2, tight=True),
            actions=cast(list[ft.Control], [
                ft.TextButton("Applica danno al personaggio", on_click=apply,
                              style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON)),
                ft.TextButton("Ignora (gestione manuale)", on_click=dismiss),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Sezione Evocazioni (tutti i personaggi)
    # ------------------------------------------------------------------

    def _section_evocazioni(self) -> ft.Container:
        """
        Bestiary delle evocazioni del personaggio.
        - Evocazioni attive: HP tracker + tasto Elimina (rimuove dall'attivo).
        - Bestiary: lista con tasto Evoca + tasto rimuovi.
        - Tasto "+ Evoca" per aggiungere dal bestiary mostri.
        """
        rows: list[ft.Control] = []

        # ── Evocazioni attive ───────────────────────────────────────────
        active_evocs = [e for e in self._evocazioni if e.is_active]
        if active_evocs:
            rows.append(ft.Text("In campo", size=11, color=COLOR_TEXT_MUTED,
                                weight=ft.FontWeight.W_600))
            for evoc in active_evocs:
                rows.append(self._active_evocazione_card(evoc))
            rows.append(ft.Divider(height=8, color=COLOR_BORDER))

        # ── Bestiary evocazioni ────────────────────────────────────────
        inactive = [e for e in self._evocazioni if not e.is_active]
        if not self._evocazioni:
            rows.append(ft.Text(
                "Nessuna evocazione salvata.\nEvoca creature tramite incantesimi e aggiungile qui.",
                size=12, color=COLOR_TEXT_MUTED, text_align=ft.TextAlign.CENTER,
            ))
        elif inactive:
            rows.append(ft.Text("Bestiary evocazioni", size=11, color=COLOR_TEXT_MUTED,
                                weight=ft.FontWeight.W_600))
            for evoc in inactive:
                rows.append(self._evocazione_row(evoc))

        rows.append(ft.Container(height=6))
        rows.append(ft.TextButton(
            "+ Evoca",
            icon=ft.Icons.ADD,
            on_click=lambda _: self._open_creature_search("evocazione"),
        ))

        return ft.Container(
            content=ft.Column(rows, spacing=8),
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

    def _active_evocazione_card(self, evoc: CreatureEntry) -> ft.Container:
        """Card con HP tracker per un'evocazione attiva in campo."""
        ratio = (evoc.hp_current / evoc.hp_max) if evoc.hp_max > 0 else 0.0
        ratio = max(0.0, min(1.0, ratio))
        hp_color = COLOR_HP_FULL if ratio > 0.5 else (COLOR_HP_MID if ratio > 0.25 else COLOR_HP_LOW)

        def apply_damage(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Danno", keyboard_type=ft.KeyboardType.NUMBER, width=120)

            def confirm(_ev: Any) -> None:
                try:
                    dmg = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = evoc.hp_current - dmg
                if new_hp <= 0:
                    # Evocazione a 0 HP: rimuove dall'attivo ma non dal bestiary
                    character_repo.update_creature_hp(evoc.id, 0)
                    character_repo.set_creature_active(evoc.id, False, reset_hp=False)
                    page.pop_dialog()
                    # Mostra avviso
                    page.show_dialog(ft.AlertDialog(
                        title=ft.Text("Evocazione eliminata"),
                        content=ft.Text(
                            f"{evoc.name.title()} ha raggiunto 0 PF ed è stata rimossa dal campo.\n"
                            "La voce rimane nel tuo bestiary per future evocazioni."
                        ),
                        actions=[ft.TextButton("OK", on_click=lambda _:
                            (page.pop_dialog(), self._refresh()) if self._page else None)],
                    ))
                else:
                    character_repo.update_creature_hp(evoc.id, new_hp)
                    page.pop_dialog()
                    self._refresh()

            dlg = ft.AlertDialog(
                title=ft.Text(f"Danno a {evoc.name.title()}"),
                content=tf,
                actions=cast(list[ft.Control], [
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ]),
            )
            page.show_dialog(dlg)

        def apply_heal(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Cura", keyboard_type=ft.KeyboardType.NUMBER, width=120)

            def confirm(_ev: Any) -> None:
                try:
                    heal = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = min(evoc.hp_max, evoc.hp_current + heal)
                character_repo.update_creature_hp(evoc.id, new_hp)
                page.pop_dialog()
                self._refresh()

            dlg = ft.AlertDialog(
                title=ft.Text(f"Cura {evoc.name.title()}"),
                content=tf,
                actions=cast(list[ft.Control], [
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ]),
            )
            page.show_dialog(dlg)

        def dismiss_evocation(_e: Any) -> None:
            """Libera l'evocazione (torna al bestiary con HP resettati)."""
            character_repo.set_creature_active(evoc.id, False, reset_hp=True)
            self._refresh()

        def show_sheet(_e: Any) -> None:
            self._show_creature_sheet(evoc)

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.GestureDetector(
                        content=ft.Text(evoc.name.title(), size=13, weight=ft.FontWeight.W_600,
                                        color=COLOR_TEXT_PRIMARY),
                        on_tap=show_sheet,
                    ),
                    ft.Text(f" — GS {evoc.cr}" if evoc.cr else "", size=11, color=COLOR_TEXT_MUTED),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.REMOVE, on_click=apply_damage,
                                  icon_color=COLOR_ACCENT_CRIMSON, icon_size=18,
                                  tooltip="Applica danno"),
                    ft.IconButton(ft.Icons.ADD, on_click=apply_heal,
                                  icon_color=COLOR_HP_FULL, icon_size=18,
                                  tooltip="Cura"),
                    ft.IconButton(ft.Icons.CLOSE, on_click=dismiss_evocation,
                                  icon_color=COLOR_TEXT_MUTED, icon_size=18,
                                  tooltip="Libera (fine combattimento)"),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                ft.Row([
                    ft.Text(str(evoc.hp_current), size=22, weight=ft.FontWeight.BOLD,
                            color=hp_color, font_family=FONT_MONO),
                    ft.Text(f" / {evoc.hp_max} PF", size=12, color=COLOR_TEXT_MUTED,
                            font_family=FONT_MONO),
                    ft.Container(expand=True),
                    ft.Text(f"CA {evoc.ac}", size=12, color=COLOR_TEXT_MUTED),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.ProgressBar(value=ratio, height=5, color=hp_color,
                                   bgcolor=COLOR_BG_SECONDARY, expand=True)
                ]),
            ], spacing=4),
            bgcolor=COLOR_BG_SECONDARY,
            padding=10,
            border_radius=6,
            border=ft.Border.all(1, COLOR_ACCENT_BLUE),
        )

    def _evocazione_row(self, evoc: CreatureEntry) -> ft.Container:
        """Riga compatta per un'evocazione nel bestiary (non attiva)."""

        def evoca(_e: Any) -> None:
            character_repo.set_creature_active(evoc.id, True, reset_hp=True)
            self._refresh()

        def show_sheet(_e: Any) -> None:
            self._show_creature_sheet(evoc)

        def remove(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            def confirm(_ev: Any) -> None:
                character_repo.delete_creature_entry(evoc.id)
                page.pop_dialog()
                self._refresh()
            dlg = ft.AlertDialog(
                title=ft.Text("Rimuovi evocazione?"),
                content=ft.Text(f"Rimuovere {evoc.name.title()} dal bestiary?"),
                actions=cast(list[ft.Control], [
                    ft.TextButton("Rimuovi", on_click=confirm,
                                  style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON)),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ]),
            )
            page.show_dialog(dlg)

        cr_text = f"GS {evoc.cr}" if evoc.cr else "GS —"
        hp_text = f"{evoc.hp_max} PF"

        return ft.Container(
            content=ft.Row([
                ft.GestureDetector(
                    content=ft.Column([
                        ft.Text(evoc.name.title(), size=13, weight=ft.FontWeight.W_600,
                                color=COLOR_TEXT_PRIMARY),
                        ft.Text(f"{cr_text} · {hp_text} · CA {evoc.ac}",
                                size=11, color=COLOR_TEXT_MUTED),
                    ], spacing=2),
                    on_tap=show_sheet,
                    expand=True,
                ),
                ft.ElevatedButton(
                    "Evoca",
                    on_click=evoca,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_BLUE,
                        color="#ffffff",
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    ),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_color=COLOR_TEXT_MUTED,
                    on_click=remove,
                    tooltip="Rimuovi dal bestiary",
                    icon_size=18,
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=6, horizontal=2),
            border=ft.Border(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

    # ------------------------------------------------------------------
    # Dialog ricerca creatura (condiviso tra Forme e Evocazioni) — Task #3/4
    # ------------------------------------------------------------------

    def _open_creature_search(self, entry_type: str) -> None:
        """
        Dialog di ricerca nel bestiary con filtri tipo/GS e vista dettaglio inline.
        Due stati nella stessa AlertDialog (no dialog annidati):
          - LIST  : filtri + lista scrollabile; click riga → DETAIL
          - DETAIL: scheda completa; ← torna lista; bottone evoca/aggiungi
        entry_type = "forma"      → filtra solo Bestie
                   = "evocazione" → tutte le creature
        """
        if not self._page:
            return
        page = self._page
        import json as _json
        from pathlib import Path

        # ── Carica monsters.json ──────────────────────────────────────────
        monsters_path = (
            Path(__file__).parent.parent.parent.parent / "data" / "game_data" / "monsters.json"
        )
        try:
            all_monsters: list[dict] = _json.loads(monsters_path.read_text(encoding="utf-8"))
        except Exception:
            all_monsters = []

        # Forma Selvatica → solo Bestie; Evocazione → tutto
        if entry_type == "forma":
            pool = [m for m in all_monsters if m.get("type") == "Bestia"]
        else:
            pool = all_monsters

        title_label = "Aggiungi Forma Selvatica" if entry_type == "forma" else "Evoca Creatura"
        existing_names = {
            e.name.upper()
            for e in (self._forme if entry_type == "forma" else self._evocazioni)
        }

        # ── Helper CR ────────────────────────────────────────────────────
        def cr_to_float(cr: Any) -> float:
            if not cr or cr in ("—", ""):
                return 9999.0
            s = str(cr)
            if "/" in s:
                try:
                    a, b = s.split("/")
                    return int(a) / int(b)
                except Exception:
                    return 9999.0
            try:
                return float(s)
            except Exception:
                return 9999.0

        # ── Opzioni filtri ───────────────────────────────────────────────
        all_types = sorted({m.get("type", "") for m in pool if m.get("type")})
        cr_vals_raw = sorted(
            {m.get("cr", "") for m in pool if m.get("cr")},
            key=cr_to_float,
        )

        # ── Stato mutabile condiviso tra chiusure ────────────────────────
        state: dict[str, Any] = {
            "mode": "list",     # "list" | "detail"
            "type_filter": "",
            "cr_max": "",
            "query": "",
        }
        # Placeholder per il dialog (assegnato più avanti)
        dlg: Any = None

        # ── Widget lista persistenti tra ri-render ────────────────────────
        type_dd = ft.Dropdown(
            label="Tipo",
            options=[
                ft.DropdownOption(key="", text="Tutti"),
            ] + [ft.DropdownOption(key=t, text=t) for t in all_types],
            value="",
            width=148,
            dense=True,
            text_size=12,
            border_radius=6,
        )
        cr_dd = ft.Dropdown(
            label="GS max",
            options=[
                ft.DropdownOption(key="", text="Tutti"),
            ] + [ft.DropdownOption(key=str(v), text=f"GS {v}") for v in cr_vals_raw],
            value="",
            width=112,
            dense=True,
            text_size=12,
            border_radius=6,
        )
        search_tf = ft.TextField(
            label="Cerca per nome...",
            prefix_icon=ft.Icons.SEARCH,
            autofocus=True,
            border_radius=8,
            dense=True,
            text_size=13,
        )
        results_col = ft.Column([], spacing=3, scroll=ft.ScrollMode.AUTO, height=270)

        # ── Filtra pool ──────────────────────────────────────────────────
        def _filtered_pool() -> list[dict]:
            q = state["query"].strip().upper()
            tf = state["type_filter"]
            cm = state["cr_max"]
            cr_limit = cr_to_float(cm) if cm else 9999.0
            out: list[dict] = []
            for m in pool:
                if tf and m.get("type", "") != tf:
                    continue
                if cr_to_float(m.get("cr", "")) > cr_limit + 1e-9:
                    continue
                if q and q not in m["name"].upper():
                    continue
                out.append(m)
            return out[:60]

        # ── Popola lista ─────────────────────────────────────────────────
        def _populate_list() -> None:
            filtered = _filtered_pool()
            results_col.controls.clear()
            for m in filtered:
                already = m["name"].upper() in existing_names
                cr_str = f"GS {m['cr']}" if m.get("cr") else "GS —"
                type_str = m.get("type", "")

                def _go_detail(_e: Any, mon: dict = m) -> None:
                    _show_detail(mon)

                results_col.controls.append(ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(
                                monster_display_name(m["name"]),
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=COLOR_TEXT_PRIMARY,
                            ),
                            ft.Text(
                                f"{type_str} · {cr_str} · {m.get('hp_max', '?')} PF",
                                size=11,
                                color=COLOR_TEXT_MUTED,
                            ),
                        ], spacing=1, expand=True),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, color=COLOR_TEXT_MUTED, size=18),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    border=ft.Border(bottom=ft.BorderSide(1, COLOR_BORDER)),
                    on_click=_go_detail,
                    ink=True,
                ))
            try:
                results_col.update()
            except RuntimeError:
                pass

        # ── Costruisce contenuto stato LISTA ─────────────────────────────
        def _list_content() -> ft.Column:
            return ft.Column(
                cast(list[ft.Control], [
                    ft.Row([type_dd, cr_dd], spacing=8),
                    ft.Container(height=4),
                    search_tf,
                    ft.Container(height=6),
                    results_col,
                    ft.Container(height=4),
                    ft.TextButton(
                        "Inserimento manuale (creatura non trovata)",
                        icon=ft.Icons.EDIT,
                        on_click=_manual_entry,
                        style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                    ),
                ]),
                spacing=4,
                tight=True,
            )

        # ── Costruisce contenuto stato DETTAGLIO (da dict JSON) ───────────
        def _detail_content(m: dict) -> ft.Column:
            def stat_col_d(abbr: str, score: int) -> ft.Column:
                mod = (score - 10) // 2
                sign = "+" if mod >= 0 else ""
                return ft.Column([
                    ft.Text(abbr, size=10, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.W_600,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text(str(score), size=16, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text(f"{sign}{mod}", size=11, color=COLOR_TEXT_MUTED,
                            text_align=ft.TextAlign.CENTER),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

            def feat_tile(name: str, text: str) -> ft.Container:
                return ft.Container(
                    content=ft.Column([
                        ft.Text(name, size=12, weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_PRIMARY, italic=True),
                        ft.Text(text, size=11, color=COLOR_TEXT_SECONDARY),
                    ], spacing=2),
                    padding=ft.Padding.only(bottom=6),
                )

            def info_r(label: str, value: str) -> ft.Row | None:
                if not value:
                    return None
                return ft.Row([
                    ft.Text(label + ":", size=11, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.W_600),
                    ft.Container(width=4),
                    ft.Text(value, size=11, color=COLOR_TEXT_PRIMARY, expand=True),
                ])

            stats_row = ft.Row([
                stat_col_d("FOR", int(m.get("str_score", 10))),
                stat_col_d("DES", int(m.get("dex_score", 10))),
                stat_col_d("COS", int(m.get("con_score", 10))),
                stat_col_d("INT", int(m.get("int_score", 10))),
                stat_col_d("SAG", int(m.get("wis_score", 10))),
                stat_col_d("CAR", int(m.get("cha_score", 10))),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY)

            info_items: list[ft.Control] = []
            ac_note = m.get("ac_note", "")
            for lbl, val in [
                ("CA",     f"{m.get('ac', 10)}{' (' + ac_note + ')' if ac_note else ''}"),
                ("PF",     str(m.get("hp_max", "—"))),
                ("Velocità", str(m.get("speed", ""))),
                ("GS",     str(m.get("cr", "—"))),
                ("Allineamento", m.get("alignment", "")),
                ("Sensi",  m.get("senses", "")),
                ("Linguaggi", m.get("languages", "")),
                ("Resistenze", m.get("damage_resistances", "")),
                ("Immunità danni", m.get("damage_immunities", "")),
                ("Immunità condizioni", m.get("condition_immunities", "")),
            ]:
                r = info_r(lbl, val)
                if r:
                    info_items.append(r)

            def _parse_list(field: str) -> list[dict]:
                raw = m.get(field, [])
                if isinstance(raw, str):
                    try:
                        return _json.loads(raw)
                    except Exception:
                        return []
                return raw if isinstance(raw, list) else []

            traits_l  = _parse_list("traits")
            actions_l = _parse_list("actions")
            leg_l     = _parse_list("legendary_actions")

            features: list[ft.Control] = []
            if traits_l:
                features.append(ft.Text("Tratti", size=12, weight=ft.FontWeight.BOLD,
                                        color=COLOR_ACCENT_CRIMSON))
                for t in traits_l:
                    features.append(feat_tile(t.get("name", ""), t.get("text", "")))
            if actions_l:
                features.append(ft.Text("Azioni", size=12, weight=ft.FontWeight.BOLD,
                                        color=COLOR_ACCENT_CRIMSON))
                for a in actions_l:
                    features.append(feat_tile(a.get("name", ""), a.get("text", "")))
            if leg_l:
                features.append(ft.Text("Azioni Leggendarie", size=12,
                                        weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON))
                for la in leg_l:
                    features.append(feat_tile(la.get("name", ""), la.get("text", "")))

            items: list[ft.Control] = cast(list[ft.Control], [
                ft.Text(
                    f"{m.get('type', '?')} · {m.get('alignment', '—')}",
                    size=11, color=COLOR_TEXT_MUTED, italic=True,
                ),
                ft.Divider(height=10, color=COLOR_BORDER),
                stats_row,
                ft.Divider(height=10, color=COLOR_BORDER),
                *info_items,
            ])
            if features:
                items.append(ft.Divider(height=10, color=COLOR_BORDER))
                items.extend(features)

            return ft.Column(items, spacing=6, scroll=ft.ScrollMode.AUTO)

        # ── Transizione a DETTAGLIO ──────────────────────────────────────
        def _show_detail(m: dict) -> None:
            already = m["name"].upper() in existing_names
            btn_label = (
                "✓ Già presente" if already
                else ("✔ Aggiungi al Bestiary" if entry_type == "forma" else "✔ Evoca")
            )
            btn_color = COLOR_ACCENT_CRIMSON if entry_type == "forma" else COLOR_ACCENT_BLUE

            def _do_add(_e: Any) -> None:
                _save_creature(m)

            def _go_back(_e: Any) -> None:
                state["mode"] = "list"
                dlg.content = ft.Container(content=_list_content(), height=480)
                dlg.title = ft.Text(title_label)
                dlg.actions = cast(list[ft.Control], [
                    ft.TextButton("Chiudi", on_click=lambda _: page.pop_dialog()),
                ])
                try:
                    page.update()
                except RuntimeError:
                    pass

            add_btn = ft.ElevatedButton(
                btn_label,
                icon=ft.Icons.CHECK if already else ft.Icons.ADD,
                disabled=already,
                on_click=_do_add,
                style=ft.ButtonStyle(
                    bgcolor=btn_color if not already else None,
                    color="#ffffff" if not already else COLOR_TEXT_MUTED,
                ),
            )

            dlg.content = ft.Container(content=_detail_content(m), height=480)
            dlg.title = ft.Row([
                ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    on_click=_go_back,
                    tooltip="Torna alla lista",
                    icon_color=COLOR_TEXT_SECONDARY,
                ),
                ft.Text(
                    monster_display_name(m["name"]),
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    expand=True,
                ),
            ])
            dlg.actions = cast(list[ft.Control], [
                add_btn,
                ft.TextButton("Chiudi", on_click=lambda _: page.pop_dialog()),
            ])
            try:
                page.update()
            except RuntimeError:
                pass

        # ── Salva nel DB e chiude ────────────────────────────────────────
        def _save_creature(m: dict) -> None:
            entry = character_repo.create_creature_entry(
                character_id=self.character.id,
                entry_type=entry_type,
                name=m["name"],
                creature_type=m.get("type", ""),
                alignment=m.get("alignment", ""),
                cr=str(m.get("cr", "")),
                ac=int(m.get("ac", 10)),
                ac_note=m.get("ac_note", ""),
                hp_max=int(m.get("hp_max", 1)),
                hp_formula=m.get("hp_formula", ""),
                speed=m.get("speed", ""),
                str_score=int(m.get("str_score", 10)),
                dex_score=int(m.get("dex_score", 10)),
                con_score=int(m.get("con_score", 10)),
                int_score=int(m.get("int_score", 10)),
                wis_score=int(m.get("wis_score", 10)),
                cha_score=int(m.get("cha_score", 10)),
                saving_throws=_json.dumps(m.get("saving_throws", {})),
                skills=_json.dumps(m.get("skills", {})),
                damage_vulnerabilities=m.get("damage_vulnerabilities", ""),
                damage_resistances=m.get("damage_resistances", ""),
                damage_immunities=m.get("damage_immunities", ""),
                condition_immunities=m.get("condition_immunities", ""),
                senses=m.get("senses", ""),
                languages=m.get("languages", ""),
                traits=_json.dumps(m.get("traits", [])),
                actions=_json.dumps(m.get("actions", [])),
                legendary_actions=_json.dumps(m.get("legendary_actions", [])),
                source_page=int(m.get("source_page", 0)),
            )
            if entry:
                if entry_type == "evocazione":
                    character_repo.set_creature_active(entry.id, True)
                page.pop_dialog()
                self._refresh()

        # ── Apertura dialog manuale ──────────────────────────────────────
        def _manual_entry(_e: Any) -> None:
            page.pop_dialog()
            self._open_manual_creature_dialog(entry_type)

        # ── Handler filtri ───────────────────────────────────────────────
        def _on_type_select(_e: Any) -> None:
            state["type_filter"] = type_dd.value or ""
            _populate_list()

        def _on_cr_select(_e: Any) -> None:
            state["cr_max"] = cr_dd.value or ""
            _populate_list()

        def _on_search_change(_e: Any) -> None:
            state["query"] = search_tf.value or ""
            _populate_list()

        cast(Any, type_dd).on_select = _on_type_select
        cast(Any, cr_dd).on_select = _on_cr_select
        cast(Any, search_tf).on_change = _on_search_change

        _populate_list()

        dlg = ft.AlertDialog(
            title=ft.Text(title_label),
            content=ft.Container(content=_list_content(), height=480),
            actions=cast(list[ft.Control], [
                ft.TextButton("Chiudi", on_click=lambda _: page.pop_dialog()),
            ]),
        )
        page.show_dialog(dlg)

    def _open_manual_creature_dialog(self, entry_type: str) -> None:
        """Dialog per inserire manualmente una creatura non presente nel bestiary."""
        if not self._page:
            return
        page = self._page

        f_name = ft.TextField(label="Nome*", autofocus=True)
        f_type = ft.TextField(label="Tipo (es. Bestia, Elementale)")
        f_cr   = ft.TextField(label="Grado Sfida (es. 1/4, 5)")
        f_ac   = ft.TextField(label="CA", value="10", keyboard_type=ft.KeyboardType.NUMBER, width=90)
        f_hp   = ft.TextField(label="PF massimi*", keyboard_type=ft.KeyboardType.NUMBER, width=120)
        f_speed= ft.TextField(label="Velocità (es. 9 m)")

        def save(_e: Any) -> None:
            if not f_name.value or not f_hp.value:
                return
            try:
                hp_max = int(f_hp.value)
                ac = int(f_ac.value or "10")
            except ValueError:
                return
            entry = character_repo.create_creature_entry(
                character_id=self.character.id,
                entry_type=entry_type,
                name=f_name.value.upper(),
                creature_type=f_type.value or "",
                cr=f_cr.value or "",
                ac=ac,
                hp_max=hp_max,
                speed=f_speed.value or "",
            )
            if entry and entry_type == "evocazione":
                character_repo.set_creature_active(entry.id, True)
            if self._page:
                page.pop_dialog()
            self._refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Inserimento manuale"),
            content=ft.Column([
                f_name,
                ft.Row([f_type, ft.Container(width=8), f_cr], spacing=0),
                ft.Row([f_ac, ft.Container(width=8), f_hp], spacing=0),
                f_speed,
            ], spacing=10, tight=True),
            actions=cast(list[ft.Control], [
                ft.TextButton("Salva", on_click=save),
                ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Dialog scheda creatura completa (condiviso) — Task #5
    # ------------------------------------------------------------------

    def _show_creature_sheet(self, c: CreatureEntry) -> None:
        """
        AlertDialog con scheda completa della creatura:
        CA, HP, velocità, 6 stat, TS, skill, resistenze, sensi, lingue, CR,
        tratti e azioni (scrollabile).
        """
        if not self._page:
            return
        page = self._page
        import json as _json

        def stat_col(abbr: str, score: int) -> ft.Column:
            mod = (score - 10) // 2
            sign = "+" if mod >= 0 else ""
            return ft.Column([
                ft.Text(abbr, size=10, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                ft.Text(str(score), size=16, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_PRIMARY, text_align=ft.TextAlign.CENTER),
                ft.Text(f"{sign}{mod}", size=11, color=COLOR_TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER),
            ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        def feature_tile(name: str, text: str) -> ft.Container:
            return ft.Container(
                content=ft.Column([
                    ft.Text(name, size=12, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY, italic=True),
                    ft.Text(text, size=11, color=COLOR_TEXT_SECONDARY),
                ], spacing=2),
                padding=ft.Padding.only(bottom=8),
            )

        def info_row(label: str, value: str) -> ft.Row | None:
            if not value:
                return None
            return ft.Row([
                ft.Text(label + ":", size=11, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.W_600),
                ft.Container(width=4),
                ft.Text(value, size=11, color=COLOR_TEXT_PRIMARY, expand=True),
            ])

        # Stat block
        stats_row = ft.Row([
            stat_col("FOR", c.str_score),
            stat_col("DES", c.dex_score),
            stat_col("COS", c.con_score),
            stat_col("INT", c.int_score),
            stat_col("SAG", c.wis_score),
            stat_col("CAR", c.cha_score),
        ], alignment=ft.MainAxisAlignment.SPACE_EVENLY)

        # Info block
        info_items: list[ft.Control] = []
        for lbl, val in [
            ("CA", f"{c.ac}{' (' + c.ac_note + ')' if c.ac_note else ''}"),
            ("PF", f"{c.hp_max}" + (f" ({c.hp_formula})" if c.hp_formula else "")),
            ("Velocità", c.speed),
            ("GS", c.cr or "—"),
            ("Allineamento", c.alignment),
        ]:
            row = info_row(lbl, val)
            if row:
                info_items.append(row)

        # TS e skill
        try:
            ts_dict: dict = _json.loads(c.saving_throws)
        except Exception:
            ts_dict = {}
        try:
            sk_dict: dict = _json.loads(c.skills)
        except Exception:
            sk_dict = {}

        if ts_dict:
            ts_str = ", ".join(f"{k} {v}" for k, v in ts_dict.items())
            r = info_row("Tiri Salvezza", ts_str)
            if r:
                info_items.append(r)
        if sk_dict:
            sk_str = ", ".join(f"{k} {v}" for k, v in sk_dict.items())
            r = info_row("Abilità", sk_str)
            if r:
                info_items.append(r)

        for lbl, val in [
            ("Vulnerabilità", c.damage_vulnerabilities),
            ("Resistenze",    c.damage_resistances),
            ("Immunità danni", c.damage_immunities),
            ("Immunità condizioni", c.condition_immunities),
            ("Sensi", c.senses),
            ("Linguaggi", c.languages),
        ]:
            r = info_row(lbl, val)
            if r:
                info_items.append(r)

        # Tratti e azioni
        try:
            traits: list[dict] = _json.loads(c.traits) if isinstance(c.traits, str) else c.traits
        except Exception:
            traits = []
        try:
            actions: list[dict] = _json.loads(c.actions) if isinstance(c.actions, str) else c.actions
        except Exception:
            actions = []
        try:
            leg_actions: list[dict] = _json.loads(c.legendary_actions) if isinstance(c.legendary_actions, str) else c.legendary_actions
        except Exception:
            leg_actions = []

        features_col: list[ft.Control] = []
        if traits:
            features_col.append(ft.Text("Tratti", size=12, weight=ft.FontWeight.BOLD,
                                        color=COLOR_ACCENT_CRIMSON))
            for t in traits:
                features_col.append(feature_tile(t.get("name", ""), t.get("text", "")))
        if actions:
            features_col.append(ft.Text("Azioni", size=12, weight=ft.FontWeight.BOLD,
                                        color=COLOR_ACCENT_CRIMSON))
            for a in actions:
                features_col.append(feature_tile(a.get("name", ""), a.get("text", "")))
        if leg_actions:
            features_col.append(ft.Text("Azioni Leggendarie", size=12, weight=ft.FontWeight.BOLD,
                                        color=COLOR_ACCENT_CRIMSON))
            for la in leg_actions:
                features_col.append(feature_tile(la.get("name", ""), la.get("text", "")))

        content = ft.Column(
            [
                # Tipo e taglia
                ft.Text(
                    f"{c.creature_type or '?'} · {c.alignment or '—'}",
                    size=11, color=COLOR_TEXT_MUTED, italic=True,
                ),
                ft.Divider(height=10, color=COLOR_BORDER),
                stats_row,
                ft.Divider(height=10, color=COLOR_BORDER),
                *info_items,
            ] + ([ft.Divider(height=10, color=COLOR_BORDER)] if features_col else [])
              + features_col,
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
        )

        dlg = ft.AlertDialog(
            title=ft.Text(monster_display_name(c.name), size=16,
                          weight=ft.FontWeight.BOLD),
            content=ft.Container(content=content, height=480),
            actions=cast(list[ft.Control], [
                ft.TextButton("Chiudi", on_click=lambda _: page.pop_dialog()),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        self._slots     = character_repo.get_spell_slots(self.character.id)
        self._profs     = character_repo.get_proficiencies(self.character.id)
        self._weapons   = character_repo.get_weapons(self.character.id)
        self._prepared  = character_repo.get_prepared_spells(self.character.id)
        self._resources = character_repo.get_class_resources(self.character.id)
        self._features     = self._load_class_features(self.character)
        self._race_traits  = get_race_display_traits(
            self.character.race or "", self.character.subrace or ""
        )
        self._forme = character_repo.get_creature_entries(self.character.id, entry_type="forma")
        self._evocazioni = character_repo.get_creature_entries(self.character.id, entry_type="evocazione")
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        if self._on_refresh:
            self._on_refresh()
