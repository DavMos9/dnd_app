"""
Vista "Bottino" — quarta tab di `MasterView` (passo 3 di
`dnd_app/docs/loot_design.md` §8). Due elenchi sulla stessa tabella
`loot_stash_entries` (`data/repositories/loot_repo.py`), distinti da
`stash_kind`: **Archivio del Master** e **Deposito del Gruppo**
(`stash_kind="party"`) — entrambi scoped al mondo correntemente
selezionato in `MasterView` (`_effective_world_id()` qui sotto;
`world_id=""` se il Master lavora in locale, comportamento di sempre per
chi non usa il Multiplayer). "Privato" (mai sincronizzato via mondo, per
l'Archivio del Master) e "scoped al mondo selezionato" non sono in
contraddizione — restano due assi indipendenti: l'archivio resta sempre
privato del dispositivo, ma è comunque filtrato per il mondo corrente.

Operazioni per voce: **assegna** (apre `master_loot_assign_dialog`),
**sposta** tra i due contenitori, **modifica**, **elimina** — più
**"+ Aggiungi voce"** per registrare a mano bottino non ancora collegato a
un generatore (uso raro: la via principale per riempire l'archivio è il
pulsante "Salva nell'archivio" nei generatori/compendi, passo 5 dello stesso
piano).
"""

from __future__ import annotations

import logging
from typing import Any, cast

import flet as ft

from core import world_permissions as perm
from core import world_sync
from core.world_backend import LocalBackend
from data.models import LootStashEntry
from data.repositories import loot_repo, world_repo
from ui import design
from ui.widgets import responsive_dialog_width, wrap_dialog_actions, show_snack

logger = logging.getLogger(__name__)

_KIND_OPTIONS: list[tuple[str, str]] = [
    ("item", "Oggetto"),
    ("magic_item", "Oggetto Magico"),
    ("artifact", "Artefatto"),
    ("weapon", "Arma"),
    ("armor", "Armatura"),
    ("poison", "Veleno"),
    ("gem", "Gemma"),
    ("art", "Oggetto d'Arte"),
    ("coins", "Monete"),
]
_KIND_LABELS: dict[str, str] = dict(_KIND_OPTIONS)
#: entry_kind con caselle MECCANICHE dedicate invece del solo nome/
#: descrizione/quantità libera — bug report Davide (2026-08-20): "non ti
#: fa selezionare armi armature... devono avere le stesse caselle di
#: quando crei l'arma o l'armatura nella sezione giocatore". Vedi
#: `master_loot_assign_dialog.build_weapon_mechanics_fields()`/
#: `build_armor_mechanics_fields()`.
_MECHANICAL_KINDS: frozenset[str] = frozenset({"weapon", "armor"})
_KIND_ICONS: dict[str, str] = {
    "item": ft.Icons.BACKPACK_OUTLINED,
    "magic_item": ft.Icons.AUTO_AWESOME,
    "artifact": ft.Icons.DIAMOND,
    "weapon": ft.Icons.FLASH_ON,
    "armor": ft.Icons.SHIELD,
    "poison": ft.Icons.SICK_OUTLINED,
    "gem": ft.Icons.DIAMOND_OUTLINED,
    "art": ft.Icons.PALETTE_OUTLINED,
    "coins": ft.Icons.PAID_OUTLINED,
}
#: Voci a tema arcano — accento `magic` (indaco/violetto, secondo registro
#: compositivo Arcane Ledger) invece di `primary`, così un oggetto magico o
#: un artefatto si distingue a colpo d'occhio dal bottino mondano nella
#: stessa lista (audit anti-AI-slop, richiesta esplicita del brief di restyle).
_MAGIC_KINDS: frozenset[str] = frozenset({"magic_item", "artifact"})
_COIN_FIELDS: list[tuple[str, str]] = [
    ("platinum", "Platino (mp)"), ("gold", "Oro (mo)"), ("electrum", "Electrum (me)"),
    ("silver", "Argento (ma)"), ("copper", "Rame (mr)"),
]


