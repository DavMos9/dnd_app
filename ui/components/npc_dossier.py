"""
Scheda "dossier" di un NPC — ritratto + campi identificativi + descrizione,
in sola lettura. Introdotta il 2026-08-20 su richiesta di Davide: "dare la
possibilità di inserire l'immagine dell'npc al master nella rubrica... in
PG incontrati vorrei farlo apparire tipo carta di identità con descrizione
sotto, tipo dossier" — riferimento visivo fornito (tessera identificativa
con intestazione a barra, foto a destra, campi etichetta/valore a sinistra),
riletto nello stile cromatico/tipografico "Arcane Ledger" già esistente
dell'app (niente bianco e nero, niente timbro, niente impronte digitali —
sostituite da una sezione descrizione testuale).

Condivisa da due punti d'ingresso (stesso principio di
`ui/components/monster_picker.py::show_stat_block_dialog`, un solo posto
che sa costruire la card invece di due copie leggermente diverse):
  - `ui/views/master/master_npc_list_view.py` (il Master, opzionalmente, per
    coerenza visiva con quello che vede il giocatore)
  - `ui/views/diary_view.py` (il giocatore, cliccando sul nome dell'NPC
    collegato a una nota di campagna condivisa — sezione "PG Incontrati")

Sola lettura per design: questo componente non offre alcun modo di
modificare l'NPC, nemmeno lato Master — la modifica resta unicamente nella
Rubrica NPC (`MasterNpcListView._open_npc_form`).
"""

from __future__ import annotations

import flet as ft

from data.models import MasterNpc
from ui.views.maps_view import _data_uri
from ui.widgets import responsive_dialog_width, wrap_dialog_actions
from ui import design


def _field_row(label: str, value: str) -> ft.Control:
    p = design.T()
    return ft.Column(
        [
            ft.Text(label.upper(), size=10, weight=ft.FontWeight.BOLD, color=p.text_3,
                     style=ft.TextStyle(letter_spacing=0.8)),
            ft.Text(value, size=14, weight=ft.FontWeight.BOLD, color=p.text),
        ],
        spacing=1, tight=True,
    )


def build_npc_dossier_column(npc: MasterNpc) -> ft.Control:
    """
    Il contenuto del dossier — SENZA titolo (il chiamante lo mette nel
    proprio `dialog_title`/header) e SENZA azioni. Ritratto grande a destra,
    campi identificativi a sinistra (`d.asymmetric_row`, si impila da solo
    su schermo stretto — nessun layout fisso a due colonne fuori posto su
    mobile), poi la descrizione sotto, a tutta larghezza.
    """
    p = design.T()

    if npc.image_data:
        photo: ft.Control = ft.Container(
            content=ft.Image(src=_data_uri(npc.image_data), fit=ft.BoxFit.COVER),
            width=140, height=140, border_radius=design.Radius.MD,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=design.elevation(2),
        )
    else:
        photo = ft.Container(
            content=ft.Icon(ft.Icons.PERSON_OUTLINE, size=48, color=p.border),
            width=140, height=140, bgcolor=p.surface_alt,
            border_radius=design.Radius.MD, alignment=ft.Alignment.CENTER,
        )

    fields: list[ft.Control] = []
    if npc.role:
        fields.append(_field_row("Ruolo", npc.role))
    if npc.race:
        fields.append(_field_row("Razza", npc.race))
    if npc.has_stat_block and npc.creature_type:
        fields.append(_field_row("Tipo creatura", npc.creature_type))
    if npc.size:
        fields.append(_field_row("Taglia", npc.size))
    if npc.alignment:
        fields.append(_field_row("Allineamento", npc.alignment))
    if not fields:
        fields.append(ft.Text("Nessun dettaglio registrato.", size=12,
                               italic=True, color=p.text_3))

    tag_list = [t.strip() for t in (npc.tags or "").split(",") if t.strip()]
    tag_chips = ft.Row(
        [design.chip(t, "neutral") for t in tag_list], spacing=6, wrap=True,
    ) if tag_list else ft.Container(height=0)

    identity = design.asymmetric_row(
        ft.Column(
            [
                ft.Text(npc.name or "(senza nome)", size=design.Size.TITLE,
                         weight=ft.FontWeight.BOLD, color=p.text,
                         font_family=design.Font.DISPLAY),
                ft.Container(height=design.Space.SM),
                ft.Column(fields, spacing=10, tight=True),
                ft.Container(height=design.Space.XS) if tag_list else ft.Container(height=0),
                tag_chips,
            ],
            spacing=0, tight=True,
        ),
        photo,
        ratio=(7, 5),
    )

    description = (npc.notes or "").strip()
    desc_block: ft.Control
    if description:
        desc_block = ft.Column(
            [
                ft.Text("DESCRIZIONE", size=10, weight=ft.FontWeight.BOLD, color=p.text_3,
                         style=ft.TextStyle(letter_spacing=0.8)),
                ft.Container(height=4),
                ft.Text(description, size=13, color=p.text, selectable=True),
            ],
            spacing=0, tight=True,
        )
    else:
        desc_block = ft.Text("Nessuna descrizione registrata.", size=12,
                              italic=True, color=p.text_3)

    return ft.Column(
        [
            identity,
            ft.Container(height=design.Space.MD),
            ft.Divider(height=1, color=p.border),
            ft.Container(height=design.Space.SM),
            desc_block,
        ],
        spacing=0, tight=True, scroll=ft.ScrollMode.AUTO,
    )


def show_npc_dossier_dialog(page: ft.Page, npc: MasterNpc) -> None:
    """AlertDialog di sola lettura con il dossier completo di `npc` — vedi
    `build_npc_dossier_column()`."""
    dlg = ft.AlertDialog(
        title=design.dialog_title("Dossier PNG", ft.Icons.BADGE_OUTLINED),
        content=ft.Container(
            content=build_npc_dossier_column(npc),
            width=responsive_dialog_width(page, 440), height=420,
        ),
        actions=wrap_dialog_actions([
            ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
        ]),
    )
    page.show_dialog(dlg)
