"""
Bottino (Loot) — calcolo puro delle ripartizioni, nessuna dipendenza Flet,
stesso principio architetturale di `treasure_generator.py`/`trap_generator.py`/
`encounter_calculator.py`/`equipment_manager.py`: nessuna scrittura su DB,
solo funzioni che calcolano un risultato a partire da input espliciti.

Fonte di progettazione: `dnd_app/docs/loot_design.md` (§5 "Ripartizione delle
monete in percentuale"). Le aliquote di cambio tra le 5 valute (rame/argento/
electrum/oro/platino) sono lette da `equipment/economy.json` tramite
`GameDataLoader.get_currency_exchange_rate()` — mai riscritte a mano qui,
stessa regola già applicata a ogni altra tabella del progetto.

Due responsabilità distinte, entrambe richieste da `loot_design.md`:

- **Ripartizione monete per quota percentuale** (`split_coins_by_percentage`):
  ogni destinatario riceve una quota (0-100%), le quote devono sommare
  esattamente a 100. Due modalità:
    - `"denomination"` (default) — ciascuna delle 5 colonne di valuta viene
      spartita INDIPENDENTEMENTE con il metodo del resto più alto (nessuna
      conversione, fedele al tavolo: "le monete si spartiscono fisicamente").
    - `"value"` — l'intero controvalore in rame viene calcolato, spartito con
      lo stesso metodo, poi ogni quota viene riconvertita nella combinazione
      di monete più efficiente (platino→oro→electrum→argento→rame).
  In entrambe le modalità la somma delle quote distribuite è sempre
  ESATTAMENTE pari al totale di partenza — nessuna moneta creata o perduta.

- **Ripartizione di un oggetto in quantità** (`split_quantity_by_shares`): per
  oggetti indivisibili posseduti in più copie (es. 3 pozioni, 5 gemme),
  ripartiti per CONTEGGIO INTERO tra i destinatari, non per percentuale.

**Metodo del resto più alto** (`largest_remainder_allocation`): calcola la
quota esatta (frazionaria) di ciascun destinatario, assegna la parte intera
per troncamento, poi distribuisce le unità rimanenti a chi ha il resto
frazionario più alto, in ordine decrescente — garantisce che la somma delle
parti assegnate sia sempre esattamente pari al totale, mai un'unità in più o
in meno.
"""

from __future__ import annotations

from typing import Any

from data.game_data.game_data_loader import game_data

# Ordine di conversione dal più alto al più basso, usato per la
# riconversione "per valore" (greedy top-down) e per la validazione quote.
_CURRENCY_ORDER = ("platinum", "gold", "electrum", "silver", "copper")

# Abbreviazione PHB (usata da GameDataLoader.get_currency_exchange_rate)
# per ciascuna colonna di valuta del progetto (stessi nomi campo già usati
# da Currency/update_currencies in tutto il progetto).
_CURRENCY_ABBR = {
    "copper": "mr",
    "silver": "ma",
    "electrum": "me",
    "gold": "mo",
    "platinum": "mp",
}


# ----------------------------------------------------------------------
# Validazione quote
# ----------------------------------------------------------------------

def validate_quotas(quotas: dict[str, float]) -> str:
    """
    Verifica che le quote (percentuali 0-100, una per destinatario) siano
    valide: nessuna negativa, somma esattamente 100 (tolleranza 1e-6 per
    arrotondamenti in virgola mobile). Ritorna una stringa di errore in
    italiano, o "" se tutto è valido. Non corregge mai da sola — per
    scelta di design (`loot_design.md` §7): "bloccate con messaggio, non
    correggibili a discrezione dell'app".
    """
    if not quotas:
        return "Nessun destinatario indicato."
    for name, pct in quotas.items():
        if pct < 0:
            return f"La quota di «{name}» non può essere negativa."
    total = sum(quotas.values())
    if abs(total - 100.0) > 1e-6:
        return f"Le quote devono sommare a 100% (attualmente {total:g}%)."
    return ""


