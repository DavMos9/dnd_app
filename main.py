"""
Entry point dell'applicazione D&D Companion.
"""

import sys
import logging
import flet as ft

# Aggiungi la root del progetto al path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data.database import init_db
from ui.app import run_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Avvio D&D Companion...")
    try:
        init_db()
        logger.info("Database pronto.")
    except Exception as e:
        logger.error(f"Impossibile inizializzare il database: {e}")
        sys.exit(1)

    ft.app(target=run_app)


if __name__ == "__main__":
    main()
