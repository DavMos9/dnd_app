"""
EquipmentManager: regole di equipaggiamento simultaneo di armi e armature.

Responsabilità:
  - Determinare quante mani richiede un'arma (proprietà "Due Mani" = 2,
    altrimenti 1 — vedi nota su "Versatile" più sotto)
  - Decidere quali armi restano equipaggiate quando il giocatore ne
    equipaggia una nuova, rispettando il limite di 2 mani del personaggio
  - Decidere quali armature/scudi restano equipaggiati quando il
    giocatore ne equipaggia uno nuovo, rispettando le due postazioni
    indipendenti "armatura indossata" / "scudo impugnato" (vedi sezione
    dedicata più sotto, "Armature e scudi")

Nessuna dipendenza da Flet: modulo puro, testabile in isolamento (stessa
convenzione di wizard_engine.py / level_manager.py — "Core: mai dipendenze
da Flet").

Fonte dati — PHB IT (verificato con pdftotext su "ED 5.0 manuale del
giocatore.pdf", Capitolo 5 "Equipaggiamento" e Capitolo 9 "Combattimento"):

  - Proprietà "Due Mani": «Questa arma richiede di essere impugnata a due
    mani quando il personaggio la usa per attaccare.» → occupa entrambe
    le mani, nessun'altra arma o scudo può restare equipaggiato insieme.
  - Scudi: «Uno scudo può essere fatto di legno o di metallo ed è
    impugnato a una mano. [...] Un personaggio può beneficiare di un solo
    scudo alla volta.» → uno scudo equipaggiato occupa 1 delle 2 mani.
  - "Combattere con Due Armi" (Capitolo 9): «Quando un personaggio
    effettua l'azione di Attacco e attacca con un'arma da mischia leggera
    impugnata a una mano, può usare un'azione bonus per attaccare con
    un'altra arma da mischia leggera impugnata nell'altra mano.» — questa
    è una regola su QUALE azione bonus è disponibile in combattimento, non
    su quali armi possono essere fisicamente impugnate insieme: due armi
    a una mano non leggere (es. una spada lunga e una mazza) si possono
    comunque equipaggiare contemporaneamente, una per mano, semplicemente
    il giocatore non potrà usare l'azione bonus di Combattere con Due Armi
    con quella coppia specifica (a meno di talenti/stili che rimuovono il
    vincolo, es. lo stile di Combattimento con Due Armi del Ranger). La
    proprietà "Leggera" NON entra quindi in questa logica di equipaggiamento
    simultaneo.
  - "Versatile": «Questa arma può essere usata a una o due mani. La
    proprietà è accompagnata da un valore in danni indicato tra parentesi
    (i danni che l'arma infligge quando viene impugnata a due mani per
    effettuare un attacco in mischia).» A differenza della prima versione
    di questo modulo (2026-07-11), l'impugnatura di un'arma Versatile è ora
    tracciata esplicitamente su `Weapon.grip_two_handed` (vedi
    `data/models.py`): se il giocatore la impugna a due mani, l'arma occupa
    2 mani esattamente come una vera arma "Due Mani" (nessun'altra arma o
    scudo equipaggiato insieme); se la impugna a una mano, occupa 1 mano
    come qualunque altra arma a una mano. Il dado danno da usare
    (`damage_dice` vs `versatile_damage_dice`) è responsabilità del
    chiamante (UI), non di questo modulo, che si occupa solo di mani/slot.
"""

from dataclasses import dataclass


@dataclass
class EquipCandidate:
    """Vista minima di un'arma sufficiente a calcolare l'occupazione delle
    mani — disaccoppiata da data.models.Weapon per restare un modulo core
    senza dipendenze verso il resto del progetto."""
    id: str
    properties: str
    is_equipped: bool
    grip_two_handed: bool = False