# ----------------------------------------------------------------------
# Metodo del resto più alto (largest remainder method)
# ----------------------------------------------------------------------

def largest_remainder_allocation(total: int, quotas: dict[str, float]) -> dict[str, int]:
    """
    Ripartisce un intero `total` tra i destinatari di `quotas` (percentuali
    0-100, devono sommare a 100 — non validato qui, vedi `validate_quotas`)
    usando il metodo del resto più alto: parte intera per troncamento, poi le
    unità residue vanno a chi ha il resto frazionario più alto (a parità,
    nell'ordine di iterazione di `quotas`). La somma dei valori ritornati è
    sempre esattamente `total`.

    `total` può essere 0 o negativo (ritorna tutti zeri/il totale negativo
    concentrato senza sballare l'invariante di somma) — nessun controllo di
    segno qui, la validazione di dominio spetta al chiamante.
    """
    if not quotas:
        return {}
    if total == 0:
        return {name: 0 for name in quotas}

    exact = {name: total * pct / 100.0 for name, pct in quotas.items()}
    floors = {name: _floor_toward_zero_or_down(v) for name, v in exact.items()}
    assigned = sum(floors.values())
    remainder = total - assigned

    # Ordina per resto frazionario decrescente (a parità, ordine di inserimento
    # in quotas — dict Python 3.7+ preserva l'ordine di iterazione).
    remainders = {name: exact[name] - floors[name] for name in quotas}
    order = sorted(quotas.keys(), key=lambda n: remainders[n], reverse=True)

    result = dict(floors)
    if remainder > 0:
        for name in order:
            if remainder <= 0:
                break
            result[name] += 1
            remainder -= 1
    elif remainder < 0:
        # Caso limite (total negativo o arrotondamenti anomali): sottrae dalle
        # quote col resto più basso, stesso principio speculare.
        for name in reversed(order):
            if remainder >= 0:
                break
            result[name] -= 1
            remainder += 1
    return result


def _floor_toward_zero_or_down(value: float) -> int:
    """Floor matematico standard (verso il basso), corretto anche per valori negativi."""
    import math
    return math.floor(value)


# ----------------------------------------------------------------------
# Conversione valuta
# ----------------------------------------------------------------------

def coins_to_copper_value(coins: dict[str, int]) -> float:
    """
    Controvalore totale di un insieme di monete espresso in monete di rame,
    usando la tabella di cambio ufficiale (equipment/economy.json). `coins`
    è un dict con chiavi eventualmente parziali tra copper/silver/electrum/
    gold/platinum (le assenti valgono 0).
    """
    total = 0.0
    for currency, abbr in _CURRENCY_ABBR.items():
        qty = coins.get(currency, 0)
        if qty:
            rate = game_data.get_currency_exchange_rate(abbr, "mr")
            total += qty * rate
    return total


def copper_value_to_coins(copper_value: float) -> dict[str, int]:
    """
    Riconverte un controvalore in rame nella combinazione di monete più
    efficiente (greedy top-down: platino→oro→electrum→argento→rame), usando
    la tabella di cambio ufficiale. L'ultima valuta (rame) assorbe sempre
    l'eventuale resto frazionario arrotondato per difetto — nessuna moneta
    frazionaria mai restituita.
    """
    remaining = copper_value
    result: dict[str, int] = {c: 0 for c in _CURRENCY_ORDER}
    for currency in _CURRENCY_ORDER:
        abbr = _CURRENCY_ABBR[currency]
        rate_to_copper = game_data.get_currency_exchange_rate(abbr, "mr")
        if rate_to_copper <= 0:
            continue
        count = int(remaining / rate_to_copper + 1e-9)
        if count > 0:
            result[currency] = count
            remaining -= count * rate_to_copper
    return result


# ----------------------------------------------------------------------
# Ripartizione monete
# ----------------------------------------------------------------------

