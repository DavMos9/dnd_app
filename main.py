"""
Entry point dell'applicazione D&D Companion.

NOTA: ft.run() deve stare a livello di modulo (non dentro if __name__ == "__main__")
perché flet build importa main.py come modulo, non lo esegue come script.
"""

import sys
import logging
import flet as ft
from pathlib import Path

# Aggiungi la root del progetto al path (necessario anche in app packaged)
sys.path.insert(0, str(Path(__file__).parent))

from data.database import init_db
from ui.app import run_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

logger.info("Avvio D&D Companion...")
try:
    init_db()
    logger.info("Database pronto.")
except Exception as e:
    logger.error(f"Impossibile inizializzare il database: {e}")
    # Non sys.exit() in app packaged — Flet gestisce il ciclo di vita

ft.run(run_app)
