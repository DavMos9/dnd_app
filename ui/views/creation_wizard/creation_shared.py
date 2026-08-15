"""
Codice condiviso tra i due flussi di creazione personaggio
(`wizard_view.WizardView` e `manual_form.ManualCreationForm`).

Perché esiste (Fase 2 della revisione 2026-07-26, punto "codice ridondante"):
i due file sono nati come copie l'uno dell'altro e sono cresciuti in
parallelo. Misurato con AST alla data di creazione di questo modulo:

  * 51 funzioni con lo stesso nome nei due file;
  * di queste, **24 hanno logica identica** (a meno di annotazioni di tipo,
    docstring e commenti) — 415 righe duplicate;
  * le altre 27 divergono davvero, ma quasi sempre per ragioni legittime
    (il wizard ha le fasi Domande/Raccomandazione, il form manuale ha
    Identità/Punteggi: `_on_class_change` nel wizard deve ricostruire mezza
    schermata perché classe e scelte convivono nella stessa fase, nel form
    la classe si sceglie in fase 1 e la fase 3 viene costruita da zero dopo).

Questo modulo raccoglie le **9 funzioni identiche che sono metodi di classe**
e quindi estraibili senza toccare altro. Le altre 15 identiche sono closure
annidate dentro i metodi giganti (`_render_confirm`, `_on_save`,
`_rebuild_race_extras_col`, `_rebuild_spells_init_col`, …): per estrarle
bisogna prima spezzare quei metodi, che è un intervento a sé — vedi la nota
"lavoro residuo" in fondo a questo docstring.

**Regola per il futuro**: qualunque nuova logica di creazione che serva a
entrambi i flussi va scritta QUI, non copiata nei due file. La duplicazione
è la causa documentata di più bug del progetto (ogni fix va applicato due
volte, e in almeno un caso registrato in CLAUDE.md è stato applicato a uno
solo dei due file).

---
Lavoro residuo, misurato, per completare la deduplicazione (non fatto qui):

| metodo                     | righe (wizard vs form) | similarità |
|----------------------------|------------------------|------------|
| `_render_confirm`          | 911 vs 845             | 73.7%      |
| `_on_save`                 | 758 vs 751             | 78.0%      |
| `_rebuild_race_extras_col` | 553 vs 557             | 91.9%      |
| `_rebuild_spells_init_col` | 312 vs 309             | 95.6%      |
| `_render_equipment`        | 269 vs 259             | 92.2%      |
| `_rebuild_lang_tool_col`   | 185 vs 164             | 86.0%      |

Verificato con un confronto del grafo delle chiamate che **nessuna** di queste
divergenze è una correzione applicata a un solo file (nessun "drift bug"):
tutte le differenze nelle funzioni chiamate si spiegano con la diversa
struttura a fasi dei due flussi.
"""

from typing import Any

import flet as ft

from config.settings import SKILLS, WEAPONS_BY_CATEGORY, get_modifier
from data.game_data.game_data_loader import GameDataLoader

_loader = GameDataLoader()

# Classi che PREPARANO gli incantesimi da un pool completo ogni giorno
# (a differenza di Bardo/Ranger/Stregone/Warlock, che ne CONOSCONO una lista
# fissa). Il Mago prepara anch'esso, ma parte da un libro degli incantesimi:
# è gestito a parte da `_compute_mago_max_prepared()`.
_PREPARED_CASTER_CLASSES: set[str] = {"chierico", "druido", "paladino"}


