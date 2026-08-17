"""
I dialoghi dell'aggiornamento in-app: barra di download reale, consegna
all'installer e "Aggiornamento completato" (2026-08-17).

Vive in un modulo suo, non in `ui/app.py`: quel file è il router dell'app e
tenerci dentro altre 300 righe di dialoghi lo renderebbe il posto dove si
guarda per capire la navigazione E per capire gli aggiornamenti. `app.py` decide
solo QUALE dialogo aprire; il come sta qui.

Tre dialoghi, per tre situazioni diverse:

1. `show_migration_dialog()` — l'aggiornamento attraversa la migrazione alla
   firma di rilascio (`UpdateInfo.requires_reinstall`), l'unico che richiede di
   disinstallare e reinstallare a mano, perdendo il database. Guida al backup
   prima di procedere, e NON scarica nulla in-app: vedi il commento nel corpo.
2. `show_download_dialog()` — l'aggiornamento normale: barra di avanzamento,
   annullamento, poi "Installa" (Android) o "Mostra nella cartella" (desktop).
3. `show_completion_dialog()` — al primo avvio dopo un aggiornamento: conferma
   che è andato a buon fine, oppure che è rimasto a metà.

### Il ponte fra il thread che scarica e la barra che si muove

`core.update_downloader.download_asset()` è bloccante e va su un thread
(`asyncio.to_thread`); mutare controlli Flet da lì sarebbe una corsa. Si usa
quindi il pattern GIÀ IN PRODUZIONE in questo progetto
(`world_view.py::_start_network_cooldown_ticker`, e per lo stesso motivo):

  - il download scrive su un `DownloadProgress` condiviso;
  - un ciclo `async` schedulato con `page.run_task` lo legge ogni 200 ms e
    aggiorna barra ed etichetta, terminando da sé quando il download finisce o
    quando `page.update()` solleva `RuntimeError` (dialogo chiuso).

Nessuna `page.run_task` per blocco scaricato, nessuna mutazione fuori dal thread
della UI.
"""

from __future__ import annotations

import asyncio
import logging
import platform as sys_platform
import threading

import flet as ft

from core import update_downloader, update_state
from core.update_checker import UpdateInfo
from data.database import get_updates_path
from ui import design as d
from ui import file_export
from ui.widgets import wrap_dialog_actions, show_snack

logger = logging.getLogger(__name__)

#: Cadenza di aggiornamento della barra. 200 ms: la barra si muove con
#: continuità percepibile senza ridisegnare la pagina più spesso del necessario.
#: Stesso valore del ticker del cooldown di rete, per la stessa ragione.
_TICK_S = 0.2


def _is_android(page: ft.Page) -> bool:
    return page.platform == ft.PagePlatform.ANDROID


def _desktop_system() -> str:
    """`"Darwin"`/`"Windows"`/`"Linux"` — per `reveal_in_file_manager` e per le
    istruzioni per sistema operativo."""
    return sys_platform.system()


def _desktop_instructions(system: str) -> str:
    """
    Cosa deve fare l'utente col pacchetto appena scaricato.

    Deliberatamente NON automatizzato: sostituire i file di un'app mentre gira
    richiede di uscire, lanciare un processo helper che aspetta la chiusura,
    scambiare i file e rilanciare — lavoro specifico per ogni sistema operativo,
    col rischio concreto che l'app non riparta più se lo scambio si interrompe a
    metà. Valutato e respinto il 2026-08-06 (vedi
    `docs/changelog_storico.md`), decisione confermata da Davide il 2026-08-17.
    """
    if system == "Darwin":
        return (
            "1. Chiudi DnD Companion.\n"
            "2. Apri lo zip scaricato e sostituisci l'app in Applicazioni.\n"
            "3. Al primo avvio fai clic destro sull'app → «Apri» "
            "(serve solo la prima volta, per via di Gatekeeper)."
        )
    if system == "Windows":
        return (
            "1. Chiudi DnD Companion.\n"
            "2. Estrai lo zip scaricato sopra la cartella dell'app, "
            "sostituendo i file esistenti.\n"
            "3. Riavvia dnd_companion.exe."
        )
    return (
        "1. Chiudi DnD Companion.\n"
        "2. Estrai l'archivio scaricato sopra la cartella dell'app.\n"
        "3. Riavvia l'eseguibile."
    )


