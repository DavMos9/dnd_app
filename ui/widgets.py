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

**Pulizia 2026-07-26 (Fase 2 della revisione)**: `dropdown_with_info()` e le
quattro `make_*_describe()` sono state **rimosse**. Erano rimaste in questo
modulo "come helper generico riutilizzabile" dopo la conversione al
`CardPicker`, ma non hanno mai più avuto un solo chiamante: erano dead code a
tutti gli effetti (~200 righe). Le funzioni `format_*_body()` restano e sono
tuttora usate dagli helper `*_card_options()` qui sotto — nessuna duplicazione
di logica di formattazione.

**Bug fix 2026-07-16, stesso giorno, feedback diretto di Davide dopo aver
provato il redesign sopra**: "lo scorrimento è difficoltoso, se scelgo
l'incantesimo e poi voglio scorrere alle sezioni sotto ho difficoltà a
scorrere la finestra perché mi scorre la lista degli incantesimi... viene
usata pure da tablet". Causa: `CardPicker.control` era una `ft.Column` a
ALTEZZA FISSA con `scroll=ft.ScrollMode.AUTO` propria — sempre annidata
dentro un contenitore GIÀ scrollabile (il content Column del dialog di
level-up in `profilo_tab.py`, o il Column dell'intera fase in
`wizard_view.py`/`manual_form.py`, entrambi già `scroll=ft.ScrollMode.AUTO`).
Due regioni scrollabili annidate = il trascinamento sopra la card list viene
sempre catturato dalla lista (la più vicina al dito), mai dal contenitore
esterno — un problema di "nested scroll" classico, particolarmente fastidioso
su touch/tablet perché non c'è una scrollbar visibile da afferrare fuori
dalla lista per "bucare" verso lo scroll esterno. Flet 0.85.3 non espone un
equivalente del "NestedScrollView" nativo (nessuna fisica "scrolla la lista
solo se non è già al suo limite, altrimenti passa lo scroll al genitore") —
l'unica soluzione robusta con i controlli disponibili è eliminare la seconda
regione scrollabile: `CardPicker.control` ora è una `ft.Column` SENZA scroll
proprio e SENZA altezza fissa (si dimensiona naturalmente al contenuto,
esattamente come qualunque altra sezione di lista già presente nel progetto,
es. `_section_spell_list`/`_section_extra_spell_list` in `spells_view.py` —
mai scroll annidato lì, sempre stato così) — diventa così parte della stessa,
unica regione scrollabile del contenitore che la ospita. Il parametro
`height` è stato rimosso dalla firma (e da tutte le ~24 chiamate nel
progetto): non serve più, dato che non c'è più nulla da "tagliare" a una
finestra fissa. **Unico punto che richiedeva una modifica aggiuntiva**: il
dialog "Aggiungi Incantesimo Bonus" in `spells_view.py`, dove il CardPicker
era l'UNICA regione scrollabile (il Column del dialog non scrollava affatto,
`tight=True`) — lì lo scroll è stato spostato sul Column del dialog stesso
(stesso pattern già in uso in tutti gli altri dialog del progetto), così la
regola resta universale e senza eccezioni: **CardPicker non scrolla mai se
stesso, è sempre il contenitore che lo ospita a scrollare**.
"""

import flet as ft
from typing import Any, Callable
from config.settings import ABILITY_KEYS, ABILITY_SCORES
from ui import design

_ABILITY_KEY_TO_LABEL: dict[str, str] = dict(zip(ABILITY_KEYS, ABILITY_SCORES))


class ScrollMemoryListView(ft.ListView):
    """
    `ft.ListView` che ricorda la posizione di scroll e la ripristina dopo un
    rebuild dei propri `controls`.

    Perché serve (bug B10 della revisione 2026-07-26): tutti i tab della scheda
    personaggio si aggiornano con lo stesso pattern
    `self.controls.clear(); self._build(); self.update()`, cioè ricostruendo
    l'intero contenuto ad OGNI singola interazione — anche un semplice "−1 HP".
    Dato che i controlli sono oggetti nuovi, Flutter riparte da capo e **lo
    scroll torna in cima**: su un tab con 21 sezioni (Combattimento) applicare
    un danno rimandava il giocatore all'inizio della pagina ogni volta. Era il
    difetto UX più fastidioso dell'app.

    Come funziona: si aggancia a `on_scroll` (evento già esposto da
    `ft.ListView` in Flet 0.85.3, con il campo `pixels`) per tenere traccia
    dell'ultimo offset noto, e `restore_scroll()` lo riapplica con
    `scroll_to(offset=..., duration=0)` — nessuna animazione, il ripristino
    deve essere invisibile. Se il contenuto si è accorciato, Flutter clampa
    l'offset da solo al massimo disponibile.

    Uso: sostituire `ft.ListView` come classe base e chiamare
    `self.restore_scroll()` in fondo al proprio `_refresh()`, subito dopo
    `self.update()`.

    Un eventuale `on_scroll` passato dal chiamante viene comunque invocato
    (non sovrascritto), così la classe resta trasparente.
    """

    # Intervallo di notifica dell'evento scroll. Il default di Flet (10 ms) è
    # inutilmente fitto per il solo scopo di ricordare un offset e in modalità
    # web produrrebbe traffico websocket a ogni frame di scorrimento.
    _SCROLL_INTERVAL_MS = 100

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        user_on_scroll = kwargs.pop("on_scroll", None)
        kwargs.setdefault("scroll_interval", self._SCROLL_INTERVAL_MS)
        super().__init__(*args, **kwargs)
        self._scroll_offset: float = 0.0
        self._user_on_scroll = user_on_scroll
        self.on_scroll = self._track_scroll

    def _track_scroll(self, e: Any) -> None:
        try:
            px = getattr(e, "pixels", None)
            if px is not None:
                self._scroll_offset = float(px)
        except (TypeError, ValueError):
            pass
        if self._user_on_scroll is not None:
            self._user_on_scroll(e)

    def restore_scroll(self) -> None:
        """
        Riapplica l'ultimo offset noto (no-op se siamo già in cima).

        ⚠️ `ScrollableControl.scroll_to()` in Flet 0.85.3 è una **coroutine**
        (`async def`, verificato con `inspect.iscoroutinefunction`): chiamarla
        senza await non fa assolutamente nulla e produce solo un
        `RuntimeWarning: coroutine was never awaited`. Va quindi pianificata
        sul loop della sessione con `page.run_task()`, che è anche il modo
        corretto di rientrare nel thread della UI.
        """
        if self._scroll_offset <= 0:
            return
        try:
            page = self.page
        except (RuntimeError, AssertionError):
            return               # controllo non montato: nulla da ripristinare
        if page is None:
            return
        try:
            page.run_task(self.scroll_to, offset=self._scroll_offset, duration=0)
        except Exception:
            # Sessione non ancora connessa / loop non disponibile: il mancato
            # ripristino dello scroll non deve mai far fallire un refresh.
            pass

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

    **Nessuno scroll proprio** (fix 2026-07-16, vedi nota di modulo più
    sopra): `.control` si dimensiona sempre al proprio contenuto — il
    contenitore che lo ospita è SEMPRE responsabile dello scroll (dialog di
    level-up, fase di creazione, ecc., già tutti scrollabili). Non annidare
    mai un secondo `scroll=ft.ScrollMode.AUTO` intorno a `.control`.

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
                            (+ `"badge"`/`"badge_color"` opzionali — un
                            piccolo chip mostrato accanto al titolo, es. il
                            livello di un incantesimo; vedi gli helper
                            `*_card_options()` sotto per costruirla dagli
                            stessi dati già usati da `make_*_describe()`).
                            Riassegnarla ricostruisce la lista e rimuove
                            dalla selezione corrente le key non più presenti
                            (stesso comportamento del pattern di esclusione
                            reciproca già in uso per i Dropdown: la
                            selezione va validata di nuovo ad ogni cambio di
                            opzioni disponibili).
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
        empty_text: str = "Nessuna opzione disponibile.",
        active_color: str | None = None,
        on_select: Callable[[Any], None] | None = None,
    ) -> None:
        self.multi = multi
        self.max_selected = max_selected
        self.empty_text = empty_text
        self.active_color = active_color or design.T().magic
        self.on_select = on_select

        self._options: list[dict[str, str]] = []
        self._value: str | None = value
        self._values: list[str] = list(values) if values is not None else (
            [value] if (multi and value) else []
        )
        self._disabled = disabled

        # Nessuno scroll/altezza fissa propria — vedi nota di modulo e
        # docstring di classe (fix 2026-07-16): il contenitore che ospita
        # `.control` è sempre responsabile dello scroll.
        self.control = ft.Column(spacing=4)
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
            rows.append(ft.Text(self.empty_text, size=12, color=design.T().text_3, italic=True))
        for opt in self._options:
            key = opt.get("key", "")
            title = opt.get("title", key)
            body = opt.get("body", "")
            badge = opt.get("badge", "")
            badge_color = opt.get("badge_color") or design.T().magic
            selected = self._is_selected(key)
            icon_name = (
                (ft.Icons.CHECK_BOX if selected else ft.Icons.CHECK_BOX_OUTLINE_BLANK)
                if self.multi else
                (ft.Icons.RADIO_BUTTON_CHECKED if selected else ft.Icons.RADIO_BUTTON_UNCHECKED)
            )
            header_children: list[ft.Control] = [
                ft.Icon(
                    icon_name, size=18,
                    color=self.active_color if selected else design.T().text_3,
                ),
                ft.Text(
                    title, size=13, weight=ft.FontWeight.W_600,
                    color=design.T().text if selected else design.T().text,
                    expand=True,
                ),
            ]
            if badge:
                header_children.append(ft.Container(
                    content=ft.Text(badge, size=10, color=design.T().on_primary,
                                     weight=ft.FontWeight.BOLD),
                    bgcolor=badge_color,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    border_radius=design.Radius.SM,
                ))
            header = ft.Row(
                header_children,
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            card_children: list[ft.Control] = [header]
            if selected and body:
                card_children.append(ft.Container(
                    content=ft.Text(body, size=12, color=design.T().text, selectable=True),
                    padding=ft.Padding.only(top=4, left=26),
                ))
            rows.append(ft.Container(
                content=ft.Column(card_children, spacing=2),
                on_click=(None if self._disabled else (lambda e, k=key: self._toggle(k))),
                bgcolor=design.T().info_bg if selected else design.T().surface,
                border=ft.Border.all(
                    1.5 if selected else 1,
                    self.active_color if selected else design.T().border,
                ),
                border_radius=design.Radius.MD,
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

    Ogni card mostra anche un badge col livello (fix 2026-07-16, richiesta
    Davide: "affianco [al titolo] sia indicato anche il livello
    dell'incantesimo" — utile soprattutto per i picker che mescolano più
    livelli nella stessa lista, es. SPELL_LEARN al level-up o "Incantesimi
    Bonus", dove non è ovvio a colpo d'occhio il livello di ogni voce).
    Stessa convenzione testo/colore già usata nei dialog di dettaglio di
    `spells_view.py` ("0" blu per i trucchetti, "Lv{N}" crimson per gli
    incantesimi) — coerenza visiva tra la lista di scelta e i dialog.
    """
    opts: list[dict[str, str]] = []
    for s in spells:
        name = s.get("name", "")
        if not name:
            continue
        level = s.get("level", 0)
        opts.append({
            "key": name, "title": name, "body": format_spell_body(s),
            "badge": "0" if level == 0 else f"Lv{level}",
            "badge_color": design.T().magic if level == 0 else design.T().primary,
        })
    return opts


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


