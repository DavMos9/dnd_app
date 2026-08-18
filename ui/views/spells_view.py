"""
SpellsView — Gestione incantesimi del personaggio.

Struttura:
  - Header: caratteristica/CD/bonus attacco + banner "X/Y preparati"
    (preparatori) o "X/Y conosciuti" (classi "know")
  - Lista slot per livello (read-only — modifica in Combattimento)
  - Sezione incantesimi, con DUE modalità distinte in base alla classe
    (task bug fix 2026-07-16, Davide: "Tutte le classi devono avere la
    modalità coerente di incantesimi"):
    · Full/half preparatori (Chierico, Druido, Mago, Paladino): intero
      catalogo di classe raggruppato per livello, con toggle di
      preparazione (cerchietto) — scrive/cancella in known_spells,
      soggetto al limite giornaliero PHB.
    · Classi "know" (Bardo, Ranger, Stregone, Warlock) e le sottoclassi
      "prese in prestito dal Mago" (Mistificatore Arcano, Cavaliere
      Mistico): SOLA LETTURA — mostra solo gli incantesimi realmente in
      `known_spells` (scelti alla creazione, o imparati/scambiati via
      SPELL_LEARN/SPELL_SWAP/CANTRIP_LEARN al level-up). Nessun toggle
      sull'intero catalogo: imparare un incantesimo qualsiasi all'istante
      da questa vista bypasserebbe il level-up, incoerente con come sono
      già gestiti Segreti Magici/Mistificatore/Cavaliere (sempre stati
      sola lettura).
    · Click sul nome → dialog con descrizione completa, in entrambi i casi.

Regole PHB preparazione/conoscenza:
  - I trucchetti (livello 0) sono sempre disponibili, non contano nel limite.
  - Full caster (Chierico, Druido, Mago): mod_car + livello classe (min 1)
  - Half caster (Paladino): mod_car + metà livello arrotondato giù (min 1)
  - Classi "know" (Bardo, Ranger, Stregone, Warlock): nessun limite/toggle,
    lista fissa di incantesimi conosciuti (sezione "Incantesimi Conosciuti",
    sola lettura) — il Ranger NON prepara ogni giorno come Chierico/Druido/
    Paladino, "conosce" incantesimi fissi esattamente come Bardo/Stregone/
    Warlock (PHB IT, ranger.json → feature "Incantesimi": "Un ranger
    conosce due incantesimi di 1° livello a sua scelta"). Corretto il
    2026-07-11 — prima era erroneamente incluso tra gli "half caster",
    vedi CLAUDE.md.
  - Override manuale del giocatore: sovrascrive la formula se ≥ 1 (solo
    per i preparatori — non ha senso per le classi "know").
"""

import flet as ft
import logging
from typing import Any, cast
from config.settings import *
from config.settings import get_modifier, char_prof_bonus
from data.models import Character, KnownSpell, SpellSlot
import data.repositories.character_repo as character_repo
from data.repositories import world_repo
from data.game_data.game_data_loader import GameDataLoader
from ui.theme import section_header, muted_text
import core.character_stats as cs
from core import world_sync
from core.world_backend import LocalBackend, RemoteBackend
from ui.components.background_sync import BackgroundSyncLoop
from ui.device_identity import resolve_device_id
from ui.components.roll_panel import show_roll
from ui.widgets import (CardPicker, ScrollMemoryListView, spell_card_options,
                        wrap_dialog_actions, responsive_dialog_width)
from ui import design

logger = logging.getLogger(__name__)

#: Stesso intervallo già validato altrove (`sheet_view.py::_SHEET_SYNC_INTERVAL_S`)
#: — copre il caso trovato da Davide (2026-08-16): un incantesimo/abilità
#: bonus concesso dal master non compariva finché il giocatore non lasciava
#: la sezione Incantesimi e ci rientrava, perché questa vista (di primo
#: livello nella sidebar, non un tab di `SheetView`) non aveva mai avuto un
#: `BackgroundSyncLoop` — nessuna vista scaricava eventi dall'host finché il
#: giocatore restava qui.
_SPELLS_SYNC_INTERVAL_S = 2.0

_loader = GameDataLoader()

_SLOT_NAMES = ["1°", "2°", "3°", "4°", "5°", "6°", "7°", "8°", "9°"]

# Classi con sistema "prepara dalla lista"
_PREP_FULL: set[str] = {"chierico", "druido", "mago"}
_PREP_HALF: set[str] = {"paladino"}
# Classi "know" (nessun limite di preparazione) — il Ranger vive qui, non in
# _PREP_HALF: PHB IT conferma "un ranger conosce due incantesimi di 1° livello
# a sua scelta", stessa meccanica di Bardo/Stregone/Warlock (vedi CLAUDE.md,
# fix 2026-07-11).
_KNOW_CLASSES: set[str] = {"bardo", "ranger", "stregone", "warlock"}


def _expected_known_spell_count_for(class_name: str, class_level: int) -> int:
    """
    Variante parametrizzata di `_expected_known_spell_count()` — stessa
    formula, ma su una classe/livello espliciti invece di leggerli sempre
    da `c.class_name`/`c.level` (il totale del personaggio). Multiclasse
    (2026-08-12): ogni classe "know" accumula i propri incantesimi
    conosciuti sul PROPRIO livello di classe (PHB IT p.165, stesso
    principio del limite di preparazione — vedi `_calc_max_prepared_value`),
    mai sul livello totale del personaggio.
    """
    total = _loader.get_spells_known_at_1(class_name)
    delta = _loader.get_spell_learn_delta(class_name)
    for lv in range(2, class_level + 1):
        total += delta.get(lv, 0)
    return total


def _expected_known_spell_count(c: Character) -> int:
    """
    Totale atteso di incantesimi (livello ≥ 1, trucchetti esclusi) che una
    classe "know" dovrebbe conoscere al livello attuale del personaggio,
    secondo le tabelle PHB già usate da core/level_manager.py per generare
    lo step SPELL_LEARN al level-up (spells_known_at_1 + spell_learn_delta
    cumulativo). Per il Ranger (nessun `spells_known_at_1`, i primi
    incantesimi arrivano al level-up verso il Lv.2) parte da 0. 0 per
    qualunque classe che non sia "know" (chiamante deve già filtrare).

    Aggiunto 2026-07-11 — bug report di Davide: "per le classi con
    incantesimi conosciuti fissi esce incantesimi conosciuti, ma non quelli
    selezionati, comodo per capire se hai sforato" — prima il banner
    mostrava solo il conteggio grezzo, senza un totale di riferimento contro
    cui confrontarlo. Percorso a CLASSE SINGOLA (o primaria) — invariato,
    delega alla variante parametrizzata sopra con `c.class_name`/`c.level`.
    """
    return _expected_known_spell_count_for(c.class_name or "", c.level)


def _max_preparable_spell_level(slots: list[SpellSlot]) -> int:
    """
    Livello massimo di incantesimo che un preparatore (Chierico/Druido/Mago/
    Paladino) può preparare, in base agli slot incantesimo realmente
    posseduti — PHB: "ogni incantesimo [...] deve essere di un livello per
    cui il personaggio possiede uno slot incantesimo". I trucchetti
    (livello 0) non hanno questo vincolo (nessuno slot richiesto), gestiti
    a parte dal chiamante.

    Bug fix 2026-07-16 (Davide): "L'aumento del livello mi mostra tutti gli
    incantesimi, invece [...] il livello massimo degli incantesimi imparati
    corrisponde al livello dello slot incantesimo più alto posseduto
    dall'incantatore" — la sezione "Incantesimi" per i preparatori mostrava
    l'intero catalogo di classe (fino al 9° livello) senza alcun filtro
    basato sugli slot realmente posseduti, permettendo di "preparare" un
    incantesimo di livello superiore a quanto il personaggio può lanciare.
    """
    return max((s.slot_level for s in slots if s.total > 0), default=0)


