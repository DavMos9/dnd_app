"""
Componenti condivisi per la ricerca nel bestiario (`monsters.json`, 444 mostri
già interamente auditati) e la visualizzazione dello stat block di una creatura.

Estratto da `ui/views/character_sheet/combattimento_tab.py` (dove viveva come
metodi privati di `CombattimentoTab` per Forma Selvatica/Evocazioni) il
2026-07-24, per essere riusato anche dalla Sezione Master (creazione NPC "dal
Bestiario", tracker di combattimento). Nessuna modifica di comportamento per
il codice esistente rispetto a prima del refactoring — stessa identica logica
di filtro/rendering, solo estratta in funzioni pure/parametrizzate invece di
essere duplicata o legata a `self.character`.

`show_monster_picker()` non scrive mai da sola su nessuna tabella: riceve un
callback `on_select(monster_dict)` e lascia al chiamante decidere cosa farne
(creature_entries per il giocatore, master_npcs/master_encounter_members per
il Master) — la logica di persistenza resta quindi in ciascun chiamante,
questo modulo si occupa solo di UI di ricerca/selezione e di rendering dello
stat block.
"""

import json as _json
from pathlib import Path
from typing import Any, Callable

import flet as ft

from config.settings import (
    COLOR_ACCENT_CRIMSON,
    COLOR_ACCENT_BLUE,
    COLOR_BORDER,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
)
# cr_to_float vive ora in data/game_data/game_data_loader.py (2026-07-25,
# serviva a core/encounter_generator.py, che per convenzione di progetto
# non può dipendere da Flet) — re-esportata qui per compatibilità con
# tutto il codice già esistente che fa `from ui.components.monster_picker
# import cr_to_float`, comportamento identico a prima.
from data.game_data.game_data_loader import cr_to_float  # noqa: F401

_MONSTERS_PATH = (
    Path(__file__).parent.parent.parent / "data" / "game_data" / "monsters.json"
)


def monster_display_name(raw_name: str) -> str:
    """Converte il nome in MAIUSCOLO del bestiario in title case leggibile."""
    return raw_name.title()