def format_equipment_item_body(item: dict, loader: Any) -> str:
    """
    Corpo descrittivo per una singola voce di equipaggiamento iniziale —
    espande il contenuto di una Dotazione ("Dotazione da Avventuriero" ecc.)
    nei singoli oggetti che contiene, via `loader.get_pack_contents(name)`
    (2026-07-11, dato già strutturato in adventuring_gear.json). Richiesta
    di Davide (2026-07-17): "rendere come la scelta degli incantesimi...
    quando scelgo voglio vedere cosa mi dà la dotazione scelta" — stesso
    principio dei formatter `format_*_body` sopra, applicato qui alle
    dotazioni invece che a incantesimi/talenti.

    Ritorna stringa vuota per un oggetto che non è una dotazione nota (nulla
    da espandere, il solo nome nel titolo della card è già sufficiente) o
    per una voce "weapon_choice" (la scelta dell'arma specifica avviene già
    nei Dropdown dedicati mostrati sotto la card, non richiede un corpo).
    """
    if item.get("item_type") == "weapon_choice":
        return ""
    name = item.get("name", "")
    if not name:
        return ""
    contents = loader.get_pack_contents(name)
    if not contents:
        return ""
    lines = [f'Contenuto di "{name}":']
    for c in contents:
        cname = c.get("name", "")
        if not cname:
            continue
        cqty = c.get("quantity", 1)
        lines.append("• " + cname + (f" ×{cqty}" if cqty and cqty > 1 else ""))
    return "\n".join(lines)


