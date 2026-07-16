"""
Widget condivisi riutilizzabili tra creazione personaggio, wizard e level-up.

Aggiunto il 2026-07-16 su richiesta di Davide: quando il giocatore deve
scegliere un incantesimo/trucchetto/talento/supplica occulta/opzione di
metamagia da un Dropdown, deve poter vedere la descrizione completa
dell'opzione ATTUALMENTE selezionata prima di confermare — non solo il
nome. Primo pattern scelto (confermato da Davide su 4 alternative proposte):
icona informazione (ⓘ) accanto al Dropdown, che apre un AlertDialog con la
descrizione.

**Sostituito il 2026-07-16, stesso giorno, su feedback diretto di Davide**:
"non mi piace quando vengono scelti gli incantesimi devi prima selezionarli
e poi premere info, è macchinoso e difficile per il player" — il pattern
Dropdown+ⓘ richiedeva due gesti separati (selezionare alla cieca, poi aprire
un dialog per leggere cosa si è appena scelto). Sostituito da `CardPicker`:
una lista scorrevole di card cliccabili dove UN SOLO click seleziona
l'opzione E ne mostra subito la descrizione completa inline, senza alcun
dialog separato — stesso principio già in uso nel compendio Talenti
(`FeatsView`), esteso qui a un widget riutilizzabile e stateful. Applicato
(confermato da Davide) a TUTTI i punti che usavano `dropdown_with_info` o
un'icona ⓘ standalone: incantesimi/trucchetti (creazione e level-up),
talento all'ASI, Metamagia, Suppliche Occulte, Discipline Elementali, Dono
del Patto, Stile di Combattimento.

`dropdown_with_info` e le funzioni `format_*_body`/`make_*_describe` restano
in questo modulo: i formatter di testo (puri, nessuna dipendenza Flet) sono
riusati direttamente dai nuovi helper `*_card_options()` sotto — nessuna
duplicazione di logica di formattazione tra il vecchio e il nuovo widget.
`dropdown_with_info` stesso non ha più chiamanti nel progetto dopo la
conversione, ma resta qui (non rimosso) come helper generico riutilizzabile
per un futuro Dropdown "semplice" che non necessiti della lista a schede
(es. poche opzioni senza descrizione lunga).
"""

import flet as ft
from typing import Any, Callable
from config.settings import (
    COLOR_TEXT_TITLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED, COLOR_ACCENT_BLUE,
    COLOR_BG_CARD, COLOR_BORDER, ABILITY_KEYS, ABILITY_SCORES,
)

_ABILITY_KEY_TO_LABEL: dict[str, str] = dict(zip(ABILITY_KEYS, ABILITY_SCORES))