# ---------------------------------------------------------------------------
# 1. Migrazione alla firma di rilascio — l'unica volta che serve disinstallare
# ---------------------------------------------------------------------------

def show_migration_dialog(page: ft.Page, info: UpdateInfo) -> None:
    """
    Aggiornamento che attraversa `version.FIRST_SIGNED_VERSION`: Android non può
    installarlo sopra quello attuale, perché cambia la firma dell'app.

    Due scelte controintuitive, entrambe volute:

    - **Non si scarica nulla in-app.** Il pacchetto andrebbe in
      `get_updates_path()`, che su Android è spazio privato dell'app e viene
      CANCELLATO dalla disinstallazione — proprio il passo che l'utente sta per
      fare. Il file svanirebbe nel momento in cui serve. Deve scaricarlo il
      browser, nella cartella Download pubblica, che sopravvive.
    - **Il backup viene prima, e si dice chiaramente che i dati si perdono.**
      Addolcire questo passaggio significherebbe far perdere una campagna a
      qualcuno.
    """
    p = d.T()

    body = ft.Column(
        [
            ft.Text(
                f"La versione {info.latest_version} cambia la firma dell'app: "
                f"Android non può installarla sopra quella attuale.",
                color=p.text, size=d.Size.BODY_SM,
            ),
            ft.Container(height=d.Space.XS),
            ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER, size=18, color=p.danger_icon),
                    ft.Text(
                        "Devi disinstallare e reinstallare l'app UNA VOLTA SOLA. "
                        "La disinstallazione cancella i dati dell'app.",
                        color=p.text, size=d.Size.BODY_SM, expand=True,
                    ),
                ],
                spacing=d.Space.XS,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            ft.Container(height=d.Space.XS),
            d.muted(
                "Da questo aggiornamento in avanti sarà tutto normale: l'app si "
                "aggiornerà da sé, senza disinstallare e senza perdere nulla."
            ),
            ft.Container(height=d.Space.SM),
            ft.Text("Prima di procedere:", color=p.text,
                    weight=ft.FontWeight.BOLD, size=d.Size.BODY_SM),
            d.muted(
                "1. Esporta i tuoi personaggi (Home → Esporta) e i mondi che "
                "ospiti tu (Mondi → Backup). I personaggi che vivono solo in un "
                "mondo ospitato da un altro dispositivo si riprendono dall'host, "
                "ma quelli locali esistono solo qui."
            ),
            d.muted(
                "2. Per ogni mondo in cui giochi ospitato da qualcun altro, "
                "chiedi al master un «codice di trasferimento»: dopo la "
                "reinstallazione questo dispositivo sarà nuovo per lui, e quel "
                "codice è ciò che ti restituisce il personaggio."
            ),
            d.muted(
                "3. Scarica il pacchetto dal browser (non da qui: un file "
                "scaricato dentro l'app verrebbe cancellato dalla "
                "disinstallazione), poi disinstalla e installa la nuova versione."
            ),
        ],
        tight=True, spacing=d.Space.XS, scroll=ft.ScrollMode.AUTO,
    )

    conferma = ft.Checkbox(
        label="Ho salvato i miei dati e capisco che l'app verrà disinstallata",
        value=False,
    )
    scarica_btn = ft.ElevatedButton(
        "Vai alla pagina di download", icon=ft.Icons.OPEN_IN_NEW,
        # `url=` NATIVA: `webbrowser.open()` è un no-op su Android e
        # `page.launch_url()`/`ft.UrlLauncher` sono controlli Service, confermati
        # rotti in questo progetto. Vedi `ui/views/home_view.py`.
        url=ft.Url(url=info.release_url, target=ft.UrlTarget.BLANK),
        disabled=True,
        style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary),
    )

    def _on_conferma(e):
        scarica_btn.disabled = not bool(conferma.value)
        try:
            page.update()
        except RuntimeError:
            pass

    conferma.on_change = _on_conferma
    body.controls.append(ft.Container(height=d.Space.SM))
    body.controls.append(conferma)

    dlg = ft.AlertDialog(
        modal=True,
        title=d.dialog_title(
            "Aggiornamento importante", ft.Icons.SYSTEM_UPDATE, tone="danger",
        ),
        content=body,
        actions=wrap_dialog_actions([
            ft.TextButton("Più tardi", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=p.text_2)),
            scarica_btn,
        ]),
    )
    page.show_dialog(dlg)


