"""
SpellsView — Gestione incantesimi del personaggio.

Struttura:
  - Header: caratteristica/CD/bonus attacco + banner "X/Y preparati"
  - Lista slot per livello (read-only — modifica in Combattimento)
  - Lista incantesimi da JSON classe, raggruppati per livello
    · Toggle preparazione (cerchietto) — scrive in known_spells
    · Click sul nome → dialog con descrizione completa

Regole PHB preparazione:
  - I trucchetti (livello 0) sono sempre disponibili, non contano nel limite.
  - Full caster (Chierico, Druido, Mago): mod_car + livello classe (min 1)
  - Half caster (Paladino): mod_car + metà livello arrotondato giù (min 1)
  - Classi "know" (Bardo, Ranger, Stregone, Warlock): nessun limite, lista fissa di
    incantesimi conosciuti (sezione "Incantesimi Conosciuti") — il Ranger NON prepara
    ogni giorno come Chierico/Druido/Paladino, "conosce" incantesimi fissi esattamente
    come Bardo/Stregone/Warlock (PHB IT, ranger.json → feature "Incantesimi": "Un ranger
    conosce due incantesimi di 1° livello a sua scelta"). Corretto il 2026-07-11 — prima
    era erroneamente incluso tra gli "half caster", vedi CLAUDE.md.
  - Override manuale del giocatore: sovrascrive la formula se ≥ 1.
"""

import flet as ft
import logging
from typing import Any, cast
from config.settings import *
from config.settings import get_modifier, char_prof_bonus
from data.models import Character, KnownSpell, SpellSlot
import data.repositories.character_repo as character_repo
from data.game_data.game_data_loader import GameDataLoader
from ui.theme import section_header
from ui.widgets import dropdown_with_info, make_spell_describe

