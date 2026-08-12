"""
Stato descrittivo di ferita per i mostri nel tracker di combattimento
condiviso (Multiplayer passo 7C, §6.5 di `dnd_app/docs/multiplayer_design.md`).

**Queste soglie sono una convenzione di quest'app, non una regola del
manuale**: il PHB italiano non definisce stati di ferita descrittivi — va
tenuto presente per non scambiarle un domani per un dato di regolamento
verificato (stessa distinzione già fatta per le altre convenzioni UI del
progetto, es. i colori di stato).
"""

from __future__ import annotations

ILLESO = "Illeso"
FERITO = "Ferito"
GRAVEMENTE_FERITO = "Gravemente ferito"
IN_FIN_DI_VITA = "In fin di vita"
FUORI_COMBATTIMENTO = "Fuori combattimento"


def wound_status_label(hp_current: int, hp_max: int) -> str:
    """
    Etichetta descrittiva da PF correnti/massimi — mai i PF esatti, per i
    mostri visti dai giocatori (§6.5):

    | Stato               | PF residui |
    |----------------------|------------|
    | Illeso               | 100%       |
    | Ferito               | sotto il 100% |
    | Gravemente ferito     | 50% o meno |
    | In fin di vita        | 25% o meno |
    | Fuori combattimento   | 0          |

    `hp_max <= 0` (dato mancante/malformato) e `hp_current` negativo sono
    guardati esplicitamente: mai una divisione per zero, mai uno stato
    inconsistente.
    """
    current = max(0, hp_current)
    if hp_max <= 0:
        return FUORI_COMBATTIMENTO if current <= 0 else ILLESO
    if current <= 0:
        return FUORI_COMBATTIMENTO
    ratio = current / hp_max
    if ratio <= 0.25:
        return IN_FIN_DI_VITA
    if ratio <= 0.5:
        return GRAVEMENTE_FERITO
    if ratio < 1.0:
        return FERITO
    return ILLESO
