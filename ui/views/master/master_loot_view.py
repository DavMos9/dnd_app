"""
Vista "Bottino" — quarta tab di `MasterView` (passo 3 di
`dnd_app/docs/loot_design.md` §8). Due elenchi sulla stessa tabella
`loot_stash_entries` (`data/repositories/loot_repo.py`), distinti da
`stash_kind`: **Archivio del Master** e **Deposito del Gruppo**
(`stash_kind="party"`) — entrambi scoped al mondo correntemente
selezionato in `MasterView` (`_effective_world_id()` qui sotto;
`world_id=""` se il Master lavora in locale, comportamento di sempre per
chi non usa il Multiplayer). Fino al 2026-08-12 l'archivio del Master era
volutamente sempre `world_id=""` (privato del dispositivo, mai scoped) —
cambiato per il bug report di Davide ("in Master... oggetti bottino...
tutto deve essere dipendente dal mondo... selezionare un mondo è come se
entrassi in un container con le sue cose"): "privato" (mai sincronizzato
via mondo, la parte davvero importante del design originale) e "scoped al
mondo selezionato" non sono in contraddizione — restano due assi
indipendenti, ed è la seconda che mancava.

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

from data.models import LootStashEntry
from data.repositories import loot_repo
from ui import design
from ui.widgets import responsive_dialog_width, wrap_dialog_actions, show_snack

logger = logging.getLogger(__name__)

_KIND_OPTIONS: list[tuple[str, str]] = [
    ("item", "Oggetto"),
    ("magic_item", "Oggetto Magico"),
    ("artifact", "Artefatto"),
    ("poison", "Veleno"),
    ("gem", "Gemma"),
    ("art", "Oggetto d'Arte"),
    ("coins", "Monete"),
]
_KIND_LABELS: dict[str, str] = dict(_KIND_OPTIONS)
_KIND_ICONS: dict[str, str] = {
    "item": ft.Icons.BACKPACK_OUTLINED,
    "magic_item": ft.Icons.AUTO_AWESOME,
    "artifact": ft.Icons.DIAMOND,
    "poison": ft.Icons.SICK_OUTLINED,
    "gem": ft.Icons.DIAMOND_OUTLINED,
    "art": ft.Icons.PALETTE_OUTLINED,
    "coins": ft.Icons.PAID_OUTLINED,
}
_COIN_FIELDS: list[tuple[str, str]] = [
    ("platinum", "Platino (mp)"), ("gold", "Oro (mo)"), ("electrum", "Electrum (me)"),
    ("silver", "Argento (ma)"), ("copper", "Rame (mr)"),
]


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

    def __init__(self, world_id: str = "") -> None:
        super().__init__(expand=True, spacing=0, scroll=ft.ScrollMode.AUTO)
        self._page: ft.Page | None = None
        #: Mondo correntemente selezionato in `MasterView` (2026-08-06,
        #: esteso all'Archivio del Master il 2026-08-12) — "" per la
        #: modalità locale. Si applica a ENTRAMBI i contenitori
        #: (`stash_kind="master"`/`"party"`): un mondo è un container, non
        #: solo per il deposito comune — la privacy dell'archivio del
        #: Master (mai sincronizzato/visibile ai giocatori) resta un asse
        #: indipendente da questo, invariata.
        self._world_id = world_id
        self._active_kind: str = "master"  # "master" | "party"
        self._list_col = ft.Column(spacing=8)
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    def _effective_world_id(self) -> str:
        """Il `world_id` da usare per l'elenco/le nuove voci correnti —
        stesso mondo selezionato per entrambi i contenitori (2026-08-12,
        vedi il commento nel costruttore)."""
        return self._world_id

    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.controls.clear()
        self.controls.append(self._build_header())
        self.controls.append(ft.Container(content=self._list_col,
                                           padding=ft.Padding.symmetric(horizontal=16, vertical=8)))
        self._populate_list()

    def _build_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, color=design.T().primary_icon, size=20),
                            ft.Container(width=8),
                            ft.Text("Bottino", size=15, weight=ft.FontWeight.BOLD, color=design.T().text,
                                    expand=True),
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
        title = "Monete" if is_coins else entry.name
        subtitle = _coin_summary(entry) if is_coins else (
            (entry.description or "").split("\n")[0][:110]
        )
        qty_bit = f" ×{entry.quantity}" if (not is_coins and entry.quantity != 1) else ""

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(_KIND_ICONS.get(entry.entry_kind, ft.Icons.BACKPACK_OUTLINED),
                                    size=16, color=design.T().primary),
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
                            design.chip(_KIND_LABELS.get(entry.entry_kind, entry.entry_kind), "neutral"),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(subtitle, size=11, color=design.T().text_2) if subtitle else ft.Container(height=0),
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
            padding=design.Space.MD, bgcolor=design.T().surface,
            border_radius=design.Radius.MD, shadow=design.elevation(1),
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
                                 world_id=self._world_id)

    def _on_move(self, entry: LootStashEntry) -> None:
        new_kind = "party" if self._active_kind == "master" else "master"
        # world_id esplicito (2026-08-12): senza, move_entry lo azzererebbe
        # al default "" — corretto per la modalità locale, ma sposterebbe
        # la voce FUORI dal mondo selezionato (invisibile nell'altro
        # contenitore finché non si torna in modalità locale). Entrambi i
        # contenitori condividono lo stesso mondo, quindi uno spostamento
        # resta sempre dentro lo stesso container.
        loot_repo.move_entry(entry.id, new_kind, new_world_id=self._world_id)
        self._refresh_list_only()

    def _on_delete(self, entry: LootStashEntry) -> None:
        page = self._page
        if page is None:
            return

        def do_delete(ev: Any) -> None:
            if page is None:
                return
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
                # scrittura usata da un solo chiamante.
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

        def save_item(ev: Any) -> None:
            if page is None:
                return
            try:
                qty = max(1, int((qty_tf.value or "1").strip()))
            except ValueError:
                qty = 1
            loot_repo.update_entry(
                entry.id, name=(name_tf.value or "").strip(),
                description=(desc_tf.value or "").strip(), quantity=qty,
                source_note=(note_tf.value or "").strip(),
            )
            page.pop_dialog()
            self._refresh_list_only()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Modifica Voce"),
            content=ft.Column([name_tf, qty_tf, desc_tf, note_tf], spacing=10,
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
        state = {"kind": "item"}
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
            if state["kind"] == "coins":
                fields_col.controls.extend(
                    [coin_tfs["platinum"], coin_tfs["gold"], coin_tfs["electrum"],
                     coin_tfs["silver"], coin_tfs["copper"], note_tf]
                )
            else:
                fields_col.controls.extend([name_tf, qty_tf, desc_tf, note_tf])
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
                loot_repo.create_entry(
                    self._active_kind, kind, name=name, description=(desc_tf.value or "").strip(),
                    quantity=qty, source_note=(note_tf.value or "").strip(),
                    world_id=self._effective_world_id(),
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
