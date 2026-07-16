"""
Tab Inventario della scheda personaggio.

Struttura (ListView scrollabile):
  - Monete          — MR / MA / ME / MO / MP con editing inline
  - Peso            — peso attuale / capacità massima (FOR × 7.5 kg)
  - Armi            — lista con aggiunta / modifica / elimina / equipaggia toggle
  - Armature        — lista armature/scudi (category="armor") con aggiunta /
                       modifica / elimina / equipaggia toggle; equipaggiare
                       applica l'esclusione reciproca di postazione (una sola
                       armatura indossata, un solo scudo impugnato — vedi
                       core/equipment_manager.py) prima di ricalcolare la CA
  - Oggetti         — lista per le restanti categorie (misc/weapon/tool/magic)
                       con aggiunta / modifica / elimina
"""

import flet as ft
import json
import logging
import re
from typing import Any, Callable, cast
from config.settings import *
from data.models import Character, Currency, InventoryItem, Weapon
import data.repositories.character_repo as character_repo
from core.equipment_manager import (
    ArmorCandidate, EquipCandidate, resolve_armor_equip, resolve_weapon_equip,
)
from data.game_data.game_data_loader import GameDataLoader, game_data as _loader
from ui.theme import section_header, muted_text, label_text, show_error_dialog

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
# "armor" ha una sezione dedicata ("Armature", vedi _section_armature) e
# non compare più nella lista generica "Oggetti" per evitare di mostrare
# le armature due volte. "weapon" ("Armi (riserva)") non è più selezionabile
# nel dialog Nuovo/Modifica Oggetto (2026-07-11, vedi CLAUDE.md "Armi
# riserva") — ogni arma va sempre creata nella sezione Armi dedicata
# (tabella weapons), unica fonte di verità che partecipa al limite di 2
# mani; resta comunque nella lista qui sotto come rete di sicurezza, così un
# eventuale item non ancora migrato (o una migrazione fallita, vedi
# _migrate_legacy_weapon_items) resta visibile e gestibile invece di
# sparire silenziosamente dalla UI.
_OGGETTI_CATEGORIES = ["misc", "weapon", "tool", "magic"]

# --- Autofill Arma da catalogo (2026-07-16, richiesta Davide) -------------
# equipment/weapons.json usa nomi/formati diversi dalla UI di questo dialog
# (nomi tipo-danno minuscoli plurali italiani, proprietà con valori
# incorporati tra parentesi es. "Versatile (1d10)"/"Munizioni (gittata
# 24/96)") — queste tabelle traducono il dato di catalogo nel formato già
# usato dai controlli esistenti, senza introdurre nessun campo nuovo.
_JSON_DAMAGE_TYPE_TO_UI: dict[str, str] = {
    "taglienti": "Taglio", "tagliente": "Taglio",
    "contundenti": "Contundente", "contundente": "Contundente",
    "perforanti": "Perforazione", "perforante": "Perforazione",
}


def _map_catalog_damage_type(raw: str) -> str:
    """Traduce il tipo-danno di equipment/weapons.json nel valore _DAMAGE_TYPES."""
    key = (raw or "").strip().lower()
    if key in _JSON_DAMAGE_TYPE_TO_UI:
        return _JSON_DAMAGE_TYPE_TO_UI[key]
    if "tagli" in key:
        return "Taglio"
    if "contund" in key:
        return "Contundente"
    if "perfor" in key:
        return "Perforazione"
    return ""


_JSON_PROPERTY_TO_UI: dict[str, str] = {
    "due mani":  "A due mani",
    "munizioni": "Munizioni",
    "lancio":    "Da lancio",
    "versatile": "Versatile",
    "ricarica":  "Carica",
    "accurata":  "Accurata",
    "pesante":   "Pesante",
    "portata":   "Portata",
    "leggera":   "Leggera",
    "speciale":  "Speciale",
}


def _resolve_catalog_weapon_properties(
    raw_props: list[str],
) -> tuple[set[str], str, int, int]:
    """
    Converte la lista di proprietà di equipment/weapons.json (es.
    ["Due Mani", "Munizioni (gittata 24/96)"]) nel formato atteso dal
    dialog Arma: (etichette checkbox da spuntare, dado Versatile a due
    mani se presente, gittata normale in metri, gittata massima in metri).
    """
    ui_labels: set[str] = set()
    versatile_dice = ""
    range_normal = 0
    range_max = 0
    for raw in raw_props:
        base = raw.split(" (")[0].strip().lower()
        ui_label = _JSON_PROPERTY_TO_UI.get(base)
        if ui_label:
            ui_labels.add(ui_label)
        if base == "versatile":
            m = re.search(r"\(([^)]+)\)", raw)
            if m:
                versatile_dice = m.group(1).strip()
        elif base in ("munizioni", "lancio"):
            m = re.search(r"gittata\s+([\d,.]+)\s*/\s*([\d,.]+)", raw)
            if m:
                try:
                    # Arrotondamento half-up (non round() di Python, che usa
                    # banker's rounding e tronca 4.5 a 4): il campo DB è
                    # INTEGER in metri, alcune armi da lancio del catalogo
                    # (es. Rete, 1,5/4,5 m) hanno gittate frazionarie reali.
                    range_normal = int(float(m.group(1).replace(",", ".")) + 0.5)
                    range_max = int(float(m.group(2).replace(",", ".")) + 0.5)
                except ValueError:
                    pass
    return ui_labels, versatile_dice, range_normal, range_max


