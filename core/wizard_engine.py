"""
Motore del wizard: accumula i punteggi dalle risposte e calcola la raccomandazione.
Non ha dipendenze da Flet: è pura logica di business.
"""

import random
import uuid
import logging
from typing import Optional

from config.settings import CLASSES, RACES, ALIGNMENTS, STANDARD_ARRAY, RACE_DATA, get_modifier
from data.models import Character
from data.game_data.wizard_data import (
    WIZARD_QUESTIONS, BACKGROUNDS,
    CLASS_PRIMARY_STATS, CLASS_SUGGESTED_RACES, CLASS_DESCRIPTIONS,
)

logger = logging.getLogger(__name__)


class WizardEngine:
    """
    Accumula i punteggi dalle risposte del wizard e produce una raccomandazione
    di classe, razza, background e allineamento coerente con il PHB 5e.
    """

    def __init__(self):
        # Punteggi cumulativi per classe
        self.class_scores: dict[str, int] = {cls: 0 for cls in CLASSES}
        # Punteggi cumulativi per background
        self.bg_scores: dict[str, int] = {bg: 0 for bg in BACKGROUNDS}
        # Assi allineamento derivati dalle risposte
        self.alignment_ge: Optional[str] = None   # Buono / Neutrale / Malvagio
        self.alignment_lc: Optional[str] = None   # Legale / Neutrale / Caotico
        # Risposte grezze {question_id: [option_id, ...]}
        self.answers: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Registrazione risposte
    # ------------------------------------------------------------------

    def record_answer(self, question_id: str, option_ids: list[str]) -> None:
        """
        Registra la risposta a una domanda e aggiorna tutti i punteggi.
        option_ids è sempre una lista (anche per domande a scelta singola).
        """
        self.answers[question_id] = option_ids

        question = next((q for q in WIZARD_QUESTIONS if q["id"] == question_id), None)
        if not question:
            logger.warning(f"Domanda non trovata: {question_id}")
            return

        for opt_id in option_ids:
            option = next((o for o in question["options"] if o["id"] == opt_id), None)
            if not option:
                continue

            # Punteggi classe
            for cls, pts in option.get("scores", {}).items():
                if cls in self.class_scores:
                    self.class_scores[cls] += pts

            # Punteggi background
            for bg, pts in option.get("scores_bg", {}).items():
                if bg in self.bg_scores:
                    self.bg_scores[bg] += pts

            # Assi allineamento
            if "alignment_axis_ge" in option:
                self.alignment_ge = option["alignment_axis_ge"]
            if "alignment_axis_lc" in option:
                self.alignment_lc = option["alignment_axis_lc"]

    def undo_answer(self, question_id: str) -> None:
        """Rimuove il contributo di una domanda (per il tasto 'indietro')."""
        if question_id not in self.answers:
            return

        question = next((q for q in WIZARD_QUESTIONS if q["id"] == question_id), None)
        if not question:
            return

        for opt_id in self.answers[question_id]:
            option = next((o for o in question["options"] if o["id"] == opt_id), None)
            if not option:
                continue
            for cls, pts in option.get("scores", {}).items():
                if cls in self.class_scores:
                    self.class_scores[cls] -= pts
            for bg, pts in option.get("scores_bg", {}).items():
                if bg in self.bg_scores:
                    self.bg_scores[bg] -= pts

        del self.answers[question_id]

    # ------------------------------------------------------------------
    # Raccomandazioni
    # ------------------------------------------------------------------

    def get_top_classes(self, n: int = 3) -> list[tuple[str, int]]:
        """Restituisce le n classi con il punteggio più alto."""
        return sorted(self.class_scores.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_recommended_class(self) -> str:
        return self.get_top_classes(1)[0][0]

    def get_recommended_background(self) -> str:
        """Background con il punteggio più alto; fallback a 'Soldato'."""
        if not any(v > 0 for v in self.bg_scores.values()):
            return "Soldato"
        return max(self.bg_scores, key=lambda k: self.bg_scores[k])

    def get_recommended_race(self, class_name: str) -> str:
        """Prima razza suggerita per la classe; fallback a 'Umano'."""
        races = CLASS_SUGGESTED_RACES.get(class_name, ["Umano"])
        # Filtra solo razze presenti in RACES
        valid = [r for r in races if r in RACES]
        return valid[0] if valid else "Umano"

    def get_alignment_string(self) -> str:
        """
        Costruisce la stringa allineamento dalle due assi.
        Caso speciale: Neutrale + Neutrale = "Neutrale" puro.
        """
        ge = self.alignment_ge or "Neutrale"
        lc = self.alignment_lc or "Neutrale"

        if ge == "Neutrale" and lc == "Neutrale":
            return "Neutrale"

        # Ordine: asse legge/caos prima, poi bene/male
        parts = []
        if lc != "Neutrale":
            parts.append(lc)
        if ge != "Neutrale":
            parts.append(ge)
        if not parts:
            parts.append("Neutrale")

        result = " ".join(parts)
        # Controlla che sia un allineamento valido
        if result in ALIGNMENTS:
            return result
        return "Neutrale"

    def get_class_description(self, class_name: str) -> str:
        return CLASS_DESCRIPTIONS.get(class_name, "")

    # ------------------------------------------------------------------
    # Distribuzione statistiche
    # ------------------------------------------------------------------

    def get_suggested_stat_assignment(self, class_name: str) -> dict[str, int]:
        """
        Suggerisce la distribuzione dello Standard Array [15,14,13,12,10,8]
        in base alla classe, mettendo i valori più alti nelle stat primarie.
        """
        primary = CLASS_PRIMARY_STATS.get(class_name, ["str", "con"])
        all_stats = ["str", "dex", "con", "int", "wis", "cha"]

        # Ordine di priorità: primarie prima, poi le secondarie per classe
        priority = list(primary)
        for s in all_stats:
            if s not in priority:
                priority.append(s)

        values = list(STANDARD_ARRAY)  # [15, 14, 13, 12, 10, 8]
        return {stat: values[i] for i, stat in enumerate(priority)}

    # ------------------------------------------------------------------
    # Costruzione personaggio finale
    # ------------------------------------------------------------------

    def build_character(
        self,
        name: str,
        player_name: str,
        class_name: str,
        race: str,
        background: str,
        alignment: str,
        stat_assignment: dict[str, int],
    ) -> Character:
        """
        Costruisce un Character di livello 1 a partire dai dati del wizard.

        HP max = max del dado vita della classe + modificatore Costituzione (PHB p.12).
        CA base = 10 + modificatore Destrezza (senza armatura).
        Velocità base: 9 metri (30 ft, standard per la maggior parte delle razze).
        """
        hit_die = CLASSES.get(class_name, {}).get("hit_die", 8)
        spellcasting = CLASSES.get(class_name, {}).get("spellcasting_ability")

        # Applica bonus razziali alle caratteristiche base
        race_info = RACE_DATA.get(race, {})
        racial_bonuses = race_info.get("ability_bonuses", {})
        race_speed = race_info.get("speed", 9)

        final_stats = {k: v for k, v in stat_assignment.items()}
        for stat_key, bonus in racial_bonuses.items():
            if stat_key in final_stats:
                final_stats[stat_key] = final_stats[stat_key] + bonus

        con_score = final_stats.get("con", 10)
        dex_score = final_stats.get("dex", 10)
        con_mod = get_modifier(con_score)
        dex_mod = get_modifier(dex_score)

        # Livello 1: HP = max(dado vita) + mod CON, minimo 1
        hp_max = max(1, hit_die + con_mod)

        # Estrae tratti casuali dal PHB per il background scelto
        bg_data = BACKGROUNDS.get(background, {})
        trait = random.choice(bg_data["traits"]) if bg_data.get("traits") else ""
        ideal = random.choice(bg_data["ideals"]) if bg_data.get("ideals") else ""
        bond  = random.choice(bg_data["bonds"])  if bg_data.get("bonds")  else ""
        flaw  = random.choice(bg_data["flaws"])  if bg_data.get("flaws")  else ""

        char = Character(
            id=str(uuid.uuid4()),
            name=name,
            player_name=player_name or "",
            class_name=class_name,
            subclass="",
            level=1,
            race=race,
            subrace="",
            background=background,
            alignment=alignment,
            xp=0,
            image_path="",
            # Caratteristiche con bonus razziali applicati
            str_score=final_stats.get("str", 10),
            dex_score=final_stats.get("dex", 10),
            con_score=final_stats.get("con", 10),
            int_score=final_stats.get("int", 10),
            wis_score=final_stats.get("wis", 10),
            cha_score=final_stats.get("cha", 10),
            # Combattimento
            hp_max=hp_max,
            hp_current=hp_max,
            hp_temp=0,
            ac=10 + dex_mod,          # senza armatura
            speed=race_speed,          # velocità dalla razza (PHB)
            hit_dice_type=hit_die,
            hit_dice_total=1,
            hit_dice_remaining=1,
            death_saves_success=0,
            death_saves_failure=0,
            # Stato turno (tutto a riposo)
            action_used=False,
            bonus_action_used=False,
            reaction_used=False,
            movement_used=0,
            previous_turn_state="",
            # Incantesimi
            spellcasting_ability=spellcasting or "",
            inspiration=False,
            # Aspetto fisico (da compilare dopo)
            age="", height="", weight="",
            eyes="", skin="", hair="",
            # Personalità (estratta dal background PHB)
            personality_traits=trait,
            ideals=ideal,
            bonds=bond,
            flaws=flaw,
            backstory="",
            allies_organizations="",
            additional_traits="",
            appearance_notes="",
        )
        return char