# ---------------------------------------------------------------------------
# 2. Aggiornamento normale: scarica, poi installa
# ---------------------------------------------------------------------------

def show_download_dialog(page: ft.Page, info: UpdateInfo) -> None:
    """
    Il dialogo dell'aggiornamento normale, con barra di avanzamento reale.

    Se la release non contiene l'asset di questa piattaforma (un job della CI
    fallito) il download in-app non è possibile: si mostra il solo link alla
    pagina della release, dicendolo, invece di offrire un pulsante che non
    potrebbe funzionare.
    """
    p = d.T()
    android = _is_android(page)
    system = _desktop_system()

    if not info.can_download:
        _mostra_solo_link(page, info)
        return

    progresso = update_downloader.DownloadProgress()
    annulla_evento = threading.Event()

    # La ProgressBar DEVE stare in una ft.Row con expand=True: una ProgressBar
    # nuda dentro una Column dentro un Container provoca un crash Flutter
    # SILENZIOSO (l'intera ListView diventa bianca, nessun errore Python) —
    # documentato in docs/regole_flet_api.md, sezione PROGRESSBAR.
    barra = ft.ProgressBar(value=0, height=8, color=p.magic, expand=True)
    barra_row = ft.Row([barra], visible=False)
    etichetta = d.muted("")
    stato = ft.Text("", color=p.danger, size=12, visible=False)

    dimensione = (f" ({update_downloader.human_size(info.asset_size)})"
                  if info.asset_size else "")
    intestazione = ft.Text(
        f"È disponibile la versione {info.latest_version}{dimensione}.",
        color=p.text, size=d.Size.BODY_SM,
    )
    istruzioni = ft.Text("", color=p.text, size=d.Size.BODY_SM, visible=False)

    scarica_btn = ft.ElevatedButton(
        "Scarica", icon=ft.Icons.DOWNLOAD,
        style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary),
    )
    annulla_download_btn = ft.TextButton(
        "Annulla download", icon=ft.Icons.CLOSE, visible=False,
        style=ft.ButtonStyle(color=p.text_2),
    )
    azione_btn = ft.ElevatedButton(
        "Installa" if android else "Mostra nella cartella",
        icon=ft.Icons.INSTALL_MOBILE if android else ft.Icons.FOLDER_OPEN,
        visible=False,
        style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary),
    )
    chiudi_btn = ft.TextButton("Più tardi", style=ft.ButtonStyle(color=p.text_2))

    def _aggiorna_ui() -> bool:
        """Ridisegna. `False` se il dialogo non c'è più (ciclo da fermare)."""
        try:
            page.update()
            return True
        except RuntimeError:
            return False

    async def _ticker() -> None:
        """Legge lo stato condiviso e muove la barra. Vedi il docstring del
        modulo per il perché di questo pattern."""
        while True:
            await asyncio.sleep(_TICK_S)
            barra.value = progresso.fraction   # None → barra indeterminata
            etichetta.value = update_downloader.progress_label(progresso)
            if not _aggiorna_ui():
                return
            if progresso.is_finished:
                return

    async def _scarica(e) -> None:
        annulla_evento.clear()
        scarica_btn.visible = False
        annulla_download_btn.visible = True
        barra_row.visible = True
        stato.visible = False
        etichetta.value = "Avvio del download…"
        _aggiorna_ui()

        page.run_task(_ticker)
        try:
            percorso = await asyncio.to_thread(
                update_downloader.download_asset,
                info.asset_url, get_updates_path(), info.asset_name,
                expected_size=info.asset_size,
                progress=progresso, cancel=annulla_evento,
            )
        except update_downloader.DownloadCancelled:
            # Annullamento: non è un errore, niente rosso e niente "riprova".
            barra_row.visible = False
            annulla_download_btn.visible = False
            scarica_btn.visible = True
            etichetta.value = ""
            _aggiorna_ui()
            return
        except Exception as ex:
            logger.warning("Download dell'aggiornamento fallito: %s", ex)
            barra_row.visible = False
            annulla_download_btn.visible = False
            scarica_btn.visible = True
            scarica_btn.text = "Riprova"
            stato.visible = True
            stato.value = f"Download fallito: {ex}"
            _aggiorna_ui()
            return

        # Riuscito.
        barra.value = 1.0
        annulla_download_btn.visible = False
        azione_btn.visible = True
        etichetta.value = (
            f"Download completato ({update_downloader.human_size(progresso.downloaded)})."
        )
        if not android:
            istruzioni.visible = True
            istruzioni.value = _desktop_instructions(system)
        _aggiorna_ui()
        logger.info("Aggiornamento %s pronto in %s", info.latest_version, percorso)

    def _annulla_download(e) -> None:
        annulla_evento.set()
        etichetta.value = "Annullamento…"
        _aggiorna_ui()

    async def _azione(e) -> None:
        """
        Consegna il pacchetto: all'installer di sistema su Android, al file
        manager su desktop.

        Il segnalibro va scritto PRIMA: su Android, subito dopo, questo processo
        viene ucciso dall'installer e non avrebbe altra occasione per farlo — è
        quel segnalibro che al prossimo avvio produce "Aggiornamento completato".

        `async def` perché il ponte verso l'estensione nativa è una coroutine
        (vedi `ui/native_apk_installer.py`). Flet invoca direttamente gli handler
        `async def`, come già fanno `_retry` e gli altri handler asincroni del
        dialogo d'ingresso LAN in `world_view.py`.
        """
        update_state.mark_update_started(info.latest_version)

        if android:
            from ui.native_apk_installer import install_apk, ApkInstallerUnavailable
            try:
                await install_apk(page, progresso.path)
            except ApkInstallerUnavailable as ex:
                # L'estensione nativa non è disponibile in questa build: il file
                # è comunque scaricato, si dice dove trovarlo invece di lasciare
                # un pulsante che non fa nulla.
                logger.warning("Installer APK non disponibile: %s", ex)
                stato.visible = True
                stato.value = (
                    f"Non riesco ad aprire l'installer di sistema. Il file è "
                    f"stato scaricato in:\n{progresso.path}\n"
                    f"Aprilo con un gestore file per installarlo."
                )
                _aggiorna_ui()
                return
            return

        threading.Thread(
            target=file_export.reveal_in_file_manager,
            args=(progresso.path, system), daemon=True,
        ).start()
        show_snack(page, "Cartella aperta: segui le istruzioni per completare.")

    scarica_btn.on_click = _scarica
    annulla_download_btn.on_click = _annulla_download
    azione_btn.on_click = _azione

    def _chiudi(e) -> None:
        # Ferma anche un download in corso: senza, il thread continuerebbe a
        # scaricare decine di MB per un dialogo che l'utente ha già chiuso.
        annulla_evento.set()
        page.pop_dialog()

    chiudi_btn.on_click = _chiudi

    dlg = ft.AlertDialog(
        title=d.dialog_title("Aggiornamento disponibile", ft.Icons.SYSTEM_UPDATE,
                              tone="magic"),
        content=ft.Column(
            [
                intestazione,
                ft.Container(height=d.Space.XS),
                barra_row,
                etichetta,
                istruzioni,
                stato,
            ],
            tight=True, spacing=d.Space.XS, scroll=ft.ScrollMode.AUTO,
        ),
        actions=wrap_dialog_actions([
            chiudi_btn, annulla_download_btn, scarica_btn, azione_btn,
        ]),
    )
    page.show_dialog(dlg)


