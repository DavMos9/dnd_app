"""
Istanze di personaggio nei Mondi condivisi — passo 3 di
`dnd_app/docs/multiplayer_design.md` §6.

Un personaggio creato sul proprio dispositivo è **locale**
(`world_id == ""`). Quando entra in un mondo nasce un'**istanza**: un record
di `characters` a tutti gli effetti (stesse 12 tabelle figlio, stesse 5
schede, stesso export `.dndchar` — nessuna riga di codice modificata altrove
per farle funzionare, è il punto centrale della scelta architetturale del
design doc), con `world_id`/`origin_character_id`/`owner_device_id`
valorizzati.

Questo modulo può usare i repository e il DB (come `core/world_backend.py`),
ma **mai Flet** — per questo la logica di equipaggiamento iniziale qui sotto
non importa `ui/views/creation_wizard/creation_shared.py` (che porta `import
flet`), anche se ne replica l'unico algoritmo rilevante: vedi
`_init_weapon_choice_default()`.

Questo modulo (passo 3) crea SEMPRE l'istanza con `is_replica=0`: nasce sul
dispositivo di chi la crea, che ne è il record autoritativo. `is_replica=1`
esiste solo dal passo 4 (rete LAN, ormai implementato) ed è scritto
altrove, da `data/repositories/character_export.py::import_replica_character()`,
quando un ALTRO dispositivo scarica questa stessa istanza dall'host — mai
qui: questo modulo non sa nulla di rete (vedi sopra, "mai Flet" vale anche
per `core/world_backend.py`/`network/*`) — pulizia 2026-08-07, il commento
diceva ancora "nessuna rete in questo passo... avrà senso solo dal passo 4",
vero solo prima che quel passo esistesse.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from config.settings import WEAPONS_BY_CATEGORY, get_modifier
from data.database import get_connection
from data.game_data.game_data_loader import GameDataLoader
from data.repositories import character_export, character_repo

logger = logging.getLogger(__name__)

_loader = GameDataLoader()

InstanceMode = Literal["as_is", "fresh"]


@dataclass
class InstanceResult:
    success: bool
    character_id: str = ""
    #: True se esisteva già un'istanza di questo personaggio in questo mondo
    #: per questo dispositivo — "riprendi" automatico (§6), `mode` ignorato.
    resumed: bool = False
    error: str = ""


@dataclass
class RefreshPreview:
    """Riepilogo «cosa cambia» mostrato prima di «Aggiorna il mio foglio»
    (§6.1: "il riepilogo mostra cosa cambia... prima di procedere")."""
    origin_exists: bool
    origin_character_id: str
    origin_name: str = ""
    level_before: int = 0
    level_after: int = 0
    xp_before: int = 0
    xp_after: int = 0
    item_count_before: int = 0
    item_count_after: int = 0


# ---------------------------------------------------------------------------
# Creazione / ripresa di un'istanza
# ---------------------------------------------------------------------------

def find_existing_instance(world_id: str, origin_character_id: str,
                            owner_device_id: str) -> str | None:
    """Id dell'istanza già esistente per questa terna, o None. Query diretta
    (nessun repository dedicato: è un lookup a una riga, non vale una nuova
    funzione pubblica in `character_repo.py` per un solo uso)."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM characters WHERE world_id=? AND origin_character_id=? "
            "AND owner_device_id=?",
            (world_id, origin_character_id, owner_device_id),
        ).fetchone()
        conn.close()
        return row["id"] if row else None
    except Exception as e:
        logger.error("Errore find_existing_instance: %s", e)
        return None


