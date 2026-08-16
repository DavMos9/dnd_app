"""
Artefatti — dialog di consultazione e generatore di proprietà casuali.

Guida del Dungeon Master, Capitolo 7 «Tesori», sezione «Artefatti» (pag. 219-227).
Dati in `data/game_data/artifacts.json`, trascritti leggendo visivamente le
pagine renderizzate del PDF (mai `pdftotext`/OCR).

**Perché non è nel compendio Oggetti Magici**: gli artefatti hanno un formato
strutturalmente diverso dalle 264 voci A-Z (nome/categoria/rarità/descrizione).
Ognuno è un pezzo unico con la propria storia e un insieme di proprietà
nominate, più quattro tabelle d100 di proprietà casuali che il DM tira quando
l'artefatto compare nel mondo — è per questo che erano rimasti fuori dal
compendio fin dalla sua trascrizione.

**Bottino (2026-07-31, `dnd_app/docs/loot_design.md` §6, punto 4/6)**: la
scheda di un artefatto (`_open_artifact`) ha "Assegna…"/"Salva nell'archivio"
— prima non c'era alcun modo di far arrivare un artefatto sulla scheda di un
giocatore. **Stessa coppia di pulsanti aggiunta anche alla scheda "Proprietà
casuali"** (segnalazione di Davide, stesso giorno): il tiro su una delle 4
tabelle veniva generato e mostrato ma non si poteva salvare/assegnare, a
differenza di ogni altro generatore della Sezione Master. Opera sull'ULTIMO
tiro soltanto (non sullo storico in `result_col`), con `entry_kind="item"`:
una proprietà casuale non è un oggetto di per sé, è un ingrediente che il
Master userebbe per comporre un artefatto/oggetto magico homebrew.
"""

from __future__ import annotations

import logging
from typing import Any

import flet as ft

from data.game_data.game_data_loader import game_data as _loader
from ui import design
from ui.theme import muted_text
from ui.widgets import responsive_dialog_width, wrap_dialog_actions

logger = logging.getLogger(__name__)

#: Le quattro tabelle, nell'ordine in cui compaiono nel manuale.
_TABLES: list[tuple[str, str, str]] = [
    ("benefiche_minori", "Benefiche minori", "success"),
    ("benefiche_maggiori", "Benefiche maggiori", "success"),
    ("nocive_minori", "Nocive minori", "danger"),
    ("nocive_maggiori", "Nocive maggiori", "danger"),
]


