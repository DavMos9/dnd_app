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
  SPELL_SWAP         — scelta OPZIONALE: sostituire un incantesimo conosciuto con un
                        altro della stessa lista (Bardo/Ranger/Stregone/Warlock, ad ogni
                        livello — PHB IT, testo identico nelle 4 feature "Incantesimi"/
                        "Magia del Patto": "quando [la classe] acquisisce un livello, può
                        scegliere un incantesimo che conosce e sostituirlo con un altro")
  CANTRIP_LEARN      — scelta nuovo trucchetto ai lv.4/10 (Bardo/Chierico/Druido/Mago/
                        Stregone/Warlock — colonna "Trucchetti Conosciuti" delle rispettive
                        tabelle di classe PHB, +1 a entrambi i livelli per tutte e 6)
  EXPERTISE          — scelta maestria abilità Ladro/Bardo
  INVOCATION         — scelta suppliche occulte Warlock
  METAMAGIC          — scelta metamagia Stregone
  PACT_CHOICE        — scelta dono del patto Warlock
  SUBCLASS_CHOICE    — scelta sottoclasse
  ARCANUM_SPELL      — scelta incantesimo di livello ESATTO (Warlock, Arcanum
                        Mistico, lv.11/13/15/17 — 6°/7°/8°/9° livello)
  MONK_DISCIPLINE    — scelta disciplina elementale aggiuntiva (Monaco, Via
                        dei Quattro Elementi, lv.6/11/17 — la scelta iniziale
                        di Lv.3 è gestita in profilo_tab.py insieme a
                        SUBCLASS_CHOICE, non tramite questo step)

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
livello di innesco e il conteggio sono piccole tabelle numeriche lette dai
rispettivi JSON di classe via GameDataLoader (vedi sotto per il changelog
del 2026-07-10) — stessa categoria di ASI_LEVELS: progressioni PHB
universali e stabili, non testo/nomi soggetti a correzione.

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
    SPELL_SWAP           = auto()  # scelta OPZIONALE: sostituisci un incantesimo conosciuto
    CANTRIP_LEARN        = auto()  # scelta nuovo trucchetto (lv.4/10, 6 classi incantatrici)
    EXPERTISE            = auto()  # scelta maestria abilità (Ladro/Bardo)
    INVOCATION           = auto()  # scelta suppliche occulte (Warlock)
    METAMAGIC            = auto()  # scelta metamagia (Stregone)
    PACT_CHOICE          = auto()  # scelta dono del patto (Warlock Lv3)
    # Mistificatore Arcano (Ladro)/Cavaliere Mistico (Guerriero) — casting
    # "preso in prestito dal Mago". L'apprendimento INIZIALE (3° livello,
    # stesso livello di SUBCLASS_CHOICE) è gestito direttamente in
    # profilo_tab.py, non tramite questi step (vedi _BORROWED_CASTER_SUBCLASS
    # più sotto per il perché) — questi 3 step coprono solo la crescita dal
    # 4° livello in poi, quando la sottoclasse è già nota.
    BORROWED_CANTRIP     = auto()  # nuovo trucchetto da mago (lv.10)
    BORROWED_SPELL_LEARN = auto()  # nuovo incantesimo da mago, vincolato per scuola
    BORROWED_SPELL_SWAP  = auto()  # scelta OPZIONALE: sostituisci un incantesimo da mago conosciuto
    # Warlock, Arcanum Mistico (lv.11/13/15/17): scelta di un incantesimo di
    # livello ESATTO (6°/7°/8°/9°) dalla lista del warlock, lanciabile senza
    # slot 1/riposo lungo. A differenza di SPELL_LEARN (livello massimo, non
    # esatto) qui il vincolo è "esattamente questo livello" — vedi CLAUDE.md
    # 2026-07-16, fix "picker Arcanum Mistico".
    ARCANUM_SPELL        = auto()
    # Monaco, Via dei Quattro Elementi (lv.6/11/17): scelta di 1 disciplina
    # elementale aggiuntiva dal pool sbloccato a quel livello (monaco.json →
    # subclasses["Via dei Quattro Elementi"].disciplines, campo "level"). La
    # scelta INIZIALE (Sintonia Elementale automatica + 1 a scelta, Lv.3) è
    # gestita direttamente in profilo_tab.py insieme al dropdown
    # SUBCLASS_CHOICE, stesso motivo/pattern di fighting_style/totem_animal/
    # land_terrain/Mistificatore Arcano — vedi CLAUDE.md 2026-07-16.
    MONK_DISCIPLINE      = auto()


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
# ma che si ripetono a più livelli con conteggi diversi.
#
# Le tabelle numeriche (_METAMAGIC_COUNT_BY_LEVEL, _INVOCATIONS_TOTAL_BY_LEVEL,
# _SEGRETI_MAGICI_LEVELS, _EXPERTISE_LEVELS, _SPELL_LEARN_DELTA) sono state
# spostate nei rispettivi JSON di classe il 2026-07-10 (stregone.json →
# "metamagic_count_by_level"/"spell_learn_delta", warlock.json →
# "invocations_total_by_level"/"spell_learn_delta", bardo.json →
# "segreti_magici_levels"/"expertise_levels"/"spell_learn_delta", ladro.json →
# "expertise_levels", ranger.json → "spell_learn_delta") — stesso principio
# già applicato a RACE_DATA/CLASS_FEATURES/ASI_LEVELS: erano tabelle PHB già
# verificate ma scritte a mano solo in Python. Lette ora tramite
# game_data.get_metamagic_count_by_level()/get_invocations_total_by_level()/
# get_segreti_magici_levels()/get_expertise_levels()/get_spell_learn_delta().
# Nessun valore cambiato in questa migrazione (verificato con test di
# regressione end-to-end su tutte le 12 classi × 20 livelli).
# ---------------------------------------------------------------------------


# Livelli in cui il numero di "Trucchetti Conosciuti" cresce di +1, per le 6
# classi che hanno un conteggio fisso di trucchetti (campo
# "cantrips_known_at_1" nel JSON di classe: bardo/chierico/druido/mago/
# stregone/warlock — non le sottoclassi "Mago aggiuntivo" di Cavaliere
# Mistico/Mistificatore Arcano, gestite separatamente e non ancora wired,
# vedi CLAUDE.md TODO dedicato). Verificato leggendo visivamente (pdftoppm,
# non pdftotext) la colonna "Trucchetti Conosciuti" delle 6 tabelle di
# classe PHB IT (Bardo p.53, Chierico p.57, Druido p.65, Mago p.82, Stregone
# p.108, Warlock p.114) il 2026-07-11: tutte e 6 crescono di esattamente +1
# al 4° livello e di nuovo +1 al 10° livello, nessuna eccezione — stessa
# categoria di ASI_LEVELS_DEFAULT: progressione PHB universale e stabile,
# non testo/nomi soggetti a correzione, quindi vive come costante Python
# invece che duplicata identica in 6 file JSON.
_CANTRIP_GROWTH_LEVELS: tuple[int, ...] = (4, 10)

# Classi con un conteggio fisso di trucchetti conosciuti (vedi sopra) — letto
# dinamicamente da cantrips_known_at_1 > 0 per non duplicare l'elenco.
_CANTRIP_CLASSES: tuple[str, ...] = (
    "Bardo", "Chierico", "Druido", "Mago", "Stregone", "Warlock",
)

# Le uniche 2 sottoclassi PHB che concedono casting "preso in prestito dal
# Mago" a una classe altrimenti non incantatrice (Ladro/Guerriero, entrambe
# spellcasting_ability=null a livello di classe base). Vedi CLAUDE.md
# 2026-07-15 per il fix completo — bug report di Davide: "Il mistificatore
# arcano non riesce a visualizzare gli incantesimi, tantomeno glieli fa
# scegliere".
_BORROWED_CASTER_SUBCLASS: dict[str, str] = {
    "Ladro": "Mistificatore Arcano",
    "Guerriero": "Cavaliere Mistico",
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

    # Warlock, Arcanum Mistico: livello incantesimo ESATTO sbloccato a ogni
    # soglia (PHB IT p.114, tabella di classe: "Arcanum Mistico (6° livello)"
    # al lv11, "(7° livello)" al lv13, "(8° livello)" al lv15, "(9° livello)"
    # al lv17 — 4 righe Privilegi distinte). Definito qui (non dentro il
    # blocco 2f più sotto) perché serve anche alla sezione 2c per escludere
    # la feature JSON "Arcanum Mistico" (registrata una sola volta al lv11)
    # dal generico FEATURE_AUTO quando viene sostituita dal picker dedicato.
    _ARCANUM_SPELL_LEVEL_BY_CLASS_LEVEL: dict[int, int] = {11: 6, 13: 7, 15: 8, 17: 9}

    # 1. HP gain — sempre primo, richiede scelta giocatore
    steps.append(LevelStep(
        step_type=StepType.HP_GAIN,
        label="Punti Ferita",
        requires_player_choice=True,
    ))

    # 1b. SPELL_LEARN per classi "know": emesso subito dopo HP
    spell_delta = game_data.get_spell_learn_delta(class_name).get(new_level, 0)
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

    # 1b2. CANTRIP_LEARN — nuovo trucchetto ai lv.4/10 per le 6 classi con un
    # conteggio fisso di trucchetti conosciuti (vedi _CANTRIP_GROWTH_LEVELS).
    # Bug segnalato da Davide 2026-07-11: "il bardo e altri incantatori
    # imparano anche altri trucchetti a determinati livelli, non solo
    # incantesimi, non mi sembra gestita questa cosa" — confermato: prima di
    # questo fix nessuno step veniva mai generato per questa crescita.
    if class_name in _CANTRIP_CLASSES and new_level in _CANTRIP_GROWTH_LEVELS:
        if (cls_data_for_cantrips := game_data.get_class(class_name)) and \
                cls_data_for_cantrips.get("cantrips_known_at_1", 0) > 0:
            steps.append(LevelStep(
                step_type=StepType.CANTRIP_LEARN,
                label="Nuovo trucchetto conosciuto (+1)",
                requires_player_choice=True,
                data={"count": 1},
            ))

    # 1c. SPELL_SWAP — scelta OPZIONALE, disponibile a OGNI level-up per le 4
    # classi "know" (Bardo/Ranger/Stregone/Warlock), non solo ai livelli in
    # cui si impara un nuovo incantesimo. Testo PHB identico (confermato da
    # Davide incollando il testo delle rispettive feature "Incantesimi"/
    # "Magia del Patto" per tutte e 4): "quando [la classe] acquisisce un
    # livello, può scegliere un incantesimo [della classe] che conosce e
    # sostituirlo con un altro incantesimo della lista [della classe]; anche
    # il nuovo incantesimo deve essere di un livello di cui [la classe]
    # possiede degli slot incantesimo". Soglia minima per classe: Bardo/
    # Stregone/Warlock hanno già incantesimi conosciuti dalla creazione
    # (Lv.1), quindi la prima occasione di scambio è al level-up verso il
    # Lv.2; il Ranger impara i suoi primi incantesimi solo al level-up verso
    # il Lv.2 (via SPELL_LEARN, delta 2), quindi la prima occasione di
    # scambio è al level-up verso il Lv.3 — prima non avrebbe nulla da
    # scambiare. Implementato il 2026-07-11 su richiesta esplicita di
    # Davide, vedi CLAUDE.md.
    _SWAP_MIN_LEVEL: dict[str, int] = {
        "Bardo": 2, "Stregone": 2, "Warlock": 2, "Ranger": 3,
    }
    if class_name in _SWAP_MIN_LEVEL and new_level >= _SWAP_MIN_LEVEL[class_name]:
        steps.append(LevelStep(
            step_type=StepType.SPELL_SWAP,
            label="Sostituisci un incantesimo conosciuto (opzionale)",
            requires_player_choice=True,
            data={"max_level": _max_spell_level_for(class_name, new_level)},
        ))

    # 1d. Mistificatore Arcano (Ladro)/Cavaliere Mistico (Guerriero): crescita
    # di trucchetti/incantesimi "presi in prestito dal Mago" dal 4° livello in
    # poi. L'apprendimento INIZIALE (3° livello, 2 incantesimi vincolati per
    # scuola + 1 libero, trucchetti fissi+scelti) avviene allo stesso livello
    # in cui si sceglie la sottoclasse — dato che `subclass` qui riflette
    # sempre la sottoclasse GIA' scelta ai level-up precedenti (mai quella
    # che il giocatore sta per scegliere in QUESTO level-up), è vuoto proprio
    # al 3° livello, stesso limite già presente per fighting_style/
    # totem_animal/land_terrain in questo file — quindi l'apprendimento
    # iniziale è gestito direttamente in profilo_tab.py insieme al dropdown
    # SUBCLASS_CHOICE (con reattività live sul valore scelto), non qui.
    # Aggiunto 2026-07-15 — fix "Il mistificatore arcano non riesce a
    # visualizzare gli incantesimi" (bug report di Davide), esteso anche al
    # Cavaliere Mistico su sua conferma esplicita.
    if (
        class_name in _BORROWED_CASTER_SUBCLASS
        and subclass == _BORROWED_CASTER_SUBCLASS[class_name]
        and new_level > 3
    ):
        prog_now = game_data.get_borrowed_caster_progression_for_level(
            class_name, subclass, new_level
        )
        prog_prev = game_data.get_borrowed_caster_progression_for_level(
            class_name, subclass, new_level - 1
        )
        if prog_now:
            cantrip_delta = prog_now.get("cantrips_known", 0) - (
                prog_prev.get("cantrips_known", 0) if prog_prev else 0
            )
            spell_delta = prog_now.get("spells_known", 0) - (
                prog_prev.get("spells_known", 0) if prog_prev else 0
            )
            slots_now: dict = prog_now.get("slots", {})
            max_lv = max(
                (int(k) for k, v in slots_now.items() if v > 0), default=1
            )

            if cantrip_delta > 0:
                steps.append(LevelStep(
                    step_type=StepType.BORROWED_CANTRIP,
                    label=f"Nuovo trucchetto da mago (+{cantrip_delta})",
                    requires_player_choice=True,
                    data={"count": cantrip_delta},
                ))

            if spell_delta > 0:
                sc_data = game_data.get_borrowed_caster_data(class_name, subclass) or {}
                unrestricted_levels = sc_data.get("unrestricted_origin_levels", [])
                restricted_schools = sc_data.get("restricted_schools", [])
                is_unrestricted = new_level in unrestricted_levels
                label = (
                    f"Incantesimo da mago conosciuto (+{spell_delta}, qualsiasi scuola)"
                    if is_unrestricted
                    else (
                        f"Incantesimo da mago conosciuto "
                        f"(+{spell_delta}, {'/'.join(restricted_schools)})"
                    )
                )
                steps.append(LevelStep(
                    step_type=StepType.BORROWED_SPELL_LEARN,
                    label=label,
                    requires_player_choice=True,
                    data={
                        "count": spell_delta,
                        "max_level": max_lv,
                        "restricted_schools": restricted_schools,
                        "unrestricted": is_unrestricted,
                    },
                ))

            # Sostituzione OPZIONALE — ogni livello dal 4° in poi (stesso
            # testo PHB delle 4 classi "know": "quando [la classe] acquisisce
            # un livello, può sostituire uno degli incantesimi da mago che
            # conosce con un altro"), non solo ai livelli con nuovi incantesimi.
            steps.append(LevelStep(
                step_type=StepType.BORROWED_SPELL_SWAP,
                label="Sostituisci un incantesimo da mago conosciuto (opzionale)",
                requires_player_choice=True,
                data={"max_level": max_lv},
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
    metamagic_by_level = game_data.get_metamagic_count_by_level()
    if new_level in metamagic_by_level and class_name == "Stregone":
        count = metamagic_by_level[new_level]
        name = _find_feature_name("metamagia", base_features, subclass_features, "Metamagia")
        steps.append(LevelStep(
            step_type=StepType.METAMAGIC,
            label=f"{name} ({count} opzion{'e' if count == 1 else 'i'})",
            requires_player_choice=True,
            data={"count": count},
        ))

    invocations_by_level = game_data.get_invocations_total_by_level()
    if new_level in invocations_by_level and class_name == "Warlock":
        total = invocations_by_level[new_level]
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
    # di innesco resta una piccola tabella numerica (bardo.json → "segreti_magici_levels").
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
        if new_level in game_data.get_segreti_magici_levels():
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

    if new_level in game_data.get_expertise_levels(class_name):
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
        if new_level in game_data.get_expertise_levels(class_name) and (
            "maestria" in feat_lower or "perizia" in feat_lower
        ):
            continue
        # Warlock, "Arcanum Mistico": registrata una sola volta nel JSON al
        # lv11 (la prosa descrive già gli incrementi successivi, stessa
        # convenzione di ASI_LEVELS), ma qui viene sostituita dal picker
        # dedicato ARCANUM_SPELL (sezione 2f) per TUTTI e 4 i livelli in cui
        # concede una scelta reale — va quindi esclusa dal FEATURE_AUTO
        # generico solo al lv11 (l'unico dove esiste davvero come voce in
        # `base_features`), non ai lv13/15/17 dove non è comunque presente.
        if (class_name == "Warlock" and "arcanum mistico" in feat_lower
                and new_level in _ARCANUM_SPELL_LEVEL_BY_CLASS_LEVEL):
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
    # ✅ Picker interattivo implementato il 2026-07-16 (era rimasto solo un
    # promemoria informativo dal 2026-07-10) — vedi CLAUDE.md.
    if class_name == "Monaco" and subclass == "Via dei Quattro Elementi" and new_level in (6, 11, 17):
        steps.append(LevelStep(
            step_type=StepType.MONK_DISCIPLINE,
            label="Discepolo degli Elementi — apprendi 1 disciplina elementale aggiuntiva a scelta",
            requires_player_choice=True,
            data={"unlock_level": new_level},
        ))

    # 2f. Warlock, "Arcanum Mistico": la tabella di classe (PHB p.114) elenca
    # esplicitamente "Arcanum Mistico (6° livello)" al lv11, "(7° livello)" al
    # lv13, "(8° livello)" al lv15, "(9° livello)" al lv17 come 4 righe
    # Privilegi distinte — non un'unica reminder come "Aure Migliorate" del
    # Paladino o "Nemico Prescelto Migliorato" del Ranger, ma 4 scelte REALI
    # separate (uno spell diverso per ciascun livello di slot). La feature
    # JSON "Arcanum Mistico" è registrata una sola volta al lv11 (stessa
    # convenzione di ASI_LEVELS/Segreti Magici: la prosa descrive già i 3
    # incrementi successivi). ✅ Picker interattivo implementato il
    # 2026-07-16 (era rimasto solo un promemoria informativo dal 2026-07-10,
    # e prima ancora il lv11 non mostrava nulla) — vedi CLAUDE.md. Include
    # ora anche il lv11 (6° livello), non solo 13/15/17.
    if class_name == "Warlock" and new_level in _ARCANUM_SPELL_LEVEL_BY_CLASS_LEVEL:
        spell_lv = _ARCANUM_SPELL_LEVEL_BY_CLASS_LEVEL[new_level]
        steps.append(LevelStep(
            step_type=StepType.ARCANUM_SPELL,
            label=f"Arcanum Mistico — scegli un incantesimo di {spell_lv}° livello dalla lista del warlock",
            requires_player_choice=True,
            data={"spell_level": spell_lv},
        ))

    # 3. ASI — ai livelli appropriati per la classe
    asi_set = game_data.get_asi_levels(class_name)
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
