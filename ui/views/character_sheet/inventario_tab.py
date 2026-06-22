"""
Tab Inventario della scheda personaggio.

Struttura (ListView scrollabile):
  - Monete          — MR / MA / ME / MO / MP con editing inline
  - Peso            — peso attuale / capacità massima (FOR × 7.5 kg)
  - Armi            — lista con aggiunta / modifica / elimina / equipaggia toggle
  - Oggetti         — lista per categoria con aggiunta / modifica / elimina
"""

import flet as ft
import json
import logging
from typing import Any, cast
from config.settings import *
from data.models import Character, Currency, InventoryItem, Weapon
import data.repositories.character_repo as character_repo
from ui.theme import section_header, muted_text, label_text

logger = logging.getLogger(__name__)

_CARRY_PER_STR = 7.5   # kg per punto Forza — PHB p.176

_CATEGORY_LABELS = {
    "armor":  "Armature & Scudi",
    "weapon": "Armi (riserva)",
    "tool":   "Strumenti",
    "magic":  "Oggetti Magici",
    "misc":   "Varie",
}
_DAMAGE_TYPES = [
    "Taglio", "Perforazione", "Contundente",
    "Fuoco", "Freddo", "Fulmine", "Tuono",
    "Acido", "Veleno", "Psichico", "Radiante",
    "Necrotico", "Forza", "—",
]
_WEAPON_PROPERTIES = [
    "Accurata",        # Finesse — usa FOR o DES
    "A due mani",      # Two-Handed
    "Da lancio",       # Thrown
    "Leggera",         # Light — attacco con due armi
    "Lunga gittata",   # Long range (per archi/balestre)
    "Munizioni",       # Ammunition
    "Pesante",         # Heavy — svantaggio per razze piccole
    "Portata",         # Reach — +1,5 m di portata
    "Speciale",        # Special (regola propria)
    "Versatile",       # Versatile — uso a 1 o 2 mani
    "Carica",          # Loading — un solo attacco per azione
    "Lanciabile",      # (arma lanciabile generica)
]
_CATEGORIES = ["misc", "armor", "weapon", "tool", "magic"]


