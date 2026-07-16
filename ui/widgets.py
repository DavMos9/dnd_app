"""
Widget condivisi riutilizzabili tra creazione personaggio, wizard e level-up.

Aggiunto il 2026-07-16 su richiesta di Davide: quando il giocatore deve
scegliere un incantesimo/trucchetto/talento/supplica occulta/opzione di
metamagia da un Dropdown, deve poter vedere la descrizione completa
dell'opzione ATTUALMENTE selezionata prima di confermare — non solo il
nome. Pattern scelto (confermato da Davide su 4 alternative proposte):
icona informazione (ⓘ) accanto al Dropdown, che apre un AlertDialog con la
descrizione. Il dialog rilegge sempre `dropdown.value` al momento del
click, quindi si aggiorna correttamente se il giocatore cambia selezione
prima di consultare la descrizione — non una snapshot presa alla creazione
del widget.

Questo modulo contiene solo il widget generico e le funzioni di formattazione
testo (pure, senza dipendenza da Flet) per i tipi di dato già presenti nel
progetto (incantesimi, talenti, invocazioni). Il wiring nei singoli dropdown
di wizard/manual_form/profilo_tab resta nei rispettivi file — qui vive solo
la parte davvero condivisa.
"""

import flet as ft
from typing import Any, Callable
from config.settings import (
    COLOR_TEXT_TITLE, COLOR_TEXT_PRIMARY, COLOR_ACCENT_BLUE,
    COLOR_BG_CARD, ABILITY_KEYS, ABILITY_SCORES,
)

_ABILITY_KEY_TO_LABEL: dict[str, str] = dict(zip(ABILITY_KEYS, ABILITY_SCORES))