def weapon_hands(properties: str, grip_two_handed: bool = False) -> int:
    """Numero di mani richieste per impugnare un'arma con queste proprietà:
      - 2 se la proprietà "Due Mani" è presente (sempre, nessuna scelta);
      - 2 se la proprietà "Versatile" è presente E `grip_two_handed=True`
        (il giocatore ha scelto di impugnarla a due mani per il dado danno
        maggiore — vedi docstring del modulo);
      - 1 in tutti gli altri casi.
    """
    props = {p.strip().lower() for p in (properties or "").split(",") if p.strip()}
    # Confronto per sottostringa, non uguaglianza esatta: la UI di creazione/
    # modifica arma (inventario_tab.py -> _WEAPON_PROPERTIES) usa l'etichetta
    # "A due mani" (non "Due Mani" nudo) per questa proprietà — un confronto
    # per uguaglianza esatta contro "due mani" non l'avrebbe mai riconosciuta,
    # facendo trattare ERRONEAMENTE ogni arma a due mani come se occupasse
    # una sola mano (bug reale trovato il 2026-07-11 mentre si estendeva
    # questa funzione per il grip Versatile — vedi CLAUDE.md).
    if any("due mani" in p for p in props):
        return 2
    if grip_two_handed and any("versatile" in p for p in props):
        return 2
    return 1


def resolve_weapon_equip(
    weapons: list[EquipCandidate],
    target_id: str,
    shield_equipped: bool,
) -> tuple[set[str], bool]:
    """
    Calcola il nuovo stato di equipaggiamento dopo che il giocatore ha
    cliccato "equipaggia" sull'arma `target_id`, applicando il limite di
    2 mani (PHB IT, vedi docstring del modulo).

    Va chiamata SOLO quando si sta equipaggiando un'arma (transizione
    non equipaggiata → equipaggiata). Il disequipaggiamento di un'arma
    già equipaggiata non richiede questa logica: libera sempre e solo le
    sue stesse mani, senza effetti a cascata su altre armi.

    Ritorna (equipped_ids, unequip_shield):
      - equipped_ids: insieme di id di TUTTE le armi che devono risultare
        equipaggiate dopo l'operazione (include sempre `target_id`).
      - unequip_shield: True se lo scudo eventualmente già equipaggiato
        deve essere disequipaggiato per fare posto (avviene solo quando
        si equipaggia un'arma a due mani).

    Il chiamante è responsabile di scrivere il nuovo stato sul DB — questa
    funzione è pura, non tocca alcuna persistenza.
    """
    target = next((w for w in weapons if w.id == target_id), None)
    if target is None:
        # Id non trovato: nessuna modifica, stato invariato.
        return ({w.id for w in weapons if w.is_equipped}, False)

    hands_needed = weapon_hands(target.properties, target.grip_two_handed)

    if hands_needed == 2:
        # Un'arma a due mani occupa l'intera capacità del personaggio:
        # nessun'altra arma né scudo può restare equipaggiato.
        return ({target.id}, shield_equipped)

    # Arma a una mano: mantieni equipaggiate le altre armi già equipaggiate
    # finché entrano nelle mani rimaste libere. Se bisogna liberare spazio,
    # si dà precedenza alle armi equipaggiate più di recente (si scorre
    # `weapons` al contrario: dato che `get_weapons` ordina per rowid/ordine
    # di creazione, l'ultima equipaggiata tende a comparire più avanti nella
    # lista) — comportamento deterministico: a parità di mani libere, "esce"
    # per prima l'arma equipaggiata da più tempo.
    hands_free = 2 - hands_needed - (1 if shield_equipped else 0)
    kept: list[str] = []
    for w in reversed(weapons):
        if w.id == target.id or not w.is_equipped:
            continue
        w_hands = weapon_hands(w.properties, w.grip_two_handed)
        if w_hands <= hands_free:
            kept.append(w.id)
            hands_free -= w_hands
        # altrimenti: quest'arma non entra più nelle mani libere e viene
        # disequipaggiata dal chiamante (non inclusa in `kept`).

    return (set(kept) | {target.id}, False)


