"""
Entry point dell'applicazione D&D Companion.

NOTA: ft.run() deve stare a livello di modulo (non dentro if __name__ == "__main__")
perché flet build importa main.py come modulo, non lo esegue come script.
"""

import sys
import os
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# File-based debug logger — stdout/stderr non arrivano su iOS device
# Output: <App sandbox>/Documents/dnd_debug.log
# Lettura: Xcode → Window → Devices and Simulators → device
#          → app dnd-companion → Download Container
#          → AppData/Documents/dnd_debug.log
# ---------------------------------------------------------------------------
_LOG_PATH = None


def _w(msg: str) -> None:
    """Scrive una riga di debug su file (failsafe, mai eccezioni)."""
    global _LOG_PATH
    try:
        if _LOG_PATH is None:
            home = os.environ.get("HOME", "/tmp")
            log_dir = Path(home) / "Documents"
            log_dir.mkdir(parents=True, exist_ok=True)
            _LOG_PATH = log_dir / "dnd_debug.log"
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass  # se anche il file non funziona, non c'è nulla che possiamo fare


_w("=" * 60)
_w(f"[1] main.py started — python {sys.version}")
_w(f"    __file__ = {__file__}")
_w(f"    cwd      = {os.getcwd()}")

# ---------------------------------------------------------------------------
# import flet
# ---------------------------------------------------------------------------
try:
    import flet as ft
    _w("[2] flet imported OK")
except Exception as e:
    _w(f"[2] flet import FAILED: {e}")
    _w(traceback.format_exc())
    raise

# ---------------------------------------------------------------------------
# sys.path + lista file bundle (debug)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
_w(f"[3] sys.path[0] = {Path(__file__).parent}")

try:
    root_files = sorted(os.listdir(Path(__file__).parent))
    _w(f"[3b] root files: {root_files}")
except Exception as e:
    _w(f"[3b] cannot list root files: {e}")

# ---------------------------------------------------------------------------
# import data.database
# ---------------------------------------------------------------------------
try:
    from data.database import init_db
    _w("[4] data.database imported OK")
except Exception as e:
    _w(f"[4] data.database import FAILED: {e}")
    _w(traceback.format_exc())
    raise

# ---------------------------------------------------------------------------
# import ui.app
# ---------------------------------------------------------------------------
try:
    from ui.app import run_app
    _w("[5] ui.app imported OK")
except Exception as e:
    _w(f"[5] ui.app import FAILED: {e}")
    _w(traceback.format_exc())
    raise

# ---------------------------------------------------------------------------
# logging standard
# ---------------------------------------------------------------------------
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------
_w("[6] calling init_db()")
try:
    init_db()
    _w("[7] init_db OK")
except Exception as e:
    _w(f"[7] init_db FAILED: {e}")
    _w(traceback.format_exc())

# ---------------------------------------------------------------------------
# ft.run — modalità web (Docker) o desktop/mobile
# FLET_WEB=true  → web server su 0.0.0.0:FLET_PORT (default 8000)
# ---------------------------------------------------------------------------
_w("[8] calling ft.run()")

_web  = os.environ.get("FLET_WEB", "").lower() in ("1", "true", "yes")
_port = int(os.environ.get("FLET_PORT", "8000"))

if _web:
    # Nota (2026-07-12): niente piu' upload_dir/get_upload_url qui --
    # il tentativo di vero upload client->server via ft.FilePicker.upload()
    # e' stato abbandonato dopo aver confermato (issue tracker upstream
    # flet-dev/flet#6040/#6250/#6251) che FilePicker e' strutturalmente
    # rotto in web mode, indipendentemente da come lo si usa. La foto
    # profilo/immagini mappa in modalita' web ora passano dalla libreria
    # immagini caricata a mano da Davide via SSH (vedi
    # data/database.py -> get_image_library_path(), ui/image_library.py) --
    # nessun endpoint di upload Flet necessario. Vedi CLAUDE.md per il
    # changelog completo.
    _w(f"[8] WEB mode — host=0.0.0.0 port={_port}")
    ft.run(run_app, view=ft.AppView.WEB_BROWSER, port=_port, host="0.0.0.0")
else:
    ft.run(run_app)
