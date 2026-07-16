"""
game_data_loader.py — Caricamento e caching dei dati di gioco D&D 5e.

Espone il singleton `game_data` con accesso lazy ai JSON di classi, razze,
background, incantesimi ed equipaggiamento. Nessuna dipendenza da Flet.

Utilizzo:
    from data.game_data.game_data_loader import game_data

    cls   = game_data.get_class("barbaro")       # dict | None
    razze = game_data.get_all_races()             # list[dict]
    armi  = game_data.get_weapon_names(category="semplice")  # list[str]
    spell = game_data.get_spells("mago")          # list[dict]
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Directory contenente questo file — tutti i JSON sono relativi ad essa.
_DATA_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helper interno
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class GameDataLoader:
    """
    Singleton lazy-loading per i dati di gioco.

    Ogni categoria viene letta da disco la prima volta che viene richiesta,
    poi tenuta in memoria per tutta la durata della sessione.
    Le chiavi dei dizionari interni sono i *nome-file* in minuscolo (es. "barbaro",
    "alto_elfo"), che corrispondono direttamente allo stem del JSON.
    """

    def __init__(self) -> None:
        # dati grezzi: stem_file → dict
        self._classes:     dict[str, dict[str, Any]] = {}
        self._races:       dict[str, dict[str, Any]] = {}
        self._backgrounds: dict[str, dict[str, Any]] = {}
        # spell: class_name_lower → lista spell (risolta dal file master)
        self._spells: dict[str, list[dict[str, Any]]] = {}
        # file master condiviso: nome incantesimo (lower) → dati completi.
        # Fonte unica di verità per il TESTO degli incantesimi (school,
        # casting_time, range, components, material, duration, description,
        # higher_levels) — rispecchia la struttura del manuale stesso, che
        # elenca le descrizioni una sola volta in ordine alfabetico e separa
        # le liste per classe (solo nomi). Evita la duplicazione di testo
        # identico tra più file classe, stesso principio già applicato a
        # RACE_DATA/CLASSES/tags.json in precedenza in questo progetto.
        self._spell_master: dict[str, dict[str, Any]] | None = None
        # talenti PHB
        self._feats: list[dict[str, Any]] = []
        # invocazioni occulte Warlock
        self._invocations: list[dict[str, Any]] = []
        # equipaggiamento (Capitolo 5 PHB: armi, armature, strumenti, ecc.)
        # una entry per file: "weapons", "armor", "adventuring_gear", "tools",
        # "mounts_and_vehicles", "economy"
        self._equipment: dict[str, dict[str, Any]] = {}
        # progressioni slot incantesimo (full/half/pact caster) + mappa classe→tipo
        self._spell_slot_progressions: dict[str, Any] | None = None

        self._classes_loaded     = False
        self._races_loaded       = False
        self._backgrounds_loaded = False
        self._feats_loaded       = False
        self._invocations_loaded = False
        self._equipment_loaded: set[str] = set()

    # ------------------------------------------------------------------
    # Classi
    # ------------------------------------------------------------------

    def get_all_classes(self) -> list[dict[str, Any]]:
        """Tutti i dati di classe, ordinati per nome file."""
        self._ensure_classes()
        return list(self._classes.values())

    def get_class(self, name: str) -> dict[str, Any] | None:
        """
        Restituisce i dati della classe indicata o None.
        `name` può essere il nome file (es. "barbaro") o il campo "name"
        nel JSON (es. "Barbaro") — il confronto è case-insensitive.
        """
        self._ensure_classes()
        key = name.lower()
        if key in self._classes:
            return self._classes[key]
        # Fallback: cerca nel campo "name" del JSON
        for data in self._classes.values():
            if data.get("name", "").lower() == key:
                return data
        return None

    def get_class_names(self) -> list[str]:
        """Nomi leggibili di tutte le classi (campo 'name' del JSON)."""
        self._ensure_classes()
        return [d.get("name", k.capitalize()) for k, d in self._classes.items()]

    # Livelli ASI PHB standard — applicabile a tutte le classi tranne le 2
    # eccezioni esplicite (Guerriero, Ladro) che hanno un campo "asi_levels"
    # dedicato nel proprio JSON. Costante universale, non "dato di classe"
    # (nessuna delle 10 classi standard avrebbe motivo di un valore diverso
    # da questo — scriverlo in tutti e 10 i file sarebbe pura duplicazione
    # dello stesso letterale, non informazione nuova).
    _ASI_LEVELS_DEFAULT: set[int] = {4, 8, 12, 16, 19}

    def get_asi_levels(self, class_name: str) -> set[int]:
        """
        Livelli in cui la classe ottiene un ASI (Ability Score Improvement).
        Legge il campo "asi_levels" dal JSON di classe se presente (Guerriero,
        Ladro — le uniche 2 progressioni non standard PHB), altrimenti
        restituisce la progressione standard {4,8,12,16,19}.
        """
        cls_data = self.get_class(class_name)
        if cls_data and "asi_levels" in cls_data:
            return set(cls_data["asi_levels"])
        return set(self._ASI_LEVELS_DEFAULT)

    def get_spell_learn_delta(self, class_name: str) -> dict[int, int]:
        """
        Numero di nuovi incantesimi (non-trucchetti) appresi a ogni livello,
        per le classi "know" (Bardo/Ranger/Stregone/Warlock). Letto dal campo
        "spell_learn_delta" del JSON di classe (chiavi stringa nel JSON,
        convertite in int qui). Dizionario vuoto per le altre classi.
        Spostato da core/level_manager.py (_SPELL_LEARN_DELTA) il 2026-07-10
        — numeri già verificati pagina per pagina contro il PHB IT nelle
        sessioni di audit level-up, nessun valore cambiato in questa migrazione.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return {}
        return {int(k): v for k, v in cls_data.get("spell_learn_delta", {}).items()}

    def get_cantrips_known_at_1(self, class_name: str) -> int:
        """
        Trucchetti conosciuti al 1° livello, per le classi che ne concedono
        alla creazione (Bardo, Chierico, Druido, Mago, Stregone, Warlock —
        Paladino e Ranger non hanno trucchetti nel PHB). Letto dal campo
        "cantrips_known_at_1" del JSON di classe. 0 se assente (classe senza
        trucchetti, o non incantatrice).

        Dato trascritto/derivato dal testo delle rispettive feature "Incantesimi"
        / "Trucchetti" / "Magia del Patto" già presente nei JSON di classe
        (verificato pagina per pagina durante gli audit level-up precedenti;
        per il Bardo il valore non era scritto esplicitamente in prosa — è
        stato usato al suo posto per verifica incrociata, vedi
        get_spells_known_at_1()).
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return 0
        return int(cls_data.get("cantrips_known_at_1", 0) or 0)

    def get_spells_known_at_1(self, class_name: str) -> int:
        """
        Incantesimi (non trucchetti) conosciuti al 1° livello, solo per le
        classi "know" che scelgono una lista fissa alla creazione (Bardo,
        Stregone, Warlock — non i "preparatori" come Chierico/Druido/Paladino,
        che ogni giorno preparano dal pool completo della classe, né il Mago,
        che parte con un libro degli incantesimi — meccanica separata).
        Letto dal campo "spells_known_at_1" del JSON di classe. 0 se assente.

        Stregone e Warlock: valore confermato testualmente nella feature
        "Incantesimi"/"Magia del Patto" ("conosce due incantesimi di 1°
        livello a sua scelta"). Bardo: non è scritto esplicitamente in prosa
        nel JSON — ricavato per calcolo da due fatti già verificati contro
        il manuale in sessioni di audit precedenti: la tabella
        `spell_learn_delta["Bardo"]` (verificata pag.53, somma dei delta dal
        Lv.2 al Lv.20 = 18) e il totale finale confermato a Lv.20 = 22
        (vedi CLAUDE.md, audit level-up Bardo) → 22 − 18 = 4.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return 0
        return int(cls_data.get("spells_known_at_1", 0) or 0)

    def get_spellbook_starting_spells(self, class_name: str) -> int:
        """
        Numero di incantesimi di 1° livello con cui il libro degli
        incantesimi del Mago inizia alla creazione (task #100, 2026-07-11).
        Letto dal campo "spellbook_starting_spells" del JSON di classe
        (aggiunto in mago.json — 6, confermato testualmente dalla feature
        "Incantesimi": "Il tuo libro inizia con 6 incantesimi di 1°
        livello."). 0 per qualunque altra classe: questa è una meccanica
        distinta sia dai trucchetti/incantesimi "conosciuti" delle classi
        know (get_cantrips_known_at_1/get_spells_known_at_1) sia dalla
        scelta di incantesimi preparati iniziali dei "preparatori"
        (Chierico/Druido/Paladino) — il Mago prepara ogni giorno dal suo
        libro, non da un pool di classe illimitato, e il libro stesso
        cresce solo con nuove trascrizioni, non con una lista fissa.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return 0
        return int(cls_data.get("spellbook_starting_spells", 0) or 0)

    def get_metamagic_count_by_level(self) -> dict[int, int]:
        """Stregone, Metamagia: nuove opzioni acquisite a ciascun livello (PHB p.102)."""
        cls_data = self.get_class("stregone")
        if not cls_data:
            return {}
        return {int(k): v for k, v in cls_data.get("metamagic_count_by_level", {}).items()}

    def get_invocations_total_by_level(self) -> dict[int, int]:
        """Warlock, Suppliche Occulte: totale cumulativo conosciuto a ciascun livello (PHB p.114)."""
        cls_data = self.get_class("warlock")
        if not cls_data:
            return {}
        return {int(k): v for k, v in cls_data.get("invocations_total_by_level", {}).items()}

    def get_segreti_magici_levels(self) -> set[int]:
        """Bardo, Segreti Magici (progressione base, PHB p.55): livelli di innesco."""
        cls_data = self.get_class("bardo")
        if not cls_data:
            return set()
        return set(cls_data.get("segreti_magici_levels", []))

    def get_expertise_levels(self, class_name: str) -> set[int]:
        """
        Livelli di innesco della Maestria/Expertise (2 abilità aggiuntive)
        per la classe indicata (Ladro Lv1/6, Bardo Lv3/10). Insieme vuoto
        per le classi senza questa meccanica.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return set()
        return set(cls_data.get("expertise_levels", []))

    def get_bardic_inspiration_die(self, level: int) -> str:
        """
        Dado di Ispirazione Bardica per il livello indicato (PHB: d6 dal
        1°, d8 dal 5°, d10 dal 10°, d12 dal 15°). Letto da
        bardo.json → "bardic_inspiration_die_by_level" (già confermato dal
        testo della feature "Ispirazione Bardica" in sessioni precedenti —
        "Il dado diventa d8 al 5° livello, d10 al 10° e d12 al 15°").
        Restituisce "d6" come fallback se il campo manca o il livello è
        sotto la soglia minima.
        """
        cls_data = self.get_class("bardo")
        table: dict[str, str] = (cls_data or {}).get("bardic_inspiration_die_by_level", {})
        if not table:
            return "d6"
        best = "d6"
        for threshold_str in sorted(table.keys(), key=int):
            if level >= int(threshold_str):
                best = table[threshold_str]
        return best

    def get_sneak_attack_dice(self, level: int) -> str:
        """
        Dado di danno dell'Attacco Furtivo del Ladro al livello indicato.
        Letto da ladro.json → "sneak_attack_dice_by_level" — tabella "Ladro"
        del PHB IT (colonna "Attacco Furtivo"), trascritta da una foto della
        pagina fornita da Davide il 2026-07-10: 1d6 al 1°, +1d6 ogni 2 livelli
        (3°,5°,7°,9°,11°,13°,15°,17°,19°), fino a 10d6 al 19°-20°.
        Restituisce "1d6" come fallback se il campo manca o il livello è
        sotto la soglia minima.
        """
        cls_data = self.get_class("ladro")
        table: dict[str, str] = (cls_data or {}).get("sneak_attack_dice_by_level", {})
        if not table:
            return "1d6"
        best = "1d6"
        for threshold_str in sorted(table.keys(), key=int):
            if level >= int(threshold_str):
                best = table[threshold_str]
        return best

    def get_class_saving_throws(self, class_name: str) -> list[str]:
        """
        Nomi italiani completi (es. ["Forza", "Costituzione"]) dei tiri
        salvezza competenti della classe, letti dal campo "saving_throws"
        (chiavi brevi es. "str") del JSON di classe. Lista vuota se la
        classe non viene trovata.
        """
        # Import locale per evitare un giro di import a livello di modulo
        # (config.settings non dipende da questo modulo, quindi è sicuro,
        # ma teniamolo locale per chiarezza sulla direzione della dipendenza).
        from config.settings import ABILITY_KEYS, ABILITY_SCORES

        cls_data = self.get_class(class_name)
        if not cls_data:
            return []
        key_to_label: dict[str, str] = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
        result: list[str] = []
        for raw_key in cls_data.get("saving_throws", []):
            k = str(raw_key)
            result.append(key_to_label.get(k, k.upper()))
        return result

    def get_fighting_styles(self, class_name: str) -> list[str]:
        """
        Nomi degli stili di combattimento disponibili per la classe indicata
        (Guerriero, Paladino, Ranger). Guerriero ha la lista canonica completa
        in `fighting_style_details`; Paladino/Ranger hanno un `options` sul
        proprio feature "Stile di Combattimento" con il sottoinsieme applicabile.
        Lista vuota per classi senza stili di combattimento.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return []
        if "fighting_style_details" in cls_data:
            return [s.get("name", "") for s in cls_data["fighting_style_details"] if s.get("name")]
        for feat in cls_data.get("features", []):
            if feat.get("name") == "Stile di Combattimento" and feat.get("options"):
                return [o.get("name", "") for o in feat["options"] if o.get("name")]
        return []

    def get_fighting_style_data(self, class_name: str) -> list[dict[str, Any]]:
        """
        Stili di combattimento disponibili per la classe indicata, come dict
        completi {"name","description"} — aggiunto il 2026-07-16 per il
        widget ⓘ del level-up (task #24). Il Guerriero ha sempre la
        descrizione completa in `fighting_style_details`; Paladino/Ranger
        hanno solo `name` nelle proprie `options` (nessuna description propria
        nel JSON) — in quel caso si risolve comunque la descrizione completa
        dalla lista canonica del Guerriero, stesso identico stile PHB.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return []
        if "fighting_style_details" in cls_data:
            return cls_data["fighting_style_details"]
        names: list[str] = []
        for feat in cls_data.get("features", []):
            if feat.get("name") == "Stile di Combattimento" and feat.get("options"):
                names = [o.get("name", "") for o in feat["options"] if o.get("name")]
                break
        if not names:
            return []
        guerriero_data = self.get_class("guerriero") or {}
        canonical = {
            s.get("name", ""): s for s in guerriero_data.get("fighting_style_details", [])
        }
        return [canonical[n] for n in names if n in canonical]

    def get_metamagic_options(self) -> list[str]:
        """Nomi delle 8 opzioni di Metamagia dello Stregone (PHB)."""
        return [o.get("name", "") for o in self.get_metamagic_option_data() if o.get("name")]

    def get_metamagic_option_data(self) -> list[dict[str, Any]]:
        """
        Le 8 opzioni di Metamagia dello Stregone come dict completi
        {"name","description"} — aggiunto il 2026-07-16 per poter mostrare la
        descrizione nel widget ⓘ del level-up (task #24), senza scartare il
        campo "description" come faceva `get_metamagic_options()`.
        """
        cls_data = self.get_class("stregone")
        if not cls_data:
            return []
        for feat in cls_data.get("features", []):
            if feat.get("name") == "Metamagia" and feat.get("options"):
                return feat["options"]
        return []

    def get_pact_boons(self) -> list[str]:
        """Nomi dei 3 Doni del Patto del Warlock (PHB)."""
        return [o.get("name", "") for o in self.get_pact_boon_data() if o.get("name")]

    def get_pact_boon_data(self) -> list[dict[str, Any]]:
        """I 3 Doni del Patto del Warlock come dict completi {"name","description"}."""
        cls_data = self.get_class("warlock")
        if not cls_data:
            return []
        for feat in cls_data.get("features", []):
            if feat.get("name") == "Dono del Patto" and feat.get("options"):
                return feat["options"]
        return []

    def get_totem_animals(self) -> list[str]:
        """
        Nomi dei 3 animali totem del Barbaro (Combattente Totemico, PHB p.10).
        A differenza degli altri metodi di questa sezione, i 3 nomi non sono
        letti da un campo strutturato di barbaro.json: sono già scritti per
        esteso nella description della feature "Spirito Totemico" di quel
        file ("Scegli un totem: Orso, Aquila o Lupo...") e Davide ha chiesto
        esplicitamente (2026-07-09) di non aggiungere lì un array parallelo
        con gli stessi 3 nomi (duplicazione pura, zero informazione nuova —
        diverso dal caso Paladino/Ranger, dove "options" seleziona un
        sottoinsieme dagli stili del Guerriero, dato non altrimenti
        ricavabile). Nomi fissi PHB, non cambiano tra edizioni italiane.
        """
        return ["Orso", "Aquila", "Lupo"]

    def get_land_terrains(self) -> list[str]:
        """
        Nomi degli 8 terreni del Druido (Circolo della Terra, PHB), letti
        dalle chiavi di `circle_spells` nella sottoclasse.
        """
        cls_data = self.get_class("druido")
        if not cls_data:
            return []
        for sc in cls_data.get("subclasses", []):
            if "circle_spells" in sc:
                return list(sc["circle_spells"].keys())
        return []

    def get_mago_cantrips(self) -> list[str]:
        """
        Nomi dei 16 trucchetti del Mago (per la scelta razziale dell'Alto
        Elfo), letti direttamente da spells/incantesimi_mago.json (livello 0)
        — unica fonte dato per gli incantesimi, nessuna copia nel JSON di
        classe. I nomi sono già stati verificati contro il manuale (vedi
        `_cantrips_note` in incantesimi_mago.json); le descrizioni complete
        di questi trucchetti restano da aggiungere con l'audit dedicato di
        quel file (Checklist Revisione Dati PHB in CLAUDE.md).
        """
        return [s["name"] for s in self.get_spells_by_level("mago", 0) if s.get("name")]

    def get_subclass_data(self, class_name: str, subclass_name: str) -> dict[str, Any] | None:
        """
        Restituisce il blocco dati di una sottoclasse (dict grezzo del JSON),
        cercato per nome esatto (case-insensitive) dentro cls_data["subclasses"].
        None se la classe o la sottoclasse non esistono.

        Aggiunto per il fix Mistificatore Arcano (Ladro)/Cavaliere Mistico
        (Guerriero) — 2026-07-15 — ma generico, utilizzabile per qualunque
        altra sottoclasse in futuro.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return None
        key = subclass_name.strip().lower()
        for sc in cls_data.get("subclasses", []):
            if sc.get("name", "").strip().lower() == key:
                return sc
        return None

    def get_subclass_bonus_proficiencies(self, class_name: str, subclass_name: str) -> list[Any]:
        """
        Restituisce la lista grezza `bonus_proficiencies` di una sottoclasse
        (dict del JSON), o [] se assente/sottoclasse non trovata. Ogni voce
        è o una stringa (token armatura/arma bare — "leggere"/"medie"/
        "pesanti"/"scudi"/"semplice"/"semplice_mischia"/"guerra"/
        "guerra_mischia", stessa convenzione di `armor_proficiencies`/
        `weapon_proficiencies` a livello di classe — oppure un nome
        letterale di competenza, es. uno strumento) o un dict
        `{"type":"choice","count":N,"from":[...]|"any_skill"}` che richiede
        una scelta del giocatore prima di poter essere applicata.

        Aggiunto il 2026-07-16 insieme alla normalizzazione dei vecchi tag
        `#armature_pesanti`/ecc. in `chierico.json`/`bardo.json` — vedi
        `character_repo.classify_bonus_proficiency_entries()` per il
        parsing e l'applicazione effettiva al personaggio.
        """
        sc = self.get_subclass_data(class_name, subclass_name)
        return list(sc.get("bonus_proficiencies", [])) if sc else []

    def get_borrowed_caster_subclass_name(self, class_name: str) -> str:
        """
        Nome della sottoclasse che concede casting "preso in prestito dal
        Mago" per la classe indicata (es. "Mistificatore Arcano" per
        "Ladro"), rilevato cercando quale sottoclasse ha un campo
        "spell_progression" — stringa vuota se la classe non ne ha nessuna.
        Evita di duplicare in UI (profilo_tab.py) una mappa classe→
        sottoclasse scritta a mano: unica fonte è il JSON di classe stesso.
        """
        cls_data = self.get_class(class_name)
        if not cls_data:
            return ""
        for sc in cls_data.get("subclasses", []):
            if "spell_progression" in sc:
                return sc.get("name", "")
        return ""

    def get_borrowed_caster_data(self, class_name: str, subclass_name: str) -> dict[str, Any] | None:
        """
        Dati di "casting preso in prestito dal Mago" per Mistificatore Arcano
        (Ladro) e Cavaliere Mistico (Guerriero) — le uniche 2 sottoclassi PHB
        che concedono incantesimi a una classe senza spellcasting_ability
        propria. Restituisce None per qualunque altra combinazione classe/
        sottoclasse (nessun casting da gestire con questo meccanismo).

        Il dict ritornato è il blocco sottoclasse stesso: contiene già
        "spellcasting_ability", "cantrip_options", "spell_progression"
        (lista {level, cantrips_known, spells_known, slots}), oltre ai 3
        campi aggiunti il 2026-07-15 per questo fix: "fixed_cantrip" (solo
        Ladro — "Mano Magica"), "restricted_schools" (le 2 scuole vincolate),
        "unrestricted_origin_levels" (livelli il cui incantesimo può essere
        di qualsiasi scuola — asimmetrico tra le due sottoclassi, vedi
        CLAUDE.md: Ladro [8,14,20], Guerriero [3,8,14,20], verificato
        testualmente contro il PHB IT, non un refuso di trascrizione).
        """
        sc = self.get_subclass_data(class_name, subclass_name)
        if not sc or "spell_progression" not in sc:
            return None
        return sc

    def get_borrowed_caster_progression_for_level(
        self, class_name: str, subclass_name: str, level: int
    ) -> dict[str, Any] | None:
        """
        Riga di spell_progression per il livello indicato (o l'ultima riga
        <= level se il livello esatto non è presente — non dovrebbe succedere
        con i dati attuali, che coprono 3-20 senza buchi, ma per sicurezza).
        None se il personaggio non ha ancora raggiunto subclass_choice_level
        (nessun casting) o la sottoclasse non è una delle 2 gestite.
        """
        sc = self.get_borrowed_caster_data(class_name, subclass_name)
        if not sc:
            return None
        rows = sc.get("spell_progression", [])
        best: dict[str, Any] | None = None
        for row in rows:
            if row.get("level", 0) <= level:
                if best is None or row.get("level", 0) > best.get("level", 0):
                    best = row
        return best

    def _ensure_spell_slot_progressions(self) -> None:
        """
        Carica pigramente spell_slot_progressions.json: le 3 tabelle PHB
        (full/half/pact caster) + la mappa classe→tipo di incantatore.
        Numeri già verificati contro il manuale in sessioni di audit
        precedenti (vedi CLAUDE.md) — questo file è solo la loro
        rappresentazione JSON, spostata da data/repositories/character_repo.py
        per evitare di avere dati PHB scritti a mano solo in Python.
        """
        if self._spell_slot_progressions is not None:
            return
        path = _DATA_DIR / "spell_slot_progressions.json"
        try:
            self._spell_slot_progressions = _load_json(path)
        except Exception as exc:
            logger.error("Errore caricamento spell_slot_progressions.json: %s", exc)
            self._spell_slot_progressions = {
                "caster_type_by_class": {}, "full_caster": [], "half_caster": [], "warlock": [],
            }

    def get_caster_type(self, class_name: str) -> str:
        """
        Restituisce "full" / "half" / "pact" per le classi incantatrici PHB,
        stringa vuota per le classi che non lanciano incantesimi a livello
        base (Barbaro, Guerriero, Ladro, Monaco — anche se possono ottenere
        casting da sottoclasse, gestito separatamente da spell_progression).
        """
        self._ensure_spell_slot_progressions()
        assert self._spell_slot_progressions is not None
        return self._spell_slot_progressions["caster_type_by_class"].get(class_name.strip().lower(), "")

    def get_spell_slot_table(self, caster_type: str) -> list[list[int]]:
        """
        Tabella slot incantesimo PHB per il tipo di incantatore indicato
        ("full" | "half" | "pact"). Indice 0 = Lv.1 ... indice 19 = Lv.20.
        Lista vuota se il tipo non è riconosciuto.
        """
        self._ensure_spell_slot_progressions()
        assert self._spell_slot_progressions is not None
        key = {"full": "full_caster", "half": "half_caster", "pact": "warlock"}.get(caster_type, "")
        return self._spell_slot_progressions.get(key, [])

    def _ensure_classes(self) -> None:
        if self._classes_loaded:
            return
        self._classes_loaded = True
        classes_dir = _DATA_DIR / "classes"
        if not classes_dir.is_dir():
            logger.warning("Directory classi non trovata: %s", classes_dir)
            return
        for path in sorted(classes_dir.glob("*.json")):
            try:
                self._classes[path.stem] = _load_json(path)
                logger.debug("Classe caricata: %s", path.stem)
            except Exception as exc:
                logger.error("Errore caricamento classe '%s': %s", path.name, exc)

    # ------------------------------------------------------------------
    # Razze
    # ------------------------------------------------------------------

    def get_all_races(self) -> list[dict[str, Any]]:
        """Tutti i dati di razza, ordinati per nome file."""
        self._ensure_races()
        return list(self._races.values())

    def get_race(self, name: str) -> dict[str, Any] | None:
        """
        Restituisce i dati della razza indicata o None.
        Confronto case-insensitive sul nome file e sul campo 'name'.
        """
        self._ensure_races()
        key = name.lower()
        if key in self._races:
            return self._races[key]
        for data in self._races.values():
            if data.get("name", "").lower() == key:
                return data
        return None

    def get_race_names(self) -> list[str]:
        """Nomi leggibili di tutte le razze."""
        self._ensure_races()
        return [d.get("name", k.capitalize()) for k, d in self._races.items()]

    def get_resolved_race(
        self, race_name: str, subrace_name: str = ""
    ) -> dict[str, Any]:
        """
        Restituisce i dati di razza "risolti", con i bonus di caratteristica
        di razza base e sottorazza già sommati e velocità/scurovisione già
        determinate secondo l'eventuale override della sottorazza.

        Unica fonte dato: i JSON in `data/game_data/races/`. Non fa mai
        riferimento a dataset scritti a mano — questo è il punto di accesso
        da usare ovunque serva applicare o mostrare bonus razziali (creazione
        personaggio, tab Esplorazione/Profilo), al posto di duplicare i dati
        altrove.

        `race_name` può essere il nome della razza base (es. "Elfo") oppure,
        per tolleranza, direttamente il nome di una sottorazza (es. "Elfo
        Alto") — in quel caso la razza base e la sottorazza vengono dedotte
        automaticamente senza bisogno di passare `subrace_name`.

        Ritorna sempre un dizionario con chiavi:
            ability_bonuses:      dict[str, int]  — bonus sommati base+sottorazza
            ability_bonuses_flex: dict | int       — regola di scelta libera (0 se assente)
            speed:                float
            darkvision:            float           — 0 se assente
            size:                 str
            languages:            list
            traits:               list[dict]       — tratti base + tratti sottorazza,
                                                       ognuno {"name": str, "description": str, ...}

        Se la razza non viene trovata, ritorna valori di default neutri
        (nessun bonus, velocità 9m, nessuna scurovisione) anziché sollevare
        un'eccezione, per non far crashare la UI su dati mancanti/in transizione.
        """
        self._ensure_races()

        def _default() -> dict[str, Any]:
            return {
                "ability_bonuses": {},
                "ability_bonuses_flex": 0,
                "speed": 9,
                "darkvision": 0,
                "size": "Media",
                "languages": [],
                "traits": [],
            }

        race_data = self.get_race(race_name)
        resolved_subrace_name = subrace_name

        # Tolleranza: race_name potrebbe già essere il nome di una sottorazza
        # (es. chiamanti che passano solo "Elfo Alto" senza razza base separata).
        if race_data is None:
            needle = race_name.lower().strip()
            for candidate in self._races.values():
                for sr in candidate.get("subraces", []):
                    if sr.get("name", "").lower() == needle:
                        race_data = candidate
                        resolved_subrace_name = sr.get("name", "")
                        break
                if race_data:
                    break

        if race_data is None:
            return _default()

        ability_bonuses: dict[str, int] = dict(race_data.get("ability_bonuses", {}))
        ability_bonuses_flex = race_data.get("ability_bonuses_flex", 0)
        speed = race_data.get("speed", 9)
        darkvision = race_data.get("darkvision", 0) or 0
        size = race_data.get("size", "Media")
        languages = list(race_data.get("languages", []))
        traits: list[dict[str, Any]] = list(race_data.get("traits", []))

        norm = (resolved_subrace_name or "").lower().strip()
        if norm:
            for sr in race_data.get("subraces", []):
                sr_name = sr.get("name", "").lower()
                if sr_name == norm or norm in sr_name or sr_name in norm:
                    for stat_key, bonus in sr.get("ability_bonuses", {}).items():
                        ability_bonuses[stat_key] = ability_bonuses.get(stat_key, 0) + bonus
                    if "ability_bonuses_flex" in sr:
                        ability_bonuses_flex = sr["ability_bonuses_flex"]
                    if "speed" in sr:
                        speed = sr["speed"]
                    if "darkvision" in sr:
                        darkvision = sr["darkvision"] or 0
                    traits = traits + list(sr.get("traits", []))
                    break

        return {
            "ability_bonuses": ability_bonuses,
            "ability_bonuses_flex": ability_bonuses_flex,
            "speed": speed,
            "darkvision": darkvision,
            "size": size,
            "languages": languages,
            "traits": traits,
        }

    def get_racial_innate_spells(
        self, race_name: str, subrace_name: str = ""
    ) -> list[dict[str, Any]]:
        """
        Incantesimi innati concessi da un tratto di razza (es. Drow "Magia
        Drow", Tiefling "Eredità Infernale") — PHB IT: lanciabili senza
        preparazione, senza slot, indipendentemente dalla classe del
        personaggio, con CD calcolata su Carisma fisso (task #15, 2026-07-16
        — TODO storico "Incantesimi razziali di Drow/Tiefling mai realmente
        utilizzabili").

        Legge il campo strutturato `"innate_spells"` presente dentro i
        singoli tratti in `data/game_data/races/*.json` (dato aggiunto in
        questa sessione, non inventato: trascrive in forma di dati la stessa
        prosa già presente e verificata nel tratto — es. "Magia Drow"/
        "Eredità Infernale" — nessun nuovo fatto di regolamento introdotto).
        Non tocca `traits`/`resources`, che restano l'unica fonte per la
        descrizione testuale e per il contatore utilizzi già gestito in
        Combattimento.

        Ogni voce ritornata ha le chiavi:
            name:          str  — nome esatto dell'incantesimo
            cast_level:    int  — livello a cui viene lanciato (0 = trucchetto;
                                  può differire dal livello base dell'incantesimo,
                                  es. Intimorire Infernale del Tiefling è
                                  lanciato come incantesimo di 2° livello)
            min_char_level: int — livello personaggio da cui il tratto è attivo
            uses:          str  — "at_will" oppure "1_per_long_rest"
            ability:       str  — chiave caratteristica per la CD ("cha")
            resource_name: str  — nome esatto della risorsa già tracciata in
                                  class_resources (per incrociare lo stato
                                  "disponibile/usata" mostrato in Combattimento),
                                  vuoto per gli "at_will"
        """
        resolved = self.get_resolved_race(race_name, subrace_name)
        out: list[dict[str, Any]] = []
        for trait in resolved.get("traits", []):
            out.extend(trait.get("innate_spells", []))
        return out

    def _ensure_races(self) -> None:
        if self._races_loaded:
            return
        self._races_loaded = True
        races_dir = _DATA_DIR / "races"
        if not races_dir.is_dir():
            logger.warning("Directory razze non trovata: %s", races_dir)
            return
        for path in sorted(races_dir.glob("*.json")):
            try:
                self._races[path.stem] = _load_json(path)
                logger.debug("Razza caricata: %s", path.stem)
            except Exception as exc:
                logger.error("Errore caricamento razza '%s': %s", path.name, exc)

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------

    def get_all_backgrounds(self) -> list[dict[str, Any]]:
        """Tutti i dati di background, ordinati per nome file."""
        self._ensure_backgrounds()
        return list(self._backgrounds.values())

    def get_background(self, name: str) -> dict[str, Any] | None:
        """
        Restituisce i dati del background indicato o None.
        Confronto case-insensitive sul nome file e sul campo 'name'.
        """
        self._ensure_backgrounds()
        key = name.lower()
        if key in self._backgrounds:
            return self._backgrounds[key]
        for data in self._backgrounds.values():
            if data.get("name", "").lower() == key:
                return data
        return None

    def get_background_names(self) -> list[str]:
        """Nomi leggibili di tutti i background."""
        self._ensure_backgrounds()
        return [d.get("name", k.capitalize()) for k, d in self._backgrounds.items()]

    def _ensure_backgrounds(self) -> None:
        if self._backgrounds_loaded:
            return
        self._backgrounds_loaded = True
        bg_dir = _DATA_DIR / "backgrounds"
        if not bg_dir.is_dir():
            logger.warning("Directory backgrounds non trovata: %s", bg_dir)
            return
        for path in sorted(bg_dir.glob("*.json")):
            try:
                data = _load_json(path)
                if data.get("_deprecated"):
                    logger.debug("Background '%s' deprecato, ignorato", path.stem)
                    continue
                self._backgrounds[path.stem] = data
                logger.debug("Background caricato: %s", path.stem)
            except Exception as exc:
                logger.error("Errore caricamento background '%s': %s", path.name, exc)

    # ------------------------------------------------------------------
    # Incantesimi
    # ------------------------------------------------------------------

    def _ensure_spell_master(self) -> dict[str, dict[str, Any]]:
        """
        Carica (lazy, una sola volta) il file master `incantesimi_completi.json`
        — dizionario {nome_esatto_da_manuale: {dati completi}}. Ritorna un
        dizionario chiave-lower per lookup case-insensitive.
        """
        if self._spell_master is None:
            path = _DATA_DIR / "spells" / "incantesimi_completi.json"
            self._spell_master = {}
            if path.exists() and path.stat().st_size > 0:
                try:
                    data = _load_json(path)
                    raw = data.get("spells", data) if isinstance(data, dict) else {}
                    for name, entry in raw.items():
                        merged = {**entry, "name": entry.get("name", name)}
                        self._spell_master[name.lower()] = merged
                    logger.debug(
                        "File master incantesimi caricato: %d voci",
                        len(self._spell_master),
                    )
                except Exception as exc:
                    logger.error("Errore caricamento incantesimi_completi.json: %s", exc)
        return self._spell_master

    def get_spells(self, class_name: str) -> list[dict[str, Any]]:
        """
        Restituisce la lista degli incantesimi per la classe indicata.

        File atteso: spells/incantesimi_{class_name_lower}.json — contiene
        SOLO la lista dei nomi conosciuti da questa classe (rispecchia le
        liste per classe del Capitolo 11 del manuale, pag.207-211). Il testo
        completo di ogni incantesimo viene risolto dal file master condiviso
        `incantesimi_completi.json` (stessa fonte per tutte le classi, così
        un incantesimo condiviso come "Cura Ferite" viene trascritto/corretto
        una sola volta invece che in ogni file classe separatamente).

        Un nome presente nella lista di classe ma non ancora nel file master
        (trascrizione in corso) viene scartato silenziosamente con un debug
        log, invece di rompere l'app con un KeyError.

        Restituisce lista vuota se il file non esiste o la classe non è
        incantatrice.
        """
        key = class_name.lower()
        if key not in self._spells:
            path = _DATA_DIR / "spells" / f"incantesimi_{key}.json"
            names: list[str] = []
            if path.exists() and path.stat().st_size > 0:
                try:
                    data = _load_json(path)
                    # Supporta lista diretta di nomi, {"spells": ["Nome", ...]}
                    # o (formato legacy pre-refactor) {"spells": [{"name":...}]}
                    raw = data if isinstance(data, list) else data.get("spells", [])
                    for item in raw:
                        if isinstance(item, str):
                            names.append(item)
                        elif isinstance(item, dict) and item.get("name"):
                            names.append(item["name"])
                except Exception as exc:
                    logger.error(
                        "Errore caricamento incantesimi '%s': %s", path.name, exc
                    )
            else:
                logger.debug("Nessun file incantesimi per classe '%s'", class_name)

            master = self._ensure_spell_master()
            resolved: list[dict[str, Any]] = []
            for name in names:
                entry = master.get(name.lower())
                if entry is not None:
                    resolved.append(entry)
                else:
                    logger.debug(
                        "Incantesimo '%s' (classe %s) non ancora nel file master",
                        name, class_name,
                    )
            self._spells[key] = resolved
            logger.debug(
                "Incantesimi risolti per '%s': %d/%d", class_name, len(resolved), len(names)
            )
        return self._spells[key]

    def get_spells_by_level(
        self, class_name: str, level: int
    ) -> list[dict[str, Any]]:
        """
        Sottolista di incantesimi filtrata per livello.
        Utile per visualizzare slot per livello nella sezione Incantesimi.
        """
        return [s for s in self.get_spells(class_name) if s.get("level") == level]

    def get_spell_by_name(
        self, name: str, class_name: str | None = None
    ) -> dict[str, Any] | None:
        """
        Cerca un incantesimo per nome (confronto case-insensitive).
        Se class_name è specificato, cerca prima in quella classe per efficienza.
        Poi cerca in tutte le classi incantatrici PHB.
        Restituisce il primo match o None se non trovato.
        """
        _ALL_SPELL_CLASSES = [
            "chierico", "bardo", "druido", "mago",
            "paladino", "ranger", "stregone", "warlock",
        ]
        name_lower = name.lower()
        classes_to_search: list[str] = []
        if class_name:
            classes_to_search.append(class_name.lower())
        for cls in _ALL_SPELL_CLASSES:
            if cls not in classes_to_search:
                classes_to_search.append(cls)
        for cls in classes_to_search:
            for spell in self.get_spells(cls):
                if spell.get("name", "").lower() == name_lower:
                    return spell
        return None

    def get_spell_master_entry(self, name: str) -> dict[str, Any] | None:
        """
        Cerca un incantesimo per nome ESCLUSIVAMENTE nel file master
        `incantesimi_completi.json` (361 incantesimi PHB), a prescindere da
        quali classi lo abbiano nella propria lista — a differenza di
        `get_spell_by_name()`, che cerca solo tra gli incantesimi già
        presenti nei file `classes/incantesimi_*.json`.

        Usato per gli incantesimi innati di razza (Drow "Magia Drow",
        Tiefling "Eredità Infernale" — task #15, 2026-07-16): sono
        incantesimi noti per tratto razziale, non per lista di classe,
        quindi il lookup deve funzionare anche se, per assurdo, nessuna
        classe li avesse nella propria lista.
        """
        master = self._ensure_spell_master()
        return master.get(name.lower())

    def get_expanded_spells(self, class_name: str, subclass_name: str) -> list[dict[str, Any]]:
        """
        Lista Incantesimi Ampliata di una sottoclasse (Warlock: Il Signore
        Fatato/L'Immondo/Il Grande Antico, `bonus_proficiencies`... no,
        campo `expanded_spells` in classes/warlock.json — dict con chiavi
        "1".."5" = livello slot, ognuna con 2 nomi incantesimo) — task #25,
        2026-07-16. A differenza degli incantesimi sempre pronti di
        Dominio/Giuramento/Circolo (vedi `sync_bonus_domain_spells` in
        character_repo.py), la Lista Ampliata NON concede incantesimi
        gratuiti: aggiunge solo nomi al POOL tra cui il Warlock può
        scegliere quando impara un nuovo incantesimo (creazione,
        SPELL_LEARN, SPELL_SWAP) — il giocatore deve comunque "spendere"
        uno dei suoi incantesimi conosciuti su di essi, PHB p.114 "Lista
        Incantesimi Ampliata: [...] questi incantesimi sono considerati
        incantesimi da warlock per il [patrono], ma non contano ai fini del
        numero di incantesimi da warlock che il personaggio conosce".

        Risolve ogni nome contro il file master (`get_spell_master_entry`,
        non `get_spell_by_name` — questi incantesimi per definizione NON
        sono nella lista base del Warlock, quindi un lookup ristretto alla
        classe non li troverebbe mai). Nomi non ancora presenti nel master
        vengono scartati silenziosamente con un debug log, stesso
        trattamento già riservato a `get_spells()` per una trascrizione in
        corso — non un errore per l'utente finale.

        Restituisce [] se la sottoclasse non esiste o non ha
        `expanded_spells` (qualunque sottoclasse di qualunque classe,
        generico — oggi solo le 3 sottoclassi Warlock lo hanno).
        """
        sc = self.get_subclass_data(class_name, subclass_name)
        expanded = (sc or {}).get("expanded_spells") or {}
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _slot_level, names in expanded.items():
            for name in names or []:
                if name in seen:
                    continue
                entry = self.get_spell_master_entry(name)
                if entry is not None:
                    result.append(entry)
                    seen.add(name)
                else:
                    logger.debug(
                        "Incantesimo Lista Ampliata '%s' (%s/%s) non ancora nel file master",
                        name, class_name, subclass_name,
                    )
        result.sort(key=lambda s: (s.get("level", 0), s.get("name", "")))
        return result

    def get_spellcasting_class_names(self) -> list[str]:
        """
        Nomi (con maiuscola, es. "Bardo") delle classi che hanno una propria
        lista di incantesimi (i file spells/incantesimi_{classe}.json
        esistenti e non vuoti) — aggiunto il 2026-07-16 per il picker
        "Incantesimi Bonus" di spells_view.py, che deve poter offrire la
        scelta della lista di provenienza a QUALSIASI personaggio, anche una
        classe non incantatrice (es. un Guerriero che riceve un incantesimo
        bonus concesso dal master). Calcolato dinamicamente (non una lista
        scritta a mano) per restare sempre coerente con quali file
        spells/incantesimi_*.json esistono davvero.
        """
        _ALL_SPELL_CLASSES = [
            "chierico", "bardo", "druido", "mago",
            "paladino", "ranger", "stregone", "warlock",
        ]
        result: list[str] = []
        for key in _ALL_SPELL_CLASSES:
            if self.get_spells(key):
                cls_data = self.get_class(key)
                result.append(cls_data.get("name", key.capitalize()) if cls_data else key.capitalize())
        return result

    # ------------------------------------------------------------------
    # Talenti (Feats)
    # ------------------------------------------------------------------

    def get_feats(self) -> list[dict[str, Any]]:
        """
        Lista completa dei talenti PHB.
        Restituisce lista vuota finché feats.json non viene compilato.
        """
        self._ensure_feats()
        return self._feats

    def get_feat_names(self) -> list[str]:
        """Nomi di tutti i talenti disponibili, ordinati alfabeticamente."""
        return sorted(f["name"] for f in self.get_feats() if f.get("name"))

    def get_feat(self, name: str) -> dict[str, Any] | None:
        """Restituisce i dati di un talento per nome esatto, o None se non trovato."""
        self._ensure_feats()
        return next((f for f in self._feats if f.get("name") == name), None)

    # ------------------------------------------------------------------
    # Invocazioni Occulte (Warlock)
    # ------------------------------------------------------------------

    def get_invocations(self, warlock_level: int = 20) -> list[dict[str, Any]]:
        """
        Lista invocazioni disponibili filtrate per livello Warlock.
        Restituisce lista vuota finché invocations.json non è compilato.
        """
        self._ensure_invocations()
        return [
            inv for inv in self._invocations
            if inv.get("prerequisite_level", 0) <= warlock_level
        ]

    def get_invocation_names(self, warlock_level: int = 20) -> list[str]:
        """Nomi delle invocazioni disponibili a quel livello, ordinati."""
        return sorted(i["name"] for i in self.get_invocations(warlock_level) if i.get("name"))

    def _ensure_invocations(self) -> None:
        if self._invocations_loaded:
            return
        self._invocations_loaded = True
        path = _DATA_DIR / "invocations.json"
        try:
            data = _load_json(path)
            self._invocations = data.get("invocations", [])
            logger.debug("Invocazioni caricate: %d", len(self._invocations))
        except Exception as exc:
            logger.error("Errore caricamento invocations.json: %s", exc)
            self._invocations = []

    def _ensure_feats(self) -> None:
        if self._feats_loaded:
            return
        self._feats_loaded = True
        path = _DATA_DIR / "feats.json"
        try:
            data = _load_json(path)
            self._feats = data.get("feats", [])
            logger.debug("Talenti caricati: %d", len(self._feats))
        except Exception as exc:
            logger.error("Errore caricamento feats.json: %s", exc)
            self._feats = []

    # ------------------------------------------------------------------
    # Equipaggiamento (Capitolo 5 PHB — armi, armature, strumenti, ecc.)
    # ------------------------------------------------------------------

    def get_weapons(self) -> dict[str, Any]:
        """Dizionario grezzo di equipment/weapons.json (regole + le 4 liste per categoria)."""
        self._ensure_equipment_file("weapons")
        return self._equipment["weapons"]

    def get_weapon(self, name: str) -> dict[str, Any] | None:
        """Cerca un'arma per nome esatto (case-insensitive) in tutte e 4 le liste."""
        needle = name.lower()
        weapons = self.get_weapons()
        for key in ("semplici_mischia", "semplici_distanza", "guerra_mischia", "guerra_distanza"):
            for w in weapons.get(key, []):
                if w.get("name", "").lower() == needle:
                    return w
        return None

    def get_weapon_names(self, category: str | None = None, range_type: str | None = None) -> list[str]:
        """
        Nomi delle armi, filtrabili per categoria ("semplice"|"guerra") e/o
        per tipo di gittata ("mischia"|"distanza") tramite i campi espliciti
        "category"/"range_type" di ogni arma. Senza filtri restituisce tutte
        e 37 le armi PHB.
        """
        weapons = self.get_weapons()
        result: list[str] = []
        for key in ("semplici_mischia", "semplici_distanza", "guerra_mischia", "guerra_distanza"):
            for w in weapons.get(key, []):
                if category and w.get("category") != category:
                    continue
                if range_type and w.get("range_type") != range_type:
                    continue
                if w.get("name"):
                    result.append(w["name"])
        return result

    def get_armor(self) -> dict[str, Any]:
        """Dizionario grezzo di equipment/armor.json (regole + leggere/medie/pesanti/scudi)."""
        self._ensure_equipment_file("armor")
        return self._equipment["armor"]

    _ARMOR_TYPE_BY_KEY = {
        "leggere": "leggera",
        "medie": "media",
        "pesanti": "pesante",
        "scudi": "scudo",
    }

    def get_armor_item(self, name: str) -> dict[str, Any] | None:
        """
        Cerca un'armatura o uno scudo per nome esatto (case-insensitive) in
        equipment/armor.json, attraversando tutte e 4 le liste (leggere/
        medie/pesanti/scudi). Il dict ritornato è una copia della voce
        originale con due campi aggiuntivi già risolti, pronti per
        `character_repo.create_inventory_item(ca_value=..., armor_type=...)`:

        - "armor_type": "leggera"|"media"|"pesante"|"scudo" (dedotto dalla
          lista di provenienza, non da un campo del JSON — armor.json non
          lo aveva perché pensato per sola consultazione, non per essere
          risolto a runtime da un nome).
        - "ca_value": intero base da sommare secondo la formula PHB già
          implementata in `calculate_and_update_ca()` (leggera=ca_value+DEX,
          media=ca_value+min(DEX,2), pesante=ca_value, scudo=+ca_value).
          Per gli scudi viene letto da "ac_bonus" (es. 2). Per le armature
          viene estratto il numero iniziale di "ac_formula" (es. "14 +
          modificatore di Des (max 2)" → 14) con una regex sul prefisso
          numerico — la parte testuale ("+ modificatore di Des...") descrive
          esattamente la stessa formula già hardcoded in
          `calculate_and_update_ca()`, quindi non va sommata di nuovo.

        Ritorna None se il nome non è presente nel catalogo (es. "Abito
        comune", che non è un'armatura del Capitolo 5 — vedi
        `_save_armor_by_name()` in wizard_view.py/manual_form.py per il
        fallback "capo non protettivo" che questo caso deve produrre).
        """
        needle = name.lower()
        armor = self.get_armor()
        for key, armor_type in self._ARMOR_TYPE_BY_KEY.items():
            for a in armor.get(key, []):
                if a.get("name", "").lower() != needle:
                    continue
                result = dict(a)
                result["armor_type"] = armor_type
                if armor_type == "scudo":
                    result["ca_value"] = int(a.get("ac_bonus", 0) or 0)
                else:
                    formula = a.get("ac_formula", "") or ""
                    match = re.match(r"\s*(\d+)", formula)
                    result["ca_value"] = int(match.group(1)) if match else 0
                return result
        return None

    def get_armor_names(self) -> list[str]:
        """
        Nomi di tutte le armature/scudi PHB (equipment/armor.json), pronti
        per popolare un Dropdown "Tipo" nel dialog di creazione/modifica
        armatura — vedi `get_armor_item()` per il dettaglio risolto
        (ca_value/armor_type) usato per l'autofill. Aggiunto 2026-07-16 su
        richiesta di Davide ("autoriempi la scheda con le caratteristiche
        del tipo di armatura").
        """
        armor = self.get_armor()
        result: list[str] = []
        for key in self._ARMOR_TYPE_BY_KEY:
            for a in armor.get(key, []):
                if a.get("name"):
                    result.append(a["name"])
        return result

    def get_adventuring_gear(self) -> dict[str, Any]:
        """Dizionario grezzo di equipment/adventuring_gear.json (items/descrizioni/dotazioni)."""
        self._ensure_equipment_file("adventuring_gear")
        return self._equipment["adventuring_gear"]

    def get_pack_contents(self, pack_name: str) -> list[dict[str, Any]] | None:
        """
        Contenuto strutturato di una Dotazione (es. "Dotazione da Avventuriero"),
        letto da equipment/adventuring_gear.json → packs[pack_name].contents_items
        (campo aggiunto il 2026-07-11, parsing manuale della prosa "contents"
        già verificata contro il manuale — vedi "_contents_items_note" nel JSON).

        Ritorna una lista di dict {"name": str, "quantity": int}, oppure None
        se pack_name non corrisponde a nessuna dotazione nota (case-insensitive
        sul nome esatto della dotazione, non sui nomi dei singoli oggetti).
        Usata da wizard_view.py/manual_form.py per espandere una voce di
        equipaggiamento "Dotazione da X" nei singoli oggetti che contiene,
        invece di creare un unico InventoryItem con quel nome letterale.
        """
        packs = self.get_adventuring_gear().get("packs", {})
        target = pack_name.strip().lower()
        for name, data in packs.items():
            if name.startswith("_"):
                continue
            if name.strip().lower() == target:
                items = data.get("contents_items")
                if items:
                    return [dict(it) for it in items]
                return None
        return None

    def get_tools(self) -> dict[str, Any]:
        """Dizionario grezzo di equipment/tools.json."""
        self._ensure_equipment_file("tools")
        return self._equipment["tools"]

    def get_mounts_and_vehicles(self) -> dict[str, Any]:
        """Dizionario grezzo di equipment/mounts_and_vehicles.json."""
        self._ensure_equipment_file("mounts_and_vehicles")
        return self._equipment["mounts_and_vehicles"]

    def get_economy(self) -> dict[str, Any]:
        """Dizionario grezzo di equipment/economy.json (ricchezza/valuta/merci/stile di vita)."""
        self._ensure_equipment_file("economy")
        return self._equipment["economy"]

    def get_equipment(self) -> dict[str, Any]:
        """
        Dizionario con tutte e 6 le sezioni di equipaggiamento unite (chiavi:
        weapons/armor/adventuring_gear/tools/mounts_and_vehicles/economy).
        Comodo per ispezione rapida; per uso normale preferire i getter
        specifici (get_weapons(), get_armor(), ecc.), più leggeri da caricare.
        """
        for section in ("weapons", "armor", "adventuring_gear", "tools", "mounts_and_vehicles", "economy"):
            self._ensure_equipment_file(section)
        return dict(self._equipment)

    def get_tool_names(self, category: str) -> list[str]:
        """
        Nomi degli strumenti di una categoria, letti da equipment/tools.json →
        items (campo "category": "strumenti_artigiano" | "strumenti_musicali"
        | "giochi" | "strumenti_vari"). Unica fonte dato — sostituisce le vecchie
        costanti ARTISAN_TOOLS/MUSICAL_INSTRUMENTS/GAMING_SETS di config/settings.py
        (rimosse il 2026-07-10, stesso refactor già applicato a RACE_DATA e alle
        7 costanti di classe).
        """
        items = self.get_tools().get("items", [])
        return [it["name"] for it in items if it.get("category") == category and it.get("name")]

    def get_tool_categories(self) -> dict[str, list[str]]:
        """
        Mappa chiave-categoria (usata nel campo "from" dei JSON classe/background,
        es. "strumenti_artigiani") → lista di nomi selezionabili. Sostituisce
        TOOL_CATEGORIES di config/settings.py.
        """
        artisan = self.get_tool_names("strumenti_artigiano")
        musical = self.get_tool_names("strumenti_musicali")
        games = self.get_tool_names("giochi")
        return {
            "strumenti_artigiani": artisan,
            "strumenti_musicali": musical,
            "strumenti_artigiani_o_musicali": artisan + musical,
            "gioco_carte": ["Mazzo di Carte"],
            "gioco_dadi": ["Dadi"],
            "scacchi": ["Scacchi dei Draghi"],
            "gioco_tre_draghi": ["Tre Draghi al Buio"],
            "altro_gioco": games,
        }

    def get_tool_category_label(self, key: str) -> str:
        """
        Label singola per una chiave categoria "a scelta singola già nota"
        (es. "gioco_carte" → "Mazzo di Carte"), usata quando il campo "from"
        di un JSON è una lista di chiavi anziché una singola chiave "a scelta
        multipla". Sostituisce TOOL_CATEGORY_LABEL di config/settings.py.
        """
        labels = {
            "gioco_carte": "Mazzo di Carte",
            "gioco_dadi": "Dadi",
            "scacchi": "Scacchi dei Draghi",
            "gioco_tre_draghi": "Tre Draghi al Buio",
            "altro_gioco": "Altro gioco a scelta",
        }
        return labels.get(key, key)

    def _ensure_equipment_file(self, section: str) -> None:
        """
        Carica pigramente equipment/{section}.json (weapons/armor/
        adventuring_gear/tools/mounts_and_vehicles/economy) — un file per
        dominio, ognuno cachato indipendentemente al primo utilizzo.
        """
        if section in self._equipment_loaded:
            return
        self._equipment_loaded.add(section)
        path = _DATA_DIR / "equipment" / f"{section}.json"
        try:
            self._equipment[section] = _load_json(path)
            logger.debug("Equipaggiamento '%s' caricato", section)
        except Exception as exc:
            logger.error("Errore caricamento equipment/%s.json: %s", section, exc)
            self._equipment[section] = {}


# ---------------------------------------------------------------------------
# Singleton globale — unica istanza condivisa da tutta l'applicazione
# ---------------------------------------------------------------------------

game_data = GameDataLoader()