def split_coins_by_percentage(
    coins: dict[str, int],
    quotas: dict[str, float],
    mode: str = "denomination",
) -> dict[str, Any]:
    """
    Ripartisce un pool di monete tra i destinatari di `quotas` (percentuali
    0-100 che devono sommare a 100 — validare con `validate_quotas` prima di
    chiamare questa funzione, che non blocca da sola input non validi oltre
    a un messaggio di errore nel risultato).

    `coins`: dict con chiavi copper/silver/electrum/gold/platinum (assenti = 0).
    `mode`: "denomination" (default) o "value".

    Ritorna un dict:
      {
        "error": str,  # "" se ok, altrimenti spiega perché non è stato calcolato nulla
        "mode": str,
        "per_recipient": {nome: {"copper":N,"silver":N,...}, ...},
        "total_copper_value": float,  # controvalore totale in rame, per il riepilogo
      }

    In modalità "denomination" ciascuna delle 5 colonne è ripartita in modo
    indipendente col metodo del resto più alto — la somma per colonna tra
    tutti i destinatari combacia sempre esattamente col totale di partenza.

    In modalità "value" l'intero controvalore in rame è ripartito col metodo
    del resto più alto (su un intero — arrotondato al rame più vicino, dato
    che il rame è l'unità indivisibile più piccola), poi ogni quota viene
    riconvertita nella combinazione di monete più efficiente.
    """
    err = validate_quotas(quotas)
    if err:
        return {"error": err, "mode": mode, "per_recipient": {}, "total_copper_value": 0.0}

    if mode not in ("denomination", "value"):
        return {
            "error": f"Modalità di ripartizione sconosciuta: «{mode}».",
            "mode": mode,
            "per_recipient": {},
            "total_copper_value": 0.0,
        }

    total_copper_value = coins_to_copper_value(coins)

    if mode == "value":
        total_copper_units = int(round(total_copper_value))
        per_recipient_copper = largest_remainder_allocation(total_copper_units, quotas)
        per_recipient = {
            name: copper_value_to_coins(float(cp)) for name, cp in per_recipient_copper.items()
        }
        return {
            "error": "",
            "mode": mode,
            "per_recipient": per_recipient,
            "total_copper_value": total_copper_value,
        }

    # mode == "denomination"
    per_recipient: dict[str, dict[str, int]] = {name: {} for name in quotas}
    for currency in _CURRENCY_ORDER:
        column_total = coins.get(currency, 0)
        allocation = largest_remainder_allocation(column_total, quotas)
        for name, qty in allocation.items():
            per_recipient[name][currency] = qty

    return {
        "error": "",
        "mode": mode,
        "per_recipient": per_recipient,
        "total_copper_value": total_copper_value,
    }


# ----------------------------------------------------------------------
# Ripartizione di un oggetto in quantità (non monete)
# ----------------------------------------------------------------------

def split_quantity_by_shares(total_quantity: int, shares: dict[str, int]) -> str:
    """
    Valida una ripartizione per CONTEGGIO (non percentuale) di un oggetto
    indivisibile posseduto in `total_quantity` copie — es. 3 pozioni, 5
    gemme — tra i destinatari di `shares` (nome → quantità intera assegnata).

    Ritorna una stringa di errore in italiano se la somma delle quantità
    assegnate non combacia esattamente con `total_quantity`, o se una
    quantità è negativa, o se `total_quantity <= 0` (voce con quantità 0 non
    ripartibile, per `loot_design.md` §7). Ritorna "" se la ripartizione è
    valida — il chiamante (UI) esegue poi la scrittura reale (una riga
    inventario per destinatario con quella quantità).
    """
    if total_quantity <= 0:
        return "La voce ha quantità 0 (o negativa): nulla da ripartire."
    if not shares:
        return "Nessun destinatario indicato."
    for name, qty in shares.items():
        if qty < 0:
            return f"La quantità assegnata a «{name}» non può essere negativa."
    assigned = sum(shares.values())
    if assigned != total_quantity:
        return (
            f"Le quantità assegnate ({assigned}) non combaciano con il totale "
            f"disponibile ({total_quantity})."
        )
    return ""
