"""
Schermata Home: selezione, creazione ed eliminazione dei personaggi.
È la prima schermata che l'utente vede all'avvio.
"""

import flet as ft
import logging
import os
import threading
from typing import cast
from config.settings import *
from data.database import get_character_exports_path
from data.models import Character
from data.repositories import character_repo, character_export
from ui.character_transfer import show_character_import_picker
from ui.theme import (
    title_text, body_text, muted_text,
    primary_button, ghost_button,
)

logger = logging.getLogger(__name__)


def _data_uri(b64: str) -> str:
    """Data URI da base64 con rilevamento formato (Flet 0.85.3 non ha src_base64)."""
    try:
        import base64 as _b64
        h = _b64.b64decode(b64[:16] + "==")
        if h[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif h[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        else:
            mime = "image/jpeg"
    except Exception:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


class HomeView(ft.Column):
    """
    Lista dei personaggi esistenti con azioni di selezione, eliminazione
    e creazione (wizard o manuale).

    Callbacks:
        on_select(character_id: str)  → carica la scheda del personaggio
        on_create_wizard()            → avvia il wizard guidato
        on_create_manual()            → apre il form manuale
        on_open_master()              → apre la Modalità Master (indipendente
                                         dai personaggi, vedi ui/views/master/)
    """

    def __init__(self, on_select, on_create_wizard, on_create_manual, on_open_master=None):
        super().__init__(expand=True, spacing=0)
        self.on_select = on_select
        self.on_create_wizard = on_create_wizard
        self.on_create_manual = on_create_manual
        self.on_open_master = on_open_master

        self._char_list_column = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO)
        self._stop_event = threading.Event()
        # FilePicker persistente per Export/Import su mobile nativo
        # (Android/iOS) — registrato in did_mount(), MAI su desktop/web
        # (vedi _ensure_file_picker() e nota 2026-07-24 più sotto).
        self._file_picker: ft.FilePicker | None = None
        self._build()
        self.refresh()
        # Polling per sincronizzare più sessioni web sullo stesso DB
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()

    def did_mount(self):
        """
        Registra il FilePicker SUBITO al mount, solo su mobile nativo —
        stesso principio già stabilito nel progetto (profilo_tab.py,
        maps_view.py): su desktop e in web mode ft.FilePicker come
        controllo non è utilizzabile (bug upstream confermato, vedi
        CLAUDE.md), quindi non va MAI registrato lì, nemmeno per Export/
        Import di personaggi.
        """
        page = self.page
        if page is not None and page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            self._ensure_file_picker()

    def stop_polling(self):
        """Ferma il polling di sincronizzazione (chiamare prima di navigare via)."""
        self._stop_event.set()

    def _poll_loop(self):
        """Aggiorna la lista personaggi ogni 5 s per sincronizzare sessioni web diverse."""
        while not self._stop_event.wait(5):
            try:
                if self.page is None:
                    break
                self.refresh()
                self.page.update()
            except Exception:
                break

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build(self):
        # Logo D&D come widget Flet — testo bold rosso, nessuna immagine
        logo_widget = ft.Text(
            "D&D",
            size=52,
            weight=ft.FontWeight.BOLD,
            color=COLOR_ACCENT_CRIMSON,
        )

        header = ft.Container(
            content=ft.Column(
                [
                    ft.Row([logo_widget], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=4),
                    # Azioni sempre visibili come pillole invece del vecchio menu a tre
                    # puntini "Altro" (2026-07-24, redesign su richiesta di Davide: lo
                    # stesso trattamento già applicato a master_view.py/
                    # master_encounter_view.py, non solo alla Sezione Master come inteso
                    # inizialmente — Davide ha chiarito che valeva anche per questa
                    # Home). `wrap=True`: su schermi stretti (smartphone) le pillole e il
                    # bottone "Nuovo Personaggio" vanno a capo su più righe invece di
                    # traboccare — niente `Container(expand=True)` in questa Row, per lo
                    # stesso motivo già documentato altrove nel progetto (incompatibile
                    # con `wrap=True`): il logo vive in una riga separata sopra.
                    ft.Row(
                        self._header_actions(),
                        spacing=8, wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    muted_text("Seleziona un personaggio o creane uno nuovo", size=13),
                ],
                spacing=6,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=16),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

        body = ft.Container(
            content=ft.Column(
                [self._char_list_column],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=ft.Padding.all(32),
        )

        self.controls = [header, body]

    def _new_character_button(self) -> ft.Control:
        """Bottone '+' che apre il dialog per scegliere wizard o manuale."""
        return ft.ElevatedButton(
            "Nuovo Personaggio",
            icon=ft.Icons.ADD,
            on_click=self._on_new_click,
            style=ft.ButtonStyle(
                bgcolor=COLOR_ACCENT_GOLD,
                color=COLOR_BG_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

    def _header_actions(self) -> list[ft.Control]:
        """Azioni header sempre visibili — pillole "Modalità Master"/"Importa
        personaggio" + il pulsante primario "Nuovo Personaggio", tutte nella
        stessa Row `wrap=True` (2026-07-24, redesign: sostituisce il vecchio
        `_more_menu()` a tre puntini, stesso trattamento "pillole sempre
        visibili" scelto da Davide per la Sezione Master — qui esteso alla
        Home su sua esplicita richiesta). "Modalità Master" compare solo se
        `on_open_master` è stato passato (stesso comportamento "nascosto se
        assente" del vecchio menu, per non rompere chiamate legacy a
        `HomeView`)."""
        actions: list[ft.Control] = []
        if self.on_open_master is not None:
            actions.append(
                self._action_pill(
                    ft.Icons.CASTLE_OUTLINED, "Modalità Master", COLOR_ACCENT_BLUE,
                    lambda e: self.on_open_master(),
                )
            )
        actions.append(
            self._action_pill(
                ft.Icons.UPLOAD_FILE, "Importa personaggio", COLOR_ACCENT_GOLD,
                self._on_import_click,
            )
        )
        actions.append(self._new_character_button())
        return actions

    @staticmethod
    def _action_pill(icon, label: str, color: str, on_click) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=15, color=color),
                    ft.Container(width=6),
                    ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=color),
                ],
                tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, color),
            border_radius=16,
            on_click=on_click,
            ink=True,
        )

    # ------------------------------------------------------------------
    # Dati
    # ------------------------------------------------------------------

    def refresh(self):
        """Ricarica la lista personaggi dal database."""
        characters = character_repo.get_all()
        self._char_list_column.controls.clear()

        if not characters:
            self._char_list_column.controls.append(self._empty_state())
        else:
            for char in characters:
                self._char_list_column.controls.append(
                    self._character_card(char)
                )

        # update() è valido solo dopo il mount sulla page
        try:
            self._char_list_column.update()
        except RuntimeError:
            pass  # chiamata da __init__, il render avviene con page.add()

    # ------------------------------------------------------------------
    # Card personaggio
    # ------------------------------------------------------------------

    def _character_card(self, char: Character) -> ft.Container:
        """Card con info essenziali del personaggio e azioni."""

        # Foto o placeholder (priorità: base64 in DB > percorso file > icona)
        if char.image_data:
            avatar = ft.Container(
                content=ft.Image(
                    src=_data_uri(char.image_data),
                    width=72, height=72,
                    fit=ft.BoxFit.COVER,
                ),
                width=72, height=72,
                border_radius=6,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )
        elif char.image_path:
            avatar = ft.Image(
                src=char.image_path,
                width=72, height=72,
                fit=ft.BoxFit.COVER,
                border_radius=ft.BorderRadius.all(6),
            )
        else:
            avatar = ft.Container(
                width=72, height=72,
                bgcolor=COLOR_BG_SECONDARY,
                border_radius=6,
                border=ft.Border.all(1, COLOR_BORDER),
                content=ft.Icon(ft.Icons.PERSON, color=COLOR_TEXT_MUTED, size=36),
                alignment=ft.Alignment.CENTER,
            )

        # Badge livello
        level_badge = ft.Container(
            content=ft.Text(
                f"Liv. {char.level}",
                size=11,
                weight=ft.FontWeight.BOLD,
                color=COLOR_BG_PRIMARY,
            ),
            bgcolor=COLOR_ACCENT_GOLD,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

        info = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            char.name or "Senza nome",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY,
                        ),
                        level_badge,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                body_text(
                    f"{char.class_name}  ·  {char.race}",
                    size=13,
                    color=COLOR_TEXT_SECONDARY,
                ),
                muted_text(
                    char.background or "Nessun background",
                    size=12,
                ),
            ],
            spacing=4,
            expand=True,
        )

        actions = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                    icon_color=COLOR_ACCENT_GOLD,
                    tooltip="Gioca con questo personaggio",
                    on_click=lambda e, cid=char.id: self.on_select(cid),
                ),
                ft.IconButton(
                    icon=ft.Icons.IOS_SHARE,
                    icon_color=COLOR_TEXT_SECONDARY,
                    tooltip="Esporta personaggio (file .dndchar)",
                    on_click=lambda e, c=char: self._on_export_click(c),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=COLOR_ACCENT_RED,
                    tooltip="Elimina personaggio",
                    on_click=lambda e, c=char: self._confirm_delete(c),
                ),
            ],
            spacing=0,
        )

        card_content = ft.Row(
            [avatar, ft.Container(width=16), info, actions],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=card_content,
            padding=16,
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
            on_click=lambda e, cid=char.id: self.on_select(cid),
            ink=True,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

    # ------------------------------------------------------------------
    # Stato vuoto
    # ------------------------------------------------------------------

    def _empty_state(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SHIELD_OUTLINED, size=80, color=COLOR_BORDER),
                    ft.Container(height=16),
                    title_text("Nessun personaggio", size=20),
                    ft.Container(height=8),
                    muted_text(
                        "Crea il tuo primo personaggio per iniziare l'avventura.",
                        size=14,
                    ),
                    ft.Container(height=24),
                    ft.Column(
                        controls=cast(list[ft.Control], [
                            primary_button(
                                "Wizard guidato",
                                on_click=lambda e: self.on_create_wizard(),
                                icon=ft.Icons.AUTO_FIX_HIGH,
                            ),
                            ghost_button(
                                "Creazione manuale",
                                on_click=lambda e: self.on_create_manual(),
                            ),
                            ft.OutlinedButton(
                                "Importa personaggio",
                                icon=ft.Icons.UPLOAD_FILE,
                                on_click=self._on_import_click,
                                style=ft.ButtonStyle(
                                    color=COLOR_TEXT_SECONDARY,
                                    side=ft.BorderSide(1, COLOR_BORDER),
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                ),
                            ),
                        ]),
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
            padding=64,
        )

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _on_new_click(self, e):
        """Dialog per scegliere wizard o creazione manuale."""
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Nuovo Personaggio",
                color=COLOR_TEXT_TITLE,
                weight=ft.FontWeight.BOLD,
            ),
            bgcolor=COLOR_BG_CARD,
            content=ft.Column(
                [
                    muted_text(
                        "Come vuoi creare il tuo personaggio?",
                        size=14,
                    ),
                    ft.Container(height=16),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Wizard guidato",
                                icon=ft.Icons.AUTO_FIX_HIGH,
                                tooltip="Rispondi ad alcune domande e l'app crea il personaggio più adatto a te",
                                on_click=lambda e: self._close_and(self.on_create_wizard),
                                expand=True,
                                style=ft.ButtonStyle(
                                    bgcolor=COLOR_ACCENT_GOLD,
                                    color=COLOR_BG_PRIMARY,
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                            ),
                        ],
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Creazione manuale",
                                icon=ft.Icons.EDIT_NOTE,
                                tooltip="Compila direttamente tutti i campi della scheda",
                                on_click=lambda e: self._close_and(self.on_create_manual),
                                expand=True,
                                style=ft.ButtonStyle(
                                    color=COLOR_ACCENT_GOLD,
                                    side=ft.BorderSide(1, COLOR_ACCENT_GOLD),
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                            ),
                        ],
                    ),
                ],
                tight=True,
                spacing=0,
            ),
            actions=[
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: self._close_dialog(),
                    style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _confirm_delete(self, char: Character):
        """Dialog di conferma eliminazione."""
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Elimina personaggio", color=COLOR_ACCENT_RED),
            bgcolor=COLOR_BG_CARD,
            content=ft.Text(
                f'Sei sicuro di voler eliminare "{char.name}"?\nQuesta azione non può essere annullata.',
                color=COLOR_TEXT_PRIMARY,
            ),
            actions=[
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: self._close_dialog(),
                    style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY),
                ),
                ft.ElevatedButton(
                    "Elimina",
                    icon=ft.Icons.DELETE,
                    on_click=lambda e: self._do_delete(dlg, char.id),
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_RED,
                        color=COLOR_TEXT_PRIMARY,
                        shape=ft.RoundedRectangleBorder(radius=6),
                    ),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _do_delete(self, dlg: ft.AlertDialog, character_id: str):
        self.page.pop_dialog()
        if character_repo.delete(character_id):
            self.refresh()
        else:
            self._show_error("Errore durante l'eliminazione del personaggio.")

    def _close_dialog(self):
        self.page.pop_dialog()

    def _close_and(self, callback):
        self.page.pop_dialog()
        callback()

    def _show_error(self, message: str):
        snack = ft.SnackBar(
            content=ft.Text(message, color=COLOR_TEXT_PRIMARY),
            bgcolor=COLOR_ACCENT_RED,
        )
        self.page.show_dialog(snack)

    def _show_success(self, message: str):
        snack = ft.SnackBar(
            content=ft.Text(message, color=COLOR_TEXT_PRIMARY),
            bgcolor=COLOR_ACCENT_GOLD,
        )
        self.page.show_dialog(snack)

    # ------------------------------------------------------------------
    # Export / Import personaggio (2026-07-24)
    #
    # Stesso principio cross-platform già stabilito nel progetto per la
    # selezione immagini (profilo_tab.py/maps_view.py): ft.FilePicker non è
    # utilizzabile né su desktop né in web mode in Flet 0.85.3 (bug
    # upstream confermato, vedi CLAUDE.md 2026-07-12) — qui va inoltre
    # notato che il metodo pick_files()/save_file() di questa esatta
    # versione di Flet non espone nemmeno un evento on_result utilizzabile
    # per il ramo mobile (verificato leggendo il sorgente del pacchetto
    # installato: FilePicker in flet==0.85.3 ha solo metodi async con
    # valore di ritorno diretto, nessun attributo on_result) — il codice
    # mobile già presente altrove nel progetto per le foto si basa su
    # quell'attributo e non è mai stato verificato con una vera build
    # mobile. Per non introdurre un percorso mobile scritto ma mai
    # verificabile in questa sessione, Export/Import mostrano un messaggio
    # esplicito "non ancora disponibile" su Android/iOS invece di tentare
    # un codice non testato — scelta di onestà tecnica, non una lacuna
    # nascosta. Desktop e Web sono invece pienamente implementati e testati.
    # ------------------------------------------------------------------

    def _ensure_file_picker(self) -> ft.FilePicker | None:
        """
        Ritorna il FilePicker mobile — normalmente già registrato in
        did_mount(); se per qualche motivo non lo fosse ancora (pagina non
        pronta al momento del mount), lo crea e registra qui al volo,
        stesso fallback difensivo già in uso in profilo_tab.py/
        maps_view.py per lo stesso identico controllo. Raggiungibile SOLO
        dai due metodi mobile qui sotto (_on_mobile_export/_on_mobile_import),
        mai da desktop/web.
        """
        page = self.page
        if page is None:
            return None
        if self._file_picker is None:
            self._file_picker = ft.FilePicker()
            page.overlay.append(self._file_picker)
            try:
                page.update()
            except RuntimeError:
                pass
        return self._file_picker

    # --- Export -----------------------------------------------------------

    def _on_export_click(self, char: Character):
        page = self.page
        if page is None:
            return
        if page.web:
            self._export_web(char)
            return
        platform = page.platform
        if platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            page.run_task(self._on_mobile_export, char)
            return
        import platform as sys_platform
        system = sys_platform.system()
        threading.Thread(target=self._export_desktop, args=(char, system), daemon=True).start()

    async def _on_mobile_export(self, char: Character):
        """
        Export su Android/iOS (2026-07-24) — a differenza del vecchio
        codice foto (profilo_tab.py/maps_view.py, mai verificato con una
        vera build mobile), qui uso l'API realmente corretta di
        flet==0.85.3: verificato leggendo il sorgente installato del
        pacchetto che FilePicker in questa versione NON ha alcun evento
        `on_result` (solo `on_upload`, per il progresso di un upload) —
        `save_file()`/`pick_files()` sono metodi `async` che restituiscono
        il risultato DIRETTAMENTE tramite `await`. Su mobile (a differenza
        del desktop) `save_file(..., src_bytes=...)` scrive anche
        realmente il file con quel contenuto: non serve alcun secondo
        passaggio di scrittura, il metodo fa tutto da solo.
        """
        picker = self._ensure_file_picker()
        if picker is None:
            return
        json_text = character_export.export_to_json_string(char.id)
        if json_text is None:
            self._show_error("Errore durante l'esportazione del personaggio.")
            return
        filename = character_export.suggested_export_filename(char.id)
        try:
            result_path = await picker.save_file(
                dialog_title="Esporta personaggio",
                file_name=filename,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["dndchar"],
                src_bytes=json_text.encode("utf-8"),
            )
        except Exception as exc:
            logger.error(f"Errore FilePicker.save_file (mobile): {exc}")
            self._show_error(f"Errore durante l'esportazione:\n{exc}")
            return
        if not result_path:
            return  # utente ha annullato, nessun errore da mostrare
        self._show_export_success_dialog(filename, result_path, system=None)

    def _export_web(self, char: Character):
        """
        Modalità web: scrive il file nella cartella condivisa
        (get_character_exports_path()) — Davide può ancora prelevarlo a
        mano via SSH/scp come prima, ma dal 2026-07-24 questa stessa
        cartella è ANCHE la assets_dir servita staticamente da Flet in
        modalità web (vedi main.py) — il file diventa quindi raggiungibile
        a un vero URL HTTP (`/<filename>`), permettendo un download reale
        da browser con un solo click (bottone "Scarica" nel dialog di
        conferma, vedi _show_export_success_dialog). Nessun controllo
        FilePicker/UrlLauncher coinvolto in questo meccanismo — è pura
        consegna di file statici lato server, per cui il bug upstream che
        blocca quei due controlli in web mode non si applica qui.
        """
        json_text = character_export.export_to_json_string(char.id)
        if json_text is None:
            self._show_error("Errore durante l'esportazione del personaggio.")
            return
        filename = character_export.suggested_export_filename(char.id)
        full_path = os.path.join(get_character_exports_path(), filename)
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(json_text)
        except OSError as exc:
            logger.error(f"Errore scrittura file export ({full_path}): {exc}")
            self._show_error("Errore durante il salvataggio del file esportato.")
            return
        self._show_export_success_dialog(
            filename, full_path, system=None, download_url=f"/{filename}",
        )

    def _export_desktop(self, char: Character, system: str):
        """Chiamato in un thread separato — dialogo nativo di salvataggio del SO."""
        json_text = character_export.export_to_json_string(char.id)
        if json_text is None:
            self._show_error("Errore durante l'esportazione del personaggio.")
            return
        default_name = character_export.suggested_export_filename(char.id)
        path, error = self._save_dialog_native(system, default_name)
        if error:
            logger.error(f"Dialogo salvataggio nativo fallito ({system}): {error}")
            self._show_error(
                "Non è stato possibile aprire la finestra di salvataggio del sistema:\n"
                f"{error}\n\n"
                "Su macOS potrebbe essere necessario autorizzare l'automazione: "
                "Impostazioni di Sistema → Privacy e Sicurezza → Automazione."
            )
            return
        if not path:
            return  # utente ha annullato il dialog (nessun errore da segnalare)
        if not path.lower().endswith((".dndchar", ".json")):
            path += ".dndchar"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(json_text)
        except OSError as exc:
            logger.error(f"Errore scrittura file export ({path}): {exc}")
            self._show_error(f"Errore durante il salvataggio del file:\n{path}\n{exc}")
            return
        if not os.path.isfile(path):
            # Il dialogo ha riportato successo ma il file non risulta scritto —
            # non promettere un salvataggio che potrebbe non essere avvenuto.
            logger.error(f"File export non trovato dopo la scrittura: {path}")
            self._show_error(
                f"Il file non risulta presente dopo il salvataggio:\n{path}\n"
                "Riprova, oppure scegli un'altra cartella."
            )
            return
        self._show_export_success_dialog(os.path.basename(path), path, system=system)

    def _save_dialog_native(self, system: str, default_name: str) -> tuple[str | None, str | None]:
        """
        Dialogo di salvataggio nativo del SO — stesso pattern subprocess
        già in uso in profilo_tab.py per il dialogo di APERTURA immagine,
        qui declinato per il SALVATAGGIO. `default_name` è già sanificato
        (solo alfanumerici/underscore/trattini, vedi
        character_export.suggested_export_filename), quindi sicuro da
        incorporare direttamente nei comandi senza escaping.

        Ritorna `(path, error)`:
        - `(path, None)` → l'utente ha scelto un percorso.
        - `(None, None)` → l'utente ha annullato il dialogo (nessun errore).
        - `(None, "messaggio")` → il dialogo non si è potuto aprire/completare
          per un motivo REALE (comando mancante, permessi di automazione
          negati, ecc.) — DISTINTO da un annullamento pulito, perché prima
          di questo fix (2026-07-24) i due casi erano indistinguibili: un
          fallimento silenzioso (es. "System Events" senza permesso di
          Automazione su macOS) produceva esattamente lo stesso risultato
          di un Annulla — nessun file scritto, nessun errore mostrato,
          "il file sparisce nel nulla" dal punto di vista dell'utente.

        Imposta esplicitamente la cartella iniziale a Desktop su tutte e 3
        le piattaforme (`default location`/`InitialDirectory`/`--filename=`
        con percorso assoluto) — un salvataggio "al buio" (utente preme
        Salva senza guardare/cambiare cartella) finisce comunque in un
        posto prevedibile e facile da controllare, invece che nell'ultima
        cartella usata da System Events/Explorer per un dialogo qualsiasi.
        """
        import subprocess
        desktop = os.path.expanduser("~/Desktop")
        path: str | None = None
        error: str | None = None
        try:
            if system == "Darwin":
                # "choose file name"/"POSIX path of" vanno eseguiti FUORI dal
                # blocco "tell application System Events" — annidarli dentro
                # (come nella prima versione di questo fix, 2026-07-24) causa
                # un errore di coercizione AppleScript reale, non un semplice
                # difetto di stile: -1700 "Can't make ... into type
                # specifier", perché System Events prova a interpretare il
                # riferimento a un file NON ANCORA esistente (restituito da
                # "choose file name") con il proprio sistema di classi
                # invece di quello generico delle Standard Additions — errore
                # confermato in produzione da Davide (macOS, vedi CLAUDE.md).
                # "System Events" serve solo per attivare/portare in primo
                # piano il dialogo; il comando vero e propio gira nel
                # contesto di scripting di livello top (Standard Additions).
                script = (
                    'tell application "System Events" to activate\n'
                    f'set f to choose file name with prompt "Esporta personaggio" '
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
                    "$d.Title = 'Esporta personaggio'; "
                    f"$d.FileName = '{default_name}'; "
                    "$d.InitialDirectory = [Environment]::GetFolderPath('Desktop'); "
                    "$d.Filter = 'File Personaggio D&D|*.dndchar|Tutti i file|*.*'; "
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
                     "--title=Esporta personaggio", f"--filename={default_path}"],
                    ["kdialog", "--getsavefilename", default_path],
                ]:
                    try:
                        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        found_tool = True
                        if r.returncode == 0 and r.stdout.strip():
                            path = r.stdout.strip()
                            error = None  # un tool successivo può riuscire dopo che uno precedente ha fallito
                            break
                        stderr = (r.stderr or "").strip()
                        if stderr:  # returncode 1 con stderr vuoto = Annulla pulito
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

    def _show_export_success_dialog(
        self, filename: str, path: str, system: str | None,
        download_url: str | None = None,
    ):
        """
        `system`: `"Darwin"`/`"Windows"`/`"Linux"` per un export desktop (mostra
        il pulsante "Mostra nel Finder/Esplora file" — risolve alla radice il
        problema "non trovo il file", indipendentemente dalla cartella
        effettiva scelta dal dialogo nativo), `None` altrimenti (web/mobile).

        `download_url` (2026-07-24, SOLO export web): path relativo servito
        staticamente da Flet quando `assets_dir` coincide con
        `get_character_exports_path()` (vedi main.py) — mostra un pulsante
        "Scarica" che apre l'URL in una nuova scheda tramite la proprietà
        `url=` NATIVA del bottone (`ft.Url(url=..., target=ft.UrlTarget.BLANK)`),
        non tramite `page.launch_url()`/`ft.UrlLauncher()` — quel meccanismo è
        confermato rotto in web mode dallo stesso bug upstream di FilePicker
        (issue flet-dev/flet#6250/#6251, "FilePicker and UrlLauncher Service
        controls fail in web mode"). La proprietà `url=` sui controlli
        bottone è invece gestita interamente lato client (non passa da un
        controllo "Service" registrato sul server), quindi non è soggetta
        allo stesso bug — verificato leggendo il sorgente del pacchetto
        installato. Il browser scarica il file invece di visualizzarlo
        perché ".dndchar" è un'estensione sconosciuta → Starlette (il
        server usato da Flet per i file statici) la serve come
        `application/octet-stream`, che ogni browser tratta come download.
        """
        page = self.page
        if page is None:
            return

        def _reveal(e):
            threading.Thread(target=self._reveal_in_file_manager,
                              args=(path, system), daemon=True).start()

        actions = []
        if download_url is not None:
            actions.append(ft.ElevatedButton(
                "Scarica",
                icon=ft.Icons.DOWNLOAD,
                url=ft.Url(url=download_url, target=ft.UrlTarget.BLANK),
                style=ft.ButtonStyle(
                    bgcolor=COLOR_ACCENT_GOLD,
                    color=COLOR_BG_PRIMARY,
                    shape=ft.RoundedRectangleBorder(radius=6),
                ),
            ))
        if system is not None:
            actions.append(ft.TextButton(
                "Mostra nel Finder" if system == "Darwin" else "Mostra nella cartella",
                icon=ft.Icons.FOLDER_OPEN, on_click=_reveal,
                style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY),
            ))
        actions.append(ft.TextButton("OK", on_click=lambda e: page.pop_dialog(),
                                      style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON)))

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Personaggio esportato", color=COLOR_TEXT_TITLE,
                          weight=ft.FontWeight.BOLD),
            bgcolor=COLOR_BG_CARD,
            content=ft.Column([
                ft.Text(f'File salvato come "{filename}".',
                        color=COLOR_TEXT_PRIMARY, size=13),
                ft.Container(height=6),
                ft.Text(path, color=COLOR_TEXT_MUTED, size=11, selectable=True),
            ], tight=True, spacing=0),
            actions=cast(list[ft.Control], actions),
        ))

    def _reveal_in_file_manager(self, path: str, system: str | None):
        """
        Apre il file manager nativo del SO con il file appena esportato
        già selezionato/in evidenza — chiamato in un thread separato
        (subprocess bloccante). Nessuna eccezione propagata: se il comando
        non esiste o fallisce, resta solo un warning nei log, il file è
        comunque stato salvato con successo (questo pulsante è un aiuto
        per trovarlo, non una conferma del salvataggio stesso).
        """
        import subprocess
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

    # --- Import -------------------------------------------------------

    def _on_import_click(self, e=None):
        page = self.page
        if page is None:
            return
        if page.web:
            show_character_import_picker(page, on_select=self._do_import_from_path)
            return
        platform = page.platform
        if platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            page.run_task(self._on_mobile_import)
            return
        import platform as sys_platform
        system = sys_platform.system()
        threading.Thread(target=self._import_pick_desktop, args=(system,), daemon=True).start()

    async def _on_mobile_import(self):
        """
        Import su Android/iOS (2026-07-24) — stessa API corretta di
        _on_mobile_export(). `pick_files(with_data=True)` restituisce
        direttamente i byte del file scelto: a differenza di desktop/web,
        su mobile non serve mai un path locale raggiungibile dal processo
        Python (che qui gira sullo stesso dispositivo del client, ma il
        path del file scelto dal picker di sistema non è comunque sempre
        garantito — vedi nota su FilePickerFile.path nel sorgente Flet),
        quindi si passa direttamente al testo in memoria.
        """
        picker = self._ensure_file_picker()
        if picker is None:
            return
        try:
            files = await picker.pick_files(
                dialog_title="Importa personaggio",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["dndchar", "json"],
                allow_multiple=False,
                with_data=True,
            )
        except Exception as exc:
            logger.error(f"Errore FilePicker.pick_files (mobile): {exc}")
            self._show_error(f"Errore durante la selezione del file:\n{exc}")
            return
        if not files:
            return  # utente ha annullato, nessun errore da mostrare
        picked = files[0]
        if picked.bytes is None:
            self._show_error("Impossibile leggere il contenuto del file selezionato.")
            return
        try:
            text = picked.bytes.decode("utf-8")
        except UnicodeDecodeError:
            self._show_error("Il file selezionato non è un file di testo valido (UTF-8 atteso).")
            return
        self._do_import_from_text(text)

    def _import_pick_desktop(self, system: str):
        path, error = self._open_dialog_native(system)
        if error:
            logger.error(f"Dialogo apertura nativo fallito ({system}): {error}")
            self._show_error(
                "Non è stato possibile aprire la finestra di selezione del sistema:\n"
                f"{error}\n\n"
                "Su macOS potrebbe essere necessario autorizzare l'automazione: "
                "Impostazioni di Sistema → Privacy e Sicurezza → Automazione."
            )
            return
        if path:
            self._do_import_from_path(path)
        # path=None ed error=None → l'utente ha annullato, nessuna azione.

    def _open_dialog_native(self, system: str) -> tuple[str | None, str | None]:
        """
        Dialogo di apertura nativo del SO, filtrato per file personaggio —
        mirror del pattern già usato per la selezione immagini (vedi
        profilo_tab.py → _pick_photo_desktop), senza filtro di tipo su
        macOS (choose file "of type" richiede UTI registrati; ".dndchar" è
        un'estensione custom non registrata, filtrarla rischierebbe di
        nascondere file validi — meglio mostrare tutti i file e lasciare
        scegliere per nome).

        Stesso contratto di ritorno `(path, error)` di `_save_dialog_native`
        (2026-07-24) — vedi lì per il motivo (distinguere un annullamento
        pulito da un fallimento reale del dialogo, prima indistinguibili).
        """
        import subprocess
        path: str | None = None
        error: str | None = None
        try:
            if system == "Darwin":
                # Stessa correzione dell'export (vedi _save_dialog_native e
                # CLAUDE.md 2026-07-24): "choose file"/"POSIX path of" fuori
                # dal blocco "tell", System Events usato solo per activate.
                script = (
                    'tell application "System Events" to activate\n'
                    'set f to choose file with prompt "Importa personaggio" '
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
                    "$d.Title = 'Importa personaggio'; "
                    "$d.InitialDirectory = [Environment]::GetFolderPath('Desktop'); "
                    "$d.Filter = 'File Personaggio D&D|*.dndchar;*.json|Tutti i file|*.*'; "
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
                    ["zenity", "--file-selection", "--title=Importa personaggio",
                     "--file-filter=File Personaggio | *.dndchar *.json"],
                    ["kdialog", "--getopenfilename", ".", "*.dndchar *.json"],
                ]:
                    try:
                        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        found_tool = True
                        if r.returncode == 0 and r.stdout.strip():
                            path = r.stdout.strip()
                            error = None  # un tool successivo può riuscire dopo che uno precedente ha fallito
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

    def _do_import_from_path(self, path: str):
        """
        Legge un file dal filesystem e delega a _do_import_from_text() —
        usato da desktop e dal picker web (entrambi lavorano su un path
        locale raggiungibile dal processo Python). Il ramo mobile
        (_on_mobile_import) chiama invece _do_import_from_text()
        direttamente con i byte già ottenuti da
        FilePicker.pick_files(with_data=True) — su mobile non c'è mai
        bisogno di passare da un path (vedi nota lì).
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            logger.error(f"Errore lettura file import ({path}): {exc}")
            self._show_error(f"Impossibile leggere il file:\n{path}")
            return
        self._do_import_from_text(text)

    def _do_import_from_text(self, text: str):
        """
        Valida e (se non in conflitto) importa il contenuto testuale di un
        file .dndchar — nucleo comune a tutte e 3 le piattaforme,
        indipendente da come il testo è stato ottenuto (path locale su
        desktop/web, byte in memoria su mobile via 2026-07-24).
        """
        data = character_export.load_json_string(text)
        if data is None:
            self._show_error("Il file selezionato non è un JSON valido.")
            return

        err = character_export.validate_export_data(data)
        if err:
            self._show_error(err)
            return

        summary = character_export.peek_character_summary(data)
        if summary is None:
            self._show_error("Impossibile leggere i dati del personaggio dal file.")
            return

        if character_export.character_id_exists(summary["id"]):
            self._show_import_conflict_dialog(data, summary)
        else:
            self._run_import(data, "new")

    def _show_import_conflict_dialog(self, data: dict, new_summary: dict):
        """
        Il personaggio nel file ha lo stesso ID di uno già presente sul
        dispositivo — chiede esplicitamente come procedere invece di
        scegliere arbitrariamente (Sovrascrivi/Crea copia/Annulla).
        """
        page = self.page
        if page is None:
            return
        existing = character_export.get_character_summary(new_summary["id"]) or {}

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Personaggio già presente", color=COLOR_TEXT_TITLE,
                          weight=ft.FontWeight.BOLD),
            bgcolor=COLOR_BG_CARD,
            content=ft.Column(
                [
                    ft.Text(
                        f'Hai già un personaggio "{existing.get("name") or "?"}" '
                        f'(Lv.{existing.get("level", "?")} {existing.get("class_name", "")}) '
                        f'con lo stesso ID del file da importare '
                        f'("{new_summary.get("name") or "?"}", '
                        f'Lv.{new_summary.get("level", "?")} {new_summary.get("class_name", "")}).',
                        color=COLOR_TEXT_PRIMARY, size=13,
                    ),
                    ft.Container(height=12),
                    muted_text("Cosa vuoi fare?", size=12),
                ],
                tight=True, spacing=0,
            ),
            actions=[
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: page.pop_dialog(),
                    style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY),
                ),
                ft.OutlinedButton(
                    "Crea copia",
                    icon=ft.Icons.CONTENT_COPY,
                    on_click=lambda e: self._confirm_import(data, "copy"),
                    style=ft.ButtonStyle(
                        color=COLOR_ACCENT_GOLD,
                        side=ft.BorderSide(1, COLOR_ACCENT_GOLD),
                        shape=ft.RoundedRectangleBorder(radius=6),
                    ),
                ),
                ft.ElevatedButton(
                    "Sovrascrivi",
                    icon=ft.Icons.WARNING_AMBER_ROUNDED,
                    on_click=lambda e: self._confirm_import(data, "overwrite"),
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_RED,
                        color=COLOR_TEXT_PRIMARY,
                        shape=ft.RoundedRectangleBorder(radius=6),
                    ),
                ),
            ],
        )
        page.show_dialog(dlg)

    def _confirm_import(self, data: dict, mode: str):
        if self.page is not None:
            self.page.pop_dialog()
        self._run_import(data, mode)

    def _run_import(self, data: dict, mode: str):
        new_id = character_export.import_character(data, mode)
        if new_id is None:
            self._show_error("Errore durante l'importazione del personaggio.")
            return
        self.refresh()
        self._show_success("Personaggio importato correttamente.")
