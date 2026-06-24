"""
LevelManager: definisce cosa succede a ogni livello per ogni classe.

Responsabilità:
  - Descrivere i LevelStep (cosa cambia a ogni livello)
  - Separare le modifiche automatiche dalle scelte del giocatore

Scelte IMPLEMENTATE:
  HP_GAIN            — scelta giocatore (max / media / dado)
  ASI                — scelta giocatore (+2 a uno / +1 a due)
  PROFICIENCY_BONUS_UP — automatico, nessuna scelta
  SPELL_LEARN        — scelta nuovi incantesimi (Bardo/Stregone/Warlock/Ranger + Segreti Magici)
  EXPERTISE          — scelta maestria abilità Ladro/Bardo
  INVOCATION         — scelta invocazioni occulte Warlock
  METAMAGIC          — scelta metamagia Stregone
  PACT_CHOICE        — scelta dono del patto Warlock
  SUBCLASS_CHOICE    — scelta sottoclasse

  FEATURE_AUTO       — feature automatica — solo info

Flusso atteso:
  profilo_tab._on_level_up_click
    → get_level_up_steps(class_name, new_level, old_pb, new_pb)
    → itera steps e costruisce dialog dinamico
    → per step.requires_player_choice == True: mostra widget di scelta
    → per step.requires_player_choice == False: mostra solo etichetta info
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum, auto

from config.settings import ASI_LEVELS, ASI_LEVELS_DEFAULT


# ---------------------------------------------------------------------------
# Tipi di step
# ---------------------------------------------------------------------------

class StepType(Enum):
    HP_GAIN              = auto()  # guadagno PF — sempre presente, scelta giocatore
    PROFICIENCY_BONUS_UP = auto()  # aumento bonus competenza — automatico
    ASI                  = auto()  # miglioramento caratteristiche o talento — scelta giocatore
    FEATURE_AUTO         = auto()  # feature di classe automatica — solo info
    SUBCLASS_CHOICE      = auto()  # scelta sottoclasse
    SPELL_LEARN          = auto()  # scelta nuovi incantesimi — futuro picker
    EXPERTISE            = auto()  # scelta maestria abilità (Ladro/Bardo)
    INVOCATION           = auto()  # scelta invocazioni occulte (Warlock)
    METAMAGIC            = auto()  # scelta metamagia (Stregone)
    PACT_CHOICE          = auto()  # scelta dono del patto (Warlock Lv3)


@dataclass
class LevelStep:
    step_type: StepType
    label: str
    requires_player_choice: bool = False
    # Metadati aggiuntivi per la UI futura
    # (es. {"spell_level": 3, "count": 1} per SPELL_LEARN)
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Feature di classe per livello — PHB 5e italiano
# [] = nessuna feature (spesso livello ASI)
# Voci con "scegli" → SUBCLASS_CHOICE (scelta futura)
# ---------------------------------------------------------------------------

_CLASS_FEATURES: dict[str, dict[int, list[str]]] = {
    "Barbaro": {
        1:  ["Rabbia (2 usi/riposo lungo)",
             "Difesa senza Armatura (CA = 10 + DES + COS)"],
        2:  ["Attacco Sconsiderato", "Senso del Pericolo"],
        3:  ["Percorso Primordiale — scegli la sottoclasse"],
        4:  [],
        5:  ["Attacco Supplementare", "Movimento Veloce (+3 m)"],
        6:  ["Slot Rabbia +1", "Capacità del Percorso Primordiale"],
        7:  ["Istinto Bestiale"],
        8:  [],
        9:  ["Critico Brutale (1 dado extra)"],
        10: ["Capacità del Percorso Primordiale"],
        11: ["Furore Implacabile"],
        12: [],
        13: ["Critico Brutale (2 dadi extra)"],
        14: ["Capacità del Percorso Primordiale"],
        15: ["Ira Persistente"],
        16: [],
        17: ["Critico Brutale (3 dadi extra)", "Slot Rabbia +1"],
        18: ["Potere Indomito"],
        19: [],
        20: ["Campione Primordiale (+4 FOR, +4 COS)"],
    },
    "Bardo": {
        1:  ["Ispirazione Bardica (d6)"],
        2:  ["Canto del Riposo (d6)", "Tuttofare"],
        3:  ["Collegio Bardico — scegli la sottoclasse", "Perizia (2 abilità)"],
        4:  [],
        5:  ["Ispirazione Bardica → d8", "Fonte d'Ispirazione"],
        6:  ["Capacità del Collegio"],
        7:  [],
        8:  [],
        9:  ["Canto del Riposo → d8"],
        10: ["Ispirazione Bardica → d10", "Perizia (2 altre abilità)",
             "Segreti Magici (2 incantesimi da qualsiasi lista)"],
        11: [],
        12: [],
        13: ["Canto del Riposo → d10"],
        14: ["Capacità del Collegio",
             "Segreti Magici (2 incantesimi aggiuntivi)"],
        15: ["Ispirazione Bardica → d12"],
        16: [],
        17: ["Canto del Riposo → d12"],
        18: ["Segreti Magici (2 incantesimi aggiuntivi)"],
        19: [],
        20: ["Ispirazione Superiore — minimo 1 uso a inizio turno"],
    },
    "Chierico": {
        1:  ["Dominio Divino — scegli la sottoclasse"],
        2:  ["Incanalare Divinità (1 uso)", "Capacità del Dominio"],
        3:  [],
        4:  [],
        5:  ["Distruggi Non Morti (CR ½)"],
        6:  ["Incanalare Divinità (2 usi)", "Capacità del Dominio"],
        7:  [],
        8:  ["Distruggi Non Morti (CR 1)", "Capacità del Dominio"],
        9:  [],
        10: ["Intervento Divino"],
        11: ["Distruggi Non Morti (CR 2)"],
        12: [],
        13: [],
        14: ["Distruggi Non Morti (CR 3)"],
        15: [],
        16: [],
        17: ["Distruggi Non Morti (CR 4)", "Capacità del Dominio"],
        18: ["Incanalare Divinità (3 usi)"],
        19: [],
        20: ["Intervento Divino — successo automatico"],
    },
    "Druido": {
        1:  ["Druido Selvatico (conosci la lingua Druida)"],
        2:  ["Forma Selvatica (CR ¼, no volo/nuoto)",
             "Cerchio Druidico — scegli la sottoclasse"],
        3:  [],
        4:  ["Forma Selvatica (CR ½, no volo)"],
        5:  [],
        6:  ["Capacità del Cerchio"],
        7:  [],
        8:  ["Forma Selvatica (CR 1)"],
        9:  [],
        10: ["Capacità del Cerchio"],
        11: [],
        12: [],
        13: [],
        14: ["Capacità del Cerchio"],
        15: [],
        16: [],
        17: [],
        18: ["Corpo Senza Tempo", "Magia Bestiale"],
        19: [],
        20: ["Incantatore di Bestie"],
    },
    "Guerriero": {
        1:  ["Secondo Respiro (1 uso/riposo breve)", "Stile di Combattimento"],
        2:  ["Ondata d'Azione (1 uso)"],
        3:  ["Archetipo del Guerriero — scegli la sottoclasse"],
        4:  [],
        5:  ["Attacco Supplementare (2 attacchi)"],
        6:  [],
        7:  ["Capacità dell'Archetipo"],
        8:  [],
        9:  ["Inarrestabile (1 uso/riposo lungo)"],
        10: ["Capacità dell'Archetipo"],
        11: ["Attacco Supplementare (3 attacchi)"],
        12: [],
        13: ["Inarrestabile (2 usi)"],
        14: [],
        15: ["Capacità dell'Archetipo"],
        16: [],
        17: ["Ondata d'Azione (2 usi)", "Attacco Supplementare (4 attacchi)"],
        18: ["Capacità dell'Archetipo"],
        19: [],
        20: ["Campione Eterno"],
    },
    "Ladro": {
        1:  ["Attacco Furtivo (1d6)", "Gergo dei Ladri",
             "Perizia (2 abilità + Strumenti da Ladro)"],
        2:  ["Azione Scaltra"],
        3:  ["Archetipo del Ladro — scegli la sottoclasse",
             "Attacco Furtivo (2d6)"],
        4:  [],
        5:  ["Attacco Furtivo (3d6)", "Schivata Prodigiosa"],
        6:  ["Perizia (2 altre abilità)", "Attacco Furtivo (3d6)"],
        7:  ["Elusione", "Attacco Furtivo (4d6)"],
        8:  [],
        9:  ["Capacità dell'Archetipo", "Attacco Furtivo (5d6)"],
        10: [],
        11: ["Talento Affidabile", "Attacco Furtivo (6d6)"],
        12: [],
        13: ["Usare Oggetto Magico", "Attacco Furtivo (7d6)"],
        14: ["Occhio Vigile", "Attacco Furtivo (7d6)"],
        15: ["Mente Scivolosa", "Attacco Furtivo (8d6)"],
        16: [],
        17: ["Capacità dell'Archetipo", "Attacco Furtivo (9d6)"],
        18: ["Elusione assoluta (immunità TirS dimezzati)"],
        19: ["Attacco Furtivo (10d6)"],
        20: ["Colpo Fortunato"],
    },
    "Mago": {
        1:  ["Recupero Arcano (slot pari a ½ livello / riposo breve)"],
        2:  ["Tradizione Arcana — scegli la sottoclasse"],
        3:  [],
        4:  [],
        5:  [],
        6:  ["Capacità della Tradizione"],
        7:  [],
        8:  [],
        9:  [],
        10: ["Capacità della Tradizione"],
        11: [],
        12: [],
        13: [],
        14: ["Capacità della Tradizione"],
        15: [],
        16: [],
        17: [],
        18: ["Maestria degli Incantesimi"],
        19: [],
        20: ["Firma degli Incantesimi (2 incantesimi a costo zero 1v/turno)"],
    },
    "Monaco": {
        1:  ["Arti Marziali", "Difesa senza Armatura (CA = 10 + DES + SAG)"],
        2:  ["Ki (punti = livello)", "Movimento senza Armatura (+3 m)",
             "Tempesta di Pugni", "Passo del Vento"],
        3:  ["Tradizione Monastica — scegli la sottoclasse",
             "Deflettere i Proiettili"],
        4:  ["Caduta Rallentata"],
        5:  ["Attacco Supplementare", "Corpo Stordente"],
        6:  ["Colpi di Ki (attacchi magici)", "Capacità della Tradizione",
             "Movimento senza Armatura (+4.5 m)"],
        7:  ["Elusione", "Mente Tranquilla"],
        8:  [],
        9:  ["Movimento senza Armatura — superfici verticali e acqua"],
        10: ["Purezza del Corpo"],
        11: ["Capacità della Tradizione"],
        12: [],
        13: ["Lingua del Sole e della Luna"],
        14: ["Anima di Diamante (competenza tutti i TirS)"],
        15: ["Corpo Senza Tempo"],
        16: [],
        17: ["Capacità della Tradizione"],
        18: ["Corpo Vuoto (invisibilità 1 min / riposo lungo)"],
        19: [],
        20: ["Essere Perfetto"],
    },
    "Paladino": {
        1:  ["Individuazione del Male e del Bene",
             "Imposizione delle Mani (PF = 5× livello)"],
        2:  ["Combattere Divinamente", "Stile di Combattimento", "Incantesimi"],
        3:  ["Giuramento Sacro — scegli la sottoclasse",
             "Sanità Divina", "Incanalare Divinità (1 uso)"],
        4:  [],
        5:  ["Attacco Supplementare"],
        6:  ["Aura di Protezione (+CAR ai TirS alleati entro 3 m)"],
        7:  ["Capacità del Giuramento"],
        8:  [],
        9:  [],
        10: ["Aura di Coraggio (alleati entro 3 m immuni a spavento)"],
        11: ["Colpo Divino Migliorato (3d8)"],
        12: [],
        13: [],
        14: ["Purificatore di Tocco"],
        15: ["Capacità del Giuramento"],
        16: [],
        17: [],
        18: ["Aure — raggio espanso a 9 m"],
        19: [],
        20: ["Forma Sacra (trasformazione 1 min / riposo lungo)"],
    },
    "Ranger": {
        1:  ["Favori della Natura (nemico prescelto + terreno preferito)"],
        2:  ["Stile di Combattimento", "Incantesimi"],
        3:  ["Archetipo del Ranger — scegli la sottoclasse",
             "Consapevolezza Primordiale"],
        4:  [],
        5:  ["Attacco Supplementare"],
        6:  ["Favori della Natura (nemico e terreno aggiuntivi)"],
        7:  ["Capacità dell'Archetipo"],
        8:  ["Passo della Terra (ignori terreno difficile non magico)"],
        9:  [],
        10: ["Nascondersi in piena vista"],
        11: ["Capacità dell'Archetipo"],
        12: [],
        13: [],
        14: ["Scomparire (Invisibile come azione)"],
        15: ["Capacità dell'Archetipo"],
        16: [],
        17: [],
        18: ["Sensi Ferini (percepisci invisibili entro 9 m)"],
        19: [],
        20: ["Cacciatore Supremo (+10 danni vs nemico prescelto 1v/turno)"],
    },
    "Stregone": {
        1:  ["Magia Istintiva (Origine Stregonica)"],
        2:  ["Punti Stregoneria (= livello)", "Metamagia (2 opzioni)"],
        3:  [],
        4:  [],
        5:  [],
        6:  ["Capacità dell'Origine Stregonica"],
        7:  [],
        8:  [],
        9:  [],
        10: ["Metamagia (opzione aggiuntiva)"],
        11: [],
        12: [],
        13: [],
        14: ["Capacità dell'Origine Stregonica"],
        15: [],
        16: [],
        17: ["Metamagia (opzione aggiuntiva)"],
        18: ["Capacità dell'Origine Stregonica"],
        19: [],
        20: ["Restaurazione Stregonica (4 punti a inizio turno, 1v)"],
    },
    "Warlock": {
        1:  ["Patrono Ultraterreno — scegli la sottoclasse"],
        2:  ["Invocazioni Eldritch (2)"],
        3:  ["Dono del Patto"],
        4:  [],
        5:  ["Invocazioni Eldritch (3)", "Slot incantesimo → 3° livello"],
        6:  ["Capacità del Patrono"],
        7:  ["Invocazioni Eldritch (4)"],
        8:  [],
        9:  ["Invocazioni Eldritch (5)", "Slot incantesimo → 5° livello"],
        10: ["Capacità del Patrono"],
        11: ["Incantesimo Mistico (6°, 1 uso)"],
        12: ["Invocazioni Eldritch (6)"],
        13: ["Incantesimo Mistico (7°)"],
        14: ["Capacità del Patrono"],
        15: ["Incantesimo Mistico (8°)", "Invocazioni Eldritch (7)"],
        16: [],
        17: ["Invocazioni Eldritch (8)"],
        18: ["Incantesimo Mistico (9°)"],
        19: [],
        20: ["Arcanum Ultraterreno"],
    },
}


# ---------------------------------------------------------------------------
# Progressione incantesimi per classi "know" (PHB 5e)
# ---------------------------------------------------------------------------

# Numero di nuovi incantesimi (non-cantrip) appresi a ogni livello.
# Solo i livelli dove il delta > 0 sono elencati.
_SPELL_LEARN_DELTA: dict[str, dict[int, int]] = {
    "Bardo":    {2:1,3:1,4:1,5:1,6:1,7:1,8:1,9:1,10:1,11:1,13:1,14:1,15:1,17:1,19:1},
    "Stregone": {2:1,3:1,4:1,5:1,6:1,7:1,8:1,9:1,10:1,11:1,13:1,14:1,15:1},
    "Warlock":  {2:1,3:1,4:1,5:1,6:1,7:1,8:1,9:1,11:1,13:1,15:1,17:1,19:1},
    "Ranger":   {2:2,3:1,5:1,7:1,9:1,11:1,13:1,15:1,17:1,19:1},
}


def _max_spell_level_for(class_name: str, level: int) -> int:
    """Massimo livello di slot incantesimo accessibile per classe e livello (PHB)."""
    cls = class_name.lower()
    if cls in ("bardo", "stregone"):
        # Full caster: slot fino a 9° livello
        for threshold, slot_lv in [(17,9),(15,8),(13,7),(11,6),(9,5),(7,4),(5,3),(3,2)]:
            if level >= threshold:
                return slot_lv
        return 1
    if cls == "warlock":
        # Pact slots: max 5° livello
        for threshold, slot_lv in [(9,5),(7,4),(5,3),(3,2)]:
            if level >= threshold:
                return slot_lv
        return 1
    if cls == "ranger":
        # Half caster
        for threshold, slot_lv in [(17,5),(13,4),(9,3),(5,2)]:
            if level >= threshold:
                return slot_lv
        return 1
    return 9  # fallback per sottoclassi incantatrici


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------

def get_level_up_steps(
    class_name: str,
    new_level: int,
    old_pb: int,
    new_pb: int,
) -> list[LevelStep]:
    """
    Restituisce i LevelStep per il passaggio a new_level.

    Ordine: HP → Feature automatiche/scelte → ASI → Bonus competenza.
    """
    steps: list[LevelStep] = []

    # 1. HP gain — sempre primo, richiede scelta giocatore
    steps.append(LevelStep(
        step_type=StepType.HP_GAIN,
        label="Punti Ferita",
        requires_player_choice=True,
    ))

    # 1b. SPELL_LEARN per classi "know": emesso subito dopo HP
    spell_delta = _SPELL_LEARN_DELTA.get(class_name, {}).get(new_level, 0)
    if spell_delta > 0:
        max_lv = _max_spell_level_for(class_name, new_level)
        label = (
            f"Incantesimi conosciuti (+{spell_delta})"
            if spell_delta > 1
            else "Incantesimo conosciuto (+1)"
        )
        steps.append(LevelStep(
            step_type=StepType.SPELL_LEARN,
            label=label,
            requires_player_choice=True,
            data={"count": spell_delta, "max_level": max_lv, "any_class": False},
        ))

    # 2. Feature di classe per questo livello
    features = _CLASS_FEATURES.get(class_name, {}).get(new_level, [])
    for feat in features:
        feat_lower = feat.lower()
        if "dono del patto" in feat_lower:
            steps.append(LevelStep(
                step_type=StepType.PACT_CHOICE,
                label=feat,
                requires_player_choice=True,
            ))
        elif "metamagia" in feat_lower:
            m = re.search(r"\((\d+)", feat)
            count = int(m.group(1)) if m else 1
            steps.append(LevelStep(
                step_type=StepType.METAMAGIC,
                label=feat,
                requires_player_choice=True,
                data={"count": count},
            ))
        elif "invocazioni" in feat_lower:
            # Invocazioni Occulte: il numero tra parentesi è il totale cumulativo
            m = re.search(r"\((\d+)\)", feat)
            total = int(m.group(1)) if m else 0
            steps.append(LevelStep(
                step_type=StepType.INVOCATION,
                label=feat,
                requires_player_choice=True,
                data={"total": total},
            ))
        elif "segreti magici" in feat_lower:
            # Bardo Lv10/14/18: scelta di 2 incantesimi da qualsiasi lista
            m = re.search(r"\((\d+)", feat)
            count = int(m.group(1)) if m else 2
            steps.append(LevelStep(
                step_type=StepType.SPELL_LEARN,
                label=feat,
                requires_player_choice=True,
                data={
                    "count": count,
                    "max_level": _max_spell_level_for(class_name, new_level),
                    "any_class": True,
                },
            ))
        elif "perizia" in feat_lower:
            # Expertise: scelta di 2 abilità da rendere maestria
            steps.append(LevelStep(
                step_type=StepType.EXPERTISE,
                label=feat,
                requires_player_choice=True,
                data={"count": 2},
            ))
        elif "scegli" in feat_lower:
            steps.append(LevelStep(
                step_type=StepType.SUBCLASS_CHOICE,
                label=feat,
                requires_player_choice=True,
                data={"future": True},
            ))
        else:
            steps.append(LevelStep(
                step_type=StepType.FEATURE_AUTO,
                label=feat,
                requires_player_choice=False,
            ))

    # 3. ASI — ai livelli appropriati per la classe
    asi_set = ASI_LEVELS.get(class_name, ASI_LEVELS_DEFAULT)
    if new_level in asi_set:
        steps.append(LevelStep(
            step_type=StepType.ASI,
            label="Miglioramento Caratteristiche",
            requires_player_choice=True,
        ))

    # 4. Bonus competenza — automatico, solo quando aumenta
    if new_pb > old_pb:
        steps.append(LevelStep(
            step_type=StepType.PROFICIENCY_BONUS_UP,
            label=f"Bonus Competenza: +{old_pb} → +{new_pb}",
            requires_player_choice=False,
        ))

    return steps


def estimate_hp_loss(hit_die: int, con_mod: int) -> int:
    """
    Stima i PF guadagnati al livello precedente (usata per Level Down).
    Usa il metodo 'media' come valore di riferimento.
    """
    return max(1, hit_die // 2 + 1 + con_mod)