class CardPicker:
    """
    Lista scorrevole di card cliccabili — sostituisce il pattern
    Dropdown/RadioGroup/Checkbox + icona ⓘ. Click su una card la
    seleziona/deseleziona E mostra subito la sua descrizione completa
    inline (espansa sotto il titolo) — un solo gesto invece di due.

    NON è un `ft.Control`: è un wrapper Python plain che possiede un
    `ft.Column` (`.control`, da inserire nell'albero Flet al posto del
    vecchio `ft.Dropdown`) e gestisce la propria reattività internamente
    (stesso principio già in uso ovunque nel progetto: mutare lo stato e
    richiamare `.update()` con guard `try/except RuntimeError`, mai
    riassegnare `.controls` — vedi CLAUDE.md).

    Modalità:
      - single-select (`multi=False`, default): al massimo una card attiva
        alla volta, comportamento equivalente a Dropdown/RadioGroup.
        `.value` è la key selezionata (str) o `None`. Ri-cliccare la card
        già selezionata non fa nulla (non si può "deselezionare" cliccando
        di nuovo — stesso comportamento di un Dropdown, che non permette di
        tornare a un valore vuoto cliccando la stessa opzione).
      - multi-select (`multi=True`): più card possono essere attive
        insieme, con un limite opzionale `max_selected` — oltre il limite
        il click su una nuova card viene ignorato silenziosamente (stesso
        comportamento "revert silenzioso" già in uso per i Checkbox di
        Metamagia/Suppliche Occulte, nessun messaggio d'errore). `.values`
        è la lista delle key selezionate.

    Attributi pubblici (stesso schema di lettura/scrittura già in uso nel
    progetto per Dropdown/Checkbox):
      .value / .values   — leggibili e scrivibili liberamente da codice
                            esterno (es. per pre-selezionare un default);
                            scriverli NON invoca `on_select` — solo un click
                            reale lo fa, stesso comportamento di
                            `Dropdown.value = ...`.
      .options            — settable: lista di dict `{"key","title","body"}`
                            (vedi gli helper `*_card_options()` sotto per
                            costruirla dagli stessi dati già usati da
                            `make_*_describe()`). Riassegnarla ricostruisce
                            la lista e rimuove dalla selezione corrente le
                            key non più presenti (stesso comportamento del
                            pattern di esclusione reciproca già in uso per i
                            Dropdown: la selezione va validata di nuovo ad
                            ogni cambio di opzioni disponibili).
      .disabled           — settable, disabilita il click su tutte le card.
      .on_select          — `Callable[[Any], None] | None`, invocato con un
                            oggetto `ev` tale che `ev.control is self` dopo
                            un click reale — stesso pattern di
                            `Dropdown.on_select` usato nel resto del
                            progetto (incluso il chaining già in uso per
                            `_compose_on_select`/`_on_class_select`: catturare
                            `_orig = picker.on_select` e richiamarlo prima di
                            aggiungere altra logica).
      .control            — la `ft.Column` da inserire nell'albero Flet.
      .update()           — richiama `.update()` sul control sottostante,
                            con guard `try/except RuntimeError` (controllo
                            non ancora montato, stesso pattern ovunque nel
                            progetto).
    """

    def __init__(
        self,
        options: list[dict[str, str]],
        value: str | None = None,
        values: list[str] | None = None,
        multi: bool = False,
        max_selected: int | None = None,
        disabled: bool = False,
        height: int = 220,
        empty_text: str = "Nessuna opzione disponibile.",
        active_color: str = COLOR_ACCENT_BLUE,
        on_select: Callable[[Any], None] | None = None,
    ) -> None:
        self.multi = multi
        self.max_selected = max_selected
        self.height = height
        self.empty_text = empty_text
        self.active_color = active_color
        self.on_select = on_select

        self._options: list[dict[str, str]] = []
        self._value: str | None = value
        self._values: list[str] = list(values) if values is not None else (
            [value] if (multi and value) else []
        )
        self._disabled = disabled

        self.control = ft.Column(height=height, scroll=ft.ScrollMode.AUTO, spacing=4)
        self.options = options  # invoca il setter -> costruisce le card iniziali

    # -- value / values --------------------------------------------------

    @property
    def value(self) -> str | None:
        return self._value

    @value.setter
    def value(self, v: str | None) -> None:
        self._value = v
        if self.multi and v and v not in self._values:
            self._values = [v]
        self._rebuild()

    @property
    def values(self) -> list[str]:
        return list(self._values)

    @values.setter
    def values(self, vs: list[str]) -> None:
        self._values = list(vs)
        self._rebuild()

    # -- options ----------------------------------------------------------

    @property
    def options(self) -> list[dict[str, str]]:
        return self._options

    @options.setter
    def options(self, opts: list[dict[str, str]]) -> None:
        self._options = opts
        valid_keys = {o.get("key", "") for o in opts}
        if self.multi:
            self._values = [v for v in self._values if v in valid_keys]
        else:
            if self._value not in valid_keys:
                self._value = None
        self._rebuild()

    # -- disabled -----------------------------------------------------------

    @property
    def disabled(self) -> bool:
        return self._disabled

    @disabled.setter
    def disabled(self, d: bool) -> None:
        self._disabled = d
        self._rebuild()

    # -- visible --------------------------------------------------------------
    # Delega direttamente a `self.control.visible` — permette di sostituire
    # meccanicamente `dd.visible = ...` con `picker.visible = ...` ovunque nel
    # progetto, senza dover riscrivere il codice chiamante per accedere a
    # `.control.visible` esplicitamente.

    @property
    def visible(self) -> bool:
        return bool(self.control.visible)

    @visible.setter
    def visible(self, v: bool) -> None:
        self.control.visible = v

    # -- lifecycle ----------------------------------------------------------

    def update(self) -> None:
        try:
            self.control.update()
        except RuntimeError:
            pass

    # -- interazione ----------------------------------------------------------

    def _is_selected(self, key: str) -> bool:
        return (key in self._values) if self.multi else (key == self._value)

    def _toggle(self, key: str) -> None:
        if self._disabled:
            return
        if self.multi:
            if key in self._values:
                self._values.remove(key)
            else:
                if self.max_selected is not None and len(self._values) >= self.max_selected:
                    return  # limite raggiunto: click ignorato silenziosamente
                self._values.append(key)
        else:
            if self._value == key:
                return  # già selezionata: nessuna modifica (stesso comportamento Dropdown)
            self._value = key
        self._rebuild()
        self.update()
        if self.on_select:
            fake_ev = type("CardPickerEvent", (), {"control": self})()
            self.on_select(fake_ev)

    def _rebuild(self) -> None:
        rows: list[ft.Control] = []
        if not self._options:
            rows.append(ft.Text(self.empty_text, size=12, color=COLOR_TEXT_MUTED, italic=True))
        for opt in self._options:
            key = opt.get("key", "")
            title = opt.get("title", key)
            body = opt.get("body", "")
            selected = self._is_selected(key)
            icon_name = (
                (ft.Icons.CHECK_BOX if selected else ft.Icons.CHECK_BOX_OUTLINE_BLANK)
                if self.multi else
                (ft.Icons.RADIO_BUTTON_CHECKED if selected else ft.Icons.RADIO_BUTTON_UNCHECKED)
            )
            header = ft.Row(
                [
                    ft.Icon(
                        icon_name, size=18,
                        color=self.active_color if selected else COLOR_TEXT_MUTED,
                    ),
                    ft.Text(
                        title, size=13, weight=ft.FontWeight.W_600,
                        color=COLOR_TEXT_TITLE if selected else COLOR_TEXT_PRIMARY,
                        expand=True,
                    ),
                ],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            card_children: list[ft.Control] = [header]
            if selected and body:
                card_children.append(ft.Container(
                    content=ft.Text(body, size=12, color=COLOR_TEXT_PRIMARY, selectable=True),
                    padding=ft.Padding.only(top=4, left=26),
                ))
            rows.append(ft.Container(
                content=ft.Column(card_children, spacing=2),
                on_click=(None if self._disabled else (lambda e, k=key: self._toggle(k))),
                bgcolor="#eef4ff" if selected else COLOR_BG_CARD,
                border=ft.Border.all(
                    1.5 if selected else 1,
                    self.active_color if selected else COLOR_BORDER,
                ),
                border_radius=6,
                padding=ft.Padding.all(8),
                ink=not self._disabled,
                opacity=0.5 if self._disabled else 1.0,
            ))
        # IMPORTANTE: mai riassegnare .controls = [...] in Flet 0.85.3 (vedi
        # CLAUDE.md) — modifica sempre in-place.
        self.control.controls.clear()
        for r in rows:
            self.control.controls.append(r)


def spell_card_options(spells: list[dict]) -> list[dict[str, str]]:
    """
    Opzioni CardPicker da una lista di dict incantesimo/trucchetto (stesso
    input di `make_spell_describe`, es. `_loader.get_spells(classe)`).
    """
    return [
        {"key": s.get("name", ""), "title": s.get("name", ""), "body": format_spell_body(s)}
        for s in spells if s.get("name")
    ]


def feat_card_options(loader: Any, names: list[str]) -> list[dict[str, str]]:
    """Opzioni CardPicker per una lista di nomi talento (risolti via `loader.get_feat`)."""
    opts: list[dict[str, str]] = []
    for n in names:
        fd = loader.get_feat(n)
        opts.append({"key": n, "title": n, "body": format_feat_body(fd) if fd else ""})
    return opts


def invocation_card_options(invocations: list[dict]) -> list[dict[str, str]]:
    """Opzioni CardPicker per una lista di dict Supplica Occulta (`_loader.get_invocations(...)`)."""
    return [
        {"key": i.get("name", ""), "title": i.get("name", ""), "body": format_invocation_body(i)}
        for i in invocations if i.get("name")
    ]


def named_option_card_options(options: list[dict]) -> list[dict[str, str]]:
    """
    Opzioni CardPicker per opzioni semplici `{"name","description"}`
    (Metamagia/Dono del Patto/Stile di Combattimento).
    """
    return [
        {"key": o.get("name", ""), "title": o.get("name", ""), "body": format_named_option_body(o)}
        for o in options if o.get("name")
    ]


def dropdown_with_info(
    page_getter: Callable[[], ft.Page | ft.BasePage | None],
    dropdown: ft.Dropdown,
    describe: Callable[[str], tuple[str, str] | None],
    tooltip: str = "Mostra descrizione",
) -> ft.Row:
    """
    Affianca un IconButton "ⓘ" a un Dropdown già costruito.

    Args:
        page_getter: funzione che restituisce la pagina corrente — sia
            `lambda: self._page` (attributo custom, tipizzato `ft.Page |
            None` in profilo_tab.py) sia `lambda: self.page` (il property
            nativo Flet `Control.page`, tipizzato dagli stub `ft.Page |
            ft.BasePage`, mai `None` a runtime dopo il mount — usato da
            wizard_view.py/manual_form.py). Entrambe le forme sono valide:
            `ft.Page` eredita da `ft.BasePage`, che espone già
            `show_dialog()`/`pop_dialog()`, le uniche API usate qui sotto —
            un riferimento diretto non basta perché in alcuni contesti
            (wizard/manual_form) la pagina viene risolta solo in
            `did_mount()`, dopo la costruzione del widget.
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