class InventarioTab(ft.ListView):
    """
    Tab inventario: monete, peso, armi (CRUD), oggetti (CRUD).
    """

    def __init__(self, character: Character, on_refresh: Callable[[], None] | None = None):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None
        self._currencies: Currency | None = character_repo.get_currencies(character.id)
        self._weapons: list[Weapon] = character_repo.get_weapons(character.id, equipped_only=False)
        self._items: list[InventoryItem] = character_repo.get_inventory(character.id)
        if self._migrate_legacy_weapon_items():
            # La migrazione ha modificato weapons/inventory_items: ricarica
            # entrambe le liste prima di costruire la UI.
            self._weapons = character_repo.get_weapons(character.id, equipped_only=False)
            self._items = character_repo.get_inventory(character.id)
        try:
            self._build()
        except Exception as exc:
            logger.error("InventarioTab._build() fallito: %s", exc, exc_info=True)
            self.controls.clear()
            self.controls.append(ft.Text(f"Errore caricamento inventario: {exc}",
                                         color=COLOR_ACCENT_CRIMSON, size=13))

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    def _migrate_legacy_weapon_items(self) -> bool:
        """
        Migrazione automatica, una tantum per personaggio: converte in righe
        vere della tabella `weapons` gli eventuali `InventoryItem` con
        `category=="weapon"` ("Armi (riserva)") creati prima del 2026-07-11
        (fallback diagnostico di `_save_weapon_by_name()` in
        wizard_view.py/manual_form.py quando un'arma iniziale non veniva
        trovata nel catalogo — vedi CLAUDE.md "Armi riserva"). Quella
        categoria viveva in una tabella diversa dalle armi vere, quindi non
        partecipava mai al limite di 2 mani di core/equipment_manager.py:
        equipaggiarla da Oggetti non sostituiva mai le armi già impugnate
        nella sezione Armi.

        Per ogni item legacy: prova a risolvere dado danno/tipo/proprietà
        dal catalogo (`equipment/weapons.json`, stesso identico tentativo già
        fatto alla creazione); se il nome non si risolve, crea comunque
        l'arma con statistiche vuote (modificabili dal dialog "Modifica" in
        Armi) invece di far sparire l'oggetto. Elimina la riga di inventario
        solo dopo che la creazione in weapons è andata a buon fine — in caso
        di errore di scrittura, l'item legacy resta visibile in Oggetti
        (categoria "Armi (riserva) — legacy", vedi _open_item_dialog) invece
        di essere perso.

        Ritorna True se ha modificato almeno un record (il chiamante deve
        ricaricare `self._weapons`/`self._items` dal DB), False altrimenti —
        idempotente: dopo la prima esecuzione riuscita per un personaggio,
        le chiamate successive non trovano più nulla da migrare.
        """
        legacy = [i for i in self._items if (i.category or "") == "weapon"]
        if not legacy:
            return False
        loader = GameDataLoader()
        migrated_any = False
        for legacy_item in legacy:
            wdata = loader.get_weapon(legacy_item.name)
            if wdata:
                props = wdata.get("properties", [])
                props_str = ", ".join(props) if isinstance(props, list) else str(props)
                ok = character_repo.create_weapon(
                    self.character.id, legacy_item.name,
                    damage_dice=wdata.get("damage_dice", ""),
                    damage_type=wdata.get("damage_type", ""),
                    properties=props_str,
                    is_equipped=False,
                )
            else:
                ok = character_repo.create_weapon(
                    self.character.id, legacy_item.name, is_equipped=False,
                )
            if ok:
                if character_repo.delete_inventory_item(legacy_item.id):
                    migrated_any = True
                else:
                    logger.warning(
                        "Migrazione arma legacy '%s': creata in weapons ma non "
                        "rimossa da inventory_items (personaggio %s) — verrà "
                        "duplicata al prossimo caricamento",
                        legacy_item.name, self.character.id,
                    )
            else:
                logger.warning(
                    "Migrazione arma legacy '%s' fallita per il personaggio %s "
                    "— l'oggetto resta in Oggetti", legacy_item.name, self.character.id,
                )
        return migrated_any

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
        self.controls.append(section_header("Armature"))
        self.controls.append(self._section_armature())
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
        calculated_carry = c.str_score * _CARRY_PER_STR
        override_carry = c.carry_capacity_override or 0.0
        max_carry = override_carry if override_carry > 0 else calculated_carry
        total_weight = sum(item.weight * item.quantity for item in self._items)
        pct = min(1.0, total_weight / max_carry) if max_carry > 0 else 0.0
        if pct >= 1.0:
            bar_color, status = COLOR_ACCENT_CRIMSON, "Sovraccarico"
        elif pct >= 0.666:
            bar_color, status = COLOR_ACCENT_AMBER, "Carico pesante"
        else:
            bar_color, status = COLOR_ACCENT_GREEN, "Carico normale"

        capacity_label = (
            f"/ {max_carry:.0f} kg  (override manuale)"
            if override_carry > 0
            else f"/ {max_carry:.0f} kg  ({c.str_score} FOR × 7.5)"
        )

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
                    ft.Text(capacity_label, size=12,
                            color=COLOR_ACCENT_BLUE if override_carry > 0 else COLOR_TEXT_MUTED,
                            font_family=FONT_BODY),
                    ft.Icon(ft.Icons.EDIT, size=12, color=COLOR_TEXT_MUTED),
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
            on_click=lambda e: self._on_edit_carry_capacity(calculated_carry),
            ink=True,
            tooltip="Modifica capacità massima di trasporto",
        )

    def _on_edit_carry_capacity(self, calculated: float) -> None:
        page = self._page
        if page is None:
            return
        c = self.character
        current_override = c.carry_capacity_override or 0.0

        tf = ft.TextField(
            label="Capacità massima (kg, override)",
            value=(f"{current_override:g}" if current_override > 0 else ""),
            hint_text=f"Vuoto = calcolato automaticamente ({calculated:.0f} kg)",
            autofocus=True,
        )

        def _save(e):
            raw = (tf.value or "").strip().replace(",", ".")
            if not raw:
                value = 0.0
            else:
                try:
                    value = max(0.0, float(raw))
                except ValueError:
                    cast(Any, tf).error_text = "Inserisci un numero valido (es. 112.5)"
                    tf.update()
                    return
            if not character_repo.update_carry_capacity_override(c.id, value):
                show_error_dialog(page, "Errore nel salvataggio della capacità di trasporto.")
                return
            c.carry_capacity_override = value
            page.pop_dialog()
            self._refresh()

        def _reset(e):
            if not character_repo.update_carry_capacity_override(c.id, 0.0):
                show_error_dialog(page, "Errore nel salvataggio della capacità di trasporto.")
                return
            c.carry_capacity_override = 0.0
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text("Capacità di Trasporto"),
            content=ft.Column(
                [
                    muted_text(
                        f"Formula PHB standard: {c.str_score} FOR × 7,5 kg = {calculated:.0f} kg. "
                        "Usa l'override per talenti/tratti che la alterano (es. Corporatura Possente).",
                        12,
                    ),
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

        # Proprietà "Versatile" (PHB p.149): il dado danno mostrato/attivo
        # dipende dall'impugnatura corrente — a due mani si usa
        # versatile_damage_dice (se compilato), non damage_dice.
        is_versatile = "versatile" in (w.properties or "").lower()
        active_dice = w.damage_dice or ""
        if is_versatile and w.grip_two_handed and w.versatile_damage_dice:
            active_dice = w.versatile_damage_dice
        dmg_str = f"{active_dice}{db_str}  {w.damage_type or ''}"
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
        action_buttons: list[ft.Control] = [
            ft.IconButton(
                icon=ft.Icons.SHIELD,
                icon_color=equip_color, icon_size=16,
                tooltip="Equipaggiata" if w.is_equipped else "Non equipaggiata",
                on_click=lambda e, ww=w: self._toggle_weapon_equipped(ww),
                padding=ft.Padding.all(2),
            ),
        ]
        if is_versatile and w.versatile_damage_dice:
            action_buttons.append(ft.IconButton(
                icon=ft.Icons.BACK_HAND if w.grip_two_handed else ft.Icons.FRONT_HAND,
                icon_color=COLOR_ACCENT_BLUE if w.grip_two_handed else COLOR_TEXT_MUTED,
                icon_size=16,
                tooltip=(
                    f"Impugnata a due mani ({w.versatile_damage_dice}) — clic per una mano"
                    if w.grip_two_handed
                    else f"Impugnata a una mano ({w.damage_dice}) — clic per due mani ({w.versatile_damage_dice})"
                ),
                on_click=lambda e, ww=w: self._toggle_weapon_grip(ww),
                padding=ft.Padding.all(2),
            ))
        action_buttons += [
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
        ]
        action_col = ft.Column(
            action_buttons, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )

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
        if is_versatile and w.versatile_damage_dice:
            grip_label = "a due mani" if w.grip_two_handed else "a una mano"
            content_rows.append(muted_text(
                f"Versatile — impugnata {grip_label}: "
                f"{w.damage_dice or '?'} (1 mano) / {w.versatile_damage_dice} (2 mani)",
                11,
            ))
        _ref_line = self._catalog_ref_line(w.name, "weapon")
        if _ref_line is not None:
            content_rows.append(_ref_line)

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
    # Armature & Scudi
    # ------------------------------------------------------------------

    def _armor_items(self) -> list[InventoryItem]:
        return [i for i in self._items if (i.category or "") == "armor"]

    def _section_armature(self) -> ft.Container:
        header: list[ft.Control] = [
            ft.Text("ARMATURE & SCUDI", size=10, color=COLOR_TEXT_MUTED,
                    weight=ft.FontWeight.BOLD,
                    style=ft.TextStyle(letter_spacing=1.5), expand=True),
            ft.ElevatedButton(
                "Aggiungi Armatura", icon=ft.Icons.ADD,
                on_click=lambda e: self._on_add_armor(),
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

        armors = self._armor_items()
        if not armors:
            cards.append(self._empty_card("Nessuna armatura — usa «Aggiungi Armatura»"))
        else:
            for a in sorted(armors, key=lambda x: x.name):
                cards.append(self._armor_card(a))

        return ft.Container(content=ft.Column(cards, spacing=6))

    _ARMOR_TYPE_LABELS = {
        "leggera": "Leggera (+ mod DES)",
        "media":   "Media (+ min mod DES, 2)",
        "pesante": "Pesante (DES ignorato)",
        "scudo":   "Scudo",
        "":        "—",
    }

    def _armor_card(self, item: InventoryItem) -> ft.Container:
        equip_color = COLOR_ACCENT_CRIMSON if item.is_equipped else COLOR_BORDER
        armor_type = item.armor_type or ""
        ca_val = item.ca_value or 0
        if armor_type == "scudo":
            ca_str = f"+{ca_val}"
        else:
            ca_str = str(ca_val) if ca_val else "—"
        type_label = self._ARMOR_TYPE_LABELS.get(armor_type, armor_type or "—")

        badge_items: list[ft.Control] = [
            self._badge(ca_str, "CA", COLOR_ACCENT_BLUE),
        ]
        if item.effects:
            badge_items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.STAR, size=10, color=COLOR_ACCENT_AMBER),
                    ft.Text("effetti", size=10, color=COLOR_ACCENT_AMBER),
                ], spacing=2),
                bgcolor="#fef9ec",
                padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                border_radius=4,
                border=ft.Border.all(1, COLOR_ACCENT_AMBER),
            ))

        action_col = ft.Column([
            ft.IconButton(
                icon=ft.Icons.SHIELD,
                icon_color=equip_color, icon_size=16,
                tooltip="Equipaggiata" if item.is_equipped else "Non equipaggiata",
                on_click=lambda e, ii=item: self._toggle_item_equipped(ii),
                padding=ft.Padding.all(2),
            ),
            ft.IconButton(
                icon=ft.Icons.EDIT,
                icon_color=COLOR_TEXT_MUTED, icon_size=16,
                tooltip="Modifica",
                on_click=lambda e, ii=item: self._on_edit_item(ii),
                padding=ft.Padding.all(2),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE,
                icon_color=COLOR_ACCENT_CRIMSON, icon_size=16,
                tooltip="Elimina",
                on_click=lambda e, ii=item: self._on_delete_item(ii),
                padding=ft.Padding.all(2),
            ),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        content_rows: list[ft.Control] = [
            ft.Row([
                ft.Text(item.name, size=14, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE),
                ft.Container(expand=True),
                muted_text(type_label, 11),
            ], spacing=6),
            ft.Row(badge_items, spacing=6, wrap=True),
        ]
        if item.description:
            content_rows.append(muted_text(item.description, 11))
        _ref_line = self._catalog_ref_line(item.name, "armor")
        if _ref_line is not None:
            content_rows.append(_ref_line)

        return ft.Container(
            content=ft.Row([
                ft.Column(content_rows, spacing=4),
                action_col,
            ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLOR_BG_SECONDARY if item.is_equipped else COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border=ft.Border(
                left=ft.BorderSide(4, equip_color),
                top=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _on_add_armor(self) -> None:
        page = self._page
        if page is None:
            return
        self._open_item_dialog(page, item=None, force_category="armor")

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

        for cat in _OGGETTI_CATEGORIES:
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
                icon=ft.Icons.CHECK_CIRCLE if item.is_equipped else ft.Icons.RADIO_BUTTON_UNCHECKED,
                icon_color=COLOR_ACCENT_CRIMSON if item.is_equipped else COLOR_BORDER,
                icon_size=14,
                tooltip="Disequipaggia" if item.is_equipped else "Equipaggia",
                on_click=lambda e, it=item: self._toggle_item_equipped(it),
                padding=ft.Padding.all(2),
            ),
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
            ], spacing=4,
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

        # Campi dedicati alla proprietà "Versatile" (PHB p.149): l'arma può
        # essere impugnata a una o due mani, con un dado danno diverso per
        # ciascuna impugnatura — visibili solo se "Versatile" è selezionata
        # tra le proprietà (vedi _on_versatile_toggle più sotto).
        f_vdice = _tf(
            "Dado danno a due mani (es. 1d10)",
            "" if is_new else (weapon.versatile_damage_dice or ""),
        )
        grip_cb = ft.Checkbox(
            label="Impugnata a due mani ora (usa il dado a due mani)",
            value=False if is_new else weapon.grip_two_handed,
        )
        versatile_fields = ft.Column(
            cast(list[ft.Control], [f_vdice, grip_cb]),
            spacing=4,
            visible=("Versatile" in existing_props) if not is_new else False,
        )
        versatile_cb = next(
            (cb for cb in props_checks if str(cb.label) == "Versatile"), None
        )

        def _on_versatile_toggle(ev: Any) -> None:
            if versatile_cb is None:
                return
            versatile_fields.visible = bool(versatile_cb.value)
            try:
                versatile_fields.update()
            except RuntimeError:
                pass

        if versatile_cb is not None:
            versatile_cb.on_change = _on_versatile_toggle

        # Autofill dal catalogo PHB (equipment/weapons.json) — 2026-07-16,
        # richiesta Davide: scegliendo il tipo dalla tendina, la scheda si
        # autoriempie con dado danno/tipo/proprietà/gittata di quell'arma;
        # i campi restano comunque liberamente modificabili dopo.
        catalog_dd = ft.Dropdown(
            label="Tipo (autoriempi da catalogo PHB)",
            value=None,
            options=(
                [ft.DropdownOption(key="", text="— nessuno, compila a mano —")]
                + [ft.DropdownOption(key=n, text=n) for n in _loader.get_weapon_names()]
            ),
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
        )

        def on_catalog_select(ev: ft.Event[ft.Dropdown]) -> None:
            name = catalog_dd.value or ""
            if not name:
                return
            data = _loader.get_weapon(name)
            if not data:
                return
            f_name.value = data.get("name") or name
            # .get(key, "") NON copre il caso in cui la chiave esista con
            # valore None (es. "Rete": damage_dice/damage_type sono null nel
            # catalogo perché non infligge danno) — .get(key) or "" sì.
            f_dice.value = data.get("damage_dice") or ""
            mapped_type = _map_catalog_damage_type(data.get("damage_type") or "")
            if mapped_type:
                dtype_dd.value = mapped_type
            ui_labels, versatile_dice, rng_n, rng_x = _resolve_catalog_weapon_properties(
                data.get("properties", [])
            )
            for cb in props_checks:
                cb.value = str(cb.label) in ui_labels
                cb.update()
            if versatile_dice:
                f_vdice.value = versatile_dice
            versatile_fields.visible = "Versatile" in ui_labels
            if rng_n or rng_x:
                f_rng.value = str(rng_n)
                f_rngmax.value = str(rng_x)
            f_name.update()
            f_dice.update()
            dtype_dd.update()
            versatile_fields.update()
            f_vdice.update()
            f_rng.update()
            f_rngmax.update()

        catalog_dd.on_select = on_catalog_select

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
            selected_props_list = [
                str(cb.label) if cb.label else ""
                for cb in props_checks
                if cb.value
            ]
            selected_props = ",".join(selected_props_list)

            # Dado a due mani/impugnatura: significativi solo se "Versatile"
            # è tra le proprietà selezionate — se il giocatore deseleziona
            # Versatile dopo averli compilati, li azzeriamo invece di
            # lasciare dati orfani non più raggiungibili dalla UI.
            is_versatile_selected = "Versatile" in selected_props_list
            versatile_dice = (f_vdice.value or "").strip() if is_versatile_selected else ""
            grip_two_handed = bool(grip_cb.value) if is_versatile_selected else False

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
                ok = character_repo.create_weapon(
                    self.character.id, name,
                    damage_dice=f_dice.value or "",
                    damage_type=dtype_dd.value or "",
                    attack_bonus=atk, damage_bonus=dbonus,
                    properties=selected_props,
                    is_equipped=equipped, is_magical=is_magical,
                    magic_description=magic_desc,
                    range_normal=rng, range_max=rngmax,
                    magic_damages=magic_damages_str,
                    versatile_damage_dice=versatile_dice,
                    grip_two_handed=grip_two_handed,
                )
            else:
                assert weapon is not None
                ok = character_repo.update_weapon(
                    weapon.id, name,
                    damage_dice=f_dice.value or "",
                    damage_type=dtype_dd.value or "",
                    attack_bonus=atk, damage_bonus=dbonus,
                    properties=selected_props,
                    is_equipped=equipped, is_magical=is_magical,
                    magic_description=magic_desc,
                    range_normal=rng, range_max=rngmax,
                    magic_damages=magic_damages_str,
                    versatile_damage_dice=versatile_dice,
                    grip_two_handed=grip_two_handed,
                )
            if not ok:
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Nuova Arma" if is_new else "Modifica Arma",
                          size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [catalog_dd, f_name, f_dice, dtype_dd, f_atk, f_dbonus,
                 props_section, versatile_fields, f_rng, f_rngmax, f_magic,
                 magic_section, equip_cb],
                spacing=8, scroll=ft.ScrollMode.AUTO,
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

    def _update_weapon_equipped_flag(
        self, weapon: Weapon, equipped: bool, grip_two_handed: bool | None = None
    ) -> bool:
        """Scrive is_equipped (e opzionalmente grip_two_handed) di un'arma,
        preservando tutti gli altri campi già presenti — helper condiviso da
        _toggle_weapon_equipped e _toggle_weapon_grip per evitare di ripetere
        l'elenco completo dei parametri ad ogni chiamata.

        `versatile_damage_dice`/`grip_two_handed` vanno SEMPRE ripassati a
        update_weapon (anche quando non cambiano): altrimenti, dato che
        update_weapon li accetta con default vuoti/False, un semplice
        equip/disequip azzererebbe silenziosamente l'impugnatura/il dado a
        due mani già impostati su un'arma Versatile (bug trovato il
        2026-07-11 mentre si implementava il grip Versatile — vedi CLAUDE.md).
        """
        return character_repo.update_weapon(
            weapon.id, weapon.name,
            damage_dice=weapon.damage_dice,
            damage_type=weapon.damage_type,
            attack_bonus=weapon.attack_bonus,
            damage_bonus=weapon.damage_bonus,
            properties=weapon.properties or "",
            is_equipped=equipped,
            is_magical=weapon.is_magical,
            magic_description=weapon.magic_description or "",
            range_normal=weapon.range_normal or 0,
            range_max=weapon.range_max or 0,
            magic_damages=weapon.magic_damages or "[]",
            versatile_damage_dice=weapon.versatile_damage_dice or "",
            grip_two_handed=(
                grip_two_handed if grip_two_handed is not None else weapon.grip_two_handed
            ),
        )

    def _toggle_weapon_equipped(self, weapon: Weapon) -> None:
        """
        Equipaggia/disequipaggia un'arma rispettando il limite di 2 mani del
        personaggio (PHB IT — vedi core/equipment_manager.py per le regole
        esatte e le fonti). Disequipaggiare è sempre un'operazione isolata
        (libera solo le mani di quell'arma). Equipaggiare invece può avere
        effetti a cascata: un'arma a due mani disequipaggia automaticamente
        tutte le altre armi e un eventuale scudo; un'arma a una mano
        disequipaggia automaticamente le armi più "vecchie" (in ordine di
        creazione) che non entrano più nelle mani rimaste libere.
        """
        if weapon.is_equipped:
            # Disequipaggiare non ha mai effetti a cascata.
            if not self._update_weapon_equipped_flag(weapon, False):
                show_error_dialog(self._page)
                return
            self._refresh()
            return

        candidates = [
            EquipCandidate(
                id=w.id, properties=w.properties or "", is_equipped=w.is_equipped,
                grip_two_handed=w.grip_two_handed,
            )
            for w in self._weapons
        ]
        shield_equipped = any(
            i.is_equipped and i.category == "armor" and i.armor_type == "scudo"
            for i in self._items
        )
        equipped_ids, unequip_shield = resolve_weapon_equip(
            candidates, weapon.id, shield_equipped
        )

        for w in self._weapons:
            new_state = w.id in equipped_ids
            if new_state != w.is_equipped:
                if not self._update_weapon_equipped_flag(w, new_state):
                    show_error_dialog(self._page)
                    return

        if unequip_shield:
            if not self._unequip_shield_and_recalc_ca():
                return

        self._refresh()

    def _unequip_shield_and_recalc_ca(self) -> bool:
        """Disequipaggia l'eventuale scudo indossato e ricalcola la CA —
        estratto come helper perché serve sia a _toggle_weapon_equipped sia
        a _toggle_weapon_grip (entrambi possono forzare un'arma a due mani,
        che non lascia mai spazio a uno scudo). Ritorna False (e mostra già
        il dialog d'errore) se una scrittura fallisce."""
        for i in self._items:
            if i.is_equipped and i.category == "armor" and i.armor_type == "scudo":
                ok = character_repo.update_inventory_item(
                    i.id, i.name, i.quantity, i.weight,
                    i.description or "", i.category or "misc",
                    False,
                    ca_value=i.ca_value or 0,
                    armor_type=i.armor_type or "",
                    effects=i.effects or "",
                )
                if not ok:
                    show_error_dialog(self._page)
                    return False
        new_ca = character_repo.calculate_and_update_ca(self.character.id)
        self.character.ac = new_ca
        return True

    def _toggle_weapon_grip(self, weapon: Weapon) -> None:
        """
        Cambia l'impugnatura (1 mano ↔ 2 mani) di un'arma con la proprietà
        "Versatile" (PHB IT, vedi core/equipment_manager.py). Passare a
        un'impugnatura a una mano non ha mai effetti a cascata (libera
        spazio, non ne occupa). Passare a due mani su un'arma già
        equipaggiata invece richiede lo stesso calcolo di conflitto usato
        per l'equip iniziale, perché l'arma da quel momento occupa
        l'intera capacità di mani del personaggio.
        """
        new_grip = not weapon.grip_two_handed

        if not (weapon.is_equipped and new_grip):
            if not self._update_weapon_equipped_flag(weapon, weapon.is_equipped, new_grip):
                show_error_dialog(self._page)
                return
            self._refresh()
            return

        candidates = [
            EquipCandidate(
                id=w.id, properties=w.properties or "", is_equipped=w.is_equipped,
                grip_two_handed=(new_grip if w.id == weapon.id else w.grip_two_handed),
            )
            for w in self._weapons
        ]
        shield_equipped = any(
            i.is_equipped and i.category == "armor" and i.armor_type == "scudo"
            for i in self._items
        )
        equipped_ids, unequip_shield = resolve_weapon_equip(
            candidates, weapon.id, shield_equipped
        )

        for w in self._weapons:
            if w.id == weapon.id:
                if not self._update_weapon_equipped_flag(w, w.is_equipped, new_grip):
                    show_error_dialog(self._page)
                    return
                continue
            new_state = w.id in equipped_ids
            if new_state != w.is_equipped:
                if not self._update_weapon_equipped_flag(w, new_state):
                    show_error_dialog(self._page)
                    return

        if unequip_shield:
            if not self._unequip_shield_and_recalc_ca():
                return

        self._refresh()

    def _toggle_item_equipped(self, item: InventoryItem) -> None:
        """
        Equipaggia/disequipaggia rapidamente un oggetto generico (armatura,
        scudo, attrezzo, ecc.) senza dover aprire il dialog "Modifica" —
        stesso pattern del toggle rapido già esistente per le armi
        (_toggle_weapon_equipped). Se l'oggetto è un'armatura/scudo:
          - equipaggiare applica l'esclusione reciproca di postazione
            (core/equipment_manager.py — una sola armatura indossata, un
            solo scudo impugnato) PRIMA di ricalcolare la CA, altrimenti
            equipaggiarne una seconda senza disequipaggiare la prima
            lasciava la CA legata alla prima armatura creata (bug reale:
            calculate_and_update_ca() usa `equipped_armor[0]`, quindi
            "vince" sempre la prima della lista finché non viene
            esplicitamente disequipaggiata);
          - disequipaggiare resta un'operazione isolata (libera solo la
            propria postazione, nessun effetto a cascata).
        """
        new_state = not item.is_equipped
        ok = character_repo.update_inventory_item(
            item.id, item.name, item.quantity, item.weight,
            item.description or "", item.category or "misc",
            new_state,
            ca_value=item.ca_value or 0,
            armor_type=item.armor_type or "",
            effects=item.effects or "",
        )
        if not ok:
            show_error_dialog(self._page)
            return
        if (item.category or "") == "armor":
            if new_state:
                self._items = character_repo.get_inventory(self.character.id)
                if not self._enforce_armor_exclusivity(item.id):
                    return
            new_ca = character_repo.calculate_and_update_ca(self.character.id)
            self.character.ac = new_ca
        self._refresh()

    def _enforce_armor_exclusivity(self, target_id: str) -> bool:
        """
        Da chiamare SUBITO DOPO aver scritto `is_equipped=True` per
        l'armatura/scudo `target_id` (già persistito su DB): calcola con
        core/equipment_manager.py quali altre armature/scudi occupano la
        stessa postazione e li disequipaggia. Si aspetta `self._items`
        già aggiornato (letto fresco dal DB) in modo da vedere lo stato
        corretto di `target_id`.

        Ritorna False (mostrando già il dialog d'errore) se una scrittura
        fallisce, True altrimenti — il chiamante deve interrompersi senza
        ricalcolare la CA se il ritorno è False, per non presentare una
        CA calcolata su uno stato di equipaggiamento parzialmente scritto.
        """
        candidates = [
            ArmorCandidate(id=i.id, armor_type=i.armor_type or "", is_equipped=i.is_equipped)
            for i in self._items if (i.category or "") == "armor"
        ]
        keep_ids = resolve_armor_equip(candidates, target_id)
        for i in self._items:
            if (i.category or "") != "armor":
                continue
            should_be_equipped = i.id in keep_ids
            if should_be_equipped != i.is_equipped:
                ok = character_repo.update_inventory_item(
                    i.id, i.name, i.quantity, i.weight,
                    i.description or "", i.category or "misc",
                    should_be_equipped,
                    ca_value=i.ca_value or 0,
                    armor_type=i.armor_type or "",
                    effects=i.effects or "",
                )
                if not ok:
                    show_error_dialog(self._page)
                    return False
        return True

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

    def _open_item_dialog(
        self, page: ft.Page, item: InventoryItem | None,
        force_category: str | None = None,
    ) -> None:
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

        if is_new:
            initial_cat = force_category or "misc"
        else:
            initial_cat = item.category or "misc"

        # "weapon" ("Armi (riserva)") deliberatamente assente dalle scelte
        # normali: le armi si creano sempre nella sezione Armi dedicata
        # (tabella weapons), non più come categoria di oggetto generico —
        # vedi CLAUDE.md 2026-07-11 "Armi riserva". Riaggiunta come opzione
        # SOLO se si sta modificando un item che ha già questa categoria
        # (es. una migrazione automatica fallita, vedi
        # _migrate_legacy_weapon_items): il Dropdown di Flet richiede che
        # `value` compaia tra `options`, altrimenti il campo si presenta
        # vuoto anche se il dato esiste.
        cat_options = [
            ft.DropdownOption(key="misc",   text="Varie"),
            ft.DropdownOption(key="armor",  text="Armature & Scudi"),
            ft.DropdownOption(key="tool",   text="Strumenti"),
            ft.DropdownOption(key="magic",  text="Oggetti Magici"),
        ]
        if initial_cat == "weapon":
            cat_options.append(ft.DropdownOption(key="weapon", text="Armi (riserva) — legacy"))

        cat_dd = ft.Dropdown(
            label="Categoria",
            value=initial_cat,
            options=cat_options,
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
        # Autofill dal catalogo PHB (equipment/armor.json) — 2026-07-16,
        # richiesta Davide: scegliendo il "Tipo" dalla tendina, la scheda si
        # autoriempie con CA/tipo/peso di quell'armatura; i campi restano
        # comunque liberamente modificabili dopo (nessun campo bloccato).
        catalog_dd = ft.Dropdown(
            label="Tipo (autoriempi da catalogo PHB)",
            value=None,
            options=(
                [ft.DropdownOption(key="", text="— nessuno, compila a mano —")]
                + [ft.DropdownOption(key=n, text=n) for n in _loader.get_armor_names()]
            ),
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
        )

        def on_catalog_select(ev: ft.Event[ft.Dropdown]) -> None:
            name = catalog_dd.value or ""
            if not name:
                return
            data = _loader.get_armor_item(name)
            if not data:
                return
            f_name.value = data.get("name", name)
            f_ca.value = str(data.get("ca_value", 0))
            armor_type_dd.value = data.get("armor_type", "")
            weight = data.get("weight_kg")
            if weight is not None:
                f_wt.value = f"{weight:g}"
            desc = data.get("description", "")
            if desc:
                f_desc.value = desc
            f_name.update()
            f_ca.update()
            armor_type_dd.update()
            f_wt.update()
            f_desc.update()

        catalog_dd.on_select = on_catalog_select

        armor_fields = ft.Column(
            cast(list[ft.Control], [label_text("CAMPI ARMATURA / SCUDO", 10),
                                    catalog_dd, f_ca, armor_type_dd]),
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
                new_id = character_repo.create_inventory_item(
                    self.character.id, name, qty, wt, desc, cat, equipped,
                    ca_value=ca_val, armor_type=arm_type, effects=effects,
                )
                if not new_id:
                    show_error_dialog(page)
                    return
                saved_id = new_id
            else:
                assert item is not None
                ok = character_repo.update_inventory_item(
                    item.id, name, qty, wt, desc, cat, equipped,
                    ca_value=ca_val, armor_type=arm_type, effects=effects,
                )
                if not ok:
                    show_error_dialog(page)
                    return
                saved_id = item.id

            # Se è un'armatura/scudo equipaggiato, applica l'esclusione
            # reciproca di postazione (core/equipment_manager.py) PRIMA di
            # ricalcolare la CA — stesso bug/fix di _toggle_item_equipped:
            # senza questo passaggio, equipaggiare una seconda armatura da
            # questo dialog senza disequipaggiare la prima non avrebbe
            # aggiornato la CA (calculate_and_update_ca() usa sempre la
            # prima armatura equipaggiata trovata).
            was_armor = (not is_new) and item is not None and item.category == "armor"
            if cat == "armor" or was_armor:
                if cat == "armor" and equipped:
                    self._items = character_repo.get_inventory(self.character.id)
                    if not self._enforce_armor_exclusivity(saved_id):
                        return
                new_ca = character_repo.calculate_and_update_ca(self.character.id)
                self.character.ac = new_ca
            page.pop_dialog()
            self._refresh()

        if is_new:
            dialog_title = "Nuova Armatura" if force_category == "armor" else "Nuovo Oggetto"
        else:
            dialog_title = "Modifica Oggetto"
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(dialog_title,
                          size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [f_name, f_qty, f_wt, cat_dd, armor_fields,
                 equip_cb, f_desc, f_effects],
                spacing=8, scroll=ft.ScrollMode.AUTO,
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

    # Etichette abbreviate PHB per le 5 valute, stesse già usate nella
    # sezione Monete di questo tab (MR/MA/ME/MO/MP).
    _CURRENCY_ABBR = {
        "copper": "mr", "silver": "ma", "electrum": "me",
        "gold": "mo", "platinum": "mp",
    }

    def _catalog_ref_line(self, name: str, kind: str) -> ft.Text | None:
        """
        Riga di sola consultazione con costo/peso PHB per un'arma o
        un'armatura, risolta dal catalogo `equipment/weapons.json`/
        `equipment/armor.json` (task #22, 2026-07-16 — wiring read-only,
        nessuna modifica allo schema DB o al calcolo del peso trasportato
        già esistente, ambito confermato con Davide). Ritorna None se il
        nome non risolve nel catalogo (es. armi/armature homebrew inserite
        a mano, o "Abito comune" — non è un errore, è previsto).

        `kind`: "weapon" o "armor".
        """
        entry = (
            _loader.get_weapon(name) if kind == "weapon"
            else _loader.get_armor_item(name)
        )
        if not entry:
            return None
        parts: list[str] = []
        cost = entry.get("cost") or {}
        qty = cost.get("quantity")
        ctype = cost.get("currency_type")
        if qty is not None and ctype:
            abbr = self._CURRENCY_ABBR.get(ctype, ctype)
            parts.append(f"{qty} {abbr}")
        weight = entry.get("weight_kg")
        if weight is not None:
            parts.append(f"{weight:g} kg")
        if kind == "armor":
            str_req = entry.get("strength_requirement")
            if str_req:
                parts.append(f"For {str_req}")
            stealth = entry.get("stealth")
            if stealth:
                parts.append(f"Furtività: {stealth}")
        if not parts:
            return None
        return ft.Text(
            f"PHB: {' · '.join(parts)}", size=10, color=COLOR_TEXT_MUTED, italic=True,
        )

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
        if self._on_refresh:
            self._on_refresh()