def _mostra_solo_link(page: ft.Page, info: UpdateInfo) -> None:
    """Ripiego quando non c'è un asset scaricabile per questa piattaforma: si
    dice perché, invece di mostrare un pulsante «Scarica» che fallirebbe."""
    p = d.T()
    dlg = ft.AlertDialog(
        title=d.dialog_title("Aggiornamento disponibile", ft.Icons.SYSTEM_UPDATE,
                              tone="magic"),
        content=ft.Column(
            [
                ft.Text(f"È disponibile la versione {info.latest_version}.",
                        color=p.text, size=d.Size.BODY_SM),
                d.muted(
                    "Per questa piattaforma il pacchetto non è scaricabile "
                    "dall'app: aprilo dalla pagina della release."
                ),
            ],
            tight=True, spacing=d.Space.XS,
        ),
        actions=wrap_dialog_actions([
            ft.TextButton("Più tardi", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=p.text_2)),
            ft.ElevatedButton(
                "Apri la pagina", icon=ft.Icons.OPEN_IN_NEW,
                url=ft.Url(url=info.release_url, target=ft.UrlTarget.BLANK),
                on_click=lambda e: page.pop_dialog(),
                style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary),
            ),
        ]),
    )
    page.show_dialog(dlg)


# ---------------------------------------------------------------------------
# 3. "Aggiornamento completato" — al primo avvio dopo l'aggiornamento
# ---------------------------------------------------------------------------