logger = logging.getLogger(__name__)

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
    cui confrontarlo.
    """
    cls = c.class_name or ""
    total = _loader.get_spells_known_at_1(cls)
    delta = _loader.get_spell_learn_delta(cls)
    for lv in range(2, c.level + 1):
        total += delta.get(lv, 0)
    return total


def _calc_max_prepared(c: Character) -> int | None:
    """
    Calcola il massimo di incantesimi preparabili secondo le regole PHB.
    Restituisce None per le classi "know" (nessun limite).
    Tiene conto dell'override manuale del giocatore (max_prepared_spells_override > 0).
    """
    if c.max_prepared_spells_override > 0:
        return c.max_prepared_spells_override

    key = (c.class_name or "").strip().lower()
    scores = {
        "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
        "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
    }
    sp_key = c.spellcasting_ability or ""
    sp_mod = get_modifier(scores.get(sp_key, 10))

    if key in _PREP_FULL:
        return max(1, sp_mod + c.level)
    if key in _PREP_HALF:
        return max(1, sp_mod + max(1, c.level // 2))
    if key in _KNOW_CLASSES:
        return None  # nessun limite — "known spells"
    # Sottoclasse incantatore (es. Guerriero Arcano, Ladro Mistificatore):
    # segnaliamo nessun limite perché la formula varia troppo
    return None


class SpellsView(ft.ListView):
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
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

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
                        title=ft.Text("Limite raggiunto", size=14,
                                      weight=ft.FontWeight.BOLD,
                                      color=COLOR_ACCENT_CRIMSON),
                        content=ft.Text(
                            f"Hai già preparato {max_prep} incantesimi, "
                            f"il massimo per il tuo livello.\n\n"
                            f"Deprepara un incantesimo oppure aumenta il limite "
                            f"manualmente con il tasto ✎.",
                            size=13, color=COLOR_TEXT_PRIMARY,
                        ),
                        actions=[
                            ft.TextButton(
                                "OK",
                                on_click=lambda e: self._page.pop_dialog()
                                if self._page else None,
                            )
                        ],
                        bgcolor=COLOR_BG_CARD,
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
            text_style=ft.TextStyle(size=14, color=COLOR_TEXT_PRIMARY,
                                    font_family=FONT_MONO),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            autofocus=True,
        )

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
            title=ft.Text("Limite Preparazione", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column([
                ft.Text(formula_desc, size=12, color=COLOR_TEXT_MUTED, italic=True),
                ft.Container(height=4),
                f_val,
                ft.Text(
                    "Imposta 0 per tornare al calcolo automatico PHB.",
                    size=11, color=COLOR_TEXT_MUTED,
                ),
            ], spacing=8),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton("Reset PHB", on_click=reset,
                              style=ft.ButtonStyle(color=COLOR_TEXT_MUTED)),
                ft.ElevatedButton(
                    "Salva", on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
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
                ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.BOLD, width=100),
                ft.Text(value, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
            ], spacing=4)

        rows: list[ft.Control] = [
            ft.Text(header_line, size=11, color=COLOR_TEXT_MUTED, italic=True),
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
                                size=11, color=COLOR_ACCENT_AMBER))
        rows.append(ft.Divider(color=COLOR_BORDER))
        rows.append(ft.Text(
            spell.get("description", "Nessuna descrizione."),
            size=13, color=COLOR_TEXT_PRIMARY, selectable=True,
        ))
        if spell.get("higher_levels"):
            rows += [
                ft.Container(height=6),
                ft.Text("Ai livelli superiori:", size=11, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.BOLD),
                ft.Text(spell["higher_levels"], size=12, color=COLOR_TEXT_SECONDARY),
            ]

        page.show_dialog(ft.AlertDialog(
            title=ft.Row([
                ft.Container(
                    content=ft.Text(
                        f"Lv{level}" if level > 0 else "0",
                        size=10, color="#ffffff", weight=ft.FontWeight.BOLD,
                    ),
                    bgcolor=COLOR_ACCENT_BLUE if level == 0 else COLOR_ACCENT_CRIMSON,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                    border_radius=4,
                ),
                ft.Container(width=8),
                ft.Text(name, size=14, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE, expand=True),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            content=ft.Column(rows, spacing=6, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Chiudi",
                              on_click=lambda e: page.pop_dialog() if page else None),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        c = self.character
        controls: list[ft.Control] = []

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

        if c.spellcasting_ability:
            controls += [section_header("Magia"), self._section_magic_header(c)]

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

        active_slots = [s for s in self._slots if s.total > 0]
        if active_slots:
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
            controls.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=48, color=COLOR_BORDER),
                    ft.Container(height=8),
                    ft.Text(
                        f"Nessun incantesimo di classe per {c.class_name} — "
                        f"puoi comunque aggiungere un Incantesimo Bonus qui sopra.",
                        size=14, color=COLOR_TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                   alignment=ft.MainAxisAlignment.CENTER),
                padding=40,
            ))
        elif self._class_spells:
            # Gli incantesimi "sempre pronti" da Dominio/Giuramento/Circolo
            # (task #26) hanno una sezione dedicata più sotto e vanno esclusi
            # da qui: altrimenti comparirebbero anche come voci normali
            # togglabili (molti, es. "Cura Ferite" per un Chierico, sono
            # anche parte della lista standard della classe).
            always_prep_names = {ks.name for ks in self._known.values() if ks.always_prepared}
            by_level: dict[int, list[dict]] = {}
            for sp in self._class_spells:
                if sp.get("name") in always_prep_names:
                    continue
                by_level.setdefault(sp.get("level", 0), []).append(sp)

            controls += [
                section_header("Incantesimi"),
                self._section_prep_banner(c),
            ]
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
                size=11, color=COLOR_TEXT_MUTED, italic=True,
            ))
            for lv in sorted(ap_by_level.keys()):
                lv_label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                controls += [
                    section_header(lv_label),
                    self._section_always_prepared_list(ap_by_level[lv]),
                ]

        # Incantesimi "extra" — conosciuti dal DB ma non nella lista JSON della classe
        # (Segreti Magici, Mistificatore, Eldritch Knight, etc.)
        class_spell_names: set[str] = {s.get("name", "") for s in self._class_spells}
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
        save_dc = 8 + pb + sp_mod
        atk_bon = pb + sp_mod
        atk_str = f"+{atk_bon}" if atk_bon >= 0 else str(atk_bon)
        sp_name = _KEY_TO_NAME.get(sp_key, sp_key)
        sp_abbr = _KEY_TO_ABBR.get(sp_key, sp_key.upper())

        def _box(label: str, value: str) -> ft.Container:
            return ft.Container(
                content=ft.Column([
                    ft.Text(label, size=9, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text(value, size=18, color=COLOR_ACCENT_BLUE,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                            font_family=FONT_MONO),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=COLOR_BG_SECONDARY,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=6, expand=True,
            )

        return ft.Container(
            content=ft.Row([
                _box(f"CARATTERISTICA\n({sp_abbr})", sp_name),
                _box("CD TIRO SALV.", str(save_dc)),
                _box("BONUS ATTACCO", atk_str),
            ], spacing=8),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_BLUE),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
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
            color = COLOR_ACCENT_CRIMSON if over else COLOR_TEXT_MUTED
            ratio = min(1.0, count / expected) if expected > 0 else 0.0
        else:
            label_text = f"{count} / {max_prep} preparati"
            at_limit   = count >= max_prep
            color      = COLOR_ACCENT_CRIMSON if at_limit else COLOR_ACCENT_BLUE
            ratio      = min(1.0, count / max_prep) if max_prep > 0 else 0.0

        if max_prep is not None:
            note = "I trucchetti (0°) non contano nel limite  ·  ✎ per modificare manuale"
        elif expected > 0 and count > expected:
            note = f"Hai {count - expected} incantesim{'o' if count - expected == 1 else 'i'} in più del previsto per il tuo livello — controlla se è corretto (Segreti Magici e simili contano a parte)"
        else:
            note = "Tocca ◉ per segnare un incantesimo come conosciuto"

        rows: list[ft.Control] = [
            ft.Row([
                ft.Text(
                    label_text, size=18, color=color,
                    weight=ft.FontWeight.BOLD, font_family=FONT_MONO,
                    expand=True,
                ),
                ft.TextButton(
                    "✎",
                    on_click=lambda e: self._open_override_dialog(),
                    style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                    tooltip="Modifica limite manualmente",
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
        ]
        if max_prep is not None or expected > 0:
            rows.append(ft.Row([ft.ProgressBar(
                value=ratio,
                color=color,
                bgcolor=COLOR_BG_SECONDARY,
                height=8, border_radius=4, expand=True,
            )]))
        rows.append(ft.Text(note, size=10, color=COLOR_TEXT_MUTED, italic=True))

        return ft.Container(
            content=ft.Column(rows, spacing=6),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, color),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _section_slots_summary(self, slots: list[SpellSlot]) -> ft.Container:
        rows: list[ft.Control] = []
        for slot in sorted(slots, key=lambda s: s.slot_level):
            avail = slot.total - slot.used
            circles = [
                ft.Text(
                    "●" if i < avail else "○",
                    size=20,
                    color=COLOR_SLOT_FULL if i < avail else COLOR_TEXT_MUTED,
                )
                for i in range(slot.total)
            ]
            rows.append(ft.Row(cast(list[ft.Control], [
                ft.Container(
                    content=ft.Text(_SLOT_NAMES[slot.slot_level - 1], size=12,
                                    color=COLOR_TEXT_SECONDARY,
                                    weight=ft.FontWeight.W_600),
                    width=28,
                ),
                ft.Row(cast(list[ft.Control], circles), spacing=2),
                ft.Container(expand=True),
                ft.Text(f"{avail}/{slot.total}", size=11,
                        color=COLOR_TEXT_MUTED, font_family=FONT_MONO),
            ]), vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4))
        rows.append(ft.Text(
            "Usa / recupera slot nel tab Combattimento.",
            size=10, color=COLOR_TEXT_MUTED, italic=True,
        ))
        return ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_BLUE),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
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
                COLOR_ACCENT_CRIMSON if prepared
                else (COLOR_BORDER if blocked else COLOR_TEXT_MUTED)
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
                                    COLOR_TEXT_PRIMARY if prepared
                                    else (COLOR_TEXT_MUTED if blocked
                                          else COLOR_TEXT_SECONDARY)
                                ),
                                weight=(
                                    ft.FontWeight.W_600 if prepared
                                    else ft.FontWeight.NORMAL
                                ),
                            ),
                            ft.Text(tags, size=11, color=COLOR_ACCENT_AMBER)
                            if tags else ft.Container(width=0),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=COLOR_TEXT_MUTED),
                        ], spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=lambda e, s=sp: self._open_spell_dialog(s),
                        expand=True, ink=True, border_radius=4,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                        tooltip="Dettagli",
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, COLOR_BORDER)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            )
            rows.append(row)

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
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
            origin_badge = ft.Container(
                content=ft.Text(
                    (ks.class_list or "?")[:4], size=9,
                    color="#ffffff", weight=ft.FontWeight.BOLD,
                ),
                bgcolor=COLOR_ACCENT_AMBER,
                padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                border_radius=4,
                tooltip=f"Da: {ks.class_list or '—'}",
            )

            def _open(e, _ks: KnownSpell = ks) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"Lv{_ks.spell_level}  ·  {_ks.school or '—'}",
                        size=11, color=COLOR_TEXT_MUTED, italic=True,
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
                            ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=COLOR_TEXT_PRIMARY, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=COLOR_TEXT_SECONDARY),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=ft.Row([
                        origin_badge,
                        ft.Container(width=8),
                        ft.Text(_ks.name, size=14, weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_TITLE, expand=True),
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
                    bgcolor=COLOR_BG_CARD,
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Text("★", size=18, color=COLOR_ACCENT_AMBER),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=COLOR_TEXT_PRIMARY,
                                weight=ft.FontWeight.W_600,
                            ),
                            origin_badge,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=COLOR_TEXT_MUTED),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=4,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, COLOR_BORDER)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_AMBER),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
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
                        size=11, color=COLOR_TEXT_MUTED, italic=True,
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
                            ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=COLOR_TEXT_PRIMARY, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=COLOR_TEXT_SECONDARY),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=ft.Row([
                        ft.Text("🔒", size=16),
                        ft.Container(width=8),
                        ft.Text(_ks.name, size=14, weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_TITLE, expand=True),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    content=ft.Column(rows_d, spacing=6, scroll=ft.ScrollMode.AUTO),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                    bgcolor=COLOR_BG_CARD,
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Text("🔒", size=16),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=COLOR_TEXT_PRIMARY,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=COLOR_TEXT_MUTED),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=4,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, COLOR_BORDER)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border(
                top=ft.BorderSide(3, "#7b1fa2"),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Incantesimi Bonus (task #25, 2026-07-16)
    # ------------------------------------------------------------------

    def _section_bonus_header(self) -> ft.Container:
        """Pulsante "+ Aggiungi Incantesimo Bonus" — sempre visibile."""
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=COLOR_ACCENT_BLUE),
                ft.Text(
                    "Incantesimi concessi manualmente (es. dal master), "
                    "aggiunti a quelli conosciuti/preparati.",
                    size=11, color=COLOR_TEXT_MUTED, expand=True,
                ),
                ft.TextButton(
                    "+ Aggiungi Incantesimo Bonus",
                    on_click=lambda e: self._open_add_bonus_spell_dialog(),
                    style=ft.ButtonStyle(color=COLOR_ACCENT_BLUE),
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_BLUE),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
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
            origin_badge = ft.Container(
                content=ft.Text(
                    (ks.class_list or "?")[:4], size=9,
                    color="#ffffff", weight=ft.FontWeight.BOLD,
                ),
                bgcolor=COLOR_ACCENT_BLUE,
                padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                border_radius=4,
                tooltip=f"Da: {ks.class_list or '—'}",
            )

            def _open(e, _ks: KnownSpell = ks) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"Lv{_ks.spell_level}  ·  {_ks.school or '—'}",
                        size=11, color=COLOR_TEXT_MUTED, italic=True,
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
                            ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=COLOR_TEXT_PRIMARY, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=COLOR_TEXT_SECONDARY),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=ft.Row([
                        origin_badge,
                        ft.Container(width=8),
                        ft.Text(_ks.name, size=14, weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_TITLE, expand=True),
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
                    bgcolor=COLOR_BG_CARD,
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
                    ft.Text("✦", size=18, color=COLOR_ACCENT_BLUE),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=COLOR_TEXT_PRIMARY,
                                weight=ft.FontWeight.W_600,
                            ),
                            origin_badge,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=COLOR_TEXT_MUTED),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=4,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE, icon_size=18,
                        icon_color=COLOR_ACCENT_CRIMSON,
                        tooltip="Rimuovi incantesimo bonus",
                        on_click=_remove,
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, COLOR_BORDER)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_BLUE),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
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
                usage_chip = ft.Container(
                    content=ft.Text("A volontà", size=10, color="#ffffff",
                                     weight=ft.FontWeight.BOLD),
                    bgcolor=COLOR_ACCENT_BLUE,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    border_radius=4,
                )
            else:
                res = resources_by_name.get(entry.get("resource_name", ""))
                available = res is None or res.current_value > 0
                usage_chip = ft.Container(
                    content=ft.Text(
                        "Disponibile" if available else "Usato (riposo lungo)",
                        size=10, color="#ffffff", weight=ft.FontWeight.BOLD,
                    ),
                    bgcolor=(COLOR_ACCENT_BLUE if available else COLOR_TEXT_MUTED),
                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                    border_radius=4,
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
                        size=11, color=COLOR_TEXT_MUTED, italic=True,
                    ),
                ]
                if _note:
                    rows_d.append(ft.Text(f"⚠ {_note}", size=11,
                                           color=COLOR_ACCENT_CRIMSON, italic=True))
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
                                ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                                        weight=ft.FontWeight.BOLD, width=100),
                                ft.Text(val, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                            ], spacing=4))
                    rows_d += [
                        ft.Divider(color=COLOR_BORDER),
                        ft.Text(
                            _master.get("description") or "Nessuna descrizione.",
                            size=13, color=COLOR_TEXT_PRIMARY, selectable=True,
                        ),
                    ]
                else:
                    rows_d.append(ft.Text(
                        "Testo dell'incantesimo non ancora disponibile nel "
                        "compendio — vedi il tratto di razza in Profilo per "
                        "il testo del privilegio.",
                        size=13, color=COLOR_TEXT_MUTED, italic=True,
                    ))
                page.show_dialog(ft.AlertDialog(
                    title=ft.Text(_name, size=14, weight=ft.FontWeight.BOLD,
                                  color=COLOR_TEXT_TITLE),
                    content=ft.Column(rows_d, spacing=6, scroll=ft.ScrollMode.AUTO),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                    bgcolor=COLOR_BG_CARD,
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Row([
                            ft.Text(name, size=13, expand=True,
                                    color=COLOR_TEXT_PRIMARY,
                                    weight=ft.FontWeight.W_600),
                            ft.Text(level_label, size=11, color=COLOR_TEXT_MUTED),
                            usage_chip,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=COLOR_TEXT_MUTED),
                        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=4,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, COLOR_BORDER)
                    if i < len(visible_entries) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=COLOR_ACCENT_CRIMSON),
                    ft.Text(
                        f"Da tratto di razza — CD {dc} (8 + comp. {pb:+d} + CAR {cha_mod:+d}), "
                        f"sempre attivi indipendentemente dalla classe.",
                        size=11, color=COLOR_TEXT_MUTED, expand=True,
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                ft.Divider(color=COLOR_BORDER, height=10),
                ft.Column(rows, spacing=0),
            ], spacing=6),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
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
            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
        )
        spell_dd = ft.Dropdown(
            label="Incantesimo",
            options=[],
            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
        )
        error_text = ft.Text("", size=12, color=COLOR_ACCENT_CRIMSON)

        def _spells_for(cls: str) -> list[dict[str, Any]]:
            return sorted(_loader.get_spells(cls), key=lambda s: (s.get("level", 0), s.get("name", "")))

        def _refresh_spell_options(ev: Any = None) -> None:
            opts = _spells_for(class_dd.value or default_class)
            new_options = []
            for s in opts:
                lv = s.get("level", 0)
                lv_label = "Trucchetto" if lv == 0 else f"Lv{lv}"
                new_options.append(ft.DropdownOption(key=s["name"], text=f"{s['name']} ({lv_label})"))
            spell_dd.options = new_options
            spell_dd.value = opts[0]["name"] if opts else None
            try:
                spell_dd.update()
            except RuntimeError:
                pass

        class_dd.on_select = _refresh_spell_options
        _refresh_spell_options()

        describe_spell = make_spell_describe(_spells_for(default_class))

        def _rewire_describe(ev: Any = None) -> None:
            nonlocal describe_spell
            describe_spell = make_spell_describe(_spells_for(class_dd.value or default_class))

        # `_refresh_spell_options` già ricostruisce le opzioni al cambio
        # classe; qui incateniamo anche il ricalcolo del describe per la
        # nuova lista, altrimenti l'icona ⓘ mostrerebbe la descrizione della
        # classe precedente.
        _orig_on_select = class_dd.on_select

        def _on_class_select(ev: Any) -> None:
            _orig_on_select(ev)
            _rewire_describe(ev)

        class_dd.on_select = _on_class_select

        def _describe_proxy(value: str) -> tuple[str, str] | None:
            return describe_spell(value)

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
            title=ft.Text("Aggiungi Incantesimo Bonus", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        "Scegli da quale lista e quale incantesimo aggiungere "
                        "(es. concesso dal master). Verrà segnato come "
                        "conosciuto/preparato.",
                        size=11, color=COLOR_TEXT_MUTED,
                    ),
                    class_dd,
                    dropdown_with_info(lambda: self._page, spell_dd, _describe_proxy),
                    error_text,
                ], spacing=10, tight=True),
                width=340,
            ),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Aggiungi", on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
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