def dropdown_with_info(
    page_getter: Callable[[], ft.Page | None],
    dropdown: ft.Dropdown,
    describe: Callable[[str], tuple[str, str] | None],
    tooltip: str = "Mostra descrizione",
) -> ft.Row:
    """
    Affianca un IconButton "ⓘ" a un Dropdown già costruito.

    Args:
        page_getter: funzione che restituisce la `ft.Page` corrente (es.
            `lambda: self._page`) — un riferimento diretto non basta perché
            in alcuni contesti (wizard/manual_form) la pagina viene risolta
            solo in `did_mount()`, dopo la costruzione del widget.
        dropdown: il Dropdown già configurato (opzioni/on_select/valore
            iniziale restano intatti e continuano a funzionare normalmente).
        describe: funzione che, dato il valore CORRENTE del dropdown
            (`dropdown.value`), restituisce `(titolo, corpo)` da mostrare
            nel dialog, oppure `None` se quel valore non è descrivibile
            (es. un placeholder tipo "" o "— nessuno —").
        tooltip: testo del tooltip sull'icona ⓘ.

    Returns:
        Una `ft.Row` con [dropdown (expand), IconButton ⓘ] — da usare al
        posto del solo `dropdown` ovunque nella UI.
    """

    def _on_info_click(e: Any) -> None:
        page = page_getter()
        if page is None:
            return
        value = dropdown.value
        if not value:
            return
        result = describe(value)
        if result is None:
            return
        title, body = result
        page.show_dialog(ft.AlertDialog(
            title=ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Container(
                content=ft.Column(
                    [ft.Text(body, size=13, color=COLOR_TEXT_PRIMARY, selectable=True)],
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=360,
                height=320,
            ),
            actions=[ft.TextButton("Chiudi", on_click=lambda ev: page.pop_dialog())],
            bgcolor=COLOR_BG_CARD,
        ))

    info_btn = ft.IconButton(
        ft.Icons.INFO_OUTLINE,
        icon_size=20,
        icon_color=COLOR_ACCENT_BLUE,
        tooltip=tooltip,
        on_click=_on_info_click,
        padding=ft.Padding.all(2),
    )
    return ft.Row(
        [dropdown, info_btn],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=2,
    )


# ---------------------------------------------------------------------------
# Formattazione testo (pure, nessuna dipendenza da Flet) — un formatter per
# ogni tipo di dato già presente nel progetto che il giocatore può dover
# scegliere da un Dropdown durante creazione/level-up.
# ---------------------------------------------------------------------------

def format_spell_body(spell: dict) -> str:
    """
    Corpo descrittivo completo per un incantesimo/trucchetto (dict da
    incantesimi_completi.json via GameDataLoader.get_spells/get_spell).
    """
    lines: list[str] = []
    level = spell.get("level", 0)
    level_label = "Trucchetto" if level == 0 else f"Incantesimo di {level}° livello"
    school = spell.get("school", "")
    header = level_label + (f" — {school}" if school else "")
    lines.append(header)

    tags: list[str] = []
    if spell.get("ritual"):
        tags.append("Rituale")
    if spell.get("concentration"):
        tags.append("Concentrazione")
    if tags:
        lines.append(" · ".join(tags))

    lines.append("")
    if spell.get("casting_time"):
        lines.append(f"Tempo di lancio: {spell['casting_time']}")
    if spell.get("range"):
        lines.append(f"Gittata: {spell['range']}")
    if spell.get("components"):
        comp = spell["components"]
        material = spell.get("material", "")
        lines.append(f"Componenti: {comp}" + (f" ({material})" if material else ""))
    if spell.get("duration"):
        lines.append(f"Durata: {spell['duration']}")

    lines.append("")
    if spell.get("description"):
        lines.append(spell["description"])
    if spell.get("higher_levels"):
        lines.append("")
        lines.append(f"Ai livelli superiori: {spell['higher_levels']}")

    return "\n".join(lines).strip()


def make_spell_describe(spells: list[dict]) -> Callable[[str], tuple[str, str] | None]:
    """
    Costruisce una funzione `describe` per `dropdown_with_info()` a partire
    da una lista di dict incantesimo (es. `_loader.get_spells(classe)`),
    cercando per nome esatto (case-insensitive).
    """
    by_name = {s.get("name", "").lower(): s for s in spells if s.get("name")}

    def _describe(value: str) -> tuple[str, str] | None:
        spell = by_name.get(value.strip().lower())
        if spell is None:
            return None
        return spell.get("name", value), format_spell_body(spell)

    return _describe


def format_feat_body(feat: dict) -> str:
    """Corpo descrittivo per un talento (dict da feats.json via get_feat())."""
    lines: list[str] = []
    prereq = feat.get("prerequisite")
    if prereq:
        lines.append(f"Prerequisito: {prereq}")
    ability_bonus = feat.get("ability_bonus")
    if ability_bonus:
        if ability_bonus.get("choose_one"):
            opt_labels: list[str] = []
            for raw_opt in ability_bonus.get("options", []):
                opt_key = str(raw_opt)
                opt_labels.append(_ABILITY_KEY_TO_LABEL.get(opt_key, opt_key))
            opts = ", ".join(opt_labels)
            lines.append(f"Bonus caratteristica: +1 a scelta tra {opts}")
        else:
            bonus_str = ", ".join(
                f"+{v} {_ABILITY_KEY_TO_LABEL.get(k, k.upper())}"
                for k, v in ability_bonus.items()
            )
            if bonus_str:
                lines.append(f"Bonus caratteristica: {bonus_str}")
    if lines:
        lines.append("")
    if feat.get("description"):
        lines.append(feat["description"])
    return "\n".join(lines).strip()


def make_feat_describe(loader) -> Callable[[str], tuple[str, str] | None]:
    """Costruisce una funzione `describe` che cerca i talenti via GameDataLoader.get_feat()."""

    def _describe(value: str) -> tuple[str, str] | None:
        feat = loader.get_feat(value)
        if feat is None:
            return None
        return feat.get("name", value), format_feat_body(feat)

    return _describe


def format_invocation_body(inv: dict) -> str:
    """Corpo descrittivo per una Supplica Occulta (dict da invocations.json)."""
    lines: list[str] = []
    prereq_level = inv.get("prerequisite_level", 0) or 0
    prereq_pact = inv.get("prerequisite_pact", "") or ""
    prereq_spell = inv.get("prerequisite_spell", "") or ""
    prereqs: list[str] = []
    if prereq_level:
        prereqs.append(f"Warlock livello {prereq_level}+")
    if prereq_pact:
        prereqs.append(f"Patto della {prereq_pact.capitalize()}" if prereq_pact != "tomo"
                        else "Patto del Tomo")
    if prereq_spell:
        prereqs.append(f"conoscere {prereq_spell}")
    if prereqs:
        lines.append("Prerequisiti: " + ", ".join(prereqs))
        lines.append("")
    if inv.get("description"):
        lines.append(inv["description"])
    return "\n".join(lines).strip()


def format_named_option_body(opt: dict) -> str:
    """
    Corpo descrittivo per una semplice opzione {"name","description"} — usato
    per Metamagia, Dono del Patto, Stile di Combattimento (nessun altro campo
    strutturato oltre al testo PHB per queste opzioni).
    """
    return (opt.get("description") or "").strip()


def make_named_option_describe(options: list[dict]) -> Callable[[str], tuple[str, str] | None]:
    """
    Costruisce una funzione `describe` per opzioni semplici {"name",
    "description"} (Metamagia/Dono del Patto/Stile di Combattimento),
    cercando per nome esatto (case-insensitive).
    """
    by_name = {o.get("name", "").lower(): o for o in options if o.get("name")}

    def _describe(value: str) -> tuple[str, str] | None:
        opt = by_name.get(value.strip().lower())
        if opt is None:
            return None
        return opt.get("name", value), format_named_option_body(opt)

    return _describe


def make_invocation_describe(invocations: list[dict]) -> Callable[[str], tuple[str, str] | None]:
    """
    Costruisce una funzione `describe` a partire da una lista di dict
    Supplica Occulta (es. `_loader.get_invocations(warlock_level)`).
    """
    by_name = {i.get("name", "").lower(): i for i in invocations if i.get("name")}

    def _describe(value: str) -> tuple[str, str] | None:
        inv = by_name.get(value.strip().lower())
        if inv is None:
            return None
        return inv.get("name", value), format_invocation_body(inv)

    return _describe
