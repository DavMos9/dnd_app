"""
Tab Inventario della scheda personaggio.

Struttura (ListView scrollabile):
  - Monete          — MR / MA / ME / MO / MP con editing inline
  - Peso            — peso attuale / capacità massima (FOR × 7.5 kg)
  - Armi            — lista con aggiunta / modifica / elimina / equipaggia toggle
  - Oggetti         — lista per categoria con aggiunta / modifica / elimina
"""

import flet as ft
import logging
from typing import cast
from config.settings import *
from data.models import Character, Currency, InventoryItem, Weapon
import data.repositories.character_repo as character_repo
from ui.theme import section_header, muted_text, label_text

logger = logging.getLogger(__name__)

_CARRY_PER_STR = 7.5   # kg per punto Forza — PHB p.176

_CATEGORY_ICON: dict[str, ft.IconData] = {
    "armor":  ft.Icons.SHIELD_OUTLINED,
    "weapon": ft.Icons.SPORTS_MARTIAL_ARTS,
    "tool":   ft.Icons.BUILD_OUTLINED,
    "magic":  ft.Icons.AUTO_AWESOME_OUTLINED,
    "misc":   ft.Icons.INVENTORY_2_OUTLINED,
}
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
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.controls = [
            section_header("Monete"),
            self._section_monete(),
            section_header("Peso"),
            self._section_peso(),
            self._section_armi(),
            self._section_oggetti(),
            ft.Container(height=24),
        ]

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

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(f"{total_weight:.1f} kg", size=22,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY, font_family=FONT_MONO),
                    muted_text(f"/ {max_carry:.0f} kg  ({c.str_score} FOR × 7.5)", 12),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.BASELINE),
                ft.Container(height=6),
                ft.ProgressBar(value=pct, height=8, color=bar_color,
                               bgcolor=COLOR_BG_SECONDARY,
                               border_radius=ft.BorderRadius.all(4)),
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

    def _section_armi(self) -> ft.Column:
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

        return ft.Column(cards, spacing=6)

    def _weapon_card(self, w: Weapon) -> ft.Container:
        att_str = f"+{w.attack_bonus}" if w.attack_bonus >= 0 else str(w.attack_bonus)
        db_str  = (f"+{w.damage_bonus}" if w.damage_bonus > 0
                   else (str(w.damage_bonus) if w.damage_bonus < 0 else ""))
        dmg_str = f"{w.damage_dice}{db_str}  {w.damage_type}"
        rng_str = (f"{w.range_normal}/{w.range_max} m" if w.range_max
                   else (f"{w.range_normal} m" if w.range_normal else "mischia"))

        equip_color = COLOR_ACCENT_CRIMSON if w.is_equipped else COLOR_BORDER

        return ft.Container(
            content=ft.Row([
                # Barra laterale equipaggiato
                ft.Container(width=4, bgcolor=equip_color, border_radius=2),
                ft.Container(width=6),
                # Contenuto
                ft.Column([
                    ft.Row([
                        ft.Text(w.name, size=14, weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_TITLE, expand=True),
                        muted_text(rng_str, 11),
                    ], spacing=6),
                    ft.Row([
                        self._badge(att_str, "ATT", COLOR_ACCENT_BLUE),
                        self._badge(dmg_str, "DANNO", COLOR_ACCENT_CRIMSON),
                        *(
                            [ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.AUTO_AWESOME, size=10,
                                            color=COLOR_ACCENT_AMBER),
                                    ft.Text("magica", size=10,
                                            color=COLOR_ACCENT_AMBER),
                                ], spacing=2),
                                bgcolor="#fef9ec",
                                padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                                border_radius=4,
                                border=ft.Border.all(1, COLOR_ACCENT_AMBER),
                            )]
                            if w.is_magical else []
                        ),
                    ], spacing=6),
                    *(
                        [muted_text(w.properties, 11)]
                        if w.properties else []
                    ),
                ], spacing=4, expand=True),
                # Azioni
                ft.Column([
                    ft.IconButton(
                        icon=ft.Icons.SHIELD if w.is_equipped else ft.Icons.SHIELD_OUTLINED,
                        icon_color=equip_color,
                        icon_size=16,
                        tooltip="Equipaggiata" if w.is_equipped else "Non equipaggiata — clicca per equipaggiare",
                        on_click=lambda e, ww=w: self._toggle_weapon_equipped(ww),
                        padding=ft.Padding.all(2),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        icon_color=COLOR_TEXT_MUTED,
                        icon_size=16,
                        tooltip="Modifica",
                        on_click=lambda e, ww=w: self._on_edit_weapon(ww),
                        padding=ft.Padding.all(2),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=COLOR_ACCENT_CRIMSON,
                        icon_size=16,
                        tooltip="Elimina",
                        on_click=lambda e, ww=w: self._on_delete_weapon(ww),
                        padding=ft.Padding.all(2),
                    ),
                ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor=COLOR_BG_SECONDARY if w.is_equipped else COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=8, vertical=10),
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Oggetti
    # ------------------------------------------------------------------

    def _section_oggetti(self) -> ft.Column:
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
            return ft.Column(rows, spacing=6)

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

        return ft.Column(
            [ft.Container(
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
            )],
            spacing=0,
        )

    def _item_row(self, item: InventoryItem) -> ft.Row:
        icon = _CATEGORY_ICON.get(item.category or "misc", ft.Icons.INVENTORY_2_OUTLINED)
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
                icon=ft.Icons.EDIT_OUTLINED,
                icon_color=COLOR_TEXT_MUTED, icon_size=14, tooltip="Modifica",
                on_click=lambda e, it=item: self._on_edit_item(it),
                padding=ft.Padding.all(2),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
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
        field_map = {
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
        _, current_val = field_map[abbr]
        field = ft.TextField(
            label=full_names[abbr], value=str(current_val),
            keyboard_type=ft.KeyboardType.NUMBER, autofocus=True,
            text_align=ft.TextAlign.CENTER,
            text_style=ft.TextStyle(size=20, color=COLOR_TEXT_PRIMARY,
                                    font_family=FONT_MONO),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
        )

        def save(ev):
            if page is None:
                return
            try:
                new_val = max(0, int(field.value or 0))
            except ValueError:
                page.pop_dialog()
                return
            cur_now = self._currencies or Currency(character_id=self.character.id)
            setattr(cur_now, field_map[abbr][0], new_val)
            character_repo.update_currencies(
                self.character.id,
                cur_now.copper, cur_now.silver, cur_now.electrum,
                cur_now.gold, cur_now.platinum,
            )
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(full_names[abbr], size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column([field], width=220, spacing=0),
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

        def _tf(label: str, value: str = "", kb=ft.KeyboardType.TEXT) -> ft.TextField:
            return ft.TextField(
                label=label, value=value,
                keyboard_type=kb,
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_CRIMSON,
                bgcolor=COLOR_BG_CARD,
                label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
            )

        f_name   = _tf("Nome arma *",      "" if is_new else weapon.name)
        f_dice   = _tf("Dadi danno (es. 1d8)", "" if is_new else weapon.damage_dice)
        f_dtype  = _tf("Tipo danno",       "" if is_new else weapon.damage_type)
        f_atk    = _tf("Bonus attacco",    "0" if is_new else str(weapon.attack_bonus),
                        ft.KeyboardType.NUMBER)
        f_dbonus = _tf("Bonus danno",      "0" if is_new else str(weapon.damage_bonus),
                        ft.KeyboardType.NUMBER)
        f_props  = _tf("Proprietà (es. Versatile, Lancio)", "" if is_new else weapon.properties)
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
            is_magical = bool(magic_desc)
            equipped   = bool(equip_cb.value)

            if is_new:
                character_repo.create_weapon(
                    self.character.id, name,
                    damage_dice=f_dice.value or "",
                    damage_type=f_dtype.value or "",
                    attack_bonus=atk, damage_bonus=dbonus,
                    properties=f_props.value or "",
                    is_equipped=equipped, is_magical=is_magical,
                    magic_description=magic_desc,
                    range_normal=rng, range_max=rngmax,
                )
            else:
                character_repo.update_weapon(
                    weapon.id, name,
                    damage_dice=f_dice.value or "",
                    damage_type=f_dtype.value or "",
                    attack_bonus=atk, damage_bonus=dbonus,
                    properties=f_props.value or "",
                    is_equipped=equipped, is_magical=is_magical,
                    magic_description=magic_desc,
                    range_normal=rng, range_max=rngmax,
                )
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Nuova Arma" if is_new else "Modifica Arma",
                          size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [f_name, f_dice, f_dtype, f_atk, f_dbonus,
                 f_props, f_rng, f_rngmax, f_magic, equip_cb],
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

        cat_dd = ft.Dropdown(
            label="Categoria",
            value="misc" if is_new else (item.category or "misc"),
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
            equipped = bool(equip_cb.value)

            if is_new:
                character_repo.create_inventory_item(
                    self.character.id, name, qty, wt, desc, cat, equipped,
                )
            else:
                character_repo.update_inventory_item(
                    item.id, name, qty, wt, desc, cat, equipped,
                )
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Nuovo Oggetto" if is_new else "Modifica Oggetto",
                          size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [f_name, f_qty, f_wt, cat_dd, equip_cb, f_desc],
                spacing=8, scroll=ft.ScrollMode.AUTO, width=340,
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
                ft.Icon(ft.Icons.INBOX_OUTLINED, size=18, color=COLOR_TEXT_MUTED),
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
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