def equipment_option_card_options(options: list[list[dict]], loader: Any) -> list[dict[str, str]]:
    """
    Opzioni CardPicker per una scelta A/B di equipaggiamento iniziale
    (`starting_equipment` → entry `"type": "choice"` → `"options"`, ognuna
    una lista di 1+ voci che compongono un unico "pacchetto" alternativo,
    es. arma+scudo OPPURE un'arma a due mani). Il titolo di ogni card resta
    il riepilogo già in uso (`"Ascia  +  Scudo"`); il corpo, mostrato solo
    quando la card è selezionata (comportamento nativo di `CardPicker`),
    espande il contenuto di ogni eventuale Dotazione presente nel pacchetto.
    """
    opts: list[dict[str, str]] = []
    for i, pkg in enumerate(options):
        parts: list[str] = []
        bodies: list[str] = []
        for it in pkg:
            if it.get("item_type") == "weapon_choice":
                cat = it.get("category", "semplice").replace("_", " ")
                cnt = it.get("count", 1)
                parts.append(f"Qualsiasi arma {cat}" + (f" ×{cnt}" if cnt > 1 else ""))
            else:
                qty = it.get("quantity", 1)
                parts.append(it.get("name", "") + (f" ×{qty}" if qty > 1 else ""))
            body = format_equipment_item_body(it, loader)
            if body:
                bodies.append(body)
        opts.append({
            "key": str(i),
            "title": "  +  ".join(parts),
            "body": "\n\n".join(bodies),
        })
    return opts


