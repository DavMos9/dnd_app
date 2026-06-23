"""
game_data_loader.py — Caricamento e caching dei dati di gioco D&D 5e.

Espone il singleton `game_data` con accesso lazy ai JSON di classi, razze,
background, incantesimi e tag. Nessuna dipendenza da Flet.

Utilizzo:
    from data.game_data.game_data_loader import game_data

    cls   = game_data.get_class("barbaro")       # dict | None
    razze = game_data.get_all_races()             # list[dict]
    armi  = game_data.expand_tags(["#armi_semplici", "Pugnale"])
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
        # tag: "#tag" → list[str]
        self._tags: dict[str, list[str]] = {}
        # talenti PHB
        self._feats: list[dict[str, Any]] = []
        # invocazioni occulte Warlock
        self._invocations: list[dict[str, Any]] = []

        self._classes_loaded     = False
        self._races_loaded       = False
        self._backgrounds_loaded = False
        self._tags_loaded        = False
        self._feats_loaded       = False
        self._invocations_loaded = False

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
                self._backgrounds[path.stem] = _load_json(path)
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
    # Tag
    # ------------------------------------------------------------------

    def expand_tags(self, items: list[str]) -> list[str]:
        """
        Espande i tag (es. "#armi_semplici") nelle liste PHB corrispondenti.
        Le stringhe senza '#' vengono lasciate invariate.
        I duplicati vengono rimossi preservando l'ordine di apparizione.

        Esempio:
            expand_tags(["#armi_semplici", "Arco lungo"])
            → ["Clava", "Pugnale", ..., "Arco corto", "Arco lungo"]
        """
        self._ensure_tags()
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            entries = self._tags.get(item, [item]) if item.startswith("#") else [item]
            for entry in entries:
                if entry not in seen:
                    seen.add(entry)
                    result.append(entry)
        return result

    def get_tag(self, tag: str) -> list[str]:
        """
        Restituisce la lista espansa per un singolo tag.
        Lista vuota se il tag non è definito in tags.json.
        """
        self._ensure_tags()
        return self._tags.get(tag, [])

    def _ensure_tags(self) -> None:
        if self._tags_loaded:
            return
        self._tags_loaded = True
        path = _DATA_DIR / "tags.json"
        try:
            self._tags = _load_json(path)
            logger.debug("Tags caricati: %d voci", len(self._tags))
        except Exception as exc:
            logger.error("Errore caricamento tags.json: %s", exc)
            self._tags = {}


# ---------------------------------------------------------------------------
# Singleton globale — unica istanza condivisa da tutta l'applicazione
# ---------------------------------------------------------------------------

game_data = GameDataLoader()
