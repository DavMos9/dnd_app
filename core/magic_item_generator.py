"""
Generatore di Oggetti Magici Casuali per la Modalità Master — logica pura
(nessuna dipendenza Flet/DB), stesso principio architetturale di
`core/encounter_generator.py`/`core/treasure_generator.py`/
`core/trap_generator.py`: nessuna scrittura persistente, solo funzioni che
prendono dati (il compendio già caricato via
`GameDataLoader.get_magic_items()`, 264 voci auditate) e restituiscono una
lista di oggetti (dict grezzi di `magic_items.json`).

A differenza del Generatore Tesori (che tira da tabelle d100 e produce solo
NOMI di oggetti magici, senza descrizione — vedi
`core/treasure_generator.py`/`master_treasure_dialog.py`, dove la nota
"descrizione completa non ancora disponibile" era necessaria perché il
Compendio non esisteva ancora), questo generatore lavora **direttamente sul
Compendio Oggetti Magici A-Z** già trascritto per intero: ogni oggetto
generato porta con sé la sua descrizione ufficiale completa, pronta per
essere aggiunta all'inventario di un personaggio senza alcuna nota di
"mancante".

Il Master fissa (entrambi opzionali — nessun filtro = l'intero compendio)
una **rarità** (una delle 6 fasce normalizzate via
`magic_item_rarity_bucket()`, la stessa funzione già usata dal browser
`MasterMagicItemsView` per gestire le voci multi-rarità come "Cintura della
Forza dei Giganti") e/o una **categoria** (base, es. "Anello"/"Arma" — via
`magic_item_category_base()`), più un numero di oggetti desiderato.

Estrazione **senza ripetizione quando il pool lo consente**
(`random.sample`) — a differenza del Generatore Incontri (dove più copie
dello stesso mostro sono realistiche, es. "4 goblin") qui gli oggetti sono
unici e nominati: chiedere 3 oggetti da un pool di 20 non deve quasi mai
restituire lo stesso oggetto due volte. Se invece la richiesta eccede la
dimensione del pool filtrato (es. 5 oggetti in una categoria che ne
contiene solo 2), il pool viene esaurito una volta per intero e poi
completato con ripetizioni (`random.choices`) solo per la parte eccedente
— non solleva mai un errore, ma nemmeno finge una varietà che i dati non
permettono. Nessun seed fisso in nessun caso: stesso bersaglio, risultati
diversi ad ogni generazione.
"""

from __future__ import annotations

import random

from data.game_data.game_data_loader import (
    magic_item_category_base,
    magic_item_rarity_bucket,
)


def get_category_options(items: list[dict]) -> list[str]:
    """Elenco ordinato delle categorie base disponibili nel pool fornito
    (dopo normalizzazione), per popolare il Dropdown "Categoria" della UI.
    Non include mai una voce vuota — l'opzione "Tutte" (nessun filtro
    categoria) va aggiunta dal chiamante come prima voce del Dropdown."""
    cats = {magic_item_category_base(it.get("category", "")) for it in items}
    cats.discard("")
    return sorted(cats)


def filter_magic_items(items: list[dict], rarity: str = "", category: str = "") -> list[dict]:
    """Ritorna solo gli oggetti la cui rarità normalizzata (bucket) e/o
    categoria base combaciano con i filtri forniti. Un filtro vuoto/falsy
    non esclude nulla su quell'asse."""
    out: list[dict] = []
    for it in items:
        if rarity and magic_item_rarity_bucket(it.get("rarity", "")) != rarity:
            continue
        if category and magic_item_category_base(it.get("category", "")) != category:
            continue
        out.append(it)
    return out


def generate_magic_items(
    items: list[dict],
    rarity: str = "",
    category: str = "",
    count: int = 1,
) -> list[dict]:
    """
    Estrae `count` oggetti magici dal pool filtrato per rarità/categoria.
    Senza ripetizioni finché il pool lo consente (`random.sample`); se
    `count` eccede la dimensione del pool, esaurisce il pool una volta e
    completa il resto con ripetizioni (`random.choices`). Lista vuota se il
    pool filtrato è vuoto o `count <= 0` — il chiamante mostra un messaggio
    informativo invece di un errore.
    """
    pool = filter_magic_items(items, rarity, category)
    if not pool or count <= 0:
        return []
    if count <= len(pool):
        return random.sample(pool, count)
    result = list(pool)
    random.shuffle(result)
    result.extend(random.choices(pool, k=count - len(pool)))
    return result