def create_or_resume_instance(world_id: str, local_character_id: str,
                               owner_device_id: str, mode: InstanceMode) -> InstanceResult:
    """
    Crea l'istanza di `local_character_id` dentro `world_id`, oppure — se
    esiste già (stesso mondo, stessa origine, stesso dispositivo) — la
    riprende senza duplicarla (§6, caso "Riprendi", automatico: `mode` non
    si applica in quel caso).

    `local_character_id` DEVE essere un personaggio locale (`world_id ==
    ""`): non si crea mai l'istanza di un'istanza.
    """
    origin = character_repo.get_by_id(local_character_id)
    if origin is None:
        return InstanceResult(False, error="Personaggio locale non trovato.")
    if origin.world_id:
        return InstanceResult(
            False, error="Solo un personaggio locale può entrare in un mondo "
                          "(questo è già un'istanza).",
        )

    existing = find_existing_instance(world_id, local_character_id, owner_device_id)
    if existing:
        return InstanceResult(True, character_id=existing, resumed=True)

    new_id = _copy_character(local_character_id)
    if new_id is None:
        return InstanceResult(False, error="Copia del personaggio fallita.")

    if not _link_to_world(new_id, world_id, local_character_id, owner_device_id):
        return InstanceResult(False, error="Collegamento al mondo fallito.")

    if mode == "fresh":
        if not _reset_to_level_one(new_id):
            return InstanceResult(
                False, error="Istanza creata ma il reset al 1° livello è "
                              "fallito a metà — verifica la scheda.",
            )

    return InstanceResult(True, character_id=new_id, resumed=False)


def _copy_character(source_id: str) -> str | None:
    """Copia integrale (§6, "porta com'è"): riusa `character_export`
    (introspezione di schema) invece di duplicare la logica di copia —
    stessa ragione per cui quel modulo esiste."""
    data = character_export.export_character(source_id)
    if data is None:
        return None
    return character_export.import_character(data, mode="copy")


