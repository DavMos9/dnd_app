"""
Re-export della vista condivisa del compendio Oggetti Magici.

La vista è definita in `ui/views/magic_items_view.py`, condivisa anche dal
giocatore. Questo modulo resta come alias, così la Sezione Master continua a
importarla dal proprio package senza duplicare una riga di codice.

Ri-esporta anche gli helper privati di formattazione: sono importati da
`master_magic_item_generator_dialog.py`, e limitarsi alla sola classe
romperebbe quel dialog con un `ImportError` visibile solo a runtime. Sono
qui per non rompere altri chiamanti; il posto canonico da cui importarli
resta `ui.views.magic_items_view`.
"""

from ui.views.magic_items_view import (  # noqa: F401
    MagicItemsView,
    _CATEGORY_ICONS,
    _RARITY_LABELS,
    _RARITY_ORDER,
    _RARITY_TONES,
    _category_base,
    _category_icon,
    _rarity_bucket,
    _rarity_color,
)

#: Nome storico usato da `master_view.py`.
MasterMagicItemsView = MagicItemsView

# Elencati in `__all__` perché sono un contratto di re-export, non import
# inutilizzati: senza questo pyflakes li segnalerebbe (non supporta `# noqa`).
__all__ = [
    "MagicItemsView", "MasterMagicItemsView",
    "_CATEGORY_ICONS", "_RARITY_LABELS", "_RARITY_ORDER", "_RARITY_TONES",
    "_category_base", "_category_icon", "_rarity_bucket", "_rarity_color",
]