class CreationSharedMixin:
    """
    Metodi condivisi dai due flussi di creazione personaggio.

    Presuppone che la classe che lo eredita definisca questi attributi
    (entrambe le view lo fanno, con gli stessi nomi):
        `_content`, `_review_class`, `_review_race`, `_review_subrace`,
        `_review_bg`, `_review_stats`, `_review_mezzelf_skills`,
        `_review_mezzelf_flex`, `_review_umano_variant_skill`.
    """

    # Dichiarazioni solo per i type checker: i valori reali sono impostati
    # dall'__init__ delle due view.
    _content: ft.Container
    _review_class: str
    _review_race: str
    _review_subrace: str
    _review_bg: str
    _review_stats: dict[str, int]
    _review_mezzelf_skills: list[str]
    _review_mezzelf_flex: list[str]
    _review_umano_variant_skill: str

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------

    def _set_content(self, control: ft.Control) -> None:
        self._content.content = control
        try:
            self._content.update()
        except RuntimeError:
            pass  # non ancora montato sulla page

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------

    def _bg_skill_proficiencies(self) -> list[str]:
        """Abilità fisse concesse dal background corrente."""
        bg_data = _loader.get_background(self._review_bg)
        return bg_data.get("skill_proficiencies", []) if bg_data else []

    def _bg_language_choices(self) -> tuple[int, str]:
        """(count, from) per le lingue a scelta del background, o (0,'') se nessuna."""
        bg_data = _loader.get_background(self._review_bg)
        if not bg_data:
            return 0, ""
        for entry in bg_data.get("languages", []):
            if isinstance(entry, dict) and entry.get("type") == "choice":
                return entry.get("count", 1), entry.get("from", "any")
        return 0, ""

    # ------------------------------------------------------------------
    # Abilità e lingue
    # ------------------------------------------------------------------

    def _class_skill_options(self) -> tuple[int, list[str]]:
        """
        (count, options) per le abilità di classe. Esclude le abilità già
        concesse dal background (fisse) e quelle già scelte tramite il
        tratto razziale Mezzelfo (Versatilità nelle Abilità) o come abilità
        dell'Umano Variante — altrimenti lo stesso personaggio potrebbe
        ottenere due volte la competenza nella stessa abilità.
        """
        cls_data = _loader.get_class(self._review_class)
        if not cls_data:
            return 0, []
        sc = cls_data.get("skill_choices", {})
        count = sc.get("count", 0)
        opts = sc.get("options", [])
        if opts == "any":
            opts = list(SKILLS.keys())
        excluded = set(self._bg_skill_proficiencies()) | set(self._review_mezzelf_skills)
        if self._review_umano_variant_skill:
            excluded.add(self._review_umano_variant_skill)
        return count, [o for o in opts if o not in excluded]

    def _race_language_choice_count(self) -> int:
        """
        Numero totale di lingue "a scelta libera" concesse dalla RAZZA (non
        dal background) — somma di tutte le entry {"type":"choice","count":N}
        in get_resolved_race(...)["languages"]. Generalizza il vecchio
        special-case hardcoded solo su "Umano" (2026-07-16, task Mezzelfo,
        CLAUDE.md TODO "Mezzelfo non riceve mai la scelta della terza lingua
        libera"): Umano e Mezzelfo hanno la stessa identica struttura dati,
        leggerla qui copre entrambi (e razze future) senza duplicare logica.
        """
        if not self._review_race:
            return 0
        resolved = _loader.get_resolved_race(self._review_race, self._review_subrace)
        total = 0
        for entry in resolved.get("languages", []):
            if isinstance(entry, dict) and entry.get("type") == "choice":
                total += int(entry.get("count", 1))
        return total

    # ------------------------------------------------------------------
    # Incantesimi preparati iniziali
    # ------------------------------------------------------------------

    def _prepared_spell_ability_score(self) -> int:
        """
        Punteggio finale (Standard Array + bonus razziali) della
        caratteristica da incantatore della classe corrente, usato per
        calcolare quanti incantesimi preparati iniziali offrire a
        Chierico/Druido/Paladino. Replica la stessa risoluzione bonus già
        applicata a `char` in fase di salvataggio (razza base + sottorazza
        via get_resolved_race, + il flex Mezzelfo se applicabile) — non
        un'approssimazione diversa.
        """
        cls_data = _loader.get_class(self._review_class) or {}
        ability_key = cls_data.get("spellcasting_ability", "")
        if not ability_key:
            return 10
        base = self._review_stats.get(ability_key, 10)
        race_bonus = 0
        if self._review_race:
            resolved_race = _loader.get_resolved_race(self._review_race, self._review_subrace)
            race_bonus = resolved_race.get("ability_bonuses", {}).get(ability_key, 0)
        mezzelf_bonus = 1 if (
            self._review_race == "Mezzelfo" and ability_key in self._review_mezzelf_flex
        ) else 0
        return min(20, base + race_bonus + mezzelf_bonus)

    def _compute_prepared_spell_count(self) -> int:
        """
        Numero di incantesimi preparati iniziali da offrire alla creazione
        per Chierico/Druido/Paladino (0 per tutte le altre classi). Stessa
        formula PHB già usata da `spells_view.py._calc_max_prepared()` per
        i "full preparatori" (mod. caratteristica + livello, min 1) — al
        Lv.1 la formula per mezzo-preparatore (Paladino) produce lo stesso
        risultato (mod + max(1, 1//2) = mod + 1), quindi un'unica formula
        basta per questa fase di creazione (sempre Lv.1).
        """
        key = (self._review_class or "").strip().lower()
        if key not in _PREPARED_CASTER_CLASSES:
            return 0
        score = self._prepared_spell_ability_score()
        return max(1, get_modifier(score) + 1)

    def _compute_mago_max_prepared(self) -> int:
        """
        Quanti dei 6 incantesimi iniziali del libro del Mago possono essere
        già "preparati" al Lv.1, secondo la stessa formula del "full caster"
        (mod. Intelligenza + livello, min 1) già usata da
        `spells_view.py._calc_max_prepared()` — il Mago è in `_PREP_FULL`
        lì. Serve a non violare quel limite già applicato dalla tab
        Incantesimi: se salvassimo tutti e 6 come `is_prepared=True` a
        prescindere dal modificatore, un Mago con INT bassa nascerebbe già
        "sopra al limite" di preparazione, uno stato incoerente che la UI
        di SpellsView non corregge mai automaticamente (blocca solo NUOVE
        preparazioni oltre il limite, non quelle già presenti).
        """
        if (self._review_class or "").strip().lower() != "mago":
            return 0
        score = self._prepared_spell_ability_score()
        return max(1, get_modifier(score) + 1)

    # ------------------------------------------------------------------
    # Equipaggiamento
    # ------------------------------------------------------------------

    @staticmethod
    def _init_weapon_choice(item: dict[str, Any]) -> dict[str, Any]:
        """Inizializza chosen_weapon/chosen_tool su un item weapon_choice/tool_choice."""
        if item.get("item_type") == "weapon_choice":
            cat = item.get("category", "semplice")
            weapons = WEAPONS_BY_CATEGORY.get(cat, [])
            count = item.get("count", 1)
            if count > 1:
                item["chosen_weapons"] = [weapons[0]] * count if weapons else []
            else:
                item["chosen_weapon"] = weapons[0] if weapons else ""
        elif item.get("item_type") == "tool_choice":
            cat = item.get("category", "strumenti_musicali")
            tools = _loader.get_tool_categories().get(cat, [])
            count = item.get("count", 1)
            if count > 1:
                item["chosen_tools"] = [tools[0]] * count if tools else []
            else:
                item["chosen_tool"] = tools[0] if tools else ""
        return item