def _link_to_world(character_id: str, world_id: str, origin_character_id: str,
                    owner_device_id: str) -> bool:
    """Valorizza le 3 colonne che fanno di un personaggio un'istanza.
    `import_character()` le azzera sempre (§14.1) — corretto per un
    `.dndchar` importato da fuori, ma qui serve il passo successivo
    esplicito per collegarla davvero al mondo."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET world_id=?, origin_character_id=?, "
            "owner_device_id=?, is_replica=0 WHERE id=?",
            (world_id, origin_character_id, owner_device_id, character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("Errore _link_to_world: %s", e)
        return False


# ---------------------------------------------------------------------------
# «Ricomincia dal 1° livello» — §6, reset completo confermato da Davide
# (2026-08-05): non solo la lista letterale del design doc (livello, PE,
# inventario, diario, condizioni), ma anche l'inversione di ASI/talenti/
# competenze bonus presi dopo il 1° livello, riusando `character_repo.
# undo_level()` — la stessa funzione già testata dietro "Scendi di livello"
# in ProfiloTab, chiamata una volta per ciascun livello da rimuovere invece
# di una volta sola. Motivazione: senza questo, un'istanza "Lv.1" manterrebbe
# bonus che un vero personaggio di 1° livello non avrebbe mai.
# ---------------------------------------------------------------------------

def _reset_to_level_one(character_id: str) -> bool:
    character = character_repo.get_by_id(character_id)
    if character is None:
        return False

    # 1. Inverte ASI/talenti/competenze bonus presi a ogni livello dal
    #    livello attuale fino al 2° incluso — undo_level filtra per
    #    `level_obtained`, quindi l'ordine delle chiamate non conta.
    for lvl in range(character.level, 1, -1):
        character_repo.undo_level(character_id, lvl)

    # Rilettura: con_score/initiative_bonus/speed possono essere cambiati
    # dall'inversione (undo_level inverte bonus_data — vedi
    # architettura_moduli.md, remove_feat_with_bonuses).
    character = character_repo.get_by_id(character_id)
    if character is None:
        return False

    # 2. Livello/PE — esplicitamente nella lista del design doc.
    character.level = 1
    character.xp = 0

    # 3. PF ricalcolati con la formula ESATTA di 1° livello (PHB p.12),
    #    non con la stima di perdita usata da "Scendi di livello" per un
    #    singolo gradino (qui non serve: si arriva al Lv.1 direttamente,
    #    stessa formula di core/wizard_engine.py::build_character).
    con_mod = get_modifier(character.con_score)
    hit_die = character.hit_dice_type or 8
    character.hp_max = max(1, hit_die + con_mod)
    character.hp_current = character.hp_max
    character.hp_temp = 0
    character.hit_dice_total = 1
    character.hit_dice_remaining = 1

    # 4. Condizioni — esplicitamente nella lista del design doc.
    character.exhaustion_level = 0

    # 5. Stato di sessione/combattimento — non nella lista esplicita del
    #    design doc, ma incoerente da lasciare su un'istanza "appena nata
    #    al 1° livello": tiri salvezza contro la morte, turno in corso,
    #    concentrazione, frenesia, bonus CA temporaneo. Non è materia di
    #    regolamento (non decide nulla sulle regole D&D), solo bookkeeping
    #    di sessione — assunzione dichiarata qui, non silenziosa.
    character.death_saves_success = 0
    character.death_saves_failure = 0
    character.action_used = False
    character.bonus_action_used = False
    character.reaction_used = False
    character.movement_used = 0.0
    character.previous_turn_state = ""
    character.concentrating_spell = ""
    character.concentrating_since = ""
    character.frenzy_active = False
    character.ca_bonus = 0

    if not character_repo.update(character):
        return False

    # 6. Slot incantesimo / risorse di classe per il Lv.1 — stesse funzioni
    #    di self-healing già usate da "Scendi di livello" e dal level-up.
    character_repo.auto_init_spell_slots(character_id, character.class_name, 1)
    character_repo.init_class_resources(character_id, character.class_name, 1, character)
    character_repo.sync_borrowed_spellcasting_ability(character)
    character_repo.init_borrowed_caster_slots(
        character_id, character.class_name or "", character.subclass or "", 1,
    )
    character_repo.sync_bonus_domain_spells(character)
    character_repo.calculate_and_update_ca(character_id)

    # 7. Condizioni attive (Appendice A) — tabella a parte, non nel record
    #    Character.
    character_repo.clear_conditions(character_id)

    # 8. Diario — solo diary_entries (il "diario" del design doc, §6.2): le
    #    Note di Campagna (`campaign_notes`, il Codex PNG/luoghi/missioni)
    #    NON sono toccate, sono appunti fuori-personaggio del giocatore che
    #    non svaniscono perché il personaggio riparte da zero. Assunzione
    #    dichiarata: il design doc dice solo "diario", non specifica il
    #    Codex.
    for entry in character_repo.get_diary_entries(character_id):
        character_repo.delete_diary_entry(entry.id)

    # 9. Inventario/armi/monete azzerati e riassegnati con l'equipaggiamento
    #    iniziale di classe (assegnazione automatica, non interattiva —
    #    confermato da Davide 2026-08-05).
    _reset_inventory(character_id, character.class_name)
    _assign_default_starting_equipment(character_id, character.class_name)

    return True


def _reset_inventory(character_id: str, class_name: str) -> None:
    for w in character_repo.get_weapons(character_id, equipped_only=False):
        character_repo.delete_weapon(w.id)
    for item in character_repo.get_inventory(character_id):
        character_repo.delete_inventory_item(item.id)
    character_repo.update_currencies(character_id, copper=0, silver=0,
                                     electrum=0, gold=0, platinum=0)


def _weapon_choice_default(item: dict) -> dict:
    """
    Stessa identica logica di
    `ui/views/creation_wizard/creation_shared.py::CreationSharedMixin.
    _init_weapon_choice()` — non importabile da qui (quel modulo porta
    `import flet`, vietato in `core/*.py`). Tenerle sincronizzate a mano se
    una delle due cambia: 4 righe, stesso algoritmo, stessa fonte dati
    (`WEAPONS_BY_CATEGORY`).
    """
    if item.get("item_type") == "weapon_choice":
        cat = item.get("category", "semplice")
        weapons = WEAPONS_BY_CATEGORY.get(cat, [])
        count = item.get("count", 1)
        if count > 1:
            item["chosen_weapons"] = [weapons[0]] * count if weapons else []
        else:
            item["chosen_weapon"] = weapons[0] if weapons else ""
    return item


def _assign_default_starting_equipment(character_id: str, class_name: str) -> None:
    """
    Versione non interattiva di `_goto_equipment()`/`_save_item()` in
    `wizard_view.py`/`manual_form.py`: ogni scelta ("type": "choice") viene
    risolta sulla prima opzione (`options[0]`, stesso indice di default già
    preselezionato nel wizard prima che il giocatore lo cambi), ogni arma a
    scelta per categoria sulla prima arma della categoria
    (`_weapon_choice_default`). Nessuna modalità "oro al posto degli
    oggetti": quella è una scelta esplicita del giocatore in creazione, non
    lo stato di default.

    I placeholder "(a scelta)" (strumento musicale/artigiano a scelta di
    background) si risolvono contro le competenze "tool" già registrate sul
    personaggio (non toccate dal reset, sono scelte di background/identità)
    invece che contro uno stato di wizard che qui non esiste.
    """
    cls_data = _loader.get_class(class_name)
    if not cls_data:
        logger.warning(
            "_assign_default_starting_equipment: classe %r non trovata, "
            "nessun equipaggiamento assegnato", class_name,
        )
        return

    tool_choices = [
        p.name for p in character_repo.get_proficiencies(character_id)
        if p.proficiency_type == "tool"
    ]
    tool_idx = 0

    def _save_item(item: dict) -> None:
        nonlocal tool_idx
        itype = item.get("item_type", "item")
        if itype == "weapon_choice":
            item = _weapon_choice_default(item)
            count = item.get("count", 1)
            if count > 1:
                for wname in item.get("chosen_weapons", []):
                    if wname:
                        _save_weapon_by_name(character_id, wname)
            else:
                wname = item.get("chosen_weapon", "")
                if wname:
                    _save_weapon_by_name(character_id, wname)
        elif itype == "currency":
            cur = character_repo.get_currencies(character_id)
            if cur:
                ctype = item.get("currency_type", "gold")
                qty = item.get("quantity", 0)
                delta = {ctype: qty}
                character_repo.update_currencies(
                    character_id=character_id,
                    copper=cur.copper + delta.get("copper", 0),
                    silver=cur.silver + delta.get("silver", 0),
                    electrum=cur.electrum + delta.get("electrum", 0),
                    gold=cur.gold + delta.get("gold", 0),
                    platinum=cur.platinum + delta.get("platinum", 0),
                )
        elif itype == "weapon":
            for _ in range(max(1, item.get("quantity", 1))):
                _save_weapon_by_name(character_id, item["name"])
        elif itype == "armor":
            _save_armor_by_name(character_id, item["name"], item.get("quantity", 1))
        else:
            item_name = item["name"]
            item_category = "misc"
            if "(a scelta)" in item_name:
                chosen = tool_choices[tool_idx] if tool_idx < len(tool_choices) else ""
                tool_idx += 1
                if chosen:
                    item_name = chosen
                    item_category = "tool"
                else:
                    logger.warning(
                        "Equipaggiamento '%s': nessuna competenza strumento "
                        "da risolvere, mantenuto il nome placeholder", item["name"],
                    )
            pack_items = _loader.get_pack_contents(item_name)
            if pack_items is not None:
                for sub in pack_items:
                    character_repo.create_inventory_item(
                        character_id=character_id, name=sub["name"],
                        quantity=sub.get("quantity", 1), weight=0.0,
                        category="misc", is_equipped=False, description="",
                    )
            else:
                character_repo.create_inventory_item(
                    character_id=character_id, name=item_name,
                    quantity=item.get("quantity", 1), weight=0.0,
                    category=item_category, is_equipped=False, description="",
                )

    for entry in cls_data.get("starting_equipment", []):
        if entry.get("type") == "fixed":
            for raw_item in entry.get("items", []):
                _save_item(dict(raw_item))
        elif entry.get("type") == "choice":
            options = entry.get("options", [])
            if options:
                for raw_item in options[0]:
                    _save_item(dict(raw_item))


def _save_weapon_by_name(character_id: str, wname: str) -> None:
    """Stessa logica di `wizard_view.py::_save_weapon_by_name` (mai
    equipaggiata di default — il giocatore equipaggia dalla tab
    Inventario)."""
    wdata = _loader.get_weapon(wname)
    if wdata:
        props = wdata.get("properties", [])
        props_str = ", ".join(props) if isinstance(props, list) else str(props)
        character_repo.create_weapon(
            character_id=character_id, name=wname,
            damage_dice=wdata.get("damage_dice", ""),
            damage_type=wdata.get("damage_type", ""),
            properties=props_str, is_equipped=False,
        )
    else:
        logger.warning("Arma '%s' non trovata in equipment/weapons.json", wname)
        character_repo.create_weapon(character_id=character_id, name=wname, is_equipped=False)


def _save_armor_by_name(character_id: str, aname: str, quantity: int = 1) -> None:
    """Stessa logica di `wizard_view.py::_save_armor_by_name`."""
    adata = _loader.get_armor_item(aname)
    if adata:
        character_repo.create_inventory_item(
            character_id=character_id, name=aname, quantity=quantity,
            weight=float(adata.get("weight_kg") or 0.0),
            category="armor", is_equipped=True,
            ca_value=adata.get("ca_value", 0), armor_type=adata.get("armor_type", ""),
        )
    else:
        logger.warning("Armatura '%s' non trovata in equipment/armor.json", aname)
        character_repo.create_inventory_item(
            character_id=character_id, name=aname, quantity=quantity,
            weight=0.0, category="armor", is_equipped=True,
            ca_value=0, armor_type="",
        )


# ---------------------------------------------------------------------------
# «Aggiorna il mio foglio» — §6.1, manuale, mai automatico
# ---------------------------------------------------------------------------

def preview_refresh(instance_id: str) -> RefreshPreview | None:
    """Riepilogo da mostrare prima della conferma esplicita (§6.1)."""
    instance = character_repo.get_by_id(instance_id)
    if instance is None or not instance.origin_character_id:
        return None
    origin = character_repo.get_by_id(instance.origin_character_id)
    return RefreshPreview(
        origin_exists=origin is not None,
        origin_character_id=instance.origin_character_id,
        origin_name=origin.name if origin else "",
        level_before=origin.level if origin else 0,
        level_after=instance.level,
        xp_before=origin.xp if origin else 0,
        xp_after=instance.xp,
        item_count_before=(
            len(character_repo.get_inventory(origin.id))
            + len(character_repo.get_weapons(origin.id, equipped_only=False))
        ) if origin else 0,
        item_count_after=(
            len(character_repo.get_inventory(instance.id))
            + len(character_repo.get_weapons(instance.id, equipped_only=False))
        ),
    )


def apply_refresh(instance_id: str) -> InstanceResult:
    """
    Ricopia lo stato dell'istanza sul personaggio locale di origine (§6.1).

    Se il personaggio locale di origine non esiste più (eliminato), crea un
    personaggio locale nuovo invece di fallire — comportamento esplicito del
    design doc, non un ripiego silenzioso.
    """
    instance = character_repo.get_by_id(instance_id)
    if instance is None:
        return InstanceResult(False, error="Istanza non trovata.")
    if not instance.origin_character_id:
        return InstanceResult(False, error="Questo personaggio non ha un'origine locale.")

    data = character_export.export_character(instance_id)
    if data is None:
        return InstanceResult(False, error="Esportazione dell'istanza fallita.")

    origin_exists = character_repo.get_by_id(instance.origin_character_id) is not None
    if origin_exists:
        # `import_character` azzera SEMPRE world_id/origin_character_id/
        # owner_device_id/is_replica/world_seq (§14.1) — il risultato è un
        # personaggio locale a tutti gli effetti, mai un'altra istanza.
        new_id = character_export.import_character(
            data, mode="overwrite", target_id=instance.origin_character_id,
        )
    else:
        new_id = character_export.import_character(data, mode="copy")

    if new_id is None:
        return InstanceResult(False, error="Scrittura sul personaggio locale fallita.")
    return InstanceResult(True, character_id=new_id)
