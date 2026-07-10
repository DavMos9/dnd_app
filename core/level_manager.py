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
  INVOCATION         — scelta suppliche occulte Warlock
  METAMAGIC          — scelta metamagia Stregone
  PACT_CHOICE        — scelta dono del patto Warlock
  SUBCLASS_CHOICE    — scelta sottoclasse

  FEATURE_AUTO       — feature automatica — solo info

Flusso atteso:
  profilo_tab._on_level_up_click
    → get_level_up_steps(class_name, new_level, old_pb, new_pb, subclass)
    → itera steps e costruisce dialog dinamico
    → per step.requires_player_choice == True: mostra widget di scelta
    → per step.requires_player_choice == False: mostra solo etichetta info

Fonte dati (2026-07-10): i nomi e le descrizioni delle feature vengono letti
SEMPRE da data/game_data/classes/*.json tramite GameDataLoader — mai da una
tabella Python scritta a mano. In precedenza esisteva qui `_CLASS_FEATURES`,
una tabella hardcoded di tutte le 12 classi × 20 livelli, rimasta ferma alle
versioni pre-audit dei nomi feature (es. Guerriero lv1 "Secondo Respiro"
invece di "Recupera Energie" già corretto in guerriero.json, Mago lv20
"Firma degli Incantesimi" invece di "Incantesimi Personali") — un bug reale,
non solo un problema architetturale: ogni level-up mostrava nomi superati
al giocatore. Rimossa interamente, vedi CLAUDE.md "Note Importanti" per il
changelog completo.

Alcune meccaniche di gioco ricorrono a più livelli ma il JSON registra la
feature una sola volta (il "perché" è nella description in prosa, non in
voci ripetute per livello): Metamagia (Stregone, +opzioni a 3/10/17),
Suppliche Occulte (Warlock, totale cumulativo a 2/5/7/9/12/15/17), Segreti
Magici (Bardo, a 10/14/18), Maestria/Expertise (Ladro 1/6, Bardo 3/10). Per
questi casi il NOME resta letto dal JSON (mai duplicato come stringa), ma il
livello di innesco e il conteggio sono piccole tabelle numeriche qui sotto
— stessa categoria di ASI_LEVELS/_SPELL_LEARN_DELTA (progressioni PHB
universali e stabili, non testo/nomi soggetti a correzione).

Scelta di scope deliberata: i promemoria puramente informativi che nel
vecchio _CLASS_FEATURES mostravano un numero crescente senza una vera scelta
del giocatore (es. "Attacco Furtivo (Nd6)", "Ispirazione Bardica → d8/d10",
"Distruggi Non Morti (CR N)") non vengono ricostruiti: richiederebbero altre
tabelle numeriche per-livello mai verificate contro il manuale in questa
sessione. Meglio mostrare meno testo informativo ma tutto tracciabile a una
fonte verificata, piuttosto che reintrodurre dati non controllati. Le feature
con scelta reale del giocatore (ASI, sottoclasse, incantesimi, ecc.) restano
tutte gestite.

Bug corretti durante l'audit Phase 3 del 2026-07-10 (task "Audit level-up:
Barbaro" — trovati verificando la robustezza generale della funzione prima
di passare classe per classe):
  1. "Segreti Magici" era rilevato con un set fisso di livelli {10,14,18}
     validi solo per la progressione BASE del Bardo — la sottoclasse
     Collegio della Conoscenza concede la stessa identica meccanica
     ("Segreti Magici Aggiuntivi", 2 incantesimi da qualsiasi classe) al
     livello 6, che spariva silenziosamente dal dialog di level-up (né
     SPELL_LEARN né FEATURE_AUTO). Ora rilevato scansionando dinamicamente
     qualunque feature (base o sottoclasse) il cui nome contenga "segreti
     magici" al livello corrente.
  2. Il filtro che esclude "Maestria"/"Perizia" dai FEATURE_AUTO generici
     (per non duplicare lo step EXPERTISE di Ladro/Bardo) era incondizionato
     per nome, quindi faceva sparire anche "Maestria negli Incantesimi" del
     Mago (lv18 — 2 incantesimi lanciabili gratuitamente, nulla a che vedere
     con l'Expertise). Ora il filtro è ristretto alla classe/livello dove
     EXPERTISE viene davvero emesso.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto

from config.settings import ASI_LEVELS, ASI_LEVELS_DEFAULT
from data.game_data.game_data_loader import game_data


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
    INVOCATION           = auto()  # scelta suppliche occulte (Warlock)
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
# Meccaniche ricorrenti registrate una sola volta nel JSON di classe
# (il nome/descrizione si legge comunque da lì — vedi _find_feature_name()),
# ma che si ripetono a più livelli con conteggi diversi. Solo NUMERI qui,
# mai testo/nomi — stessa categoria di ASI_LEVELS/_SPELL_LEARN_DELTA.
# ---------------------------------------------------------------------------

# Stregone, Metamagia: nuove opzioni acquisite a ciascun livello (PHB p.102).
_METAMAGIC_COUNT_BY_LEVEL: dict[int, int] = {3: 2, 10: 1, 17: 1}

# Warlock, Suppliche Occulte: TOTALE cumulativo conosciuto a ciascun livello.
_INVOCATIONS_TOTAL_BY_LEVEL: dict[int, int] = {
    2: 2, 5: 3, 7: 4, 9: 5, 12: 6, 15: 7, 17: 8,
}

# Bardo, Segreti Magici (progressione BASE, PHB p.55): 2 incantesimi da
# qualsiasi lista a ciascun livello — un'unica feature JSON al lv10 la cui
# description descrive in prosa i due incrementi successivi. NON copre la
# versione di sottoclasse (Collegio della Conoscenza lv6, "Segreti Magici
# Aggiuntivi"), rilevata invece dinamicamente in get_level_up_steps().
_SEGRETI_MAGICI_LEVELS: set[int] = {10, 14, 18}

# Maestria/Expertise (2 abilità aggiuntive in maestria): livelli di innesco
# per classe. Nome feature identico per entrambe ("Maestria", PHB) — letto
# comunque dal JSON, non hardcoded qui.
_EXPERTISE_LEVELS: dict[str, set[int]] = {
    "Ladro": {1, 6},
    "Bardo": {3, 10},
}


# ---------------------------------------------------------------------------
# Progressione incantesimi per classi "know" (PHB 5e)
# ---------------------------------------------------------------------------

# Numero di nuovi incantesimi (non-cantrip) appresi a ogni livello.
# Solo i livelli dove il delta > 0 sono elencati.
#
# Verificato il 2026-07-10 (task "Audit level-up: Bardo") leggendo visivamente
# la colonna "Incantesimi Conosciuti" delle tabelle di classe dal PHB IT
# (pdftoppm, non pdftotext): pag.53 Bardo, pag.103 Ranger, pag.108 Stregone,
# pag.114 Warlock. Trovati e corretti 2 bug reali (Ranger e Warlock erano già
# corretti):
#   - Bardo: mancavano i salti di +2 (non +1) ai livelli 10/14/18 (Segreti
#     Magici cumulativi) e c'era un +1 in eccesso al lv19 (che nel manuale
#     non concede nulla) — il totale finale a lv20 tornava per coincidenza
#     vicino al valore corretto (19 invece di 22) ma i valori intermedi e la
#     tempistica delle scelte erano sbagliati.
#   - Stregone: +1 in eccesso al lv14 (il manuale non concede nulla quel
#     livello) e mancava il +1 al lv17 — stesso tipo di "errore compensato"
#     che nascondeva il problema al lv20 (15=15) ma sbagliava i livelli 14-17.
_SPELL_LEARN_DELTA: dict[str, dict[int, int]] = {
    "Bardo":    {2:1,3:1,4:1,5:1,6:1,7:1,8:1,9:1,10:2,11:1,13:1,14:2,15:1,17:1,18:2},
    "Stregone": {2:1,3:1,4:1,5:1,6:1,7:1,8:1,9:1,10:1,11:1,13:1,15:1,17:1},
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

def _find_feature_name(
    keyword: str,
    base_features: list[dict],
    subclass_features: list[dict],
    fallback: str,
) -> str:
    """
    Cerca (case-insensitive, substring) `keyword` nel nome di una feature
    base o di sottoclasse, in qualsiasi punto della progressione — usato
    per le meccaniche ricorrenti che il JSON registra una sola volta
    (Metamagia, Suppliche Occulte, Segreti Magici, Maestria). Restituisce
    il nome esatto dal JSON se trovato, altrimenti `fallback`.
    """
    kw = keyword.lower()
    for feat in base_features + subclass_features:
        name = feat.get("name", "")
        if kw in name.lower():
            return name
    return fallback


def get_level_up_steps(
    class_name: str,
    new_level: int,
    old_pb: int,
    new_pb: int,
    subclass: str = "",
) -> list[LevelStep]:
    """
    Restituisce i LevelStep per il passaggio a new_level.

    Ordine: HP → Feature automatiche/scelte → ASI → Bonus competenza.
    I nomi delle feature sono sempre letti da data/game_data/classes/*.json
    (GameDataLoader), mai da una tabella Python scritta a mano — vedi
    docstring del modulo per il changelog del 2026-07-10.

    `subclass`: nome della sottoclasse già scelta dal personaggio (se nota
    a questo livello) — usato per includere anche le feature di sottoclasse
    nel punto esatto in cui compaiono nel JSON, invece del generico
    "Capacità della sottoclasse" mostrato in precedenza.
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

    cls_data = game_data.get_class(class_name) or {}
    base_features: list[dict] = cls_data.get("features", [])
    subclass_features: list[dict] = []
    if subclass:
        for sc in cls_data.get("subclasses", []):
            if sc.get("name", "").strip().lower() == subclass.strip().lower():
                subclass_features = sc.get("features", [])
                break

    # 2a. Meccaniche ricorrenti (nome dal JSON, conteggio/livello da tabella
    # numerica — vedi docstring del modulo).
    if new_level in _METAMAGIC_COUNT_BY_LEVEL and class_name == "Stregone":
        count = _METAMAGIC_COUNT_BY_LEVEL[new_level]
        name = _find_feature_name("metamagia", base_features, subclass_features, "Metamagia")
        steps.append(LevelStep(
            step_type=StepType.METAMAGIC,
            label=f"{name} ({count} opzion{'e' if count == 1 else 'i'})",
            requires_player_choice=True,
            data={"count": count},
        ))

    if new_level in _INVOCATIONS_TOTAL_BY_LEVEL and class_name == "Warlock":
        total = _INVOCATIONS_TOTAL_BY_LEVEL[new_level]
        name = _find_feature_name("supplic", base_features, subclass_features, "Suppliche Occulte")
        steps.append(LevelStep(
            step_type=StepType.INVOCATION,
            label=f"{name} ({total})",
            requires_player_choice=True,
            data={"total": total},
        ))

    # Segreti Magici (Bardo): la progressione BASE è un'unica feature JSON
    # ("Segreti Magici", registrata al lv10) la cui description descrive in
    # prosa i due incrementi successivi ("Apprendi altri 2 al 14° livello e
    # 2 al 18° livello") — stessa convenzione di ASI_LEVELS, quindi il livello
    # di innesco resta una piccola tabella numerica (_SEGRETI_MAGICI_LEVELS).
    # La sottoclasse Collegio della Conoscenza concede la STESSA meccanica
    # ("Segreti Magici Aggiuntivi", 2 incantesimi da qualsiasi classe) come
    # una feature JSON a sé stante al lv6 — rilevata invece dinamicamente,
    # cercando qualunque feature di sottoclasse con "segreti magici" nel nome
    # al livello corrente. Bug reale corretto il 2026-07-10: prima esisteva
    # solo il set fisso {10,14,18}, quindi la versione di sottoclasse
    # spariva silenziosamente dal dialog di level-up (il filtro di esclusione
    # più sotto la toglieva comunque dai FEATURE_AUTO, ma nessun altro step
    # la sostituiva) — vedi CLAUDE.md "Note Importanti".
    if class_name == "Bardo":
        if new_level in _SEGRETI_MAGICI_LEVELS:
            name = _find_feature_name("segreti magici", base_features, subclass_features, "Segreti Magici")
            steps.append(LevelStep(
                step_type=StepType.SPELL_LEARN,
                label=f"{name} (2 incantesimi)",
                requires_player_choice=True,
                data={
                    "count": 2,
                    "max_level": _max_spell_level_for(class_name, new_level),
                    "any_class": True,
                },
            ))
        else:
            for feat in subclass_features:
                if feat.get("level") == new_level and "segreti magici" in feat.get("name", "").lower():
                    steps.append(LevelStep(
                        step_type=StepType.SPELL_LEARN,
                        label=f"{feat['name']} (2 incantesimi)",
                        requires_player_choice=True,
                        data={
                            "count": 2,
                            "max_level": _max_spell_level_for(class_name, new_level),
                            "any_class": True,
                        },
                    ))

    if new_level in _EXPERTISE_LEVELS.get(class_name, set()):
        # Il nome PHB per questa meccanica è "Maestria" sia per Ladro che
        # per Bardo (confermato nell'audit di entrambi i JSON) — cerchiamo
        # comunque anche "perizia" come fallback difensivo, nel caso in cui
        # una futura correzione manuale usasse quel termine altrove.
        name = _find_feature_name("maestria", base_features, subclass_features, "") \
            or _find_feature_name("perizia", base_features, subclass_features, "Maestria")
        steps.append(LevelStep(
            step_type=StepType.EXPERTISE,
            label=f"{name} (2 abilità)",
            requires_player_choice=True,
            data={"count": 2},
        ))

    # 2b. Scelta sottoclasse — livello esatto dal JSON (subclass_choice_level),
    # non più rilevato cercando "scegli" in una stringa scritta a mano.
    if cls_data.get("subclass_choice_level") == new_level:
        subclass_label = cls_data.get("subclass_label") or "Sottoclasse"
        steps.append(LevelStep(
            step_type=StepType.SUBCLASS_CHOICE,
            label=f"{subclass_label} — scegli la sottoclasse",
            requires_player_choice=True,
            data={"future": True},
        ))

    # 2c. Feature base/sottoclasse definite esattamente a questo livello nel
    # JSON, escluse quelle già emesse sopra come step speciali.
    for feat in base_features + subclass_features:
        if feat.get("level") != new_level:
            continue
        feat_name = feat.get("name", "")
        feat_lower = feat_name.lower()
        if "metamagia" in feat_lower or "supplic" in feat_lower:
            continue
        if class_name == "Bardo" and "segreti magici" in feat_lower:
            continue
        # Esclusa qui SOLO per la classe/livello dove "Maestria"/"Perizia"
        # corrisponde davvero alla meccanica di Expertise gestita sopra come
        # step dedicato (Ladro lv1/6, Bardo lv3/10). Altre classi possono
        # avere una feature con lo stesso termine ma un effetto completamente
        # diverso — es. Mago lv18 "Maestria negli Incantesimi" (2 incantesimi
        # lanciabili gratis, non scelta di abilità) — che deve comunque essere
        # mostrata come FEATURE_AUTO. Bug reale corretto il 2026-07-10: prima
        # il filtro era incondizionato e faceva sparire "Maestria negli
        # Incantesimi" dal level-up del Mago — vedi CLAUDE.md "Note Importanti".
        if new_level in _EXPERTISE_LEVELS.get(class_name, set()) and (
            "maestria" in feat_lower or "perizia" in feat_lower
        ):
            continue
        if "dono del patto" in feat_lower:
            steps.append(LevelStep(
                step_type=StepType.PACT_CHOICE,
                label=feat_name,
                requires_player_choice=True,
            ))
            continue
        steps.append(LevelStep(
            step_type=StepType.FEATURE_AUTO,
            label=feat_name,
            requires_player_choice=False,
        ))

    # 2d. Druido, "Forma Selvatica Migliorata" (PHB p.65): NON è una feature
    # JSON a sé stante — un audit precedente l'ha rimossa in favore della
    # tabella dati pura `wild_shape_forms` (livello/GS max/limitazione), la
    # stessa fonte già usata altrove per queste soglie. Ma il manuale la
    # elenca esplicitamente come "Privilegio" guadagnato ai lv4/8 (lv2 è già
    # coperto dallo step "Forma Selvatica" stesso). Bug reale corretto il
    # 2026-07-10 (task "Audit level-up: Druido"): senza questo step, il
    # level-up di un Druido a questi livelli mostrava SOLO l'ASI, senza alcun
    # accenno all'aumento del GS massimo delle forme bestiali disponibili —
    # confermato contro la tabella di classe a pag.65.
    if class_name == "Druido":
        for form in cls_data.get("wild_shape_forms", []):
            if form.get("level") == new_level and new_level > 2:
                cr = form.get("cr_max", "?")
                limitation = (form.get("limitation") or "").strip()
                extra = f" — {limitation}" if limitation and limitation.lower() != "nessuna" else ""
                steps.append(LevelStep(
                    step_type=StepType.FEATURE_AUTO,
                    label=f"Forma Selvatica Migliorata (GS max {cr}{extra})",
                    requires_player_choice=False,
                ))

    # 2e. Monaco, Via dei Quattro Elementi: apprende una disciplina elementale
    # aggiuntiva a scelta ai lv6/11/17, oltre a quella scelta al lv3 con
    # "Discepolo degli Elementi" (PHB p.93, confermato testualmente: "Apprende
    # una disciplina elementale aggiuntiva a sua scelta al 6°, 11° e 17°
    # livello"). Bug reale trovato durante l'audit Phase 3 (2026-07-10): le
    # altre due tradizioni monastiche (Mano Aperta, Ombra) hanno feature
    # nominate a questi stessi 3 livelli, ma questa no — la sua progressione
    # vive solo nell'array `disciplines` (campo `level` per disciplina), mai
    # controllato da `get_level_up_steps()`, quindi il level-up di un monaco
    # Quattro Elementi a lv6/11/17 non mostrava assolutamente nulla.
    # Fix limitato: emette un promemoria informativo (FEATURE_AUTO), NON un
    # picker interattivo per scegliere la disciplina — costruire quel picker
    # richiederebbe una nuova UI dedicata in profilo_tab.py, fuori scope per
    # un fix di audit; vedi TODO in CLAUDE.md.
    if class_name == "Monaco" and subclass == "Via dei Quattro Elementi" and new_level in (6, 11, 17):
        steps.append(LevelStep(
            step_type=StepType.FEATURE_AUTO,
            label="Discepolo degli Elementi — apprendi 1 disciplina elementale aggiuntiva a scelta",
            requires_player_choice=False,
        ))

    # 2f. Warlock, "Arcanum Mistico": la tabella di classe (PHB p.114) elenca
    # esplicitamente "Arcanum Mistico (6° livello)" al lv11, "(7° livello)" al
    # lv13, "(8° livello)" al lv15, "(9° livello)" al lv17 come 4 righe
    # Privilegi distinte — non un'unica reminder come "Aure Migliorate" del
    # Paladino o "Nemico Prescelto Migliorato" del Ranger, ma 4 scelte REALI
    # separate (uno spell diverso per ciascun livello di slot). La feature
    # JSON "Arcanum Mistico" è registrata una sola volta al lv11 (stessa
    # convenzione di ASI_LEVELS/Segreti Magici: la prosa descrive già i 3
    # incrementi successivi) — senza questo blocco il level-up di un Warlock
    # ai lv13/15/17 non mostrava assolutamente nulla oltre ai PF, nonostante
    # il manuale conceda un nuovo incantesimo di livello via via più alto.
    # Bug reale trovato durante l'audit Phase 3 (2026-07-10, task "Audit
    # level-up: Warlock"). Fix limitato allo stesso scope di Monaco/Druido:
    # promemoria informativo (FEATURE_AUTO), NON un picker interattivo per
    # scegliere lo specifico incantesimo — richiederebbe una UI dedicata in
    # profilo_tab.py; vedi TODO in CLAUDE.md.
    _ARCANUM_SPELL_LEVEL_BY_CLASS_LEVEL: dict[int, int] = {13: 7, 15: 8, 17: 9}
    if class_name == "Warlock" and new_level in _ARCANUM_SPELL_LEVEL_BY_CLASS_LEVEL:
        spell_lv = _ARCANUM_SPELL_LEVEL_BY_CLASS_LEVEL[new_level]
        steps.append(LevelStep(
            step_type=StepType.FEATURE_AUTO,
            label=f"Arcanum Mistico ({spell_lv}° livello) — scegli un incantesimo di {spell_lv}° livello dalla lista del warlock",
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
