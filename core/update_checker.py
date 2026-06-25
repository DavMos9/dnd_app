"""
Controllo aggiornamenti via GitHub Releases API.

Gira in un thread separato per non bloccare la UI.
Uso:
    from core.update_checker import check_for_updates
    has_update, version, url = check_for_updates()
"""

import logging
import urllib.request
import urllib.error
import json
from typing import Tuple

from version import APP_VERSION, GITHUB_REPO

logger = logging.getLogger(__name__)

_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_TIMEOUT = 5  # secondi


def _parse_version(version_str: str) -> Tuple[int, ...]:
    """Converte '1.2.3' o 'v1.2.3' in (1, 2, 3) per confronto ordinale."""
    clean = version_str.lstrip("v").strip()
    try:
        return tuple(int(x) for x in clean.split("."))
    except ValueError:
        return (0,)


def check_for_updates() -> Tuple[bool, str, str]:
    """
    Controlla se esiste una versione più recente su GitHub Releases.

    Returns:
        (has_update, latest_version, release_url)
        - has_update: True se esiste una versione più recente
        - latest_version: stringa della versione più recente (es. "0.2.0")
        - release_url: URL della pagina di rilascio su GitHub
    """
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"DnDCompanion/{APP_VERSION}",
            },
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())

        tag = data.get("tag_name", "")
        html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
        latest_version = tag.lstrip("v").strip()

        if not latest_version:
            logger.warning("update_checker: tag_name vuoto nella risposta GitHub")
            return False, "", ""

        current = _parse_version(APP_VERSION)
        latest = _parse_version(latest_version)

        has_update = latest > current
        if has_update:
            logger.info(f"Aggiornamento disponibile: {APP_VERSION} → {latest_version}")
        else:
            logger.info(f"App aggiornata (versione corrente: {APP_VERSION})")

        return has_update, latest_version, html_url

    except urllib.error.URLError as e:
        # Nessuna connessione — normale in offline-first
        logger.debug(f"update_checker: nessuna connessione ({e})")
        return False, "", ""
    except Exception as e:
        logger.warning(f"update_checker: errore inatteso ({e})")
        return False, "", ""
