"""
Controllo aggiornamenti via GitHub Releases API.

Gira in un thread separato per non bloccare la UI (vedi
`ui/app.py::DnDApp._start_update_check`). Uso:

    from core.update_checker import check_for_updates
    has_update, info = check_for_updates()
    if has_update:
        ...  # info.asset_url, info.asset_size, info.requires_reinstall

Legge anche gli `assets` della release e individua quello della piattaforma
corrente — è ciò che rende possibile il download in-app con barra di
avanzamento (`core/update_downloader.py`), invece di limitarsi a dire che
un aggiornamento esiste e aprire la pagina della release nel browser.

Nessun import di Flet, come tutto `core/*.py`: la piattaforma si rileva
dall'ambiente, non da `page.platform`.
"""

import json
import logging
import os
import platform
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from version import APP_VERSION, FIRST_SIGNED_VERSION, GITHUB_REPO, parse_version

logger = logging.getLogger(__name__)

_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_TIMEOUT = 5  # secondi

#: Nome dell'asset pubblicato dalla CI per ciascuna piattaforma. DEVE restare
#: allineato ai nomi in `.github/workflows/release.yml` (job `release`, elenco
#: `files:`): sono un contratto fra la CI e questo modulo, e un refuso qui
#: significa "nessun aggiornamento scaricabile" in silenzio — per questo un test
#: (`test_aggiornamento_app.py`) confronta questa tabella col workflow reale.
ASSET_NAMES: dict[str, str] = {
    "Android": "dnd-companion-android.apk",
    "Windows": "dnd-companion-windows.zip",
    "Darwin": "dnd-companion-macos.zip",
    "Linux": "dnd-companion-linux.tar.gz",
}


@dataclass(frozen=True)
class UpdateInfo:
    """
    Tutto ciò che serve alla UI per proporre — ed eseguire — un aggiornamento.

    `asset_url`/`asset_size` sono vuoti/zero quando la release non contiene un
    asset per questa piattaforma: l'aggiornamento va comunque annunciato (esiste
    una versione più recente), ma solo come link alla pagina della release, non
    come download in-app.
    """
    latest_version: str
    release_url: str
    asset_name: str = ""
    asset_url: str = ""       # browser_download_url dell'asset
    asset_size: int = 0       # byte, dal campo `size` dell'API
    requires_reinstall: bool = False

    @property
    def can_download(self) -> bool:
        return bool(self.asset_url)


def is_dev_checkout() -> bool:
    """
    True quando l'app gira dal repository sorgente invece che da un pacchetto
    rilasciato (`.git/` presente accanto al codice).

    Serve perché `version.APP_VERSION` è affidabile SOLO dentro un pacchetto: la
    CI lo riscrive dal tag git al momento della build, quindi nel working tree
    resta il valore committato, tipicamente più basso dell'ultimo tag. Senza
    questa guardia `python main.py` annuncia un aggiornamento a ogni avvio,
    verso una versione che è già quella in esecuzione.

    Stessa forma della guardia `if self.page.web: return` in
    `ui/app.py::_start_update_check()`: un controllo esplicito e dichiarato, non
    un fallimento silenzioso.
    """
    try:
        return (Path(__file__).resolve().parent.parent / ".git").is_dir()
    except OSError:
        return False


def current_platform_key() -> str:
    """
    `"Android"` | `"Windows"` | `"Darwin"` | `"Linux"`, oppure `""` se non
    riconosciuta.

    `ANDROID_DATA` per primo: su Android `platform.system()` restituisce
    `"Linux"` e sceglierebbe il tar.gz desktop. È lo stesso test già usato da
    `data/database.py::get_db_path()`.
    """
    if os.environ.get("ANDROID_DATA"):
        return "Android"
    system = platform.system()
    return system if system in ASSET_NAMES else ""


def platform_asset_name() -> str:
    """Nome del file da cercare fra gli asset della release, `""` se la
    piattaforma non è fra quelle pubblicate dalla CI."""
    return ASSET_NAMES.get(current_platform_key(), "")


def _pick_asset(assets: list, wanted_name: str) -> tuple[str, int]:
    """`(browser_download_url, size)` dell'asset con questo nome, o `("", 0)`."""
    if not wanted_name:
        return "", 0
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") == wanted_name:
            url = str(asset.get("browser_download_url", ""))
            try:
                size = int(asset.get("size", 0) or 0)
            except (TypeError, ValueError):
                size = 0
            return url, size
    return "", 0


def crosses_signing_migration(current: str, latest: str) -> bool:
    """
    True se aggiornare da `current` a `latest` attraversa
    `version.FIRST_SIGNED_VERSION`, cioè richiede la disinstallazione manuale
    una-volta-sola descritta in RELEASE.md.

    Funzione a sé (pura, senza rete) perché è la condizione che decide QUALE
    dialogo mostrare, e sbagliarla nei due versi ha conseguenze opposte e
    entrambe brutte: proporre un download in-app che Android rifiuterà di
    installare, oppure spaventare con un avviso di perdita dati chi non ne ha
    bisogno.
    """
    return (
        parse_version(current)
        < parse_version(FIRST_SIGNED_VERSION)
        <= parse_version(latest)
    )


def check_for_updates() -> Tuple[bool, UpdateInfo | None]:
    """
    Controlla se esiste una versione più recente su GitHub Releases.

    Returns:
        `(has_update, info)`. `info` è `None` quando non c'è aggiornamento o
        quando il controllo non è stato possibile (offline, risposta
        inattesa) — mai un'eccezione verso il chiamante: il controllo
        aggiornamenti non deve poter impedire l'avvio dell'app.
    """
    if is_dev_checkout():
        logger.info(
            "update_checker: esecuzione da checkout di sviluppo "
            f"(versione {APP_VERSION} non affidabile) — controllo disattivato"
        )
        return False, None

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
            return False, None

        current = parse_version(APP_VERSION)
        latest = parse_version(latest_version)

        if latest <= current:
            logger.info(f"App aggiornata (versione corrente: {APP_VERSION})")
            return False, None

        wanted = platform_asset_name()
        asset_url, asset_size = _pick_asset(data.get("assets"), wanted)
        if wanted and not asset_url:
            # Release senza l'asset di questa piattaforma: succede se un job
            # della CI è fallito. Va detto nel log, perché il sintomo per
            # l'utente è "mi dice che c'è un aggiornamento ma non lo scarica".
            logger.warning(
                "update_checker: la release %s non contiene l'asset %r — "
                "l'aggiornamento sarà proposto solo come link alla pagina",
                latest_version, wanted,
            )

        info = UpdateInfo(
            latest_version=latest_version,
            release_url=html_url,
            asset_name=wanted if asset_url else "",
            asset_url=asset_url,
            asset_size=asset_size,
            requires_reinstall=crosses_signing_migration(APP_VERSION, latest_version),
        )
        logger.info(
            "Aggiornamento disponibile: %s → %s (asset: %s, %s byte, "
            "reinstallazione necessaria: %s)",
            APP_VERSION, latest_version, info.asset_name or "nessuno",
            info.asset_size, info.requires_reinstall,
        )
        return True, info

    except urllib.error.URLError as e:
        # Nessuna connessione — normale in offline-first
        logger.debug(f"update_checker: nessuna connessione ({e})")
        return False, None
    except Exception as e:
        logger.warning(f"update_checker: errore inatteso ({e})")
        return False, None