def load_monsters() -> list[dict]:
    """Carica l'intero bestiario da `monsters.json`. Lista vuota se il file
    manca o è malformato (mai un crash per un problema di I/O)."""
    try:
        return _json.loads(_MONSTERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _desc(d: dict) -> str:
    return d.get("description", "") or d.get("text", "")


def build_stat_block_column(m: dict) -> ft.Column:
    """
    Costruisce la colonna scrollabile con l'intero stat block: 6 caratteristiche,
    CA/PF/velocità/GS, allineamento, tiri salvezza/abilità, resistenze/immunità,
    sensi/lingue, e le sezioni facoltative Tratti/Azioni/Reazioni/Azioni
    Leggendarie/Azioni di Tana/Effetti Regionali/Varianti Opzionali.

    `m` deve essere un dict "risolto": traits/actions/reactions/
    legendary_actions/lair_actions/regional_effects/variant_rules sono già
    liste Python (non stringhe JSON), saving_throws/skills sono già dict — i
    dict grezzi di `monsters.json` sono già in questa forma; per dati
    persistiti su DB (es. `CreatureEntry`, `MasterNpc`) usare prima
    `creature_entry_dict()` per convertirli.
    """

    def stat_col_d(abbr: str, score: int) -> ft.Column:
        mod = (score - 10) // 2
        sign = "+" if mod >= 0 else ""
        return ft.Column(
            [
                ft.Text(abbr, size=10, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                ft.Text(str(score), size=16, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_PRIMARY, text_align=ft.TextAlign.CENTER),
                ft.Text(f"{sign}{mod}", size=11, color=COLOR_TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER),
            ],
            spacing=1,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def feat_tile(name: str, text: str) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(name, size=12, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY, italic=True),
                    ft.Text(text, size=11, color=COLOR_TEXT_SECONDARY),
                ],
                spacing=2,
            ),
            padding=ft.Padding.only(bottom=6),
        )

    def info_r(label: str, value: str) -> ft.Row | None:
        if not value:
            return None
        return ft.Row(
            [
                ft.Text(label + ":", size=11, color=COLOR_TEXT_MUTED, weight=ft.FontWeight.W_600),
                ft.Container(width=4),
                ft.Text(value, size=11, color=COLOR_TEXT_PRIMARY, expand=True),
            ]
        )

    stats_row = ft.Row(
        [
            stat_col_d("FOR", int(m.get("str_score", 10))),
            stat_col_d("DES", int(m.get("dex_score", 10))),
            stat_col_d("COS", int(m.get("con_score", 10))),
            stat_col_d("INT", int(m.get("int_score", 10))),
            stat_col_d("SAG", int(m.get("wis_score", 10))),
            stat_col_d("CAR", int(m.get("cha_score", 10))),
        ],
        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
    )

    ac_note = m.get("ac_note", "")
    hp_formula = m.get("hp_formula", "")
    st_dict = m.get("saving_throws", {})
    sk_dict = m.get("skills", {})

    info_items: list[ft.Control] = []
    for lbl, val in [
        ("CA", f"{m.get('ac', 10)}{' (' + ac_note + ')' if ac_note else ''}"),
        ("PF", f"{m.get('hp_max', '—')}" + (f" ({hp_formula})" if hp_formula else "")),
        ("Velocità", str(m.get("speed", ""))),
        ("GS", str(m.get("cr", "—"))),
        ("Allineamento", m.get("alignment", "")),
        ("Tiri Salvezza", ", ".join(f"{k} {v}" for k, v in st_dict.items()) if isinstance(st_dict, dict) else ""),
        ("Abilità", ", ".join(f"{k} {v}" for k, v in sk_dict.items()) if isinstance(sk_dict, dict) else ""),
        ("Vulnerabilità", m.get("damage_vulnerabilities", "")),
        ("Resistenze", m.get("damage_resistances", "")),
        ("Immunità danni", m.get("damage_immunities", "")),
        ("Immunità condizioni", m.get("condition_immunities", "")),
        ("Sensi", m.get("senses", "")),
        ("Linguaggi", m.get("languages", "")),
    ]:
        r = info_r(lbl, val)
        if r:
            info_items.append(r)

    traits_l: list[dict] = m.get("traits", []) or []
    actions_l: list[dict] = m.get("actions", []) or []
    react_l: list[dict] = m.get("reactions", []) or []
    leg_l: list[dict] = m.get("legendary_actions", []) or []
    lair_l: list[str] = m.get("lair_actions", []) or []
    regional_l: list[str] = m.get("regional_effects", []) or []
    variants_l: list[dict] = m.get("variant_rules", []) or []

    features: list[ft.Control] = []
    if traits_l:
        features.append(ft.Text("Tratti", size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON))
        for t in traits_l:
            features.append(feat_tile(t.get("name", ""), _desc(t)))
    if actions_l:
        features.append(ft.Text("Azioni", size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON))
        for a in actions_l:
            features.append(feat_tile(a.get("name", ""), _desc(a)))
    if react_l:
        features.append(ft.Text("Reazioni", size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON))
        for r in react_l:
            features.append(feat_tile(r.get("name", ""), _desc(r)))
    if leg_l:
        features.append(ft.Text("Azioni Leggendarie", size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON))
        for la in leg_l:
            features.append(feat_tile(la.get("name", ""), _desc(la)))
    if lair_l:
        features.append(ft.Text("Azioni di Tana", size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON))
        lair_intro = m.get("lair_actions_intro", "")
        if lair_intro:
            features.append(ft.Text(lair_intro, size=11, color=COLOR_TEXT_SECONDARY, italic=True))
        for eff in lair_l:
            features.append(ft.Text(f"•  {eff}", size=11, color=COLOR_TEXT_SECONDARY))
    if regional_l:
        reg_label = m.get("regional_effects_label", "") or "Effetti Regionali"
        features.append(ft.Text(reg_label, size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON))
        reg_intro = m.get("regional_effects_intro", "")
        if reg_intro:
            features.append(ft.Text(reg_intro, size=11, color=COLOR_TEXT_SECONDARY, italic=True))
        for eff in regional_l:
            features.append(ft.Text(f"•  {eff}", size=11, color=COLOR_TEXT_SECONDARY))
    if variants_l:
        features.append(ft.Text("Varianti Opzionali", size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_BLUE))
        for v in variants_l:
            features.append(feat_tile(v.get("name", ""), _desc(v)))

    items: list[ft.Control] = [
        ft.Text(
            f"{m.get('type', m.get('creature_type', '?'))} · {m.get('alignment', '—')}",
            size=11, color=COLOR_TEXT_MUTED, italic=True,
        ),
        ft.Divider(height=10, color=COLOR_BORDER),
        stats_row,
        ft.Divider(height=10, color=COLOR_BORDER),
        *info_items,
    ]
    if features:
        items.append(ft.Divider(height=10, color=COLOR_BORDER))
        items.extend(features)

    return ft.Column(items, spacing=6, scroll=ft.ScrollMode.AUTO)