def show_completion_dialog(page: ft.Page, current_version: str,
                            pending_version: str, outcome: str) -> None:
    """
    `outcome` viene da `core.update_state.classify_pending_update()`. Questa
    funzione si aspetta solo `"completed"` o `"failed"`: `"none"` e `"stale"` non
    mostrano nulla e vengono gestiti dal chiamante (`ui/app.py`).
    """
    p = d.T()

    if outcome == "completed":
        dlg = ft.AlertDialog(
            title=d.dialog_title("Aggiornamento completato", ft.Icons.CHECK_CIRCLE,
                                  tone="success"),
            content=ft.Column(
                [
                    ft.Text(f"Ora stai usando la versione {current_version}.",
                            color=p.text, size=d.Size.BODY_SM),
                    d.muted("I tuoi personaggi e i tuoi mondi sono al loro posto."),
                ],
                tight=True, spacing=d.Space.XS,
            ),
            actions=wrap_dialog_actions([
                ft.ElevatedButton("Perfetto", on_click=lambda e: page.pop_dialog(),
                                   style=ft.ButtonStyle(bgcolor=p.magic,
                                                        color=p.on_primary)),
            ]),
        )
        page.show_dialog(dlg)
        return

    dlg = ft.AlertDialog(
        title=d.dialog_title("Aggiornamento non completato", ft.Icons.INFO_OUTLINE,
                              tone="warning"),
        content=ft.Column(
            [
                ft.Text(
                    f"L'aggiornamento alla versione {pending_version} era stato "
                    f"avviato ma non è stato completato: stai ancora usando la "
                    f"{current_version}.",
                    color=p.text, size=d.Size.BODY_SM,
                ),
                d.muted("Puoi riprovare quando vuoi dal controllo aggiornamenti."),
            ],
            tight=True, spacing=d.Space.XS,
        ),
        actions=wrap_dialog_actions([
            ft.TextButton("Ho capito", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=p.text_2)),
        ]),
    )
    page.show_dialog(dlg)