class InventarioTab(ft.ListView):
    """
    Tab inventario: monete, peso, armi (CRUD), oggetti (CRUD).
    """

    def __init__(self, character: Character):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._page: ft.Page | None = None
        self._currencies: Currency | None = character_repo.get_currencies(character.id)
        self._weapons: list[Weapon] = character_repo.get_weapons(character.id, equipped_only=False)
        self._items: list[InventoryItem] = character_repo.get_inventory(character.id)
        try:
            self._build()
        except Exception as exc:
            logger.error("InventarioTab._build() fallito: %s", exc, exc_info=True)
            self.controls.clear()
            self.controls.append(ft.Text(f"Errore caricamento inventario: {exc}",
                                         color=COLOR_ACCENT_CRIMSON, size=13))

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # IMPORTANTE: modificare self.controls IN-PLACE.
        # In Flet 0.85.3, self.controls = [...] rimpiazza la ControlsList interna
        # che Flutter usa per il rendering → schermata bianca.
        self.controls.clear()
        self.controls.append(section_header("Monete"))
        self.controls.append(self._section_monete())
        self.controls.append(section_header("Peso"))
        self.controls.append(self._section_peso())
        self.controls.append(section_header("Armi"))
        self.controls.append(self._section_armi())
        self.controls.append(section_header("Oggetti"))
        self.controls.append(self._section_oggetti())

    # ------------------------------------------------------------------
    # Monete
    # ------------------------------------------------------------------

    def _section_monete(self) -> ft.Container:
        cur = self._currencies
        values = {
            "MR": cur.copper   if cur else 0,
            "MA": cur.silver   if cur else 0,
            "ME": cur.electrum if cur else 0,
            "MO": cur.gold     if cur else 0,
            "MP": cur.platinum if cur else 0,
        }
        colors = {
            "MR": "#b87333", "MA": "#a0a0b0", "ME": "#6a9060",
            "MO": "#c8a000", "MP": "#a0c8d0",
        }
        cells: list[ft.Control] = []
        for abbr in ["MR", "MA", "ME", "MO", "MP"]:
            cells.append(ft.Container(
                content=ft.Column(
                    [
                        ft.Container(width=20, height=20, bgcolor=colors[abbr],
                                     border_radius=10,
                                     border=ft.Border.all(1, "#00000030")),
                        ft.Text(str(values[abbr]), size=18,
                                weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_PRIMARY, font_family=FONT_MONO,
                                text_align=ft.TextAlign.CENTER),
                        label_text(abbr, 9),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                expand=True,
                on_click=lambda e, a=abbr: self._on_edit_currency(a),
                ink=True,
                padding=ft.Padding.symmetric(horizontal=4, vertical=10),
                border=ft.Border.all(1, COLOR_BORDER),
                border_radius=6,
                bgcolor=COLOR_BG_CARD,
            ))
        return ft.Container(content=ft.Row(cells, spacing=6), bgcolor=COLOR_BG_PRIMARY)

    # ------------------------------------------------------------------
    # Peso
    # ------------------------------------------------------------------

    def _section_peso(self) -> ft.Container:
        c = self.character
        max_carry = c.str_score * _CARRY_PER_STR
        total_weight = sum(item.weight * item.quantity for item in self._items)
        pct = min(1.0, total_weight / max_carry) if max_carry > 0 else 0.0
        if pct >= 1.0:
            bar_color, status = COLOR_ACCENT_CRIMSON, "Sovraccarico"
        elif pct >= 0.666:
            bar_color, status = COLOR_ACCENT_AMBER, "Carico pesante"
        else:
            bar_color, status = COLOR_ACCENT_GREEN, "Carico normale"

        # La ProgressBar in Flutter richiede un vincolo di larghezza esplicito.
        # Wrapping in ft.Row(expand=True) glielo fornisce correttamente.
        bar = ft.Row([
            ft.ProgressBar(value=pct, height=8, color=bar_color,
                           bgcolor=COLOR_BG_SECONDARY, expand=True),
        ])

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(f"{total_weight:.1f} kg", size=22,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY, font_family=FONT_MONO),
                    muted_text(f"/ {max_carry:.0f} kg  ({c.str_score} FOR × 7.5)", 12),
                ], spacing=8),
                ft.Container(height=6),
                bar,
                ft.Container(height=4),
                muted_text(status, 11),
            ], spacing=0),
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
    # Armi
    # ------------------------------------------------------------------

    def _section_armi(self) -> ft.Container:
        header: list[ft.Control] = [
            ft.Text("ARMI", size=10, color=COLOR_TEXT_MUTED,
                    weight=ft.FontWeight.BOLD,
                    style=ft.TextStyle(letter_spacing=1.5), expand=True),
            ft.ElevatedButton(
                "Aggiungi Arma", icon=ft.Icons.ADD,
                on_click=lambda e: self._on_add_weapon(),
                style=ft.ButtonStyle(
                    bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                    shape=ft.RoundedRectangleBorder(radius=4),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                ),
            ),
        ]

        cards: list[ft.Control] = [
            ft.Container(
                content=ft.Row(header,
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.only(top=4, bottom=4),
            )
        ]

        if not self._weapons:
            cards.append(self._empty_card("Nessuna arma — usa «Aggiungi Arma»"))
        else:
            for w in self._weapons:
                cards.append(self._weapon_card(w))

        return ft.Container(content=ft.Column(cards, spacing=6))

    def _weapon_card(self, w: Weapon) -> ft.Container:
        # Guard null: campi int possono essere None se il DB ha NULL
        atk_bonus = w.attack_bonus if w.attack_bonus is not None else 0
        dmg_bonus = w.damage_bonus if w.damage_bonus is not None else 0
        att_str = f"+{atk_bonus}" if atk_bonus >= 0 else str(atk_bonus)
        db_str  = (f"+{dmg_bonus}" if dmg_bonus > 0
                   else (str(dmg_bonus) if dmg_bonus < 0 else ""))
        dmg_str = f"{w.damage_dice or ''}{db_str}  {w.damage_type or ''}"
        rng_n   = w.range_normal if w.range_normal is not None else 0
        rng_x   = w.range_max   if w.range_max   is not None else 0
        rng_str = (f"{rng_n}/{rng_x} m" if rng_x
                   else (f"{rng_n} m" if rng_n else "mischia"))

        equip_color = COLOR_ACCENT_CRIMSON if w.is_equipped else COLOR_BORDER

        # Riga badge magica (opzionale)
        badge_items: list[ft.Control] = [
            self._badge(att_str, "ATT", COLOR_ACCENT_BLUE),
            self._badge(dmg_str, "DANNO", COLOR_ACCENT_CRIMSON),
        ]
        if w.is_magical:
            badge_items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.STAR, size=10, color=COLOR_ACCENT_AMBER),
                    ft.Text("magica", size=10, color=COLOR_ACCENT_AMBER),
                ], spacing=2),
                bgcolor="#fef9ec",
                padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                border_radius=4,
                border=ft.Border.all(1, COLOR_ACCENT_AMBER),
            ))

        # Colonna azioni (destra)
        action_col = ft.Column([
            ft.IconButton(
                icon=ft.Icons.SHIELD,
                icon_color=equip_color, icon_size=16,
                tooltip="Equipaggiata" if w.is_equipped else "Non equipaggiata",
                on_click=lambda e, ww=w: self._toggle_weapon_equipped(ww),
                padding=ft.Padding.all(2),
            ),
            ft.IconButton(
                icon=ft.Icons.EDIT,
                icon_color=COLOR_TEXT_MUTED, icon_size=16,
                tooltip="Modifica",
                on_click=lambda e, ww=w: self._on_edit_weapon(ww),
                padding=ft.Padding.all(2),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE,
                icon_color=COLOR_ACCENT_CRIMSON, icon_size=16,
                tooltip="Elimina",
                on_click=lambda e, ww=w: self._on_delete_weapon(ww),
                padding=ft.Padding.all(2),
            ),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        # Colonna contenuto — NO expand=True (causa layout infinito in ListView)
        content_rows: list[ft.Control] = [
            ft.Row([
                ft.Text(w.name, size=14, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE),
                ft.Container(expand=True),   # spacer leggero
                muted_text(rng_str, 11),
            ], spacing=6),
            ft.Row(badge_items, spacing=6, wrap=True),
        ]
        if w.properties:
            content_rows.append(muted_text(w.properties, 11))

        # Il bordo sinistro colorato sostituisce la sidebar Container (evita STRETCH)
        return ft.Container(
            content=ft.Row([
                ft.Column(content_rows, spacing=4),
                action_col,
            ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLOR_BG_SECONDARY if w.is_equipped else COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border=ft.Border(
                left=ft.BorderSide(4, equip_color),
                top=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Oggetti
    # ------------------------------------------------------------------

    def _section_oggetti(self) -> ft.Container:
        header: list[ft.Control] = [
            ft.Text("OGGETTI", size=10, color=COLOR_TEXT_MUTED,
                    weight=ft.FontWeight.BOLD,
                    style=ft.TextStyle(letter_spacing=1.5), expand=True),
            ft.ElevatedButton(
                "Aggiungi Oggetto", icon=ft.Icons.ADD,
                on_click=lambda e: self._on_add_item(),
                style=ft.ButtonStyle(
                    bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                    shape=ft.RoundedRectangleBorder(radius=4),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                ),
            ),
        ]

        rows: list[ft.Control] = [
            ft.Container(
                content=ft.Row(header,
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.only(top=4, bottom=4),
            )
        ]

        if not self._items:
            rows.append(self._empty_card("Inventario vuoto — usa «Aggiungi Oggetto»"))
            return ft.Container(content=ft.Column(rows, spacing=6))

        by_cat: dict[str, list[InventoryItem]] = {}
        for item in self._items:
            by_cat.setdefault(item.category or "misc", []).append(item)

        for cat in _CATEGORIES:
            items = by_cat.get(cat, [])
            if not items:
                continue
            rows.append(ft.Container(
                content=ft.Text(
                    _CATEGORY_LABELS.get(cat, cat).upper(),
                    size=9, color=COLOR_TEXT_MUTED,
                    weight=ft.FontWeight.BOLD,
                    style=ft.TextStyle(letter_spacing=1),
                ),
                margin=ft.Margin.only(top=6, bottom=2),
            ))
            for item in sorted(items, key=lambda x: x.name):
                rows.append(self._item_row(item))

        return ft.Container(
            content=ft.Column(rows, spacing=4),
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

    def _item_row(self, item: InventoryItem) -> ft.Row:
        _cat_icon: dict[str, ft.IconData] = {
            "armor":  ft.Icons.SHIELD,
            "weapon": ft.Icons.FLASH_ON,
            "tool":   ft.Icons.BUILD,
            "magic":  ft.Icons.STAR,
            "misc":   ft.Icons.INBOX,
        }
        icon = _cat_icon.get(item.category or "misc", ft.Icons.INBOX)
        wt_str = f"{item.weight * item.quantity:.1f} kg" if item.weight else ""
        equip_mark = " ◆" if item.is_equipped else ""

        return ft.Row([
            ft.Icon(icon, size=14, color=COLOR_TEXT_MUTED),
            ft.Text(
                f"{item.name}{equip_mark}",
                size=13,
                color=COLOR_TEXT_PRIMARY if item.is_equipped else COLOR_TEXT_SECONDARY,
                weight=ft.FontWeight.BOLD if item.is_equipped else ft.FontWeight.NORMAL,
                expand=True,
            ),
            ft.Text(f"×{item.quantity}", size=12, color=COLOR_TEXT_SECONDARY,
                    font_family=FONT_MONO, width=32,
                    text_align=ft.TextAlign.RIGHT),
            muted_text(wt_str, 11),
            ft.IconButton(
                icon=ft.Icons.EDIT,
                icon_color=COLOR_TEXT_MUTED, icon_size=14, tooltip="Modifica",
                on_click=lambda e, it=item: self._on_edit_item(it),
                padding=ft.Padding.all(2),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE,
                icon_color=COLOR_ACCENT_CRIMSON, icon_size=14, tooltip="Elimina",
                on_click=lambda e, it=item: self._on_delete_item(it),
                padding=ft.Padding.all(2),
            ),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # ------------------------------------------------------------------
    # Dialog monete
    # ------------------------------------------------------------------

    def _on_edit_currency(self, abbr: str) -> None:
        page = self._page
        if page is None:
            return
        cur = self._currencies
        field_map: dict[str, tuple[str, int]] = {
            "MR": ("copper",   cur.copper   if cur else 0),
            "MA": ("silver",   cur.silver   if cur else 0),
            "ME": ("electrum", cur.electrum if cur else 0),
            "MO": ("gold",     cur.gold     if cur else 0),
            "MP": ("platinum", cur.platinum if cur else 0),
        }
        full_names = {
            "MR": "Monete di Rame", "MA": "Monete d'Argento",
            "ME": "Monete di Elettro", "MO": "Monete d'Oro", "MP": "Monete di Platino",
        }
        col_name, current_val = field_map[abbr]

        # Testo "attuale" aggiornabile dinamicamente
        current_text = ft.Text(
            str(current_val),
            size=48, weight=ft.FontWeight.BOLD,
            color=COLOR_TEXT_PRIMARY, font_family=FONT_MONO,
            text_align=ft.TextAlign.CENTER,
        )

        delta_field = ft.TextField(
            value="1",
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            text_align=ft.TextAlign.CENTER,
            text_style=ft.TextStyle(size=22, color=COLOR_TEXT_PRIMARY,
                                    font_family=FONT_MONO, weight=ft.FontWeight.BOLD),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
            width=100,
            height=56,
            content_padding=ft.Padding.symmetric(horizontal=8, vertical=0),
        )

        def _apply(delta: int) -> None:
            if page is None:
                return
            try:
                amount = max(1, int(delta_field.value or 1))
            except ValueError:
                amount = 1
            cur_now = self._currencies or Currency(character_id=self.character.id)
            old = getattr(cur_now, col_name)
            new_val = max(0, old + delta * amount)
            setattr(cur_now, col_name, new_val)
            character_repo.update_currencies(
                self.character.id,
                cur_now.copper, cur_now.silver, cur_now.electrum,
                cur_now.gold, cur_now.platinum,
            )
            self._currencies = cur_now
            current_text.value = str(new_val)
            try:
                current_text.update()
            except RuntimeError:
                pass
            self._refresh()

        btn_style_sub = ft.ButtonStyle(
            bgcolor=COLOR_BG_SECONDARY, color=COLOR_ACCENT_CRIMSON,
            shape=ft.RoundedRectangleBorder(radius=8),
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD),
        )
        btn_style_add = ft.ButtonStyle(
            bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
            shape=ft.RoundedRectangleBorder(radius=8),
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD),
        )

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(full_names[abbr], size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column([
                # Quantità attuale — numero grande centrato
                ft.Container(
                    content=ft.Column([
                        current_text,
                        muted_text("quantità attuale", 11),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                    alignment=ft.Alignment.CENTER,
                    width=300,
                    padding=ft.Padding.symmetric(vertical=8),
                ),
                ft.Divider(height=1, color=COLOR_BORDER),
                ft.Container(height=8),
                # Riga: [− Sottrai] [campo] [+ Aggiungi]
                ft.Row([
                    ft.ElevatedButton(
                        "−",
                        on_click=lambda ev: _apply(-1),
                        style=btn_style_sub,
                        width=72, height=52,
                    ),
                    delta_field,
                    ft.ElevatedButton(
                        "+",
                        on_click=lambda ev: _apply(+1),
                        style=btn_style_add,
                        width=72, height=52,
                    ),
                ], spacing=12,
                   alignment=ft.MainAxisAlignment.CENTER,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=4),
                muted_text("inserisci la quantità e premi + o −", 11),
            ], width=300, spacing=4,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            actions=[
                ft.TextButton("Chiudi",
                              on_click=lambda ev: page.pop_dialog() if page else None),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Dialog arma — condiviso tra aggiungi e modifica
    # ------------------------------------------------------------------

    def _on_add_weapon(self) -> None:
        page = self._page
        if page is None:
            return
        self._open_weapon_dialog(page, weapon=None)

    def _on_edit_weapon(self, weapon: Weapon) -> None:
        page = self._page
        if page is None:
            return
        self._open_weapon_dialog(page, weapon=weapon)

    def _open_weapon_dialog(self, page: ft.Page, weapon: Weapon | None) -> None:
        is_new = weapon is None

        def _tf(label: str, value: str = "", kb=ft.KeyboardType.TEXT,
                expand: bool = False) -> ft.TextField:
            return ft.TextField(
                label=label, value=value, keyboard_type=kb, expand=expand,
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_CRIMSON,
                bgcolor=COLOR_BG_CARD,
                label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
            )

        f_name   = _tf("Nome arma *",      "" if is_new else weapon.name)
        f_dice   = _tf("Dadi danno (es. 1d8)", "" if is_new else weapon.damage_dice)

        # Tipo danno — dropdown
        dtype_dd = ft.Dropdown(
            label="Tipo danno",
            value=(weapon.damage_type or None) if not is_new else None,
            options=[ft.DropdownOption(key=t, text=t) for t in _DAMAGE_TYPES],
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
        )

        f_atk    = _tf("Bonus attacco",    "0" if is_new else str(weapon.attack_bonus),
                        ft.KeyboardType.NUMBER)
        f_dbonus = _tf("Bonus danno",      "0" if is_new else str(weapon.damage_bonus),
                        ft.KeyboardType.NUMBER)

        # Proprietà — checkbox multi-select
        existing_props: set[str] = set()
        if not is_new and weapon.properties:
            existing_props = {p.strip() for p in weapon.properties.split(",") if p.strip()}
        props_checks = [
            ft.Checkbox(label=p, value=(p in existing_props))
            for p in _WEAPON_PROPERTIES
        ]
        props_section = ft.Column(
            cast(list[ft.Control], [label_text("Proprietà", 10),
                                    ft.Column(cast(list[ft.Control], props_checks), spacing=2)]),
            spacing=4,
        )

        f_rng    = _tf("Gittata normale (m, 0=mischia)",
                        "0" if is_new else str(weapon.range_normal or 0),
                        ft.KeyboardType.NUMBER)
        f_rngmax = _tf("Gittata max (m, 0=nessuna)",
                        "0" if is_new else str(weapon.range_max or 0),
                        ft.KeyboardType.NUMBER)
        f_magic  = _tf("Descrizione magica (vuoto=non magica)",
                        "" if is_new else weapon.magic_description)

        equip_cb = ft.Checkbox(
            label="Equipaggiata",
            value=True if is_new else weapon.is_equipped,
        )

        # --- Sezione danni magici aggiuntivi (repeatable) ---
        existing_magic = json.loads((weapon.magic_damages or "[]") if not is_new else "[]")
        magic_rows_col = ft.Column(spacing=4)

        def _make_magic_row(dice_v: str = "", type_v: str = "Fuoco", note_v: str = "") -> ft.Row:
            row_dice = ft.TextField(
                label="Dadi (es. 1d6)", value=dice_v, width=100,
                text_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
            )
            row_type = ft.Dropdown(
                label="Tipo", value=type_v, width=120,
                options=[ft.DropdownOption(key=t, text=t) for t in _DAMAGE_TYPES],
                text_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                bgcolor=COLOR_BG_CARD,
            )
            row_note = ft.TextField(
                label="Note", value=note_v, expand=True,
                text_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
            )
            row_ref: list[ft.Row] = []

            def remove_this(ev: ft.Event[ft.IconButton]) -> None:
                if row_ref:
                    try:
                        magic_rows_col.controls.remove(row_ref[0])
                        magic_rows_col.update()
                    except ValueError:
                        pass

            r = ft.Row(
                cast(list[ft.Control], [row_dice, row_type, row_note,
                     ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                   icon_color=COLOR_ACCENT_CRIMSON, icon_size=16,
                                   on_click=remove_this, tooltip="Rimuovi",
                                   padding=ft.Padding.all(0))]),
                spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            row_ref.append(r)
            return r

        for md in existing_magic:
            magic_rows_col.controls.append(
                _make_magic_row(md.get("dice", ""), md.get("type", "Fuoco"), md.get("note", ""))
            )

        def add_magic_row(ev: ft.Event[ft.TextButton]) -> None:
            magic_rows_col.controls.append(_make_magic_row())
            magic_rows_col.update()

        magic_section = ft.Column(
            cast(list[ft.Control], [
                ft.Row(
                    cast(list[ft.Control], [
                        label_text("Danni magici aggiuntivi", 10),
                        ft.TextButton(
                            "+ Aggiungi danno",
                            on_click=add_magic_row,
                            style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON),
                        ),
                    ]),
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                magic_rows_col,
            ]),
            spacing=2,
        )

        def save(ev):
            if page is None:
                return
            name = (f_name.value or "").strip()
            if not name:
                return
            try:
                atk    = int(f_atk.value or 0)
                dbonus = int(f_dbonus.value or 0)
                rng    = int(f_rng.value or 0)
                rngmax = int(f_rngmax.value or 0)
            except ValueError:
                atk = dbonus = rng = rngmax = 0
            magic_desc = (f_magic.value or "").strip()
            equipped   = bool(equip_cb.value)

            # Proprietà selezionate (cb.label è StrOrControl nei type stub → str() safe)
            selected_props = ",".join([
                str(cb.label) if cb.label else ""
                for cb in props_checks
                if cb.value
            ])

            # Colleziona danni magici dalle righe dinamiche
            magic_dmgs = []
            for row_ctrl in magic_rows_col.controls:
                row = cast(ft.Row, row_ctrl)
                dice_v = cast(ft.TextField, row.controls[0]).value or ""
                type_v = cast(ft.Dropdown, row.controls[1]).value or "Fuoco"
                note_v = cast(ft.TextField, row.controls[2]).value or ""
                if dice_v.strip():
                    magic_dmgs.append({"dice": dice_v.strip(),
                                       "type": type_v, "note": note_v.strip()})
            magic_damages_str = json.dumps(magic_dmgs, ensure_ascii=False)
            is_magical = bool(magic_desc) or bool(magic_dmgs)

            if is_new:
                character_repo.create_weapon(
                    self.character.id, name,
                    damage_dice=f_dice.value or "",
                    damage_type=dtype_dd.value or "",
                    attack_bonus=atk, damage_bonus=dbonus,
                    properties=selected_props,
                    is_equipped=equipped, is_magical=is_magical,
                    magic_description=magic_desc,
                    range_normal=rng, range_max=rngmax,
                    magic_damages=magic_damages_str,
                )
            else:
                assert weapon is not None
                character_repo.update_weapon(
                    weapon.id, name,
                    damage_dice=f_dice.value or "",
                    damage_type=dtype_dd.value or "",
                    attack_bonus=atk, damage_bonus=dbonus,
                    properties=selected_props,
                    is_equipped=equipped, is_magical=is_magical,
                    magic_description=magic_desc,
                    range_normal=rng, range_max=rngmax,
                    magic_damages=magic_damages_str,
                )
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Nuova Arma" if is_new else "Modifica Arma",
                          size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [f_name, f_dice, dtype_dd, f_atk, f_dbonus,
                 props_section, f_rng, f_rngmax, f_magic, magic_section, equip_cb],
                spacing=8, scroll=ft.ScrollMode.AUTO, width=380,
            ),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Salva", on_click=save,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    def _on_delete_weapon(self, weapon: Weapon) -> None:
        page = self._page
        if page is None:
            return

        def do_delete(ev):
            if page is None:
                return
            character_repo.delete_weapon(weapon.id)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Elimina arma", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Text(f"Eliminare «{weapon.name}»?", size=13,
                            color=COLOR_TEXT_PRIMARY),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Elimina", on_click=do_delete,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    def _toggle_weapon_equipped(self, weapon: Weapon) -> None:
        character_repo.update_weapon(
            weapon.id, weapon.name,
            damage_dice=weapon.damage_dice,
            damage_type=weapon.damage_type,
            attack_bonus=weapon.attack_bonus,
            damage_bonus=weapon.damage_bonus,
            properties=weapon.properties or "",
            is_equipped=not weapon.is_equipped,
            is_magical=weapon.is_magical,
            magic_description=weapon.magic_description or "",
            range_normal=weapon.range_normal or 0,
            range_max=weapon.range_max or 0,
            magic_damages=weapon.magic_damages or "[]",
        )
        self._refresh()

    # ------------------------------------------------------------------
    # Dialog oggetto — condiviso tra aggiungi e modifica
    # ------------------------------------------------------------------

    def _on_add_item(self) -> None:
        page = self._page
        if page is None:
            return
        self._open_item_dialog(page, item=None)

    def _on_edit_item(self, item: InventoryItem) -> None:
        page = self._page
        if page is None:
            return
        self._open_item_dialog(page, item=item)

    def _open_item_dialog(self, page: ft.Page, item: InventoryItem | None) -> None:
        is_new = item is None

        def _tf(label: str, value: str = "", kb=ft.KeyboardType.TEXT) -> ft.TextField:
            return ft.TextField(
                label=label, value=value, keyboard_type=kb,
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_CRIMSON,
                bgcolor=COLOR_BG_CARD,
                label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
            )

        f_name = _tf("Nome oggetto *", "" if is_new else item.name)
        f_qty  = _tf("Quantità", "1" if is_new else str(item.quantity),
                     ft.KeyboardType.NUMBER)
        f_wt   = _tf("Peso (kg per unità)", "0" if is_new else str(item.weight),
                     ft.KeyboardType.NUMBER)
        f_desc = _tf("Descrizione / note", "" if is_new else item.description)
        f_effects = _tf("Effetti magici / note speciali",
                        "" if is_new else (item.effects or ""))

        initial_cat = "misc" if is_new else (item.category or "misc")

        cat_dd = ft.Dropdown(
            label="Categoria",
            value=initial_cat,
            options=[
                ft.DropdownOption(key="misc",   text="Varie"),
                ft.DropdownOption(key="armor",  text="Armature & Scudi"),
                ft.DropdownOption(key="weapon", text="Armi (riserva)"),
                ft.DropdownOption(key="tool",   text="Strumenti"),
                ft.DropdownOption(key="magic",  text="Oggetti Magici"),
            ],
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
        )
        equip_cb = ft.Checkbox(
            label="Equipaggiato / indossato",
            value=False if is_new else item.is_equipped,
        )

        # --- Campi specifici per armature/scudi (category="armor") ---
        f_ca = _tf("Valore CA base (es. 14 per cotta di maglia)",
                   "0" if is_new else str(item.ca_value or 0),
                   ft.KeyboardType.NUMBER)
        armor_type_dd = ft.Dropdown(
            label="Tipo armatura",
            value="" if is_new else (item.armor_type or ""),
            options=[
                ft.DropdownOption(key="",        text="— seleziona —"),
                ft.DropdownOption(key="leggera", text="Leggera (+ mod DES)"),
                ft.DropdownOption(key="media",   text="Media (+ min(mod DES, 2))"),
                ft.DropdownOption(key="pesante", text="Pesante (DES ignorato)"),
                ft.DropdownOption(key="scudo",   text="Scudo (bonus CA fisso)"),
            ],
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
        )
        armor_fields = ft.Column(
            cast(list[ft.Control], [label_text("CAMPI ARMATURA / SCUDO", 10),
                                    f_ca, armor_type_dd]),
            spacing=8,
            visible=(initial_cat == "armor"),
        )

        def on_cat_select(ev: ft.Event[ft.Dropdown]) -> None:
            armor_fields.visible = (cat_dd.value == "armor")
            armor_fields.update()

        cat_dd.on_select = on_cat_select

        def save(ev):
            if page is None:
                return
            name = (f_name.value or "").strip()
            if not name:
                return
            try:
                qty = max(1, int(f_qty.value or 1))
                wt  = max(0.0, float(f_wt.value or 0))
            except ValueError:
                qty, wt = 1, 0.0
            cat      = cat_dd.value or "misc"
            desc     = (f_desc.value or "").strip()
            effects  = (f_effects.value or "").strip()
            equipped = bool(equip_cb.value)
            try:
                ca_val = int(f_ca.value or 0)
            except ValueError:
                ca_val = 0
            arm_type = (armor_type_dd.value or "") if cat == "armor" else ""

            if is_new:
                character_repo.create_inventory_item(
                    self.character.id, name, qty, wt, desc, cat, equipped,
                    ca_value=ca_val, armor_type=arm_type, effects=effects,
                )
            else:
                assert item is not None
                character_repo.update_inventory_item(
                    item.id, name, qty, wt, desc, cat, equipped,
                    ca_value=ca_val, armor_type=arm_type, effects=effects,
                )
            # Ricalcola CA se ci sono armature/scudi coinvolti
            if cat == "armor" or (not is_new and item is not None and item.category == "armor"):
                new_ca = character_repo.calculate_and_update_ca(self.character.id)
                self.character.ac = new_ca
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Nuovo Oggetto" if is_new else "Modifica Oggetto",
                          size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [f_name, f_qty, f_wt, cat_dd, armor_fields,
                 equip_cb, f_desc, f_effects],
                spacing=8, scroll=ft.ScrollMode.AUTO, width=360,
            ),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Salva", on_click=save,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    def _on_delete_item(self, item: InventoryItem) -> None:
        page = self._page
        if page is None:
            return

        def do_delete(ev):
            if page is None:
                return
            character_repo.delete_inventory_item(item.id)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Elimina oggetto", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Text(f"Eliminare «{item.name}»?", size=13,
                            color=COLOR_TEXT_PRIMARY),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Elimina", on_click=do_delete,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _badge(self, value: str, label: str, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Column([
                ft.Text(value, size=12, weight=ft.FontWeight.BOLD,
                        color=color, font_family=FONT_MONO,
                        text_align=ft.TextAlign.CENTER),
                ft.Text(label, size=9, color=COLOR_TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                        style=ft.TextStyle(letter_spacing=0.8)),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1),
            bgcolor=COLOR_BG_SECONDARY,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=4,
        )

    def _empty_card(self, msg: str) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.INBOX, size=18, color=COLOR_TEXT_MUTED),
                muted_text(msg, 13),
            ], spacing=8),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=14),
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
        self._currencies = character_repo.get_currencies(self.character.id)
        self._weapons    = character_repo.get_weapons(self.character.id, equipped_only=False)
        self._items      = character_repo.get_inventory(self.character.id)
        try:
            self._build()
        except Exception as exc:
            logger.error("InventarioTab._build() fallito in _refresh: %s", exc, exc_info=True)
            self.controls.clear()
            self.controls.append(
                ft.Text(f"Errore aggiornamento inventario: {exc}",
                        color=COLOR_ACCENT_CRIMSON, size=13)
            )
        try:
            if self._page:
                self._page.update()
            else:
                self.update()
        except RuntimeError:
            pass