def wrap_dialog_actions(buttons: list[ft.Control]) -> list[ft.Control]:
    """
    Avvolge una lista di pulsanti da usare in `ft.AlertDialog(actions=...)`
    in un'unica `ft.Row` con `wrap=True`.

    Aggiunto il 2026-07-24 (bug report Davide: "l'interfaccia si deve sempre
    adattare alla finestra, conta che deve essere usato anche per
    smartphone"). `AlertDialog.actions` in Flet è renderizzato come una Row
    che NON va mai a capo da sola — con 3+ pulsanti (es. "Annulla" / "Reset"
    / "Applica") su una finestra stretta o su smartphone i pulsanti in più
    escono dal bordo del dialog invece di diventare una seconda riga.

    Usare così: `actions=wrap_dialog_actions([btn1, btn2, btn3])` al posto
    di `actions=[btn1, btn2, btn3]` — su schermi larghi il risultato visivo
    è identico (un'unica riga allineata a destra), su schermi stretti i
    pulsanti in eccesso vanno semplicemente a capo invece di essere tagliati.
    Con 1-2 pulsanti il comportamento è invariato (mai vanno a capo).
    """
    return [ft.Row(buttons, wrap=True, alignment=ft.MainAxisAlignment.END, spacing=8)]


def responsive_dialog_width(page: Any, base_width: int, margin: int = 32, min_width: int = 260) -> int:
    """
    Calcola una larghezza sicura per il content di un `ft.AlertDialog`, che
    non superi mai lo spazio disponibile della finestra/schermo.

    Aggiunto il 2026-07-24 (stesso bug report "l'interfaccia si deve sempre
    adattare alla finestra... anche per smartphone" già alla base di
    `wrap_dialog_actions`): diversi dialog della Sezione Master (Genera
    Tesoro/Trappola, Malattie e Veleni, Incontri per Ambiente) avevano un
    `width=` fisso (420-440px) sul `ft.Column` di contenuto — su uno
    smartphone più stretto di quel valore (es. iPhone SE, ~375px di
    viewport) il dialog stesso va in overflow orizzontale, indipendentemente
    da quanto siano responsive i pulsanti al suo interno.

    Uso: `width=responsive_dialog_width(page, 420)` al posto di `width=420`
    — su schermi larghi il risultato è identico al valore fisso originale
    (`base_width`), su schermi più stretti si riduce fino a `min_width`
    (mai sotto, per non produrre un dialog illeggibile) lasciando `margin`
    px di rispetto ai bordi. Se `page.width` non è ancora disponibile
    (`None`, prima del primo layout) ricade su `base_width` invariato.
    """
    page_width = getattr(page, "width", None)
    if not page_width:
        return base_width
    return max(min_width, min(base_width, int(page_width) - margin))