def _mechanics_summary(entry: LootStashEntry) -> str:
    """Riepilogo a colpo d'occhio delle caselle meccaniche di una voce
    "weapon"/"armor" (2026-08-20) — vuoto per ogni altro entry_kind."""
    if entry.entry_kind == "weapon":
        bits = [b for b in (entry.weapon_damage_dice, entry.weapon_damage_type) if b]
        if entry.weapon_category:
            bits.append(_KIND_LABELS.get(entry.weapon_category, entry.weapon_category))
        if entry.weapon_attack_bonus:
            bits.append(f"{entry.weapon_attack_bonus:+d} attacco")
        if entry.weapon_damage_bonus:
            bits.append(f"{entry.weapon_damage_bonus:+d} danno")
        return " · ".join(bits)
    if entry.entry_kind == "armor":
        bits = []
        if entry.armor_ca_value:
            bits.append(f"CA {entry.armor_ca_value}")
        if entry.armor_type:
            bits.append(entry.armor_type.capitalize())
        return " · ".join(bits)
    return ""


def _coin_summary(entry: LootStashEntry) -> str:
    parts = []
    for key, abbr in (("platinum", "mp"), ("gold", "mo"), ("electrum", "me"),
                      ("silver", "ma"), ("copper", "mr")):
        val = getattr(entry, key, 0)
        if val:
            parts.append(f"{val} {abbr}")
    return ", ".join(parts) if parts else "nessuna moneta"