def show_artifacts_dialog(page: ft.Page, world_id: str = "") -> None:
    """Dialog a due schede: elenco degli artefatti e generatore di proprietà.

    `world_id` (2026-08-06): il mondo correntemente selezionato in
    `MasterView` — "" per la modalità locale, inoltrato ai pulsanti
    "Assegna…"/"Salva nell'archivio" sotto."""
    data = _loader.get_artifacts_data()
    artifacts = _loader.get_artifacts()

    body = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)
    state = {"tab": "artefatti"}

    def _tab_button(key: str, label: str) -> ft.Control:
        active = state["tab"] == key
        p = design.T()
        return ft.Container(
            content=ft.Text(label, size=12, weight=ft.FontWeight.BOLD,
                            color=p.on_primary if active else p.text_2,
                            font_family=design.Font.BODY),
            padding=ft.Padding.symmetric(horizontal=14, vertical=7),
            bgcolor=p.primary_fill if active else "transparent",
            border_radius=design.Radius.PILL,
            on_click=lambda e, k=key: _switch(k),
            ink=True,
        )

    def _switch(key: str) -> None:
        state["tab"] = key
        _render()

    # ------------------------------------------------------------------
    # Scheda "Artefatti"
    # ------------------------------------------------------------------

    def _artifact_card(art: dict[str, Any]) -> ft.Control:
        p = design.T()
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(art.get("name", ""), size=14, weight=ft.FontWeight.BOLD,
                            color=p.text, font_family=design.Font.DISPLAY),
                    ft.Text(art.get("subtitle", ""), size=11, color=p.text_2,
                            italic=True),
                    muted_text(f"Guida del Master, pag. {art.get('source_page', '?')}", 10),
                ],
                spacing=2, tight=True,
            ),
            padding=design.Space.MD,
            bgcolor=p.surface,
            border=ft.Border.only(left=ft.BorderSide(3, p.primary)),
            border_radius=design.Radius.MD,
            shadow=design.elevation(1),
            on_click=lambda e, a=art: _open_artifact(a),
            ink=True,
            animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
            tooltip=f"Apri la scheda di {art.get('name', '')}",
        )

    def _open_artifact(art: dict[str, Any]) -> None:
        rows: list[ft.Control] = [
            ft.Text(art.get("subtitle", ""), size=12, color=design.T().text_2,
                    italic=True),
            ft.Divider(height=10, color=design.T().border),
            ft.Text(art.get("lore", ""), size=12, color=design.T().text,
                    selectable=True),
        ]
        for prop in art.get("properties", []):
            rows.append(ft.Container(height=6))
            rows.append(ft.Text(prop.get("name", ""), size=12,
                                weight=ft.FontWeight.BOLD, color=design.T().primary))
            rows.append(ft.Text(prop.get("text", ""), size=12,
                                color=design.T().text, selectable=True))
        rows.append(ft.Container(height=8))
        rows.append(muted_text(
            f"Guida del Master, pag. {art.get('source_page', '?')}", 10))

        # -- Bottino: "Assegna…"/"Salva nell'archivio" (2026-07-31,
        # `dnd_app/docs/loot_design.md` §6, punto 4/6) — prima non c'era
        # alcun modo di far arrivare un artefatto sulla scheda di un
        # giocatore. La descrizione porta lore + TUTTE le proprietà nominate
        # per esteso (mai un riassunto, stessa regola di `LootStashEntry`).
        def _build_loot_item() -> dict[str, Any]:
            from ui.views.master.master_loot_assign_dialog import simple_item
            parts = [art.get("lore", "")]
            for prop in art.get("properties", []):
                parts.append(f"{prop.get('name', '')}. {prop.get('text', '')}")
            requires_att = "sintonia" in art.get("subtitle", "").lower()
            return simple_item(
                "artifact", art.get("name", ""), description="\n\n".join(p for p in parts if p),
                source_note=f"Artefatti — Guida del Master pag. {art.get('source_page', '?')}",
                requires_attunement=requires_att,
            )

        def _on_assign_loot(ev: Any) -> None:
            from ui.views.master.master_loot_assign_dialog import show_loot_assign_dialog
            show_loot_assign_dialog(page, [_build_loot_item()], world_id=world_id)

        def _on_save_to_archive(ev: Any) -> None:
            from ui.views.master.master_loot_assign_dialog import save_items_to_stash
            from ui.widgets import show_snack
            save_items_to_stash([_build_loot_item()])
            show_snack(page, f"«{art.get('name', '')}» salvato nell'archivio.")

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(art.get("name", ""),
                                      icon=ft.Icons.AUTO_AWESOME),
            content=ft.Container(
                content=ft.Column(rows, spacing=4, scroll=ft.ScrollMode.AUTO),
                width=responsive_dialog_width(page, 440), height=460,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
                ft.OutlinedButton("Salva nell'archivio", icon=ft.Icons.ARCHIVE_OUTLINED,
                                  on_click=_on_save_to_archive),
                ft.OutlinedButton("Assegna…", icon=ft.Icons.SEND_OUTLINED, on_click=_on_assign_loot),
            ]),
        ))

    # ------------------------------------------------------------------
    # Scheda "Proprietà casuali"
    # ------------------------------------------------------------------

    result_col = ft.Column(spacing=6)
    #: Ultimo tiro (per il Bottino, sotto) — solo l'ultimo, non l'intero
    #: storico: stesso principio "un solo risultato corrente da poter
    #: assegnare/salvare" già seguito da tutti gli altri generatori
    #: (Tesoro, Oggetto Magico).
    last_roll: dict[str, Any] = {}

    def _roll(key: str, label: str, tone: str) -> None:
        res = _loader.roll_artifact_property(key)
        if res is None:
            return
        last_roll.clear()
        last_roll.update({"key": key, "label": label, **res})
        result_col.controls.insert(0, ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        design.chip(label, tone),   # type: ignore[arg-type]
                        ft.Text(f"d100 = {res['roll']}  ({res['range']})",
                                size=11, color=design.T().text_3,
                                font_family=design.Font.MONO),
                    ], spacing=8, wrap=True),
                    ft.Text(res["text"], size=12, color=design.T().text,
                            selectable=True),
                ],
                spacing=4, tight=True,
            ),
            padding=design.Space.MD,
            bgcolor=design.T().surface_alt,
            border_radius=design.Radius.MD,
        ))
        del result_col.controls[8:]   # tiene solo gli ultimi tiri
        try:
            result_col.update()
        except (RuntimeError, AssertionError):
            pass

    # -- Bottino: "Assegna…"/"Salva nell'archivio" sull'ultimo tiro
    # (2026-07-31, segnalazione di Davide: la scheda "Proprietà casuali"
    # genera un tiro e lo mostra ma non dava modo di farlo arrivare da
    # nessuna parte, a differenza degli altri generatori). Una proprietà
    # casuale non è di per sé un oggetto — è un ingrediente che il Master
    # userebbe per comporre un artefatto o oggetto magico homebrew — quindi
    # `entry_kind="item"`, un generico appunto di testo, non "artifact".
    def _build_property_loot_item() -> dict[str, Any] | None:
        if not last_roll:
            return None
        from ui.views.master.master_loot_assign_dialog import simple_item
        return simple_item(
            "item", f"Proprietà {last_roll['label']} (d100={last_roll['roll']})",
            description=last_roll.get("text", ""),
            source_note=f"Artefatti — tabella proprietà casuali, {last_roll['label']}",
        )

    def _on_assign_property(ev: Any) -> None:
        item = _build_property_loot_item()
        if item is None:
            from ui.widgets import show_snack
            show_snack(page, "Tira prima una proprietà (premi uno dei pulsanti sopra).", tone="warning")
            return
        from ui.views.master.master_loot_assign_dialog import show_loot_assign_dialog
        show_loot_assign_dialog(page, [item], world_id=world_id)

    def _on_save_property_to_archive(ev: Any) -> None:
        item = _build_property_loot_item()
        from ui.widgets import show_snack
        if item is None:
            show_snack(page, "Tira prima una proprietà (premi uno dei pulsanti sopra).", tone="warning")
            return
        from ui.views.master.master_loot_assign_dialog import save_items_to_stash
        save_items_to_stash([item])
        show_snack(page, "Proprietà salvata nell'archivio.")

    # ------------------------------------------------------------------

    def _render() -> None:
        body.controls.clear()
        body.controls.append(ft.Row(
            [_tab_button("artefatti", "Artefatti"),
             _tab_button("proprieta", "Proprietà casuali")],
            spacing=6, wrap=True,
        ))

        if state["tab"] == "artefatti":
            body.controls.append(ft.Text(
                data.get("examples_intro", ""), size=11,
                color=design.T().text_3, italic=True))
            for art in artifacts:
                body.controls.append(_artifact_card(art))
            note = data.get("_incomplete_note")
            if note:
                body.controls.append(ft.Container(
                    content=ft.Text(note, size=11, color=design.T().text_3,
                                    italic=True),
                    padding=design.Space.MD,
                    bgcolor=design.T().note_bg,
                    border_radius=design.Radius.MD,
                ))
        else:
            body.controls.append(ft.Text(
                data.get("properties_intro", ""), size=11,
                color=design.T().text_2))
            body.controls.append(ft.Row(
                [ft.OutlinedButton(label, icon=ft.Icons.CASINO_OUTLINED,
                                   on_click=lambda e, k=key, l=label, t=tone: _roll(k, l, t))
                 for key, label, tone in _TABLES],
                spacing=6, wrap=True,
            ))
            body.controls.append(result_col)
            body.controls.append(ft.Divider(height=1, color=design.T().border))
            body.controls.append(ft.Row(
                [
                    ft.OutlinedButton("Salva nell'archivio", icon=ft.Icons.ARCHIVE_OUTLINED,
                                      on_click=_on_save_property_to_archive),
                    ft.OutlinedButton("Assegna…", icon=ft.Icons.SEND_OUTLINED,
                                      on_click=_on_assign_property),
                ],
                spacing=8, wrap=True,
            ))

        try:
            body.update()
        except (RuntimeError, AssertionError):
            pass

    _render()
    page.show_dialog(ft.AlertDialog(
        title=design.dialog_title("Artefatti", icon=ft.Icons.AUTO_AWESOME),
        content=ft.Container(
            content=body,
            width=responsive_dialog_width(page, 440), height=480,
        ),
        actions=wrap_dialog_actions([
            ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
        ]),
    ))