def creature_entry_dict(c: Any) -> dict:
    """
    Adapter: converte un oggetto con attributi in stile `CreatureEntry` (o
    qualunque oggetto/dict con gli stessi nomi di campo, es. `MasterNpc`) in
    un dict "risolto" pronto per `build_stat_block_column()`/`show_stat_block_dialog()`
    — decodifica i campi persistiti come stringa JSON (traits/actions/ecc.,
    saving_throws/skills) in liste/dict Python veri.
    """

    def _get(field: str, default: Any = "") -> Any:
        if isinstance(c, dict):
            return c.get(field, default)
        return getattr(c, field, default)

    def _jload(field: str, empty: Any) -> Any:
        raw = _get(field, empty)
        if isinstance(raw, str):
            try:
                return _json.loads(raw)
            except Exception:
                return empty
        return raw if raw is not None else empty

    return {
        "name": _get("name"),
        "type": _get("creature_type"),
        "creature_type": _get("creature_type"),
        "alignment": _get("alignment"),
        "ac": _get("ac", 10),
        "ac_note": _get("ac_note"),
        "hp_max": _get("hp_max", 1),
        "hp_formula": _get("hp_formula"),
        "speed": _get("speed"),
        "cr": _get("cr"),
        "str_score": _get("str_score", 10),
        "dex_score": _get("dex_score", 10),
        "con_score": _get("con_score", 10),
        "int_score": _get("int_score", 10),
        "wis_score": _get("wis_score", 10),
        "cha_score": _get("cha_score", 10),
        "saving_throws": _jload("saving_throws", {}),
        "skills": _jload("skills", {}),
        "damage_vulnerabilities": _get("damage_vulnerabilities"),
        "damage_resistances": _get("damage_resistances"),
        "damage_immunities": _get("damage_immunities"),
        "condition_immunities": _get("condition_immunities"),
        "senses": _get("senses"),
        "languages": _get("languages"),
        "traits": _jload("traits", []),
        "actions": _jload("actions", []),
        "reactions": _jload("reactions", []),
        "legendary_actions": _jload("legendary_actions", []),
        "lair_actions_intro": _get("lair_actions_intro"),
        "lair_actions": _jload("lair_actions", []),
        "regional_effects_label": _get("regional_effects_label"),
        "regional_effects_intro": _get("regional_effects_intro"),
        "regional_effects": _jload("regional_effects", []),
        "variant_rules": _jload("variant_rules", []),
    }


def show_stat_block_dialog(page: ft.Page, name: str, data: dict) -> None:
    """AlertDialog di sola lettura con lo stat block completo di `data` (già
    risolto — vedi `build_stat_block_column`)."""
    dlg = ft.AlertDialog(
        title=ft.Text(monster_display_name(name), size=16, weight=ft.FontWeight.BOLD),
        content=ft.Container(content=build_stat_block_column(data), height=480),
        actions=[ft.TextButton("Chiudi", on_click=lambda _e: page.pop_dialog())],
    )
    page.show_dialog(dlg)