class MasterLootView(ft.Column):
    """Tab «Bottino»: archivio del Master + deposito del gruppo."""

    def __init__(self, world_id: str = "", device_id: str = "") -> None:
        super().__init__(expand=True, spacing=0, scroll=ft.ScrollMode.AUTO)
        self._page: ft.Page | None = None
        #: Mondo correntemente selezionato in `MasterView` — "" per la
        #: modalità locale. Si applica a ENTRAMBI i contenitori
        #: (`stash_kind="master"`/`"party"`): un mondo è un container, non
        #: solo per il deposito comune — la privacy dell'archivio del
        #: Master (mai sincronizzato/visibile ai giocatori) resta un asse
        #: indipendente da questo, invariata.
        self._world_id = world_id
        #: Identità di questo dispositivo — instrada le
        #: scritture sul deposito del gruppo (`stash_kind="party"`) via
        #: rete quando `_world_id` è valorizzato, vedi
        #: `_resolve_stash_backend()`. L'archivio del Master
        #: (`stash_kind="master"`) resta sempre locale, non lo usa mai.
        self._device_id = device_id
        self._remote_backends: dict[str, Any] = {}
        self._active_kind: str = "master"  # "master" | "party"
        self._list_col = ft.Column(spacing=8)
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    def _effective_world_id(self) -> str:
        """Il `world_id` da usare per l'elenco/le nuove voci correnti —
        stesso mondo selezionato per entrambi i contenitori, vedi il
        commento nel costruttore."""
        return self._world_id

    def _resolve_stash_backend(self):
        """Backend per un comando `CMD_LOOT_STASH_*` — `None` se non c'è un
        mondo selezionato o l'host non è raggiungibile, stesso meccanismo
        di `MasterEncounterView._resolve_encounter_backend()`."""
        if not self._world_id:
            return None
        world = world_repo.get_world(self._world_id)
        if world is None:
            return None
        return world_sync.resolve_backend_for_world(
            world, self._device_id or "", LocalBackend(), self._remote_backends,
        )

    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.controls.clear()
        self.controls.append(self._build_header())
        self.controls.append(ft.Container(content=self._list_col,
                                           padding=ft.Padding.symmetric(horizontal=16, vertical=8)))
        self._populate_list()

    def _build_header(self) -> ft.Container:
        # Unico momento "hero" di questa tab (Arcane Ledger): prima un
        # `ft.Text` di 15px come qualunque altra etichetta, qui è la vera
        # intestazione della schermata "Bottino".
        title_block = design.hero_title("Bottino")
        title_block.expand = True
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            design.icon_badge(ft.Icons.INVENTORY_2_OUTLINED, tone="primary", size=36),
                            ft.Container(width=design.Space.MD),
                            title_block,
                            ft.ElevatedButton(
                                "+ Aggiungi voce", icon=ft.Icons.ADD,
                                on_click=lambda e: self._open_add_dialog(),
                                style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    self._build_kind_switch(),
                ],
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            bgcolor=design.T().surface,
            border=ft.Border(bottom=ft.BorderSide(1, design.T().border)),
        )

    def _build_kind_switch(self) -> ft.Control:
        items = []
        for key, label, icon in (
            ("master", "Archivio del Master", ft.Icons.LOCK_OUTLINE),
            ("party", "Deposito del Gruppo", ft.Icons.GROUPS_OUTLINED),
        ):
            is_sel = key == self._active_kind
            items.append(ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=14, color=design.T().primary_icon if is_sel else design.T().text_3),
                     ft.Container(width=6),
                     ft.Text(label, size=12, weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.W_500,
                             color=design.T().primary if is_sel else design.T().text_2)],
                    alignment=ft.MainAxisAlignment.CENTER, tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=design.Space.MD, vertical=design.Space.SM),
                border_radius=design.Radius.PILL,
                bgcolor=design.T().surface_alt if is_sel else "transparent",
                shadow=design.elevation(1) if is_sel else None,
                on_click=lambda e, k=key: self._on_kind_switch(k),
                ink=True, expand=True,
            ))
        return ft.Container(
            content=ft.Row(items, spacing=design.Space.XS),
            bgcolor=design.T().bg, border_radius=design.Radius.PILL, padding=design.Space.XS,
        )

    def _on_kind_switch(self, key: str) -> None:
        if key == self._active_kind:
            return
        self._active_kind = key
        self._refresh()

    # ------------------------------------------------------------------
    # Lista
    # ------------------------------------------------------------------

    def _populate_list(self) -> None:
        entries = loot_repo.get_entries(self._active_kind, world_id=self._effective_world_id())
        self._list_col.controls.clear()
        if not entries:
            self._list_col.controls.append(design.empty_state(
                ft.Icons.INVENTORY_2_OUTLINED,
                "Nessuna voce" if self._active_kind == "master" else "Deposito vuoto",
                "Salva bottino qui dai generatori, dal Compendio o dagli Artefatti, "
                "oppure aggiungilo a mano con «+ Aggiungi voce».",
            ))
            return
        for entry in entries:
            self._list_col.controls.append(self._entry_card(entry))

    def _entry_card(self, entry: LootStashEntry) -> ft.Control:
        is_coins = entry.entry_kind == "coins"
        is_magic = entry.entry_kind in _MAGIC_KINDS
        title = "Monete" if is_coins else entry.name
        subtitle = _coin_summary(entry) if is_coins else (
            (entry.description or "").split("\n")[0][:110]
        )
        qty_bit = f" ×{entry.quantity}" if (not is_coins and entry.quantity != 1) else ""
        icon_color = design.T().magic if is_magic else design.T().primary

        return design.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(_KIND_ICONS.get(entry.entry_kind, ft.Icons.BACKPACK_OUTLINED),
                                    size=16, color=icon_color),
                            ft.Container(width=8),
                            # `expand=True` + `wrap=True` sulla stessa Row non è valido in Flet
                            # 0.85.3: `wrap=True` genera un widget Flutter `Wrap`, che non supporta
                            # figli `Expanded` (solo `Row`/`Column` lo supportano) — la combinazione
                            # produce un crash silenzioso lato Flutter (nessun errore Python, il
                            # widget appare come un riquadro grigio vuoto). Fix: niente `wrap` su
                            # questa Row, il titolo tronca con l'ellissi invece di andare a capo.
                            ft.Text(f"{title}{qty_bit}", size=13, weight=ft.FontWeight.BOLD,
                                    color=design.T().text, expand=True,
                                    no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                            design.chip(_KIND_LABELS.get(entry.entry_kind, entry.entry_kind),
                                        "magic" if is_magic else "neutral"),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(subtitle, size=11, color=design.T().text_2) if subtitle else ft.Container(height=0),
                    ft.Text(_mechanics_summary(entry), size=11, color=design.T().primary_icon,
                            weight=ft.FontWeight.W_600) if _mechanics_summary(entry) else ft.Container(height=0),
                    ft.Text(f"Fonte: {entry.source_note}", size=10, color=design.T().text_3, italic=True)
                    if entry.source_note else ft.Container(height=0),
                    ft.Row(
                        [
                            ft.OutlinedButton("Assegna…", icon=ft.Icons.SEND_OUTLINED,
                                              on_click=lambda e, en=entry: self._on_assign(en)),
                            ft.OutlinedButton(
                                "Sposta al Deposito" if self._active_kind == "master" else "Sposta all'Archivio",
                                icon=ft.Icons.SWAP_HORIZ,
                                on_click=lambda e, en=entry: self._on_move(en),
                            ),
                            ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, icon_size=18,
                                          tooltip="Modifica", on_click=lambda e, en=entry: self._open_edit_dialog(en)),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=18,
                                          icon_color=design.T().danger_icon, tooltip="Elimina",
                                          on_click=lambda e, en=entry: self._on_delete(en)),
                        ],
                        spacing=6, wrap=True,
                    ),
                ],
                spacing=4,
            ),
            accent=design.T().magic if is_magic else None,
            density="dense",
        )

    def _refresh(self) -> None:
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass

    def _refresh_list_only(self) -> None:
        self._populate_list()
        try:
            self._list_col.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Azioni
    # ------------------------------------------------------------------

    def _on_assign(self, entry: LootStashEntry) -> None:
        page = self._page
        if page is None:
            return
        from ui.views.master.master_loot_assign_dialog import item_from_stash_entry, show_loot_assign_dialog
        show_loot_assign_dialog(page, [item_from_stash_entry(entry)], on_committed=self._refresh_list_only,
                                 world_id=self._world_id, device_id=self._device_id)

    def _on_move(self, entry: LootStashEntry) -> None:
        new_kind = "party" if self._active_kind == "master" else "master"
        # Con un mondo selezionato lo spostamento passa dalla rete
        # (`CMD_LOOT_STASH_MOVE`) — l'handler host non distingue l'origine
        # (`entry.stash_kind` d'origine), quindi funziona in entrambe le
        # direzioni master<->party, vedi il suo docstring in
        # `core/world_backend.py`. Fallback locale se l'host non è
        # raggiungibile o non c'è un mondo selezionato — world_id passato
        # esplicito: senza, `move_entry` lo azzererebbe al default "".
        backend = self._resolve_stash_backend()
        if self._world_id and backend is not None:
            result = backend.send_command(
                self._world_id, self._device_id or "", perm.CMD_LOOT_STASH_MOVE,
                {"entry_id": entry.id, "new_stash_kind": new_kind},
                target_type="loot_stash", target_id=entry.id,
            )
            if not result.success and self._page is not None:
                show_snack(self._page, result.error or "Spostamento fallito.", tone="danger")
        else:
            loot_repo.move_entry(entry.id, new_kind, new_world_id=self._world_id)
        self._refresh_list_only()

    def _on_delete(self, entry: LootStashEntry) -> None:
        page = self._page
        if page is None:
            return

        def do_delete(ev: Any) -> None:
            if page is None:
                return
            # Solo una voce "party" con un mondo selezionato passa dalla
            # rete — l'archivio del Master resta sempre locale, stesso
            # motivo di `_on_move` sopra (vedi `_handle_loot_stash_delete`,
            # che rifiuta apposta una voce non "party").
            backend = self._resolve_stash_backend()
            if self._world_id and entry.stash_kind == "party" and backend is not None:
                result = backend.send_command(
                    self._world_id, self._device_id or "", perm.CMD_LOOT_STASH_DELETE,
                    {"entry_id": entry.id}, target_type="loot_stash", target_id=entry.id,
                )
                if not result.success:
                    show_snack(page, result.error or "Eliminazione fallita.", tone="danger")
                    page.pop_dialog()
                    return
            else:
                loot_repo.delete_entry(entry.id)
            page.pop_dialog()
            self._refresh_list_only()

        title = "Monete" if entry.entry_kind == "coins" else (entry.name or "voce")
        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Elimina voce"),
            content=ft.Text(f"Eliminare «{title}» dal bottino? L'azione non è reversibile.",
                             size=13, color=design.T().text),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=do_delete,
                                  style=ft.ButtonStyle(bgcolor=design.T().danger_fill, color=design.T().on_primary_fill)),
            ]),
        ))

    def _open_edit_dialog(self, entry: LootStashEntry) -> None:
        page = self._page
        if page is None:
            return
        is_coins = entry.entry_kind == "coins"

        if is_coins:
            fields = {k: ft.TextField(value=str(getattr(entry, k, 0)), label=label, dense=True,
                                       keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
                      for k, label in _COIN_FIELDS}
            note_tf = ft.TextField(value=entry.source_note, label="Fonte / note", dense=True, **design.field_style())

            def save_coins(ev: Any) -> None:
                if page is None:
                    return
                values = {}
                for k, tf in fields.items():
                    try:
                        values[k] = max(0, int((tf.value or "0").strip()))
                    except ValueError:
                        values[k] = 0
                # `loot_repo.update_entry()` non tocca le 5 colonne valuta (pensato
                # per le voci non monetarie): per una voce "coins" si passa da
                # elimina+ricrea, più semplice che aggiungere una funzione di
                # scrittura usata da un solo chiamante — stesso principio in
                # rete (CMD_LOOT_STASH_DELETE + CMD_LOOT_STASH_ADD) quando la
                # voce è "party" e c'è un mondo selezionato.
                backend = self._resolve_stash_backend()
                if self._world_id and entry.stash_kind == "party" and backend is not None:
                    backend.send_command(
                        self._world_id, self._device_id or "", perm.CMD_LOOT_STASH_DELETE,
                        {"entry_id": entry.id}, target_type="loot_stash", target_id=entry.id,
                    )
                    backend.send_command(
                        self._world_id, self._device_id or "", perm.CMD_LOOT_STASH_ADD,
                        {
                            "entry_kind": "coins", "source_note": (note_tf.value or "").strip(),
                            **values,
                        },
                        target_type="loot_stash",
                    )
                else:
                    loot_repo.delete_entry(entry.id)
                    loot_repo.create_entry(
                        entry.stash_kind, "coins", source_note=(note_tf.value or "").strip(),
                        world_id=entry.world_id,
                        copper=values["copper"], silver=values["silver"], electrum=values["electrum"],
                        gold=values["gold"], platinum=values["platinum"],
                    )
                page.pop_dialog()
                self._refresh_list_only()

            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title("Modifica Monete"),
                content=ft.Column([fields["platinum"], fields["gold"], fields["electrum"],
                                    fields["silver"], fields["copper"], note_tf],
                                   spacing=10, scroll=ft.ScrollMode.AUTO,
                                   width=responsive_dialog_width(page, 380)),
                actions=wrap_dialog_actions([
                    ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog() if page else None),
                    ft.ElevatedButton("Salva", icon=ft.Icons.SAVE_OUTLINED, on_click=save_coins,
                                      style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill)),
                ]),
            ))
            return

        name_tf = ft.TextField(value=entry.name, label="Nome", dense=True, **design.field_style())
        qty_tf = ft.TextField(value=str(entry.quantity), label="Quantità", dense=True,
                               keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        desc_tf = ft.TextField(value=entry.description, label="Descrizione", multiline=True,
                                min_lines=3, max_lines=10, **design.field_style())
        note_tf = ft.TextField(value=entry.source_note, label="Fonte / note", dense=True, **design.field_style())

        # Voce "weapon"/"armor" (2026-08-20): stesse caselle meccaniche di
        # `_open_add_dialog`, precompilate dai valori correnti — vedi
        # `master_loot_assign_dialog.build_weapon_mechanics_fields()`/
        # `build_armor_mechanics_fields()`.
        mechanics_getter = None
        content_controls: list[ft.Control] = [name_tf, qty_tf, desc_tf, note_tf]
        if entry.entry_kind in _MECHANICAL_KINDS:
            from ui.views.master.master_loot_assign_dialog import (
                build_armor_mechanics_fields, build_weapon_mechanics_fields,
            )
            prefill = {
                "weapon_damage_dice": entry.weapon_damage_dice,
                "weapon_damage_type": entry.weapon_damage_type,
                "weapon_category": entry.weapon_category,
                "weapon_properties": entry.weapon_properties,
                "weapon_attack_bonus": entry.weapon_attack_bonus,
                "weapon_damage_bonus": entry.weapon_damage_bonus,
                "armor_ca_value": entry.armor_ca_value,
                "armor_type": entry.armor_type,
                "armor_effects": entry.armor_effects,
            }
            builder = (build_weapon_mechanics_fields if entry.entry_kind == "weapon"
                       else build_armor_mechanics_fields)
            mechanics_control, mechanics_getter = builder(prefill)
            content_controls.append(ft.Divider(height=1, color=design.T().border))
            content_controls.append(mechanics_control)

        def save_item(ev: Any) -> None:
            if page is None:
                return
            try:
                qty = max(1, int((qty_tf.value or "1").strip()))
            except ValueError:
                qty = 1
            mechanics = mechanics_getter() if mechanics_getter else {}
            backend = self._resolve_stash_backend()
            if self._world_id and entry.stash_kind == "party" and backend is not None:
                backend.send_command(
                    self._world_id, self._device_id or "", perm.CMD_LOOT_STASH_UPDATE,
                    {
                        "entry_id": entry.id, "name": (name_tf.value or "").strip(),
                        "description": (desc_tf.value or "").strip(), "quantity": qty,
                        "source_note": (note_tf.value or "").strip(),
                        **mechanics,
                    },
                    target_type="loot_stash", target_id=entry.id,
                )
            else:
                loot_repo.update_entry(
                    entry.id, name=(name_tf.value or "").strip(),
                    description=(desc_tf.value or "").strip(), quantity=qty,
                    source_note=(note_tf.value or "").strip(),
                    **mechanics,
                )
            page.pop_dialog()
            self._refresh_list_only()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Modifica Voce"),
            content=ft.Column(content_controls, spacing=10,
                               scroll=ft.ScrollMode.AUTO, width=responsive_dialog_width(page, 420)),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog() if page else None),
                ft.ElevatedButton("Salva", icon=ft.Icons.SAVE_OUTLINED, on_click=save_item,
                                  style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill)),
            ]),
        ))

    def _open_add_dialog(self) -> None:
        page = self._page
        if page is None:
            return
        state: dict[str, Any] = {"kind": "item", "mechanics_getter": None}
        kind_dd = ft.Dropdown(
            label="Tipo di voce", value="item",
            options=[ft.DropdownOption(key=k, text=label) for k, label in _KIND_OPTIONS],
            **design.field_style(),
        )
        fields_col = ft.Column(spacing=10)

        name_tf = ft.TextField(label="Nome", dense=True, **design.field_style())
        qty_tf = ft.TextField(label="Quantità", value="1", dense=True,
                              keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        desc_tf = ft.TextField(label="Descrizione", multiline=True, min_lines=3, max_lines=8,
                               **design.field_style())
        note_tf = ft.TextField(label="Fonte / note (opzionale)", dense=True, **design.field_style())
        coin_tfs = {k: ft.TextField(label=label, value="0", dense=True,
                                    keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
                    for k, label in _COIN_FIELDS}

        def _render_fields() -> None:
            fields_col.controls.clear()
            state["mechanics_getter"] = None
            if state["kind"] == "coins":
                fields_col.controls.extend(
                    [coin_tfs["platinum"], coin_tfs["gold"], coin_tfs["electrum"],
                     coin_tfs["silver"], coin_tfs["copper"], note_tf]
                )
            else:
                fields_col.controls.extend([name_tf, qty_tf, desc_tf, note_tf])
                if state["kind"] in _MECHANICAL_KINDS:
                    from ui.views.master.master_loot_assign_dialog import (
                        build_armor_mechanics_fields, build_weapon_mechanics_fields,
                    )
                    builder = (build_weapon_mechanics_fields if state["kind"] == "weapon"
                               else build_armor_mechanics_fields)
                    mechanics_control, getter = builder()
                    state["mechanics_getter"] = getter
                    fields_col.controls.append(ft.Divider(height=1, color=design.T().border))
                    fields_col.controls.append(mechanics_control)
            try:
                fields_col.update()
            except RuntimeError:
                pass

        def _on_kind_change(e: Any) -> None:
            state["kind"] = kind_dd.value or "item"
            _render_fields()

        kind_dd.on_select = _on_kind_change

        def save(ev: Any) -> None:
            if page is None:
                return
            kind = state["kind"]
            # Solo il deposito del gruppo ("party") con un mondo selezionato
            # passa dalla rete — l'archivio del Master resta sempre locale.
            backend = self._resolve_stash_backend() if self._active_kind == "party" else None
            use_network = bool(self._world_id and self._active_kind == "party" and backend is not None)
            if kind == "coins":
                values = {}
                for k, tf in coin_tfs.items():
                    try:
                        values[k] = max(0, int((tf.value or "0").strip()))
                    except ValueError:
                        values[k] = 0
                if not any(values.values()):
                    show_snack(page, "Nessuna moneta indicata.", tone="warning")
                    return
                if use_network:
                    backend.send_command(
                        self._world_id, self._device_id or "", perm.CMD_LOOT_STASH_ADD,
                        {
                            "entry_kind": "coins", "source_note": (note_tf.value or "").strip(),
                            **values,
                        },
                        target_type="loot_stash",
                    )
                else:
                    loot_repo.create_entry(
                        self._active_kind, "coins", source_note=(note_tf.value or "").strip(),
                        copper=values["copper"], silver=values["silver"], electrum=values["electrum"],
                        gold=values["gold"], platinum=values["platinum"],
                        world_id=self._effective_world_id(),
                    )
            else:
                name = (name_tf.value or "").strip()
                if not name:
                    show_snack(page, "Il nome è obbligatorio.", tone="warning")
                    return
                try:
                    qty = max(1, int((qty_tf.value or "1").strip()))
                except ValueError:
                    qty = 1
                mechanics = state["mechanics_getter"]() if state["mechanics_getter"] else {}
                if use_network:
                    backend.send_command(
                        self._world_id, self._device_id or "", perm.CMD_LOOT_STASH_ADD,
                        {
                            "entry_kind": kind, "name": name,
                            "description": (desc_tf.value or "").strip(), "quantity": qty,
                            "source_note": (note_tf.value or "").strip(),
                            **mechanics,
                        },
                        target_type="loot_stash",
                    )
                else:
                    loot_repo.create_entry(
                        self._active_kind, kind, name=name, description=(desc_tf.value or "").strip(),
                        quantity=qty, source_note=(note_tf.value or "").strip(),
                        world_id=self._effective_world_id(),
                        **mechanics,
                    )
            page.pop_dialog()
            self._refresh_list_only()

        _render_fields()
        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Aggiungi Voce di Bottino"),
            content=ft.Column([kind_dd, fields_col], spacing=10, scroll=ft.ScrollMode.AUTO,
                              width=responsive_dialog_width(page, 420), height=460, tight=True),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog() if page else None),
                ft.ElevatedButton("Aggiungi", icon=ft.Icons.ADD, on_click=save,
                                  style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill)),
            ]),
        ))
