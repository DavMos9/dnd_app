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
        # spell: class_name_lower → lista spell
        self._spells: dict[str, list[dict[str, Any]]] = {}
        # talenti PHB
        self._feats: list[dict[str, Any]] = []
        # invocazioni occulte Warlock
        self._invocations: list[dict[str, Any]] = []
        # equipaggiamento (Capitolo 5 PHB: armi, armature, strumenti, ecc.)
        # una entry per file: "weapons", "armor", "adventuring_gear", "tools",
        # "mounts_and_vehicles", "economy"
        self._equipment: dict[str, dict[str, Any]] = {}

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
        key_to_label = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
        return [key_to_label.get(k, k.upper()) for k in cls_data.get("saving_throws", [])]

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

    def get_metamagic_options(self) -> list[str]:
        """Nomi delle 8 opzioni di Metamagia dello Stregone (PHB)."""
        cls_data = self.get_class("stregone")
        if not cls_data:
            return []
        for feat in cls_data.get("features", []):
            if feat.get("name") == "Metamagia" and feat.get("options"):
                return [o.get("name", "") for o in feat["options"] if o.get("name")]
        return []

    def get_pact_boons(self) -> list[str]:
        """Nomi dei 3 Doni del Patto del Warlock (PHB)."""
        cls_data = self.get_class("warlock")
        if not cls_data:
            return []
        for feat in cls_data.get("features", []):
            if feat.get("name") == "Dono del Patto" and feat.get("options"):
                return [o.get("name", "") for o in feat["options"] if o.get("name")]
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

    def get_spells(self, class_name: str) -> list[dict[str, Any]]:
        """
        Restituisce la lista degli incantesimi per la classe indicata.
        File atteso: spells/incantesimi_{class_name_lower}.json
        Restituisce lista vuota se il file non esiste o la classe non è
        incantatrice.
        """
        key = class_name.lower()
        if key not in self._spells:
            path = _DATA_DIR / "spells" / f"incantesimi_{key}.json"
            if path.exists():
                if path.stat().st_size == 0:
                    logger.debug("File incantesimi '%s' vuoto (placeholder)", path.name)
                    self._spells[key] = []
                else:
                    try:
                        data = _load_json(path)
                        # Supporta sia lista diretta che {"spells": [...]}
                        if isinstance(data, list):
                            self._spells[key] = data
                        else:
                            self._spells[key] = data.get("spells", [])
                        logger.debug(
                            "Incantesimi caricati per '%s': %d spell",
                            class_name, len(self._spells[key]),
                        )
                    except Exception as exc:
                        logger.error(
                            "Errore caricamento incantesimi '%s': %s", path.name, exc
                        )
                        self._spells[key] = []
            else:
                logger.debug("Nessun file incantesimi per classe '%s'", class_name)
                self._spells[key] = []
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

    def get_adventuring_gear(self) -> dict[str, Any]:
        """Dizionario grezzo di equipment/adventuring_gear.json (items/descrizioni/dotazioni)."""
        self._ensure_equipment_file("adventuring_gear")
        return self._equipment["adventuring_gear"]

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