def show_monster_picker(
    page: ft.Page,
    title: str,
    pool: list[dict],
    existing_names: set[str] | None = None,
    on_select: Callable[[dict], None] | None = None,
    select_label: str = "✔ Aggiungi",
    select_color: str = COLOR_ACCENT_CRIMSON,
    already_label: str = "✓ Già presente",
    manual_label: str = "Inserimento manuale (creatura non trovata)",
    on_manual: Callable[[], None] | None = None,
) -> None:
    """
    Dialog di ricerca/filtro sul bestiario, generico e riusabile ovunque serva
    scegliere un mostro da `monsters.json` (Forma Selvatica/Evocazioni del
    giocatore, creazione NPC "dal Bestiario" del Master, aggiunta rapida a un
    incontro). Due stati nella stessa AlertDialog: LIST (filtri tipo/GS/nome +
    risultati) e DETAIL (stat block completo + pulsante azione), stesso
    identico comportamento del dialog originale in `CombattimentoTab` prima
    di questo refactoring.

    `pool` è già filtrato dal chiamante (es. solo "Bestia" per Forma
    Selvatica, l'intero bestiario per il Master) — questa funzione applica
    solo i filtri interattivi scelti dall'utente nel dialog stesso.
    `on_select(monster_dict)` viene invocato alla conferma; il chiamante
    decide cosa farne e chiude il dialog da sé (`page.pop_dialog()`) se
    opportuno — questa funzione non presume nulla sulla destinazione dei dati.
    `on_manual`, se fornito, aggiunge un link "inserimento manuale" che chiude
    il dialog e invoca il callback (tipicamente per aprire un form dedicato).
    """
    existing_names = existing_names or set()

    all_types = sorted({m.get("type", "") for m in pool if m.get("type")})
    cr_vals_raw = sorted({m.get("cr", "") for m in pool if m.get("cr")}, key=cr_to_float)

    state: dict[str, Any] = {"type_filter": "", "cr_max": "", "query": ""}
    dlg: Any = None

    type_dd = ft.Dropdown(
        label="Tipo",
        options=[ft.DropdownOption(key="", text="Tutti")]
        + [ft.DropdownOption(key=t, text=t) for t in all_types],
        value="", width=148, dense=True, text_size=12, border_radius=6,
    )
    cr_dd = ft.Dropdown(
        label="GS max",
        options=[ft.DropdownOption(key="", text="Tutti")]
        + [ft.DropdownOption(key=str(v), text=f"GS {v}") for v in cr_vals_raw],
        value="", width=112, dense=True, text_size=12, border_radius=6,
    )
    search_tf = ft.TextField(
        label="Cerca per nome...", prefix_icon=ft.Icons.SEARCH, autofocus=True,
        border_radius=8, dense=True, text_size=13,
    )
    results_col = ft.Column([], spacing=3, scroll=ft.ScrollMode.AUTO, height=270)

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

    def _populate_list() -> None:
        filtered = _filtered_pool()
        results_col.controls.clear()
        for m in filtered:
            already = m["name"].upper() in existing_names
            cr_str = f"GS {m['cr']}" if m.get("cr") else "GS —"
            type_str = m.get("type", "")
            subtitle = f"{type_str} · {cr_str} · {m.get('hp_max', '?')} PF"
            if already:
                subtitle += " · Già aggiunta"

            def _go_detail(_e: Any, mon: dict = m) -> None:
                _show_detail(mon)

            results_col.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        monster_display_name(m["name"]),
                                        size=13, weight=ft.FontWeight.W_600,
                                        color=COLOR_TEXT_MUTED if already else COLOR_TEXT_PRIMARY,
                                    ),
                                    ft.Text(
                                        subtitle, size=11,
                                        color=COLOR_ACCENT_CRIMSON if already else COLOR_TEXT_MUTED,
                                    ),
                                ],
                                spacing=1, expand=True,
                            ),
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE if already else ft.Icons.CHEVRON_RIGHT,
                                color=COLOR_ACCENT_CRIMSON if already else COLOR_TEXT_MUTED, size=18,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    border=ft.Border(bottom=ft.BorderSide(1, COLOR_BORDER)),
                    on_click=_go_detail,
                    ink=True,
                )
            )
        try:
            results_col.update()
        except RuntimeError:
            pass

    def _list_content() -> ft.Column:
        controls: list[ft.Control] = [
            ft.Row([type_dd, cr_dd], spacing=8),
            ft.Container(height=4),
            search_tf,
            ft.Container(height=6),
            results_col,
        ]
        if on_manual is not None:
            controls.append(ft.Container(height=4))
            controls.append(
                ft.TextButton(
                    manual_label, icon=ft.Icons.EDIT,
                    on_click=lambda _e: (page.pop_dialog(), on_manual()),
                    style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                )
            )
        return ft.Column(controls, spacing=4, tight=True)

    def _show_detail(m: dict) -> None:
        already = m["name"].upper() in existing_names
        btn_label = already_label if already else select_label

        def _do_select(_e: Any) -> None:
            if on_select is not None:
                on_select(m)

        def _go_back(_e: Any) -> None:
            dlg.content = ft.Container(content=_list_content(), height=480)
            dlg.title = ft.Text(title)
            dlg.actions = [ft.TextButton("Chiudi", on_click=lambda _e: page.pop_dialog())]
            try:
                page.update()
            except RuntimeError:
                pass

        add_btn = ft.ElevatedButton(
            btn_label, icon=ft.Icons.CHECK if already else ft.Icons.ADD, disabled=already,
            on_click=_do_select,
            style=ft.ButtonStyle(
                bgcolor=select_color if not already else None,
                color="#ffffff" if not already else COLOR_TEXT_MUTED,
            ),
        )
        dlg.content = ft.Container(content=build_stat_block_column(m), height=480)
        dlg.title = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.ARROW_BACK, on_click=_go_back, tooltip="Torna alla lista",
                    icon_color=COLOR_TEXT_SECONDARY,
                ),
                ft.Text(monster_display_name(m["name"]), size=15, weight=ft.FontWeight.BOLD, expand=True),
            ]
        )
        dlg.actions = [add_btn, ft.TextButton("Chiudi", on_click=lambda _e: page.pop_dialog())]
        try:
            page.update()
        except RuntimeError:
            pass

    def _on_type_select(_e: Any) -> None:
        state["type_filter"] = type_dd.value or ""
        _populate_list()

    def _on_cr_select(_e: Any) -> None:
        state["cr_max"] = cr_dd.value or ""
        _populate_list()

    def _on_search_change(_e: Any) -> None:
        state["query"] = search_tf.value or ""
        _populate_list()

    type_dd.on_select = _on_type_select
    cr_dd.on_select = _on_cr_select
    search_tf.on_change = _on_search_change

    _populate_list()

    dlg = ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Container(content=_list_content(), height=480),
        actions=[ft.TextButton("Chiudi", on_click=lambda _e: page.pop_dialog())],
    )
    page.show_dialog(dlg)