def _calc_max_prepared_value(
    class_name: str, class_level: int, spellcasting_ability: str,
    scores: dict[str, int], override: int,
) -> int | None:
    """
    Nucleo della formula PHB di `_calc_max_prepared()`, parametrizzato su
    classe/livello/caratteristica espliciti invece che letti sempre da un
    `Character` a classe singola. Multiclasse (2026-08-12): PHB IT p.165,
    "determina gli incantesimi che puoi preparare per ciascuna classe
    individualmente, come se fossi un personaggio a classe singola di
    quella classe" — ogni classe usa il SUO livello di classe (mai il
    totale del personaggio) e la SUA caratteristica da incantatore.
    """
    if override > 0:
        return override
    key = (class_name or "").strip().lower()
    sp_mod = get_modifier(scores.get(spellcasting_ability or "", 10))
    if key in _PREP_FULL:
        return max(1, sp_mod + class_level)
    if key in _PREP_HALF:
        return max(1, sp_mod + max(1, class_level // 2))
    if key in _KNOW_CLASSES:
        return None  # nessun limite — "known spells"
    # Sottoclasse incantatore (es. Guerriero Arcano, Ladro Mistificatore):
    # segnaliamo nessun limite perché la formula varia troppo
    return None


def _calc_max_prepared(c: Character) -> int | None:
    """
    Calcola il massimo di incantesimi preparabili secondo le regole PHB.
    Restituisce None per le classi "know" (nessun limite).
    Tiene conto dell'override manuale del giocatore (max_prepared_spells_override > 0).
    Percorso a CLASSE SINGOLA (o primaria) — invariato, delega alla
    variante parametrizzata sopra con `c.class_name`/`c.level` (il totale,
    che per un personaggio a classe singola coincide col livello di
    classe).
    """
    scores = {
        "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
        "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
    }
    return _calc_max_prepared_value(
        c.class_name or "", c.level, c.spellcasting_ability or "",
        scores, c.max_prepared_spells_override,
    )


class _ClassAbilityView:
    """
    Vista di sola lettura che espone `spellcasting_ability` di UNA classe
    specifica (usata per calcolare CD/bonus attacco DI QUELLA CLASSE con
    `core/character_stats.py`, che legge `character.spellcasting_ability`
    tramite `getattr`) delegando ogni altro attributo — punteggi di
    caratteristica, livello TOTALE, bonus di competenza: tutti condivisi a
    livello di PERSONAGGIO, mai di singola classe (PHB IT p.165) — al
    Character reale sottostante.

    Multiclasse (2026-08-12, bug report Davide: "la sezione incantesimi
    tiene conto solo della classe principale") — usata SOLO quando il
    personaggio ha più di una classe con lista incantesimi propria
    (`SpellsView._caster_rows`, vedi `_section_magic_header_mc`); per un
    personaggio a classe singola l'header resta quello di sempre
    (`_section_magic_header`, `c.spellcasting_ability` letto direttamente).
    """

    def __init__(self, character: Character, spellcasting_ability: str) -> None:
        object.__setattr__(self, "_character", character)
        object.__setattr__(self, "spellcasting_ability", spellcasting_ability)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_character"), name)


def _caster_class_rows(character: Character) -> list[tuple[Any, list[dict[str, Any]]]]:
    """
    Righe di `character_classes` che hanno una PROPRIA lista di incantesimi
    (Chierico/Druido/Mago/Paladino/Bardo/Ranger/Stregone/Warlock) — esclude
    le classi senza spellcasting_ability propria (es. Guerriero puro senza
    sottoclasse incantatrice) e le sottoclassi "casting preso in prestito
    dal Mago" (Mistificatore Arcano/Cavaliere Mistico), che restano gestite
    dal meccanismo "Incantesimi Extra" già esistente (invariato — la loro
    lista di classe propria è sempre vuota per definizione).

    Per un personaggio a classe singola ritorna sempre esattamente una
    riga (la primaria, byte-identica a `character.class_name`/`.level`) —
    usata SOLO per decidere se attivare il rendering multiclasse
    (`len(...) > 1`): il percorso a classe singola resta quello di sempre,
    mai da qui (2026-08-12, vedi `SpellsView._build()`).
    """
    rows = []
    for cc in character_repo.get_character_classes(character.id):
        spells = _loader.get_spells(cc.class_name)
        if spells:
            rows.append((cc, spells))
    return rows


class SpellsView(ScrollMemoryListView):
    """Vista incantesimi: preparazione e consultazione."""

    def __init__(self, character: Character) -> None:
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._page: ft.Page | None = None
        # Mistificatore Arcano (Ladro)/Cavaliere Mistico (Guerriero): sync
        # difensivo ad ogni apertura tab (stesso pattern di
        # combattimento_tab.py) — no-op per qualunque altra classe/
        # sottoclasse. Copre anche i personaggi la cui sottoclasse era già
        # stata scelta PRIMA di questo fix (2026-07-15).
        character_repo.sync_borrowed_spellcasting_ability(character)
        character_repo.init_borrowed_caster_slots(
            character.id, character.class_name or "", character.subclass or "", character.level
        )
        # Incantesimi sempre pronti da Dominio/Giuramento/Circolo della Terra
        # — sync difensiva ad ogni apertura tab, stesso pattern del casting
        # "preso in prestito" sopra (self-healing anche per personaggi la
        # cui sottoclasse/terreno era già impostato prima di questo fix).
        character_repo.sync_bonus_domain_spells(character)
        # Incantesimi innati di razza (Drow "Magia Drow", Tiefling "Eredità
        # Infernale" — task #15, 2026-07-16): sync difensiva delle risorse
        # (Luminescenza/Oscurità/Intimorire Infernale, 1/riposo lungo) così
        # il contatore esiste anche se il giocatore apre questa tab PRIMA di
        # Combattimento — stesso pattern self-healing già in uso sopra.
        character_repo.init_class_resources(
            character.id, character.class_name or "", character.level, character
        )
        self._racial_innate: list[dict[str, Any]] = _loader.get_racial_innate_spells(
            character.race or "", character.subrace or ""
        )
        self._slots: list[SpellSlot] = character_repo.get_spell_slots(character.id)
        self._known: dict[tuple[str, int], KnownSpell] = {}
        self._reload_known()
        self._class_spells: list[dict[str, Any]] = _loader.get_spells(
            character.class_name or ""
        )
        # Multiclasse (2026-08-12, bug report Davide: "la sezione
        # incantesimi tiene conto solo della classe principale") — righe di
        # character_classes con una PROPRIA lista di incantesimi. Per un
        # personaggio a classe singola contiene sempre esattamente una riga
        # (la primaria): il rendering più sotto resta quello di sempre in
        # quel caso, il percorso multiclasse (nuovo) si attiva solo con
        # len(self._caster_rows) > 1. `self._class_spells` sopra resta
        # quella della sola PRIMARIA (invariata, per tutti i punti che la
        # usavano già prima di questo fix), MAI usata per decidere se
        # mostrare il nuovo rendering multiclasse.
        self._caster_rows: list[tuple[Any, list[dict[str, Any]]]] = _caster_class_rows(character)

        # Sincronizzazione in background (2026-08-16) — vedi commento su
        # `_SPELLS_SYNC_INTERVAL_S`. Scoped al SOLO mondo di questo
        # personaggio, stesso pattern di `sheet_view.py::SheetView`.
        self.device_id: str | None = None
        self.backend = LocalBackend()
        self._remote_backends: dict[str, RemoteBackend] = {}
        self._sync_loop: BackgroundSyncLoop | None = None
        self._connection_state: str = "connected"

        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)
        page = self.page
        if page is not None:
            page.run_task(self._init_world_sync)

    def will_unmount(self) -> None:
        self._stop_world_sync()

    async def _init_world_sync(self) -> None:
        if not self.character.world_id:
            return
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        self._start_world_sync()

    def _start_world_sync(self) -> None:
        if self._sync_loop is not None or not self.character.world_id:
            return
        world_id = self.character.world_id

        def _apply() -> None:
            world = world_repo.get_world(world_id)
            if world is None or world.is_local_host:
                return
            backend = world_sync.resolve_backend_for_world(
                world, self.device_id or "", self.backend, self._remote_backends,
            )
            if backend is not None and isinstance(backend, RemoteBackend):
                self._connection_state = backend.connection_state()
                world_sync.sync_replica(backend, world_id)
            else:
                self._connection_state = "disconnected"

        def _signature() -> str | None:
            world = world_repo.get_world(world_id)
            seq = world.last_synced_seq if world is not None else 0
            return f"{self._connection_state}|{seq}"

        async def _redraw() -> None:
            self._refresh()

        loop = BackgroundSyncLoop(
            get_page=lambda: self.page,
            signature_fn=_signature,
            async_redraw_fn=_redraw,
            apply_fn=_apply,
            interval_s=_SPELLS_SYNC_INTERVAL_S,
            thread_name=f"spells-sync-{self.character.id[:8]}",
        )
        self._sync_loop = loop
        loop.start()

    def _stop_world_sync(self) -> None:
        if self._sync_loop is not None:
            self._sync_loop.stop()
        self._sync_loop = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reload_known(self) -> None:
        self._known = {
            (s.name, s.spell_level): s
            for s in character_repo.get_known_spells(self.character.id)
        }

    def _is_prepared(self, name: str, level: int) -> bool:
        ks = self._known.get((name, level))
        return ks is not None and ks.is_prepared

    def _bonus_known(self) -> list[KnownSpell]:
        """Incantesimi bonus aggiunti manualmente dal giocatore (task #25, 2026-07-16)."""
        return [ks for ks in self._known.values() if ks.is_bonus]

    def _prepared_count(self) -> int:
        """
        Conta solo gli incantesimi preparati di livello ≥ 1 (trucchetti
        esclusi). Esclude anche gli incantesimi "sempre pronti" da privilegio
        di Dominio/Giuramento/Circolo (`always_prepared`) — PHB: questi
        incantesimi non contano nel numero di incantesimi che il personaggio
        può preparare (task #26, 2026-07-16).
        """
        return sum(
            1 for (_, lv), ks in self._known.items()
            if ks.is_prepared and lv > 0 and not ks.always_prepared
        )

    def _prepared_count_for_class(self, class_name: str) -> int:
        """
        Come `_prepared_count()` ma filtrato sulla sola classe indicata
        (`class_list`) — usato dalle sezioni multiclasse (2026-08-12), dove
        ogni classe ha il proprio limite/conteggio indipendente (PHB IT
        p.165). Stessa esclusione di `always_prepared`, NON esclude i
        bonus (`is_bonus`) — stessa scelta già fatta in `_prepared_count()`,
        mai cambiata qui per restare coerente.

        Limite noto: `known_spells` non ha una chiave che includa la
        classe (solo nome+livello), quindi un incantesimo con lo STESSO
        nome+livello posseduto da ENTRAMBE le classi del personaggio (raro
        — es. "Cura Ferite" 1° livello, in comune a Chierico e Paladino)
        condivide la stessa riga e comparirebbe preparato in entrambe le
        sezioni contemporaneamente.
        """
        key = (class_name or "").strip().lower()
        return sum(
            1 for (_, lv), ks in self._known.items()
            if ks.is_prepared and lv > 0 and not ks.always_prepared
            and (ks.class_list or "").strip().lower() == key
        )

    def _toggle_prepared(self, spell: dict[str, Any]) -> None:
        name  = spell.get("name", "")
        level = spell.get("level", 0)
        was_prepared = self._is_prepared(name, level)

        # I trucchetti (level 0) non hanno limite — sempre togglabili
        if not was_prepared and level > 0:
            max_prep = _calc_max_prepared(self.character)
            if max_prep is not None and self._prepared_count() >= max_prep:
                # Limite raggiunto: mostra snackbar e blocca
                if self._page:
                    self._page.show_dialog(ft.AlertDialog(
                        title=design.dialog_title("Limite raggiunto"),
                        content=ft.Text(
                            f"Hai già preparato {max_prep} incantesimi, "
                            f"il massimo per il tuo livello.\n\n"
                            f"Deprepara un incantesimo oppure aumenta il limite "
                            f"manualmente con il tasto ✎.",
                            size=13, color=design.T().text,
                        ),
                        actions=[
                            ft.TextButton(
                                "OK",
                                on_click=lambda e: self._page.pop_dialog()
                                if self._page else None,
                            )
                        ],
                    ))
                return

        if was_prepared:
            character_repo.remove_known_spell(self.character.id, name, level)
        else:
            comps = spell.get("components", [])
            comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
            if spell.get("material"):
                comp_str += f" ({spell['material']})"
            character_repo.upsert_known_spell(
                character_id=self.character.id,
                name=name, level=level, is_prepared=True,
                school=spell.get("school", ""),
                casting_time=spell.get("casting_time", ""),
                spell_range=spell.get("range", ""),
                components=comp_str,
                duration=spell.get("duration", ""),
                description=spell.get("description", ""),
                higher_levels=spell.get("higher_levels", "") or "",
                class_list=self.character.class_name or "",
            )

        self._reload_known()
        self._refresh()

    def _toggle_prepared_mc(self, spell: dict[str, Any], class_name: str) -> None:
        """
        Variante multiclasse di `_toggle_prepared()` (2026-08-12) — stessa
        logica, ma limite/conteggio calcolati SOLO sulla classe passata
        (`class_list`), e salva lo spell con `class_list=class_name`
        invece di `self.character.class_name` (che per una classe
        secondaria sarebbe quello sbagliato — PHB IT p.165, ogni classe si
        prepara come se fosse a classe singola). Chiamata SOLO dalle
        sezioni multiclasse (`self._caster_rows` con più di una riga); il
        percorso a classe singola continua a passare da `_toggle_prepared`,
        invariato.
        """
        c = self.character
        name = spell.get("name", "")
        level = spell.get("level", 0)
        was_prepared = self._is_prepared(name, level)

        if not was_prepared and level > 0:
            cc = next((r[0] for r in self._caster_rows if r[0].class_name == class_name), None)
            class_level = cc.level if cc else c.level
            cls_data = _loader.get_class(class_name) or {}
            sp_ability = cls_data.get("spellcasting_ability", "") or ""
            scores = {
                "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
                "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
            }
            max_prep = _calc_max_prepared_value(class_name, class_level, sp_ability, scores, 0)
            if max_prep is not None and self._prepared_count_for_class(class_name) >= max_prep:
                if self._page:
                    self._page.show_dialog(ft.AlertDialog(
                        title=design.dialog_title("Limite raggiunto"),
                        content=ft.Text(
                            f"Hai già preparato {max_prep} incantesimi da {class_name}, "
                            f"il massimo per il tuo livello in questa classe.\n\n"
                            f"Deprepara un incantesimo di {class_name} per farne spazio.",
                            size=13, color=design.T().text,
                        ),
                        actions=[
                            ft.TextButton(
                                "OK",
                                on_click=lambda e: self._page.pop_dialog()
                                if self._page else None,
                            )
                        ],
                    ))
                return

        if was_prepared:
            character_repo.remove_known_spell(c.id, name, level)
        else:
            comps = spell.get("components", [])
            comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
            if spell.get("material"):
                comp_str += f" ({spell['material']})"
            character_repo.upsert_known_spell(
                character_id=c.id,
                name=name, level=level, is_prepared=True,
                school=spell.get("school", ""),
                casting_time=spell.get("casting_time", ""),
                spell_range=spell.get("range", ""),
                components=comp_str,
                duration=spell.get("duration", ""),
                description=spell.get("description", ""),
                higher_levels=spell.get("higher_levels", "") or "",
                class_list=class_name,
            )

        self._reload_known()
        self._refresh()

    def _open_override_dialog(self) -> None:
        """Dialog per modificare manualmente il limite di preparazione."""
        if not self._page:
            return
        page = self._page
        c = self.character
        # Calcola il valore formula escludendo l'override corrente
        tmp_override = c.max_prepared_spells_override
        c.max_prepared_spells_override = 0
        formula_val  = _calc_max_prepared(c)
        c.max_prepared_spells_override = tmp_override

        formula_desc = (
            f"Formula PHB: {formula_val}"
            if formula_val is not None
            else "Classe senza limite di preparazione"
        )

        f_val = ft.TextField(
            label="Massimo incantesimi preparabili",
            value=str(c.max_prepared_spells_override or ""),
            hint_text="Lascia vuoto o 0 per usare la formula PHB",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=14, color=design.T().text,
                                    font_family=design.Font.MONO),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            bgcolor=design.T().surface,
            autofocus=True,
            border_radius=design.field_style()['border_radius'])

        def save(ev):
            if page is None:
                return
            try:
                val = int(f_val.value or 0)
            except ValueError:
                val = 0
            val = max(0, val)
            character_repo.update_max_prepared_override(c.id, val)
            c.max_prepared_spells_override = val
            page.pop_dialog()
            self._refresh()

        def reset(ev):
            if page is None:
                return
            character_repo.update_max_prepared_override(c.id, 0)
            c.max_prepared_spells_override = 0
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Limite Preparazione"),
            content=ft.Column([
                ft.Text(formula_desc, size=12, color=design.T().text_3, italic=True),
                ft.Container(height=4),
                f_val,
                ft.Text(
                    "Imposta 0 per tornare al calcolo automatico PHB.",
                    size=11, color=design.T().text_3,
                ),
            ], spacing=8),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton("Reset PHB", on_click=reset,
                              style=ft.ButtonStyle(color=design.T().text_3)),
                ft.ElevatedButton(
                    "Salva", on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().magic, color=design.T().on_accent,
                    ),
                ),
            ]),
        ))

    def _open_spell_dialog(self, spell: dict[str, Any]) -> None:
        if not self._page:
            return
        page = self._page
        name   = spell.get("name", "")
        level  = spell.get("level", 0)
        school = spell.get("school", "")
        comps  = spell.get("components", [])
        comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
        if spell.get("material"):
            comp_str += f" ({spell['material']})"

        conc_icon   = "◉ Concentrazione  " if spell.get("concentration") else ""
        ritual_icon = "☽ Rituale"          if spell.get("ritual")        else ""
        level_label = "Trucchetto" if level == 0 else f"{_SLOT_NAMES[level - 1]} livello"
        header_line = f"{level_label}  ·  {school}" if school else level_label

        def _info_row(label: str, value: str) -> ft.Row:
            return ft.Row([
                ft.Text(label, size=11, color=design.T().text_3,
                        weight=ft.FontWeight.BOLD, width=100),
                ft.Text(value, size=12, color=design.T().text, expand=True),
            ], spacing=4)

        rows: list[ft.Control] = [
            ft.Text(header_line, size=11, color=design.T().text_3, italic=True),
            ft.Container(height=4),
        ]
        for label, key in [
            ("Tempo:", "casting_time"), ("Gittata:", "range"),
            ("Durata:", "duration"),
        ]:
            if spell.get(key):
                rows.append(_info_row(label, spell[key]))
        if comp_str:
            rows.append(_info_row("Componenti:", comp_str))
        if conc_icon or ritual_icon:
            rows.append(ft.Text(f"{conc_icon}{ritual_icon}",
                                size=11, color=design.T().warning))
        rows.append(ft.Divider(color=design.T().border))
        rows.append(ft.Text(
            spell.get("description", "Nessuna descrizione."),
            size=13, color=design.T().text, selectable=True,
        ))
        if spell.get("higher_levels"):
            rows += [
                ft.Container(height=6),
                ft.Text("Ai livelli superiori:", size=11, color=design.T().text_3,
                        weight=ft.FontWeight.BOLD),
                ft.Text(spell["higher_levels"], size=12, color=design.T().text_2),
            ]

        page.show_dialog(ft.AlertDialog(
            title=ft.Row([
                # Chip di livello via primitiva condivisa (`design.chip()`) —
                # distinzione trucchetto/incantesimo di livello preservata
                # (tone="magic" per i trucchetti, "primary" per i restanti,
                # esattamente come prima con gli hex diretti).
                design.chip(f"Lv{level}" if level > 0 else "0",
                            tone="magic" if level == 0 else "primary", filled=True),
                ft.Container(width=8),
                ft.Text(name, size=14, weight=ft.FontWeight.BOLD,
                        color=design.T().text, expand=True),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            content=ft.Column(rows, spacing=6, scroll=ft.ScrollMode.AUTO),
            actions=wrap_dialog_actions([
                ft.TextButton("Chiudi",
                              on_click=lambda e: page.pop_dialog() if page else None),
                *([ft.ElevatedButton(
                    "Attiva concentrazione", icon=ft.Icons.CENTER_FOCUS_STRONG,
                    on_click=lambda e, n=name: self._activate_concentration(n),
                    style=ft.ButtonStyle(bgcolor=design.T().magic,
                                         color=design.T().on_accent),
                )] if spell.get("concentration") else []),
            ]),
        ))

    def _activate_concentration(self, spell_name: str) -> None:
        """
        Attiva la concentrazione su questo incantesimo.

        PHB p.203: "Un incantatore non può concentrarsi su due incantesimi alla
        volta" — se una concentrazione è già attiva, l'app **avverte** che verrà
        interrotta invece di sostituirla in silenzio.
        """
        page = self._page
        if page is None:
            return
        c = self.character
        current = (c.concentrating_spell or "").strip()

        def _do(_e=None):
            character_repo.set_concentration(c.id, spell_name)
            c.concentrating_spell = spell_name
            page.pop_dialog()
            self._refresh()

        if not current:
            _do()
            return

        if current == spell_name:
            page.pop_dialog()
            return

        page.pop_dialog()   # chiude il dettaglio dell'incantesimo
        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Sostituire la concentrazione?"),
            content=ft.Text(
                f"Ti stai già concentrando su «{current}»: attivare "
                f"«{spell_name}» la interrompe.\n"
                "PHB p.203 — un incantatore non può concentrarsi su due "
                "incantesimi alla volta.",
                size=13, color=design.T().text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Sostituisci", icon=ft.Icons.CENTER_FOCUS_STRONG, on_click=_do,
                    style=ft.ButtonStyle(bgcolor=design.T().magic,
                                         color=design.T().on_accent),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        c = self.character
        controls: list[ft.Control] = []

        # Momento tipografico "hero" della schermata (Arcane Ledger, audit
        # anti-AI-slop 2026-08-18) — stessa struttura di dice_view.py
        # (l'altro forte candidato al registro indaco/magic): icona in
        # cerchietto tonalità "magic" + `hero_title()`. SpellsView è una
        # sezione di primo livello nella sidebar (vedi ui/app.py, come
        # DiceView), senza alcun titolo di pagina preesistente altrove —
        # nessuna duplicazione da rimuovere.
        controls.append(ft.Container(
            content=ft.Row(
                [
                    design.icon_badge(ft.Icons.AUTO_AWESOME, tone="magic"),
                    ft.Container(width=design.Space.MD),
                    design.hero_title(
                        "Incantesimi",
                        c.class_name or "",
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
            padding=ft.Padding.only(bottom=16),
        ))

        # Incantesimi Razziali (Drow/Tiefling — task #15, 2026-07-16) —
        # sezione SEMPRE visibile quando la razza/sottorazza li concede,
        # indipendentemente da spellcasting_ability: sono incantesimi
        # innati legati al tratto di razza (CD su Carisma fisso), non alla
        # classe del personaggio — un Barbaro Drow li possiede comunque.
        if self._racial_innate:
            controls += [
                section_header("Incantesimi Razziali"),
                self._section_racial_spells(c),
            ]

        # Multiclasse (2026-08-12, bug report Davide: "la sezione
        # incantesimi tiene conto solo della classe principale") — CD/bonus
        # attacco si calcolano SEPARATAMENTE per ciascuna classe
        # incantatrice (PHB IT p.165), non un unico header sulla sola
        # primaria. Attivo solo con più di una classe con lista propria
        # (self._caster_rows); per una sola classe (compresi Mistificatore
        # Arcano/Cavaliere Mistico, che vivono fuori da _caster_rows)
        # resta l'header globale di sempre, invariato.
        # Calcolato qui (prima serviva solo più sotto) per poter affiancare
        # l'header CD/bonus attacco agli slot rimasti nel percorso a classe
        # singola — vedi commento su `paired_slots` poco sotto. Pura
        # anticipazione di un calcolo puro (list comprehension su
        # `self._slots`, nessun effetto collaterale): l'insieme risultante è
        # identico a quello usato più sotto prima di questo cambiamento.
        active_slots = [s for s in self._slots if s.total > 0]
        paired_slots = False

        if len(self._caster_rows) > 1:
            controls.append(section_header("Magia"))
            for cc, _spells in self._caster_rows:
                _cls_data = _loader.get_class(cc.class_name) or {}
                _sp_ability = _cls_data.get("spellcasting_ability", "") or ""
                if _sp_ability:
                    controls.append(self._section_magic_header_mc(cc.class_name, _sp_ability))
            # In multiclasse gli slot sono un unico pool condiviso fra le
            # classi (self._slots non è per-classe) — non appartengono a UNA
            # sola classe/header, quindi restano nella loro sezione dedicata
            # più sotto invece di affiancarsi a uno degli header per classe.
        elif c.spellcasting_ability:
            controls.append(section_header("Magia"))
            if active_slots:
                # Audit anti-AI-slop (2026-08-18): CD/bonus attacco e slot
                # rimasti sono la coppia di dati più consultata insieme
                # durante il gioco vero e proprio — stesso principio di
                # HP+statistiche in combattimento_tab.py
                # (`design.asymmetric_row`). Solo nel percorso a classe
                # singola (vedi sopra per il perché non in multiclasse).
                controls.append(design.asymmetric_row(
                    self._section_magic_header(c),
                    self._section_slots_summary(active_slots),
                    ratio=(7, 5),
                ))
                paired_slots = True
            else:
                controls.append(self._section_magic_header(c))

        # Incantesimi Bonus (2026-07-16, richiesta Davide: "Permettere a
        # tutte le classi di aggiungere un incantesimo... il player può
        # scegliere tra tutti gli incantesimi e aggiungerli a quelli
        # conosciuti o preparati") — sezione SEMPRE presente, anche per
        # classi senza spellcasting_ability (es. un Guerriero che riceve un
        # incantesimo concesso dal master). Distinta dal meccanismo "extra"
        # già esistente (Segreti Magici/Mistificatore) tramite il flag
        # `is_bonus` dedicato, per non confondersi con un incantesimo scelto
        # dalla stessa lista della classe del personaggio.
        bonus_spells = self._bonus_known()
        controls += [section_header("Incantesimi Bonus"), self._section_bonus_header()]
        if bonus_spells:
            bonus_by_level: dict[int, list[KnownSpell]] = {}
            for ks in bonus_spells:
                bonus_by_level.setdefault(ks.spell_level, []).append(ks)
            for lv in sorted(bonus_by_level.keys()):
                lv_label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                controls += [
                    section_header(lv_label),
                    self._section_bonus_spell_list(bonus_by_level[lv]),
                ]

        if active_slots and not paired_slots:
            controls += [
                section_header("Slot Incantesimo"),
                self._section_slots_summary(active_slots),
            ]

        # Mistificatore Arcano (Ladro)/Cavaliere Mistico (Guerriero): queste
        # 2 sottoclassi concedono casting "preso in prestito dal Mago" senza
        # una propria lista di classe (_class_spells resta sempre vuota per
        # Ladro/Guerriero) — i loro incantesimi vivono nella sezione
        # "Incantesimi Extra" più sotto (stesso meccanismo già usato per i
        # Segreti Magici del Bardo). Il placeholder "Nessun incantesimo"
        # sarebbe fuorviante per un personaggio che invece ha regolarmente
        # accesso a incantesimi da mago — soppresso quando
        # spellcasting_ability è valorizzata (accade solo per queste 2
        # sottoclassi quando _class_spells è vuota, dato che ogni classe con
        # una propria lista ha sempre spellcasting_ability + _class_spells
        # non vuota insieme). Aggiunto 2026-07-15, fix Mistificatore Arcano/
        # Cavaliere Mistico. Escluso anche se il personaggio ha già almeno un
        # incantesimo bonus (2026-07-16) — altrimenti il messaggio "nessun
        # incantesimo" sarebbe contraddetto dalla sezione appena mostrata
        # sopra.
        if not self._class_spells and not c.spellcasting_ability and not bonus_spells:
            controls.append(design.empty_state(
                ft.Icons.AUTO_AWESOME,
                f"Nessun incantesimo di classe per {c.class_name}",
                "Puoi comunque aggiungere un Incantesimo Bonus qui sopra.",
            ))
        elif self._class_spells:
            # Gli incantesimi "sempre pronti" da Dominio/Giuramento/Circolo
            # (task #26) hanno una sezione dedicata più sotto e vanno esclusi
            # da qui: altrimenti comparirebbero anche come voci normali
            # togglabili (molti, es. "Cura Ferite" per un Chierico, sono
            # anche parte della lista standard della classe).
            always_prep_names = {ks.name for ks in self._known.values() if ks.always_prepared}

            if len(self._caster_rows) > 1:
                # Multiclasse (2026-08-12, bug report Davide: "la sezione
                # incantesimi tiene conto solo della classe principale") —
                # una sotto-sezione "Incantesimi" per CIASCUNA classe con
                # lista propria, ciascuna col proprio banner di
                # preparazione/limite e la propria lista, invece
                # dell'unica sezione sulla sola primaria del percorso a
                # classe singola sotto (che qui viene saltato per intero).
                controls.append(section_header("Incantesimi"))
                for cc, cls_spells in self._caster_rows:
                    controls += self._build_caster_class_section(cc, cls_spells, always_prep_names)
            else:
                controls += [
                    section_header("Incantesimi"),
                    self._section_prep_banner(c),
                ]
                key = (c.class_name or "").strip().lower()
                if key in _KNOW_CLASSES:
                    # Bug fix 2026-07-16 (Davide): Bardo/Ranger/Stregone/Warlock
                    # NON preparano ogni giorno dall'intera lista di classe come
                    # Chierico/Druido/Mago — "conoscono" un set fisso di
                    # incantesimi, scelto alla creazione e modificato SOLO tramite
                    # i meccanismi di level-up già esistenti (SPELL_LEARN,
                    # SPELL_SWAP, CANTRIP_LEARN). Mostrare qui l'intero catalogo
                    # con un toggle libero (come per i preparatori puri) permette
                    # di "imparare" all'istante un incantesimo qualsiasi,
                    # bypassando quei meccanismi — incoerente con come sono già
                    # gestiti Segreti Magici/Mistificatore Arcano/Cavaliere
                    # Mistico (sempre in sola lettura). Qui mostriamo quindi SOLO
                    # gli incantesimi realmente in `known_spells` che appartengono
                    # alla lista della classe, in sola lettura (stesso stile della
                    # sezione "Incantesimi Extra"): per imparane di nuovi si passa
                    # dal level-up (o, per aggiunte eccezionali/case, da
                    # "Incantesimi Bonus" qui sopra).
                    class_spell_names_set = {sp.get("name", "") for sp in self._class_spells}
                    known_own_list = [
                        ks for ks in self._known.values()
                        if ks.name in class_spell_names_set
                        and not ks.always_prepared and not ks.is_bonus
                    ]
                    by_level_known: dict[int, list[KnownSpell]] = {}
                    for ks in known_own_list:
                        by_level_known.setdefault(ks.spell_level, []).append(ks)

                    if by_level_known:
                        for lv in sorted(by_level_known.keys()):
                            label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                            controls += [
                                section_header(label),
                                self._section_known_class_spell_list(by_level_known[lv]),
                            ]
                    else:
                        # Stato vuoto uniforme (`design.empty_state()`),
                        # continuando la stessa migrazione già avviata più
                        # sopra per "Nessun incantesimo di classe" — stesso
                        # tono neutro (nessun accento: non c'è nulla da
                        # segnalare, coerente con l'altro stato vuoto di
                        # questa vista).
                        controls.append(design.empty_state(
                            ft.Icons.AUTO_AWESOME,
                            "Nessun incantesimo ancora conosciuto",
                            "Si impara alla creazione del personaggio o salendo di livello.",
                        ))
                else:
                    max_prep_level = _max_preparable_spell_level(self._slots)
                    by_level: dict[int, list[dict]] = {}
                    for sp in self._class_spells:
                        if sp.get("name") in always_prep_names:
                            continue
                        lvl = sp.get("level", 0)
                        # PHB: un incantesimo di livello > 0 è preparabile solo
                        # se il personaggio possiede almeno uno slot di quel
                        # livello — eccezione per un incantesimo già preparato
                        # in precedenza (es. dopo un level-down, o un vecchio
                        # stato salvato prima di questo fix), che resta visibile
                        # per poterlo comunque togliere dal giocatore.
                        if (
                            lvl > 0
                            and lvl > max_prep_level
                            and not self._is_prepared(sp.get("name", ""), lvl)
                        ):
                            continue
                        by_level.setdefault(lvl, []).append(sp)
                    for lv in sorted(by_level.keys()):
                        label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                        controls += [
                            section_header(label),
                            self._section_spell_list(by_level[lv]),
                        ]

        # Incantesimi "sempre pronti" da privilegio di Dominio/Giuramento/
        # Circolo della Terra (task #26, 2026-07-16) — sezione dedicata,
        # badge 🔒, non disattivabile dal giocatore (si aggiorna solo
        # automaticamente in base a sottoclasse/terreno/livello, vedi
        # character_repo.sync_bonus_domain_spells()).
        always_prepared_known = [ks for ks in self._known.values() if ks.always_prepared]
        if always_prepared_known:
            ap_by_level: dict[int, list[KnownSpell]] = {}
            for ks in always_prepared_known:
                ap_by_level.setdefault(ks.spell_level, []).append(ks)
            controls.append(section_header("Incantesimi Sempre Pronti"))
            controls.append(ft.Text(
                "Concessi dal tuo Dominio/Giuramento/Circolo — non contano nel "
                "limite di preparazione e sono sempre disponibili.",
                size=11, color=design.T().text_3, italic=True,
            ))
            for lv in sorted(ap_by_level.keys()):
                lv_label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                controls += [
                    section_header(lv_label),
                    self._section_always_prepared_list(ap_by_level[lv]),
                ]

        # Incantesimi "extra" — conosciuti dal DB ma non nella lista JSON di
        # NESSUNA classe posseduta (Segreti Magici, Mistificatore, Eldritch
        # Knight, etc.). Multiclasse (2026-08-12, bug report Davide):
        # l'insieme è l'UNIONE delle liste di TUTTE le classi con lista
        # propria (self._caster_rows), non solo quella della primaria —
        # prima di questo fix gli incantesimi di una classe secondaria
        # (es. il libro di un Mago preso in multiclasse) finivano
        # erroneamente qui, etichettati come "Incantesimi Extra" invece
        # che nella loro sezione "Incantesimi" dedicata. Per una sola
        # classe l'unione coincide con self._class_spells, nessun cambio
        # di comportamento.
        class_spell_names: set[str] = {
            sp.get("name", "") for _, spells in self._caster_rows for sp in spells
        }
        extra_known: list[KnownSpell] = [
            ks for ks in self._known.values()
            if ks.name not in class_spell_names and ks.is_prepared
            and not ks.is_bonus and not ks.always_prepared
        ]
        if extra_known:
            extra_by_level: dict[int, list[KnownSpell]] = {}
            for ks in extra_known:
                extra_by_level.setdefault(ks.spell_level, []).append(ks)

            if (c.class_name or "").lower() == "bardo":
                section_label = "Segreti Magici"
            elif (c.subclass or "") in ("Mistificatore Arcano", "Cavaliere Mistico"):
                section_label = "Incantesimi da Mago"
            else:
                section_label = "Incantesimi Extra"
            controls.append(section_header(section_label))
            for lv in sorted(extra_by_level.keys()):
                lv_label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                controls += [
                    section_header(lv_label),
                    self._section_extra_spell_list(extra_by_level[lv]),
                ]

        self.controls.clear()
        for ctrl in controls:
            self.controls.append(ctrl)

    def _build_caster_class_section(
        self, cc: Any, cls_spells: list[dict[str, Any]], always_prep_names: set[str],
    ) -> list[ft.Control]:
        """
        Sotto-sezione "Incantesimi" di UNA classe del personaggio, usata
        SOLO dal percorso multiclasse (`self._caster_rows` con più di una
        riga — 2026-08-12, bug report Davide: "la sezione incantesimi
        tiene conto solo della classe principale"). Stessa logica del
        percorso a classe singola in `_build()` (preparatori full/half
        contro classi "know"), ma su `cc.class_name`/`cc.level` (il
        livello DI QUESTA CLASSE, mai il totale — PHB IT p.165) invece di
        `c.class_name`/`c.level`, e coi metodi `_mc` che filtrano/salvano
        per classe (`class_list`).
        """
        controls: list[ft.Control] = [
            ft.Text(f"{cc.class_name}  ·  Lv.{cc.level}", size=13,
                    weight=ft.FontWeight.BOLD, color=design.T().magic),
        ]
        cls_data = _loader.get_class(cc.class_name) or {}
        sp_ability = cls_data.get("spellcasting_ability", "") or ""
        controls.append(self._section_prep_banner_mc(cc.class_name, cc.level, sp_ability))

        key = (cc.class_name or "").strip().lower()
        if key in _KNOW_CLASSES:
            class_spell_names_set = {sp.get("name", "") for sp in cls_spells}
            known_own_list = [
                ks for ks in self._known.values()
                if ks.name in class_spell_names_set
                and (ks.class_list or "").strip().lower() == key
                and not ks.always_prepared and not ks.is_bonus
            ]
            by_level_known: dict[int, list[KnownSpell]] = {}
            for ks in known_own_list:
                by_level_known.setdefault(ks.spell_level, []).append(ks)

            if by_level_known:
                for lv in sorted(by_level_known.keys()):
                    label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                    controls += [
                        section_header(label),
                        self._section_known_class_spell_list(by_level_known[lv]),
                    ]
            else:
                # Stessa migrazione a `design.empty_state()` della variante
                # a classe singola sopra in `_build()`.
                controls.append(design.empty_state(
                    ft.Icons.AUTO_AWESOME,
                    "Nessun incantesimo ancora conosciuto",
                    "Si impara alla creazione del personaggio o salendo di livello.",
                ))
        else:
            max_prep_level = _max_preparable_spell_level(self._slots)
            by_level: dict[int, list[dict]] = {}
            for sp in cls_spells:
                if sp.get("name") in always_prep_names:
                    continue
                lvl = sp.get("level", 0)
                if (
                    lvl > 0
                    and lvl > max_prep_level
                    and not self._is_prepared(sp.get("name", ""), lvl)
                ):
                    continue
                by_level.setdefault(lvl, []).append(sp)
            for lv in sorted(by_level.keys()):
                label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                controls += [
                    section_header(label),
                    self._section_spell_list_mc(by_level[lv], cc.class_name, cc.level),
                ]

        controls.append(ft.Container(height=4))
        return controls

    # ------------------------------------------------------------------
    # Sezioni UI
    # ------------------------------------------------------------------

    def _section_magic_header(self, c: Character) -> ft.Container:
        _KEY_TO_NAME = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
        _KEY_TO_ABBR = dict(zip(ABILITY_KEYS, ABILITY_ABBR))
        _KEY_TO_SCORE = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }
        pb      = char_prof_bonus(c)
        sp_key  = c.spellcasting_ability or ""
        sp_mod  = get_modifier(_KEY_TO_SCORE.get(sp_key, 10))
        # Formula PHB "8 + competenza + mod" — riusa core/character_stats.py
        # invece di ricalcolarla qui (era duplicata anche in
        # combattimento_tab.py: stessa formula in due posti, pulizia
        # 2026-08-07). `_section_magic_header` è chiamata SOLO se
        # `c.spellcasting_ability` è valorizzato (vedi `_build()`), quindi
        # `spell_save_dc()` non ritorna mai `None` qui.
        save_dc = cs.spell_save_dc(c)
        atk_bon = pb + sp_mod
        atk_str = f"+{atk_bon}" if atk_bon >= 0 else str(atk_bon)
        sp_name = _KEY_TO_NAME.get(sp_key, sp_key)
        sp_abbr = _KEY_TO_ABBR.get(sp_key, sp_key.upper())

        def _box(label: str, value: str, on_click=None, tooltip: str | None = None,
                 rollable: bool = False) -> ft.Container:
            value_ctl: ft.Control = ft.Text(
                value, size=18, color=design.T().magic,
                weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
                font_family=design.Font.MONO)
            if rollable:
                value_ctl = ft.Row(
                    [value_ctl,
                     ft.Icon(ft.Icons.CASINO_OUTLINED, size=12, color=design.T().magic)],
                    spacing=4, tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            return ft.Container(
                content=ft.Column([
                    ft.Text(label, size=9, color=design.T().text_3,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER),
                    value_ctl,
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=design.T().surface_alt,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=design.Radius.MD, expand=True,
                on_click=on_click, ink=bool(on_click), tooltip=tooltip,
            )

        atk_spec = cs.spell_attack_roll(c)

        return ft.Container(
            content=ft.Row([
                _box(f"CARATTERISTICA\n({sp_abbr})", sp_name),
                _box("CD TIRO SALV.", str(save_dc)),
                _box("BONUS ATTACCO", atk_str,
                     on_click=(lambda e: show_roll(
                         self._page, cs.spell_attack_roll(self.character))
                     ) if atk_spec else None,
                     tooltip=(f"Tira l'attacco con incantesimo ({atk_spec.note})"
                              if atk_spec else None),
                     rollable=bool(atk_spec)),
            ], spacing=8),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_magic_header_mc(self, class_name: str, spellcasting_ability: str) -> ft.Container:
        """
        Variante multiclasse di `_section_magic_header()` (2026-08-12) —
        stessa resa visiva (caratteristica/CD/bonus attacco), ma calcolata
        con la caratteristica da incantatore DI QUESTA CLASSE tramite
        `_ClassAbilityView` invece di `c.spellcasting_ability` (quello
        della primaria) — PHB IT p.165: CD e bonus attacco si calcolano
        separatamente per ciascuna classe incantatrice. Preceduta da
        un'etichetta col nome della classe. Usata SOLO quando il
        personaggio ha più di una classe con lista incantesimi propria
        (`self._caster_rows`); per una sola classe resta
        `_section_magic_header()`, invariata.
        """
        c = self.character
        view = _ClassAbilityView(c, spellcasting_ability)
        _KEY_TO_NAME = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
        _KEY_TO_ABBR = dict(zip(ABILITY_KEYS, ABILITY_ABBR))
        _KEY_TO_SCORE = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }
        pb = char_prof_bonus(c)
        sp_mod = get_modifier(_KEY_TO_SCORE.get(spellcasting_ability, 10))
        save_dc = cs.spell_save_dc(view)
        atk_bon = pb + sp_mod
        atk_str = f"+{atk_bon}" if atk_bon >= 0 else str(atk_bon)
        sp_name = _KEY_TO_NAME.get(spellcasting_ability, spellcasting_ability)
        sp_abbr = _KEY_TO_ABBR.get(spellcasting_ability, spellcasting_ability.upper())

        def _box(label: str, value: str, on_click=None, tooltip: str | None = None,
                 rollable: bool = False) -> ft.Container:
            value_ctl: ft.Control = ft.Text(
                value, size=18, color=design.T().magic,
                weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
                font_family=design.Font.MONO)
            if rollable:
                value_ctl = ft.Row(
                    [value_ctl,
                     ft.Icon(ft.Icons.CASINO_OUTLINED, size=12, color=design.T().magic)],
                    spacing=4, tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            return ft.Container(
                content=ft.Column([
                    ft.Text(label, size=9, color=design.T().text_3,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER),
                    value_ctl,
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=design.T().surface_alt,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=design.Radius.MD, expand=True,
                on_click=on_click, ink=bool(on_click), tooltip=tooltip,
            )

        atk_spec = cs.spell_attack_roll(view)

        return ft.Container(
            content=ft.Column([
                ft.Text(class_name, size=12, weight=ft.FontWeight.BOLD, color=design.T().magic),
                ft.Row([
                    _box(f"CARATTERISTICA\n({sp_abbr})", sp_name),
                    _box("CD TIRO SALV.", str(save_dc)),
                    _box("BONUS ATTACCO", atk_str,
                         on_click=(lambda e: show_roll(self._page, cs.spell_attack_roll(view)))
                         if atk_spec else None,
                         tooltip=(f"Tira l'attacco con incantesimo ({atk_spec.note})"
                                  if atk_spec else None),
                         rollable=bool(atk_spec)),
                ], spacing=8),
            ], spacing=6),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_prep_banner(self, c: Character) -> ft.Container:
        """
        Banner "X / Y preparati ✎" — mostra il limite e permette l'override.
        I trucchetti non contano nel limite (PHB).
        """
        max_prep = _calc_max_prepared(c)
        count    = self._prepared_count()
        expected = 0  # valorizzato sotto solo per le classi "know" (max_prep is None)

        if max_prep is None:
            # Classi "know": nessun limite RIGIDO (il toggle resta libero,
            # coerente con la stessa scelta già accettata per i trucchetti —
            # vedi CLAUDE.md), ma ora mostriamo comunque il totale atteso
            # per livello (spells_known_at_1 + spell_learn_delta cumulativo,
            # la stessa tabella usata dal level-up) così il giocatore può
            # verificare a colpo d'occhio se ha selezionato più incantesimi
            # di quanti dovrebbe conoscere al suo livello.
            expected = _expected_known_spell_count(c)
            over     = expected > 0 and count > expected
            label_text = f"{count} / {expected} incantesimi conosciuti"
            color = design.T().primary if over else design.T().text_3
            ratio = min(1.0, count / expected) if expected > 0 else 0.0
        else:
            label_text = f"{count} / {max_prep} preparati"
            at_limit   = count >= max_prep
            color      = design.T().primary if at_limit else design.T().magic
            ratio      = min(1.0, count / max_prep) if max_prep > 0 else 0.0

        if max_prep is not None:
            max_lv = _max_preparable_spell_level(self._slots)
            lvl_note = f"Lv. max preparabile: {max_lv}°" if max_lv > 0 else "Nessuno slot incantesimo disponibile"
            note = f"I trucchetti (0°) non contano nel limite  ·  {lvl_note}  ·  ✎ per modificare manuale"
        elif expected > 0 and count > expected:
            note = f"Hai {count - expected} incantesim{'o' if count - expected == 1 else 'i'} in più del previsto per il tuo livello — controlla se è corretto (Segreti Magici e simili contano a parte)"
        else:
            note = "Nuovi incantesimi si imparano alla creazione o al level-up"

        rows: list[ft.Control] = [
            ft.Row([
                ft.Text(
                    label_text, size=18, color=color,
                    weight=ft.FontWeight.BOLD, font_family=design.Font.MONO,
                    expand=True,
                ),
                ft.TextButton(
                    "✎",
                    on_click=lambda e: self._open_override_dialog(),
                    style=ft.ButtonStyle(color=design.T().text_3),
                    tooltip="Modifica limite manualmente",
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
        ]
        if max_prep is not None or expected > 0:
            rows.append(ft.Row([ft.ProgressBar(
                value=ratio,
                color=color,
                bgcolor=design.T().surface_alt,
                height=8, border_radius=4, expand=True,
            )]))
        rows.append(ft.Text(note, size=10, color=design.T().text_3, italic=True))

        return ft.Container(
            content=ft.Column(rows, spacing=6),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, color)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_prep_banner_mc(self, class_name: str, class_level: int, spellcasting_ability: str) -> ft.Container:
        """
        Variante multiclasse di `_section_prep_banner()` (2026-08-12) —
        stessa resa visiva, ma limite/conteggio calcolati SOLO sugli
        incantesimi DI QUESTA CLASSE (`class_list`), col SUO livello e la
        SUA caratteristica (PHB IT p.165) — mai quelli globali usati dal
        percorso a classe singola. Nessun pulsante "✎" di override manuale
        qui: quel campo resta un unico valore per personaggio (non per
        classe), applicarlo separatamente a due classi diverse ne
        raddoppierebbe l'effetto in modo ambiguo — resta disponibile solo
        dal percorso a classe singola.
        """
        scores = {
            "str": self.character.str_score, "dex": self.character.dex_score,
            "con": self.character.con_score, "int": self.character.int_score,
            "wis": self.character.wis_score, "cha": self.character.cha_score,
        }
        max_prep = _calc_max_prepared_value(class_name, class_level, spellcasting_ability, scores, 0)
        count = self._prepared_count_for_class(class_name)

        if max_prep is None:
            expected = _expected_known_spell_count_for(class_name, class_level)
            over = expected > 0 and count > expected
            label_text = f"{count} / {expected} incantesimi conosciuti"
            color = design.T().primary if over else design.T().text_3
            ratio = min(1.0, count / expected) if expected > 0 else 0.0
            if over:
                note = f"Hai {count - expected} incantesim{'o' if count - expected == 1 else 'i'} in più del previsto per il tuo livello in questa classe"
            else:
                note = "Nuovi incantesimi si imparano al level-up di questa classe"
        else:
            label_text = f"{count} / {max_prep} preparati"
            at_limit = count >= max_prep
            color = design.T().primary if at_limit else design.T().magic
            ratio = min(1.0, count / max_prep) if max_prep > 0 else 0.0
            max_lv = _max_preparable_spell_level(self._slots)
            lvl_note = f"Lv. max preparabile: {max_lv}°" if max_lv > 0 else "Nessuno slot incantesimo disponibile"
            note = f"I trucchetti (0°) non contano nel limite  ·  {lvl_note}"

        rows: list[ft.Control] = [
            ft.Text(label_text, size=16, color=color, weight=ft.FontWeight.BOLD,
                    font_family=design.Font.MONO),
        ]
        if max_prep is not None or (max_prep is None and count > 0):
            rows.append(ft.Row([ft.ProgressBar(
                value=ratio, color=color, bgcolor=design.T().surface_alt,
                height=8, border_radius=4, expand=True,
            )]))
        rows.append(ft.Text(note, size=10, color=design.T().text_3, italic=True))

        return ft.Container(
            content=ft.Column(rows, spacing=6),
            bgcolor=design.T().surface,
            padding=12,
            border=ft.Border.only(left=ft.BorderSide(3, color)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_slots_summary(self, slots: list[SpellSlot]) -> ft.Container:
        # Slot come pallini pieni/anello (Fase E.4 del restyle): prima erano i
        # caratteri "●"/"○" di un font di testo — dimensione e allineamento
        # dipendevano dal font, e in tema scuro il vuoto sparisce. Ora sono
        # forme vere, dalla primitiva condivisa `design.slot_dots()`.
        p = design.T()
        rows: list[ft.Control] = []
        for slot in sorted(slots, key=lambda s: s.slot_level):
            avail = slot.total - slot.used
            rows.append(ft.Row(cast(list[ft.Control], [
                ft.Container(
                    content=ft.Text(_SLOT_NAMES[slot.slot_level - 1],
                                    size=design.Size.LABEL,
                                    color=p.text_2,
                                    weight=ft.FontWeight.BOLD,
                                    font_family=design.Font.MONO),
                    bgcolor=p.surface_alt,
                    border_radius=design.Radius.SM,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    width=34,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(width=design.Space.SM),
                design.slot_dots(slot.total, slot.used),
                ft.Container(expand=True),
                ft.Text(f"{avail}/{slot.total}", size=design.Size.LABEL,
                        color=p.text_3, font_family=design.Font.MONO),
            ]), vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0))
        rows.append(ft.Text(
            "Usa / recupera slot nel tab Combattimento.",
            size=design.Size.LABEL, color=p.text_3, italic=True,
            font_family=design.Font.BODY,
        ))
        # Audit anti-AI-slop: unico elemento "hero" della vista Incantesimi —
        # gli slot rimasti sono il dato più consultato durante il gioco vero e
        # proprio, stesso ruolo degli HP in combattimento_tab.py. Elevazione
        # maggiorata (level=2) + padding=XL invece del default, MAI un colore
        # diverso (accent=magic resta lo stesso delle altre sezioni qui sopra).
        return ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor=design.T().surface,
            padding=design.Space.XL,
            border=ft.Border.only(left=ft.BorderSide(4, design.T().magic)),
            shadow=design.layered_shadow(2, design.T().magic),
            border_radius=design.Radius.MD,
        )

    def _section_spell_list(self, spells: list[dict]) -> ft.Container:
        """Lista incantesimi con toggle preparazione e link al dettaglio."""
        max_prep  = _calc_max_prepared(self.character)
        count     = self._prepared_count()
        at_limit  = (max_prep is not None) and (count >= max_prep)

        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.get("name", ""))
        for i, sp in enumerate(sorted_spells):
            name     = sp.get("name", "")
            level    = sp.get("level", 0)
            prepared = self._is_prepared(name, level)
            conc     = "◉" if sp.get("concentration") else ""
            ritual   = "☽" if sp.get("ritual") else ""
            tags     = f"  {conc}{ritual}".rstrip() if (conc or ritual) else ""

            # Blocca il toggle solo per incantesimi non preparati di lv ≥ 1 quando al limite
            blocked = at_limit and not prepared and level > 0

            toggle_icon  = "◉" if prepared else ("✕" if blocked else "○")
            toggle_color = (
                design.T().primary if prepared
                else (design.T().border if blocked else design.T().text_3)
            )

            row = ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(toggle_icon, size=22, color=toggle_color),
                        on_click=(lambda e, s=sp: self._toggle_prepared(s))
                        if not blocked else None,
                        tooltip=(
                            "Rimuovi dalla preparazione" if prepared
                            else ("Limite raggiunto" if blocked else "Prepara")
                        ),
                        border_radius=14,
                        ink=not blocked,
                        padding=ft.Padding.all(2),
                        width=32,
                    ),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                name, size=13, expand=True,
                                color=(
                                    design.T().text if prepared
                                    else (design.T().text_3 if blocked
                                          else design.T().text_2)
                                ),
                                weight=(
                                    ft.FontWeight.W_600 if prepared
                                    else ft.FontWeight.NORMAL
                                ),
                            ),
                            ft.Text(tags, size=11, color=design.T().warning)
                            if tags else ft.Container(width=0),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=design.T().text_3),
                        ], spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=lambda e, s=sp: self._open_spell_dialog(s),
                        expand=True, ink=True, border_radius=design.Radius.SM,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                        tooltip="Dettagli",
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, design.T().border)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            )
            rows.append(row)

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            # Bordo "magic" (non "primary"): il catalogo di classe è
            # contenuto arcano "core" della schermata — il toggle "◉"
            # dentro ogni riga resta invece "primary" (stato "preparato",
            # distinzione di stato invariata, audit anti-AI-slop 2026-08-18).
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_spell_list_mc(self, spells: list[dict], class_name: str, class_level: int) -> ft.Container:
        """
        Variante multiclasse di `_section_spell_list()` (2026-08-12) —
        stesso toggle di preparazione, ma limite/conteggio SOLO per questa
        classe e salvataggio via `_toggle_prepared_mc` (che scrive
        `class_list=class_name`, mai `self.character.class_name`). Usata
        SOLO quando il personaggio ha più di una classe con lista
        incantesimi propria; per una sola classe resta `_section_spell_list`,
        invariata.
        """
        c = self.character
        cls_data = _loader.get_class(class_name) or {}
        sp_ability = cls_data.get("spellcasting_ability", "") or ""
        scores = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }
        max_prep = _calc_max_prepared_value(class_name, class_level, sp_ability, scores, 0)
        count = self._prepared_count_for_class(class_name)
        at_limit = (max_prep is not None) and (count >= max_prep)

        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.get("name", ""))
        for i, sp in enumerate(sorted_spells):
            name     = sp.get("name", "")
            level    = sp.get("level", 0)
            prepared = self._is_prepared(name, level)
            conc     = "◉" if sp.get("concentration") else ""
            ritual   = "☽" if sp.get("ritual") else ""
            tags     = f"  {conc}{ritual}".rstrip() if (conc or ritual) else ""

            blocked = at_limit and not prepared and level > 0

            toggle_icon  = "◉" if prepared else ("✕" if blocked else "○")
            toggle_color = (
                design.T().primary if prepared
                else (design.T().border if blocked else design.T().text_3)
            )

            row = ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(toggle_icon, size=22, color=toggle_color),
                        on_click=(lambda e, s=sp, cn=class_name: self._toggle_prepared_mc(s, cn))
                        if not blocked else None,
                        tooltip=(
                            "Rimuovi dalla preparazione" if prepared
                            else ("Limite raggiunto" if blocked else "Prepara")
                        ),
                        border_radius=14,
                        ink=not blocked,
                        padding=ft.Padding.all(2),
                        width=32,
                    ),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                name, size=13, expand=True,
                                color=(
                                    design.T().text if prepared
                                    else (design.T().text_3 if blocked
                                          else design.T().text_2)
                                ),
                                weight=(
                                    ft.FontWeight.W_600 if prepared
                                    else ft.FontWeight.NORMAL
                                ),
                            ),
                            ft.Text(tags, size=11, color=design.T().warning)
                            if tags else ft.Container(width=0),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=design.T().text_3),
                        ], spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=lambda e, s=sp: self._open_spell_dialog(s),
                        expand=True, ink=True, border_radius=design.Radius.SM,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                        tooltip="Dettagli",
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, design.T().border)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            )
            rows.append(row)

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            # Bordo "magic" (non "primary"): il catalogo di classe è
            # contenuto arcano "core" della schermata — il toggle "◉"
            # dentro ogni riga resta invece "primary" (stato "preparato",
            # distinzione di stato invariata, audit anti-AI-slop 2026-08-18).
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_known_class_spell_list(self, spells: list[KnownSpell]) -> ft.Container:
        """
        Lista degli incantesimi REALMENTE conosciuti (dalla propria lista di
        classe) per le classi "know" (Bardo/Ranger/Stregone/Warlock — task
        bug fix 2026-07-16). Sola lettura, stesso principio di
        `_section_extra_spell_list()`/`_section_always_prepared_list()`:
        nessun toggle per "preparare" un incantesimo qualunque dall'intero
        catalogo — i nuovi incantesimi si ottengono solo tramite i passi di
        level-up dedicati (SPELL_LEARN/SPELL_SWAP/CANTRIP_LEARN) o dalla
        creazione del personaggio, mai da questa vista.
        """
        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.name)
        for i, ks in enumerate(sorted_spells):
            def _open(e, _ks: KnownSpell = ks) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"Lv{_ks.spell_level}  ·  {_ks.school or '—'}",
                        size=11, color=design.T().text_3, italic=True,
                    ),
                    ft.Container(height=4),
                ]
                for label, val in [
                    ("Tempo:", _ks.casting_time),
                    ("Gittata:", _ks.spell_range),
                    ("Durata:", _ks.duration),
                    ("Componenti:", _ks.components),
                ]:
                    if val:
                        rows_d.append(ft.Row([
                            ft.Text(label, size=11, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=design.T().text, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=design.T().border),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=design.T().text, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=design.T().text_3, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=design.T().text_2),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=design.dialog_title(_ks.name),
                    content=ft.Column(
                        rows_d, spacing=6, scroll=ft.ScrollMode.AUTO
                    ),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    # Bullet/bordo "magic" (non "primary"): stessa lista
                    # incantesimi conosciuti "core" delle classi know, non
                    # una distinzione di stato per riga (audit anti-AI-slop,
                    # registro arcano di questa schermata).
                    ft.Text("●", size=18, color=design.T().magic),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=design.T().text,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=design.T().text_3),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=design.Radius.SM,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, design.T().border)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_extra_spell_list(self, spells: list[KnownSpell]) -> ft.Container:
        """
        Lista di incantesimi "extra" (Segreti Magici, Mistificatore, etc.)
        letti dal DB — mostra dettagli già salvati, permette apertura dialog.
        Non ha toggle preparazione: sono sempre "conosciuti".
        """
        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.name)
        for i, ks in enumerate(sorted_spells):
            # Badge via `design.chip()` (tono "warning" invariato — segnala
            # una lista PRESA IN PRESTITO da un'altra classe/meccanismo,
            # distinzione volutamente diversa dal registro "magic" del resto
            # della schermata), avvolto per mantenere il tooltip che
            # `chip()` non espone.
            origin_badge = ft.Container(
                content=design.chip((ks.class_list or "?")[:4], tone="warning", filled=True),
                tooltip=f"Da: {ks.class_list or '—'}",
            )

            def _open(e, _ks: KnownSpell = ks) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"Lv{_ks.spell_level}  ·  {_ks.school or '—'}",
                        size=11, color=design.T().text_3, italic=True,
                    ),
                    ft.Container(height=4),
                ]
                for label, val in [
                    ("Tempo:", _ks.casting_time),
                    ("Gittata:", _ks.spell_range),
                    ("Durata:", _ks.duration),
                    ("Componenti:", _ks.components),
                ]:
                    if val:
                        rows_d.append(ft.Row([
                            ft.Text(label, size=11, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=design.T().text, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=design.T().border),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=design.T().text, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=design.T().text_3, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=design.T().text_2),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=ft.Row([
                        origin_badge,
                        ft.Container(width=8),
                        ft.Text(_ks.name, size=14, weight=ft.FontWeight.BOLD,
                                color=design.T().text, expand=True),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    content=ft.Column(
                        rows_d, spacing=6, scroll=ft.ScrollMode.AUTO
                    ),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Text("★", size=18, color=design.T().warning),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=design.T().text,
                                weight=ft.FontWeight.W_600,
                            ),
                            origin_badge,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=design.T().text_3),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=design.Radius.SM,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, design.T().border)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border.only(left=ft.BorderSide(3, design.T().warning)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_always_prepared_list(self, spells: list[KnownSpell]) -> ft.Container:
        """
        Lista degli incantesimi "sempre pronti" da Dominio/Giuramento/
        Circolo della Terra (task #26, 2026-07-16) — badge 🔒, nessun
        toggle e nessun pulsante di rimozione: lo stato è determinato
        esclusivamente da sottoclasse/terreno/livello del personaggio e si
        aggiorna solo tramite `character_repo.sync_bonus_domain_spells()`
        (chiamata ad ogni apertura tab e level-up/level-down).
        """
        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.name)
        for i, ks in enumerate(sorted_spells):
            def _open(e, _ks: KnownSpell = ks) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"Lv{_ks.spell_level}  ·  {_ks.school or '—'}  ·  Sempre pronto",
                        size=11, color=design.T().text_3, italic=True,
                    ),
                    ft.Container(height=4),
                ]
                for label, val in [
                    ("Tempo:", _ks.casting_time),
                    ("Gittata:", _ks.spell_range),
                    ("Durata:", _ks.duration),
                    ("Componenti:", _ks.components),
                ]:
                    if val:
                        rows_d.append(ft.Row([
                            ft.Text(label, size=11, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=design.T().text, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=design.T().border),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=design.T().text, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=design.T().text_3, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=design.T().text_2),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=ft.Row([
                        ft.Text("🔒", size=16),
                        ft.Container(width=8),
                        ft.Text(_ks.name, size=14, weight=ft.FontWeight.BOLD,
                                color=design.T().text, expand=True),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    content=ft.Column(rows_d, spacing=6, scroll=ft.ScrollMode.AUTO),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Text("🔒", size=16),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=design.T().text,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=design.T().text_3),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=design.Radius.SM,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, design.T().border)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Incantesimi Bonus (task #25, 2026-07-16)
    # ------------------------------------------------------------------

    def _section_bonus_header(self) -> ft.Container:
        """Pulsante "+ Aggiungi Incantesimo Bonus" — sempre visibile."""
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=design.T().magic),
                ft.Text(
                    "Incantesimi concessi manualmente (es. dal master), "
                    "aggiunti a quelli conosciuti/preparati.",
                    size=11, color=design.T().text_3, expand=True,
                ),
                ft.TextButton(
                    "+ Aggiungi Incantesimo Bonus",
                    on_click=lambda e: self._open_add_bonus_spell_dialog(),
                    style=ft.ButtonStyle(color=design.T().magic),
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_bonus_spell_list(self, spells: list[KnownSpell]) -> ft.Container:
        """
        Lista degli incantesimi bonus di un livello — stessa presentazione
        di `_section_extra_spell_list()` ma con un pulsante di rimozione
        dedicato (a differenza dei Segreti Magici, un incantesimo bonus non
        ha una meccanica di sostituzione al level-up: il giocatore deve
        poterlo rimuovere liberamente in qualsiasi momento).
        """
        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.name)
        for i, ks in enumerate(sorted_spells):
            # Badge via `design.chip()` (tono "magic", invariato), avvolto
            # per mantenere il tooltip che `chip()` non espone.
            origin_badge = ft.Container(
                content=design.chip((ks.class_list or "?")[:4], tone="magic", filled=True),
                tooltip=f"Da: {ks.class_list or '—'}",
            )

            def _open(e, _ks: KnownSpell = ks) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"Lv{_ks.spell_level}  ·  {_ks.school or '—'}",
                        size=11, color=design.T().text_3, italic=True,
                    ),
                    ft.Container(height=4),
                ]
                for label, val in [
                    ("Tempo:", _ks.casting_time),
                    ("Gittata:", _ks.spell_range),
                    ("Durata:", _ks.duration),
                    ("Componenti:", _ks.components),
                ]:
                    if val:
                        rows_d.append(ft.Row([
                            ft.Text(label, size=11, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=design.T().text, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=design.T().border),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=design.T().text, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=design.T().text_3, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=design.T().text_2),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=ft.Row([
                        origin_badge,
                        ft.Container(width=8),
                        ft.Text(_ks.name, size=14, weight=ft.FontWeight.BOLD,
                                color=design.T().text, expand=True),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    content=ft.Column(
                        rows_d, spacing=6, scroll=ft.ScrollMode.AUTO
                    ),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                ))

            def _remove(e, _ks: KnownSpell = ks) -> None:
                character_repo.remove_known_spell(
                    self.character.id, _ks.name, _ks.spell_level
                )
                self._reload_known()
                self._build()
                try:
                    self.update()
                except RuntimeError:
                    pass

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Text("✦", size=18, color=design.T().magic),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=design.T().text,
                                weight=ft.FontWeight.W_600,
                            ),
                            origin_badge,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=design.T().text_3),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=design.Radius.SM,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE, icon_size=18,
                        # Azione distruttiva vera (rimozione definitiva
                        # dell'incantesimo bonus, `character_repo.
                        # remove_known_spell`) — token isolato `danger_icon`,
                        # non più `primary_icon` (Arcane Ledger separa i due
                        # registri, audit anti-AI-slop 2026-08-18).
                        icon_color=design.T().danger_icon,
                        tooltip="Rimuovi incantesimo bonus",
                        on_click=_remove,
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, design.T().border)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_racial_spells(self, c: Character) -> ft.Container:
        """
        Incantesimi innati da tratto di razza (Drow "Magia Drow", Tiefling
        "Eredità Infernale" — task #15, 2026-07-16). Sola lettura: nessun
        toggle preparazione (non passano da slot/preparazione, sono innati),
        nessuna rimozione (sono un tratto fisso di razza, non una scelta del
        giocatore). CD calcolata su Carisma FISSO — PHB: "il modificatore
        per questi incantesimi è Carisma", indipendentemente dalla
        caratteristica da incantatore della classe (un Barbaro Drow calcola
        comunque la CD su Carisma, non su Forza/Costituzione).

        Per gli incantesimi "1/riposo lungo" mostra lo stato attuale
        incrociando `class_resources` (già sincronizzato in __init__) per
        nome esatto — lo stesso contatore già gestito e utilizzabile dalla
        tab Combattimento: questa sezione non duplica la logica di
        utilizzo/reset, si limita a renderla visibile insieme al testo
        dell'incantesimo (il gap originale: l'incantesimo esisteva come
        contatore ma non era mai consultabile/leggibile da nessuna parte).
        """
        pb = char_prof_bonus(c)
        cha_mod = get_modifier(c.cha_score)
        dc = 8 + pb + cha_mod

        resources_by_name = {
            r.name: r for r in character_repo.get_class_resources(c.id)
        }

        rows: list[ft.Control] = []
        visible_entries = [
            e for e in self._racial_innate
            if c.level >= e.get("min_char_level", 1)
        ]
        for i, entry in enumerate(visible_entries):
            name = entry.get("name", "")
            master = _loader.get_spell_master_entry(name)
            cast_level = entry.get("cast_level", 0)
            level_label = "Trucchetto" if cast_level == 0 else f"{cast_level}° livello"
            note = entry.get("note", "")

            if entry.get("uses") == "at_will":
                # Via `design.chip()` — tono "magic", stesso risultato visivo
                # di prima (bgcolor magic + testo on_accent).
                usage_chip = design.chip("A volontà", tone="magic", filled=True)
            else:
                res = resources_by_name.get(entry.get("resource_name", ""))
                available = res is None or res.current_value > 0
                # tone="neutral" → tone_color() restituisce `text_3`, stesso
                # grigio usato prima per lo stato "esaurito".
                usage_chip = ft.Container(
                    content=design.chip(
                        "Disponibile" if available else "Usato (riposo lungo)",
                        tone="magic" if available else "neutral", filled=True,
                    ),
                    tooltip="Contatore gestito nella tab Combattimento",
                )

            def _open(e, _name: str = name, _master=master, _level_label=level_label,
                       _dc: int = dc, _note: str = note) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"{_level_label}  ·  CD {_dc}  ·  CD su Carisma (tratto razziale)",
                        size=11, color=design.T().text_3, italic=True,
                    ),
                ]
                if _note:
                    rows_d.append(ft.Text(f"⚠ {_note}", size=11,
                                           color=design.T().primary, italic=True))
                rows_d.append(ft.Container(height=4))
                if _master:
                    for label, val in [
                        ("Tempo:", _master.get("casting_time", "")),
                        ("Gittata:", _master.get("range", "")),
                        ("Durata:", _master.get("duration", "")),
                        ("Componenti:", ", ".join(_master.get("components", []))
                                        if isinstance(_master.get("components"), list)
                                        else str(_master.get("components", ""))),
                    ]:
                        if val:
                            rows_d.append(ft.Row([
                                ft.Text(label, size=11, color=design.T().text_3,
                                        weight=ft.FontWeight.BOLD, width=100),
                                ft.Text(val, size=12, color=design.T().text, expand=True),
                            ], spacing=4))
                    rows_d += [
                        ft.Divider(color=design.T().border),
                        ft.Text(
                            _master.get("description") or "Nessuna descrizione.",
                            size=13, color=design.T().text, selectable=True,
                        ),
                    ]
                else:
                    rows_d.append(ft.Text(
                        "Testo dell'incantesimo non ancora disponibile nel "
                        "compendio — vedi il tratto di razza in Profilo per "
                        "il testo del privilegio.",
                        size=13, color=design.T().text_3, italic=True,
                    ))
                page.show_dialog(ft.AlertDialog(
                    title=design.dialog_title(_name),
                    content=ft.Column(rows_d, spacing=6, scroll=ft.ScrollMode.AUTO),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Row([
                            ft.Text(name, size=13, expand=True,
                                    color=design.T().text,
                                    weight=ft.FontWeight.W_600),
                            ft.Text(level_label, size=11, color=design.T().text_3),
                            usage_chip,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=design.T().text_3),
                        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=design.Radius.SM,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, design.T().border)
                    if i < len(visible_entries) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    # Icona/bordo "magic" (non "primary"): incantesimi
                    # innati restano contenuto arcano, stesso registro delle
                    # altre sezioni di questa schermata (audit anti-AI-slop).
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=design.T().magic),
                    ft.Text(
                        f"Da tratto di razza — CD {dc} (8 + comp. {pb:+d} + CAR {cha_mod:+d}), "
                        f"sempre attivi indipendentemente dalla classe.",
                        size=11, color=design.T().text_3, expand=True,
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                ft.Divider(color=design.T().border, height=10),
                ft.Column(rows, spacing=0),
            ], spacing=6),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _open_add_bonus_spell_dialog(self) -> None:
        """
        Dialog "+ Aggiungi Incantesimo Bonus" — picker a due livelli
        (classe → incantesimo, entrambi con icona ⓘ per la descrizione
        dell'opzione corrente, task #3/#22) sempre disponibile, anche per
        classi non incantatrici.
        """
        if not self._page:
            return
        page = self._page
        c = self.character

        class_names = _loader.get_spellcasting_class_names()
        if not class_names:
            return

        default_class = (
            c.class_name if c.class_name in class_names
            else class_names[0]
        )

        class_dd = ft.Dropdown(
            label="Lista incantesimi",
            value=default_class,
            options=[ft.DropdownOption(key=n, text=n) for n in class_names],
            bgcolor=design.T().surface, color=design.T().text,
            label_style=ft.TextStyle(color=design.T().text_3, size=12),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        error_text = ft.Text("", size=12, color=design.T().primary)

        def _spells_for(cls: str) -> list[dict[str, Any]]:
            return sorted(_loader.get_spells(cls), key=lambda s: (s.get("level", 0), s.get("name", "")))

        spell_dd = CardPicker(
            options=spell_card_options(_spells_for(default_class)),
        )

        def _refresh_spell_options(ev: Any = None) -> None:
            opts = _spells_for(class_dd.value or default_class)
            spell_dd.options = spell_card_options(opts)
            spell_dd.value = opts[0]["name"] if opts else None
            spell_dd.update()

        class_dd.on_select = _refresh_spell_options
        _refresh_spell_options()

        def save(ev: Any) -> None:
            if page is None:
                return
            cls = class_dd.value or default_class
            name = spell_dd.value
            if not name:
                error_text.value = "Scegli un incantesimo."
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return
            spell = next(
                (s for s in _loader.get_spells(cls) if s.get("name") == name), None
            )
            if spell is None:
                error_text.value = "Incantesimo non trovato."
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return
            comps = spell.get("components", [])
            comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
            if spell.get("material"):
                comp_str += f" ({spell['material']})"
            character_repo.upsert_known_spell(
                character_id=c.id,
                name=spell.get("name", name),
                level=spell.get("level", 0),
                is_prepared=True,
                school=spell.get("school", ""),
                casting_time=spell.get("casting_time", ""),
                spell_range=spell.get("range", ""),
                components=comp_str,
                duration=spell.get("duration", ""),
                description=spell.get("description", ""),
                higher_levels=spell.get("higher_levels", "") or "",
                class_list=cls,
                is_bonus=True,
            )
            page.pop_dialog()
            self._reload_known()
            self._build()
            try:
                self.update()
            except RuntimeError:
                pass

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Aggiungi Incantesimo Bonus"),
            content=ft.Container(
                # scroll + altezza fissa spostati QUI (2026-07-16, fix
                # scorrimento annidato — vedi ui/widgets.py): CardPicker non
                # scrolla più se stesso, quindi il contenitore del dialog
                # deve farlo — stesso ruolo già svolto dal content Column del
                # dialog di level-up in profilo_tab.py.
                content=ft.Column([
                    ft.Text(
                        "Scegli da quale lista e quale incantesimo aggiungere "
                        "(es. concesso dal master). Verrà segnato come "
                        "conosciuto/preparato.",
                        size=11, color=design.T().text_3,
                    ),
                    class_dd,
                    muted_text("Incantesimo", size=11),
                    spell_dd.control,
                    error_text,
                ], spacing=10, scroll=ft.ScrollMode.AUTO),
                width=responsive_dialog_width(page, 340),
                height=460,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Aggiungi", on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().magic, color=design.T().on_accent,
                    ),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        self._slots = character_repo.get_spell_slots(self.character.id)
        self._reload_known()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        # Ripristina la posizione di scroll: il rebuild sopra ricrea tutti i
        # controlli, quindi senza questo la vista tornerebbe in cima ad ogni
        # singola azione (bug B10, revisione 2026-07-26).
        self.restore_scroll()