# ---------------------------------------------------------------------------
# Cambio tema (Fase D del restyle, 2026-07-30)
# ---------------------------------------------------------------------------

#: Icona ed etichetta per ciascuna preferenza di tema. Un unico posto, così i
#: tre punti d'uso (Home, sidebar/bottom nav, Sezione Master) non divergono —
#: stesso problema già capitato con le 3 copie di `_action_pill`, poi unificate
#: nella primitiva `design.pill()`.
#: I nomi icona sono verificati per introspezione su `flet==0.85.3`.
THEME_TOGGLE_LOOK: dict[str, tuple[ft.IconData, str]] = {
    "light":  (ft.Icons.LIGHT_MODE,       "Chiaro"),
    "dark":   (ft.Icons.DARK_MODE,        "Scuro"),
    "system": (ft.Icons.BRIGHTNESS_AUTO,  "Sistema"),
}


def theme_toggle_look(preference: str) -> tuple[ft.IconData, str]:
    """
    Icona ed etichetta da mostrare per la preferenza corrente.

    Una preferenza non riconosciuta ricade su "system" invece di sollevare:
    il pulsante resta usabile anche partendo da uno stato sporco, e cliccarlo
    riporta comunque il ciclo su un valore valido (vedi
    `settings_repo.next_theme_preference`).
    """
    return THEME_TOGGLE_LOOK.get(preference, THEME_TOGGLE_LOOK["system"])


def theme_toggle_tooltip(preference: str) -> str:
    """Testo del tooltip: dice sia lo stato attuale sia cosa fa il click."""
    _, label = theme_toggle_look(preference)
    return f"Tema: {label} — clicca per cambiare (Chiaro → Scuro → Sistema)"


def theme_toggle_pill(preference: str,
                      on_click: Callable[[Any], None],
                      *, color: str | None = None) -> ft.Container:
    """
    Pillola di cambio tema per i contesti a pillole (Home, Sezione Master).

    Mostra **icona + etichetta**, mai un'icona muta: è il principio "nulla di
    nascosto" già stabilito per il progetto — chi apre l'app per la prima volta
    deve capire cosa fa il pulsante senza doverlo premere. L'etichetta è lo
    stato ATTUALE ("Chiaro"/"Scuro"/"Sistema"), non l'azione, coerente con il
    fatto che il ciclo ha tre stati e non è un semplice interruttore.

    La sidebar e la bottom nav non usano questa pillola ma la stessa coppia
    icona/etichetta tramite `theme_toggle_look()`, perché lì la forma corretta
    è quella delle altre voci di navigazione (colonna icona sopra etichetta su
    fondo scuro), non una pillola.
    """
    icon, label = theme_toggle_look(preference)
    return design.pill(
        icon, label,
        color=color or design.T().text_2,
        on_click=on_click,
        tooltip=theme_toggle_tooltip(preference),
    )
