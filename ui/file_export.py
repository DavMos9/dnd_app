"""
Dialoghi nativi del SO per salvare/aprire un file di testo (JSON), generici
— estratti dalla logica già collaudata per l'export/import di un personaggio
(`ui/views/home_view.py::_save_dialog_native`/`_open_dialog_native`/
`_reveal_in_file_manager`), parametrizzati per titolo/nome suggerito/filtro
invece che scritti a mano per ".dndchar" — così l'export del Mondo
(`.dndworld`) può riusarli senza duplicare ~150 righe di subprocess
AppleScript/PowerShell/zenity, e senza toccare (quindi senza alcun rischio di
regressione su) il codice di `home_view.py` già verificato su build reali.

Deliberatamente NON usato per rifattorizzare `home_view.py`: quel codice è
già in produzione e confermato funzionante su macOS/Windows/Linux — un
refactor "a costo zero" sulla carta ha comunque un rischio reale su codice
di automazione OS così delicato (vedi CLAUDE.md). Questo modulo è la base
per OGNI nuovo export/import di file di testo che si aggiunga da qui in
avanti.
"""

from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def native_save_dialog(
    system: str, *, dialog_title: str, default_name: str,
    filter_label: str, filter_ext: str,
) -> tuple[str | None, str | None]:
    """
    Dialogo di salvataggio nativo del SO. `default_name` deve già essere
    sanificato (solo alfanumerici/underscore/trattini) — sicuro da
    incorporare direttamente nei comandi senza escaping, stessa garanzia
    già richiesta dal chiamante originale in `home_view.py`.

    Ritorna `(path, error)`:
    - `(path, None)` → l'utente ha scelto un percorso.
    - `(None, None)` → l'utente ha annullato il dialogo (nessun errore).
    - `(None, "messaggio")` → il dialogo non si è potuto aprire/completare
      per un motivo REALE (comando mancante, permessi di automazione
      negati, ecc.) — DISTINTO da un annullamento pulito.

    Imposta esplicitamente la cartella iniziale a Desktop su tutte e 3 le
    piattaforme — un salvataggio "al buio" finisce comunque in un posto
    prevedibile.
    """
    desktop = os.path.expanduser("~/Desktop")
    path: str | None = None
    error: str | None = None
    try:
        if system == "Darwin":
            # "choose file name"/"POSIX path of" FUORI dal blocco "tell
            # application System Events" — annidarli dentro causa un errore
            # di coercizione AppleScript reale (-1700), non un difetto di
            # stile: System Events prova a interpretare il riferimento a un
            # file NON ANCORA esistente col proprio sistema di classi
            # invece di quello generico delle Standard Additions. "System
            # Events" serve solo per attivare/portare in primo piano il
            # dialogo.
            script = (
                'tell application "System Events" to activate\n'
                f'set f to choose file name with prompt "{dialog_title}" '
                f'default name "{default_name}" '
                'default location (path to desktop folder)\n'
                'return POSIX path of f'
            )
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                path = r.stdout.strip()
            else:
                stderr = (r.stderr or "").strip()
                if "-128" in stderr or "user canceled" in stderr.lower():
                    pass  # annullamento pulito, nessun errore da mostrare
                else:
                    error = stderr or "errore sconosciuto in AppleScript"

        elif system == "Windows":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.SaveFileDialog; "
                f"$d.Title = '{dialog_title}'; "
                f"$d.FileName = '{default_name}'; "
                "$d.InitialDirectory = [Environment]::GetFolderPath('Desktop'); "
                f"$d.Filter = '{filter_label}|*{filter_ext}|Tutti i file|*.*'; "
                "if ($d.ShowDialog() -eq 'OK') { $d.FileName }"
            )
            r = subprocess.run(["powershell", "-Command", ps],
                               capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                path = r.stdout.strip()  # vuoto = Annulla, non un errore
            else:
                error = (r.stderr or "").strip() or "errore sconosciuto in PowerShell"

        elif system == "Linux":
            default_path = os.path.join(desktop, default_name)
            found_tool = False
            for cmd in [
                ["zenity", "--file-selection", "--save", "--confirm-overwrite",
                 f"--title={dialog_title}", f"--filename={default_path}"],
                ["kdialog", "--getsavefilename", default_path],
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    found_tool = True
                    if r.returncode == 0 and r.stdout.strip():
                        path = r.stdout.strip()
                        error = None
                        break
                    stderr = (r.stderr or "").strip()
                    if stderr:
                        error = stderr
                        continue
                except FileNotFoundError:
                    continue
            if not found_tool and path is None and error is None:
                error = "nessun dialogo file disponibile (zenity/kdialog non installati)"

    except Exception as ex:
        logger.warning(f"Dialogo salvataggio nativo non disponibile ({system}): {ex}")
        error = str(ex)

    return (path or None), error


def native_open_dialog(
    system: str, *, dialog_title: str, filter_label: str, filter_ext: str,
) -> tuple[str | None, str | None]:
    """Dialogo di apertura nativo del SO, filtrato per estensione. Stesso
    contratto di ritorno `(path, error)` di `native_save_dialog`. Nessun
    filtro di tipo su macOS ("choose file... of type" richiede UTI
    registrati; un'estensione custom non lo è — mostra tutti i file)."""
    path: str | None = None
    error: str | None = None
    try:
        if system == "Darwin":
            script = (
                'tell application "System Events" to activate\n'
                f'set f to choose file with prompt "{dialog_title}" '
                'default location (path to desktop folder)\n'
                'return POSIX path of f'
            )
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                path = r.stdout.strip()
            else:
                stderr = (r.stderr or "").strip()
                if "-128" in stderr or "user canceled" in stderr.lower():
                    pass
                else:
                    error = stderr or "errore sconosciuto in AppleScript"

        elif system == "Windows":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                f"$d.Title = '{dialog_title}'; "
                "$d.InitialDirectory = [Environment]::GetFolderPath('Desktop'); "
                f"$d.Filter = '{filter_label}|*{filter_ext}|Tutti i file|*.*'; "
                "if ($d.ShowDialog() -eq 'OK') { $d.FileName }"
            )
            r = subprocess.run(["powershell", "-Command", ps],
                               capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                path = r.stdout.strip()
            else:
                error = (r.stderr or "").strip() or "errore sconosciuto in PowerShell"

        elif system == "Linux":
            found_tool = False
            for cmd in [
                ["zenity", "--file-selection", f"--title={dialog_title}",
                 f"--file-filter={filter_label} | *{filter_ext}"],
                ["kdialog", "--getopenfilename", ".", f"*{filter_ext}"],
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    found_tool = True
                    if r.returncode == 0 and r.stdout.strip():
                        path = r.stdout.strip()
                        error = None
                        break
                    stderr = (r.stderr or "").strip()
                    if stderr:
                        error = stderr
                        continue
                except FileNotFoundError:
                    continue
            if not found_tool and path is None and error is None:
                error = "nessun dialogo file disponibile (zenity/kdialog non installati)"

    except Exception as ex:
        logger.warning(f"Dialogo apertura nativo non disponibile ({system}): {ex}")
        error = str(ex)

    return (path or None), error


def reveal_in_file_manager(path: str, system: str | None) -> None:
    """Apre il file manager nativo del SO con il file già selezionato —
    chiamare in un thread separato (subprocess bloccante). Nessuna
    eccezione propagata: se il comando fallisce resta solo un warning nei
    log, il file è comunque già stato salvato con successo."""
    try:
        if system == "Darwin":
            subprocess.run(["open", "-R", path], timeout=15)
        elif system == "Windows":
            subprocess.run(["explorer", f"/select,{path}"], timeout=15)
        elif system == "Linux":
            folder = os.path.dirname(path)
            try:
                subprocess.run(["nautilus", "--select", path], timeout=15)
            except FileNotFoundError:
                subprocess.run(["xdg-open", folder], timeout=15)
    except Exception as ex:
        logger.warning(f"Impossibile aprire il file manager per {path}: {ex}")