# ----------------------------------------------------------------------
# Armature e scudi (InventoryItem, category="armor")
# ----------------------------------------------------------------------
#
# Fonte dati — PHB IT, Capitolo 5 "Equipaggiamento":
#   - Scudi: «Un personaggio può beneficiare di un solo scudo alla volta.»
#     Citazione letterale — un solo scudo equipaggiato per volta.
#   - Armatura indossata (leggera/media/pesante): il manuale non contiene
#     una singola frase che vieti esplicitamente di indossarne più di una,
#     ma lo implica costantemente con la grammatica singolare usata in
#     tutto il capitolo — «L'armatura che un personaggio indossa [...]
#     determinano la sua Classe Armatura base», «aggiunge [...] al numero
#     base del SUO tipo di armatura» — e dalla tabella "Indossare e
#     Togliere Armature", che descrive il tempo per indossare UN
#     determinato tipo di armatura, non la sovrapposizione di più corazze.
#     Questa è quindi una DECISIONE DI PROGETTAZIONE (fisicamente ovvia —
#     non si indossano due corazze contemporaneamente), non una citazione
#     letterale come per lo scudo: va tenuta distinta nella documentazione
#     da quanto è invece scritto testualmente nel manuale.
#
# Le due "postazioni" — corpo (armatura vera O indumento comune, es.
# "Abito comune" con armor_type="") e scudo — sono indipendenti:
# equipaggiare un'armatura non tocca lo scudo già impugnato, e viceversa
# (un guerriero con cotta di maglia + scudo indossa entrambi insieme).
#
# NOTA (2026-07-11, bug report Davide: "non devo poter indossare più
# armature alla volta, o indosso abito comune o indosso armatura di
# maglia ecc."): la postazione "corpo" include ANCHE gli item con
# armor_type="" (indumenti non protettivi come "Abito comune", creati da
# `_save_armor_by_name()` quando il nome non risolve nel catalogo
# equipment/armor.json — vedi CLAUDE.md). Prima di questo fix, un item
# con armor_type="" veniva trattato come una "postazione diversa" che non
# escludeva né veniva esclusa da una vera armatura corporea: un
# personaggio poteva risultare con "Abito comune" E "Cotta di Maglia"
# equipaggiati insieme (senza alcun effetto visibile sulla CA, dato che
# solo l'armatura vera viene sommata — ma comunque scorretto: fisicamente
# non si indossano contemporaneamente vestiti comuni e un'armatura sopra,
# e la UI mostrava entrambi come "equipaggiati" in modo fuorviante). Ora
# è sufficiente verificare "non è uno scudo" per appartenere alla
# postazione corpo, quindi qualunque indumento/armatura la occupa e la
# esclude in modo reciproco.

@dataclass
class ArmorCandidate:
    """Vista minima di un'armatura/scudo sufficiente a calcolare quale
    "postazione" occupa — disaccoppiata da data.models.InventoryItem per
    restare un modulo core senza dipendenze verso il resto del progetto."""
    id: str
    armor_type: str   # "leggera" | "media" | "pesante" | "scudo" | ""
    is_equipped: bool


def resolve_armor_equip(armors: list["ArmorCandidate"], target_id: str) -> set[str]:
    """
    Calcola quali armature/scudi restano equipaggiati dopo che il
    giocatore ha equipaggiato `target_id`, applicando le due postazioni
    indipendenti descritte sopra.

    Va chiamata SOLO quando si sta equipaggiando un'armatura/scudo
    (transizione non equipaggiato → equipaggiato). Il disequipaggiamento
    di un oggetto già equipaggiato non richiede questa logica: libera
    sempre e solo la propria postazione, senza effetti a cascata.

    Ritorna l'insieme di id di TUTTI gli oggetti che devono risultare
    equipaggiati dopo l'operazione (include sempre `target_id`). Il
    chiamante è responsabile di scrivere il nuovo stato sul DB — questa
    funzione è pura, non tocca alcuna persistenza.
    """
    target = next((a for a in armors if a.id == target_id), None)
    if target is None:
        # Id non trovato: nessuna modifica, stato invariato.
        return {a.id for a in armors if a.is_equipped}

    is_shield = target.armor_type == "scudo"
    kept: set[str] = set()
    for a in armors:
        if a.id == target.id or not a.is_equipped:
            continue
        if is_shield and a.armor_type == "scudo":
            continue   # un solo scudo alla volta: espelle l'altro
        if (not is_shield) and a.armor_type != "scudo":
            # Postazione "corpo": qualunque armatura vera (leggera/media/
            # pesante) O indumento non protettivo (armor_type="", es.
            # "Abito comune") occupa questa stessa postazione ed espelle
            # chiunque altro la occupi già — non solo le armature vere.
            continue
        kept.add(a.id)  # postazione diversa: non tocca

    return kept | {target.id}
