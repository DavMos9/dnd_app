"""
Schermata Home: selezione, creazione ed eliminazione dei personaggi.
È la prima schermata che l'utente vede all'avvio.
"""

import base64
import flet as ft
import logging
import os
import threading
from typing import cast
from data.database import get_character_exports_path, get_web_export_staging_path
from data.models import Character, World
from data.repositories import character_repo, character_export, world_repo
from core import character_instances as ci
from core import world_permissions as perm
from core import world_sync
from core.world_backend import LocalBackend, RemoteBackend
from ui.character_transfer import show_character_import_picker
from ui.components.background_sync import BackgroundSyncLoop
from ui.device_identity import resolve_device_id
from ui.mobile_webview_picker import pick_file_via_webview
from ui.native_file_picker import pick_file_native, FilePickerUnavailable
from ui.theme import primary_button, ghost_button
from ui import design as d
from ui.widgets import show_snack, wrap_dialog_actions

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
        on_open_worlds()              → apre la Sezione Mondi (Multiplayer, passo
                                         2 — indipendente dai personaggi, vedi
                                         ui/views/world/). Nascosta se assente,
                                         stesso comportamento di `on_open_master`.
        on_toggle_theme(e)            → cicla Chiaro/Scuro/Sistema (Fase D del
                                         restyle). Se assente la pillola del
                                         tema non compare, stesso comportamento
                                         "nascosto se assente" di
                                         `on_open_master`.
    """

    def __init__(self, on_select, on_create_wizard, on_create_manual, on_open_master=None,
                 on_toggle_theme=None, theme_preference: str = "system", on_open_worlds=None):
        super().__init__(expand=True, spacing=0)
        self.on_select = on_select
        self.on_create_wizard = on_create_wizard
        self.on_create_manual = on_create_manual
        self.on_open_master = on_open_master
        self.on_toggle_theme = on_toggle_theme
        self.theme_preference = theme_preference
        self.on_open_worlds = on_open_worlds

        self._char_list_column = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO)
        self._stop_event = threading.Event()
        # Il polling di sincronizzazione gira su un thread separato e tocca gli
        # stessi controlli del thread della UI (eliminazione/import personaggio):
        # il lock serializza le due ricostruzioni della lista.
        self._refresh_lock = threading.RLock()
        self._last_signature: str | None = None
        self._poll_thread: threading.Thread | None = None
        # FilePicker persistente per Export/Import su mobile nativo
        # (Android/iOS) — registrato in modo lazy da _ensure_file_picker(),
        # mai in did_mount() e mai su desktop/web (vedi did_mount() più sotto).
        self._file_picker: ft.FilePicker | None = None
        # Identità del dispositivo (Multiplayer passo 3) — risolta in modo
        # asincrono in did_mount(), None finché non è pronta. Finché è None
        # la Home mostra la lista piatta di sempre (nessuna sezione per
        # mondo): mai bloccare l'apertura della Home in attesa della rete/
        # del servizio di storage.
        self.device_id: str | None = None

        # Sincronizzazione in background delle istanze di mondo possedute da
        # questo dispositivo: quando il master rimuove un'istanza dal mondo,
        # la Home del giocatore ospitato deve rifletterlo.
        # DISTINTA da `_poll_loop`/`_start_polling` sopra (quella è solo per
        # più schede web sullo stesso DB locale, mai per la rete LAN vera) —
        # questa gira su QUALUNQUE piattaforma, chiama `world_sync.
        # sync_replica()` per ogni mondo remoto in cui questo dispositivo ha
        # un'istanza, esattamente come già fa `WorldsView._start_detail_sync`
        # per la Sezione Mondi. `self.backend`/`self._remote_backends` sono
        # lo stesso stato persistente (cache di connessione) di `WorldsView`.
        self.backend = LocalBackend()
        self._remote_backends: dict[str, RemoteBackend] = {}
        self._world_sync_loop: BackgroundSyncLoop | None = None
        #: Ultimo `RemoteBackend.connection_state()` osservato per ogni
        #: mondo remoto — alimenta il LED di `_section_label`, aggiornato
        #: ad ogni giro di `_start_world_sync`.
        self._world_connection_states: dict[str, str] = {}

        # NOTA: il timer anti-spam di `_push_instance_to_host()` NON vive
        # come attributo di istanza qui, perché `HomeView` viene ricreata ad
        # ogni navigazione/cambio tema in `ui/app.py` — vive a livello di
        # modulo in `core.world_sync` (`instance_push_cooldown_remaining`/
        # `mark_instance_push`), richiamato direttamente da
        # `_push_instance_to_host` più sotto.

        self._build()
        self.refresh()
        # Il polling parte in did_mount(), non qui: serve `self.page` per sapere
        # se siamo in modalità web (unico caso in cui più sessioni condividono
        # lo stesso DB e la sincronizzazione ha senso).

    def did_mount(self):
        """
        Non registra il FilePicker qui: farlo produce un errore ("Unknown
        control: FilePicker") alla semplice apertura della Home su mobile
        nativo, prima di qualunque interazione — stesso problema già visto
        in web mode (vedi `dnd_app/docs/regole_flet_api.md`).
        `_ensure_file_picker()` resta comunque chiamato in modo lazy da
        `_on_mobile_export()`/`_on_mobile_import()` al primo tocco reale di
        quei pulsanti.
        """
        page = self.page
        self._start_polling()
        if page is not None:
            page.run_task(self._init_identity)

    async def _init_identity(self):
        """Risolve `device_id` (Multiplayer passo 3) e ricostruisce la lista
        raggruppata per mondo una volta pronta — vedi `ui/device_identity.py`."""
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        if self.refresh(force=True):
            try:
                page.update()
            except RuntimeError:
                pass
        self._start_world_sync()

    def _start_polling(self):
        """
        Avvia il polling di sincronizzazione — SOLO in modalità web, dove più
        sessioni browser condividono lo stesso DB sul server. Su desktop e
        mobile la sessione è unica: il polling sarebbe puro spreco (una lettura
        del DB e una potenziale ricostruzione della lista ogni 5 secondi).
        """
        page = self.page
        if page is None or not page.web:
            return
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="home-sync-poll",
        )
        self._poll_thread.start()

    def stop_polling(self):
        """Ferma il polling di sincronizzazione (chiamare prima di navigare via)."""
        self._stop_event.set()
        self._stop_world_sync()

    # ------------------------------------------------------------------
    # Sincronizzazione in background delle istanze di mondo —
    # vedi il commento su `self._world_sync_loop` in `__init__` per il
    # perché. Stesso `BackgroundSyncLoop` di `WorldsView`/
    # `MasterEncounterView`, dominio diverso: qui si scaricano gli eventi
    # nuovi di OGNI mondo remoto in cui questo dispositivo possiede
    # un'istanza (non solo quello aperto in Sezione Mondi), così un
    # cambiamento fatto dal master (PE, condizioni, e ora anche una
    # rimozione dal mondo) si vede sulla Home senza dover aprire Sezione
    # Mondi apposta.
    # ------------------------------------------------------------------

    def _my_remote_world_ids(self) -> list[str]:
        """Mondi in cui questo dispositivo possiede almeno un'istanza e che
        NON ospita (per i mondi ospitati il DB locale È già lo stato
        autoritativo, sincronizzarli non avrebbe alcun effetto — stesso
        principio di `WorldsView._start_detail_sync`)."""
        if not self.device_id:
            return []
        world_ids: set[str] = set()
        for c in character_repo.get_all():
            if c.world_id and c.owner_device_id == self.device_id:
                world_ids.add(c.world_id)
        remote_ids = []
        for world_id in world_ids:
            world = world_repo.get_world(world_id)
            if world is not None and not world.is_local_host:
                remote_ids.append(world_id)
        return remote_ids

    def _start_world_sync(self):
        if self._world_sync_loop is not None:
            return

        def _apply() -> None:
            for world_id in self._my_remote_world_ids():
                world = world_repo.get_world(world_id)
                if world is None:
                    continue
                backend = world_sync.resolve_backend_for_world(
                    world, self.device_id or "", self.backend, self._remote_backends,
                )
                if backend is not None:
                    if isinstance(backend, RemoteBackend):
                        self._world_connection_states[world_id] = backend.connection_state()
                    world_sync.sync_replica(backend, world_id)
                else:
                    self._world_connection_states[world_id] = "disconnected"

        def _signature() -> str | None:
            conn_sig = "|".join(
                f"{wid}:{state}" for wid, state in sorted(self._world_connection_states.items())
            )
            return f"{self._list_signature(character_repo.get_all())}|{conn_sig}"

        async def _redraw() -> None:
            page = self.page
            if page is None:
                return
            if self.refresh(force=True):
                try:
                    page.update()
                except RuntimeError:
                    pass

        loop = BackgroundSyncLoop(
            get_page=lambda: self.page,
            signature_fn=_signature,
            async_redraw_fn=_redraw,
            apply_fn=_apply,
            interval_s=2.0,
            thread_name="home-world-sync",
        )
        self._world_sync_loop = loop
        loop.start()

    def _stop_world_sync(self):
        if self._world_sync_loop is not None:
            self._world_sync_loop.stop()
        self._world_sync_loop = None

    def _poll_loop(self):
        """
        Sincronizza la lista personaggi tra sessioni web diverse.

        `refresh(force=False)` ricostruisce le card solo se la firma della lista
        è cambiata, e `page.update()` viene chiamato solo in quel caso, per
        evitare ricostruzioni a vuoto ogni 5 secondi. Un'eccezione transitoria
        (es. DB momentaneamente bloccato) viene loggata e il ciclo continua,
        così la sincronizzazione non muore in silenzio al primo errore.
        """
        while not self._stop_event.wait(5):
            if self._stop_event.is_set():
                break
            page = self.page
            if page is None:
                break            # vista smontata: qui il break è corretto
            try:
                if self.refresh(force=False):
                    page.update()
            except RuntimeError:
                # Controllo non più montato tra il check e l'update
                break
            except Exception as e:
                logger.debug("Polling sincronizzazione: errore transitorio (%s)", e)

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build(self):
        p = d.T()
        # Logo: il wordmark dell'app, UNICO momento "hero" di questa schermata
        # (Arcane Ledger — vedi design.hero_title). Usa il token HERO=40
        # dedicato, con l'oro `primary_icon` a marcare il brand.
        logo_widget = d.hero_title("D&D", "COMPANION", color=p.primary_icon)

        header = d.surface(
            ft.Column(
                [
                    ft.Row([logo_widget], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=d.Space.MD),
                    # Azioni sempre visibili come pillole invece di un menu a tre
                    # puntini "Altro" (stesso trattamento di master_view.py/
                    # master_encounter_view.py). `wrap=True`: su schermi stretti
                    # (smartphone) le pillole e il bottone "Nuovo Personaggio" vanno
                    # a capo su più righe invece di traboccare — niente
                    # `Container(expand=True)` in questa Row, incompatibile con
                    # `wrap=True`: il logo vive in una riga separata sopra.
                    ft.Row(
                        self._header_actions(),
                        spacing=d.Space.SM, wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=d.Space.XS),
                    d.muted("Seleziona un personaggio o creane uno nuovo"),
                ],
                spacing=d.Space.SM,
                tight=True,
            ),
            # Header = l'unico elemento "hero" della schermata (MAX uno per
            # schermata, vedi design.py): livello/padding di `surface()`
            # bumpati di conseguenza. `radius=0` esplicito perché è una barra
            # a piena larghezza a filo schermo, non una card — angoli
            # arrotondati qui sarebbero fuori registro. `accent=p.primary`
            # accende l'alone dorato attorno all'header in tema scuro
            # (`accent_glow()`, no-op in tema chiaro/level<2).
            hero=True,
            radius=0,
            accent=p.primary,
        )

        body = ft.Container(
            content=ft.Column(
                [self._char_list_column],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=ft.Padding.symmetric(horizontal=d.Space.XL, vertical=d.Space.XL),
            # Pergamena: gradiente a contrasto minimo, nessuna immagine
            gradient=d.page_gradient(),
        )

        self.controls = [header, body]

    def _new_character_button(self) -> ft.Control:
        """Bottone '+' che apre il dialog per scegliere wizard o manuale."""
        p = d.T()
        return ft.ElevatedButton(
            "Nuovo Personaggio",
            icon=ft.Icons.ADD,
            on_click=self._on_new_click,
            style=ft.ButtonStyle(
                bgcolor=p.primary_fill,
                color=p.on_primary_fill,
                shape=ft.RoundedRectangleBorder(radius=d.Radius.PILL),
                padding=ft.Padding.symmetric(horizontal=d.Space.LG,
                                             vertical=d.Space.MD),
            ),
        )

    def _header_actions(self) -> list[ft.Control]:
        """Azioni header sempre visibili — pillole "Modalità Master"/"Importa
        personaggio" + il pulsante primario "Nuovo Personaggio", tutte nella
        stessa Row `wrap=True`. "Modalità Master" compare solo se
        `on_open_master` è stato passato (nascosto se assente, per non
        rompere chiamate legacy a `HomeView`)."""
        p = d.T()
        actions: list[ft.Control] = []
        if self.on_open_worlds is not None:
            actions.append(d.pill(ft.Icons.PUBLIC, "Mondi",
                                  color=p.magic, on_click=lambda e: self.on_open_worlds()))
        if self.on_open_master is not None:
            actions.append(d.pill(ft.Icons.CASTLE_OUTLINED, "Modalità Master",
                                  color=p.magic,
                                  on_click=lambda e: self.on_open_master()))
        actions.append(d.pill(ft.Icons.UPLOAD_FILE, "Importa personaggio",
                              color=p.text_2, on_click=self._on_import_click))
        if self.on_toggle_theme is not None:
            from ui.widgets import theme_toggle_pill
            actions.append(theme_toggle_pill(self.theme_preference,
                                             self.on_toggle_theme))
        actions.append(self._new_character_button())
        return actions

    # ------------------------------------------------------------------
    # Dati
    # ------------------------------------------------------------------

    @staticmethod
    def _list_signature(characters: list[Character]) -> str:
        """
        Firma sintetica della lista personaggi, per capire se è cambiato
        qualcosa senza ricostruire le card. Include `updated_at` così una
        modifica fatta in un'altra sessione web viene comunque rilevata,
        `world_id`/`owner_device_id` (Multiplayer passo 3) così un
        personaggio appena entrato in un mondo sposta sezione, e
        `world_instance_archived` così la rimozione di
        un'istanza dal mondo — che non tocca `updated_at` della RIGA
        stessa in ogni percorso, es. `import_replica_character` durante un
        resync — sposta comunque sezione senza aspettare un'altra modifica.
        """
        return "|".join(
            f"{c.id}:{c.updated_at}:{c.world_id}:{c.owner_device_id}:"
            f"{int(c.world_instance_archived)}"
            for c in characters
        )

    def _partition_characters(
        self, characters: list[Character],
    ) -> tuple[list[Character], dict[str, list[Character]], list[Character]]:
        """
        Separa i personaggi locali dalle istanze possedute da QUESTO
        dispositivo, raggruppate per mondo (Multiplayer passo 3, §6 —
        "Home raggruppata per mondo, personaggio locale in una sezione
        'Non in un mondo'"), più le istanze RIMOSSE dal master
        (`characters.world_instance_archived`) in una terza sezione a sé: la
        rimozione lato master deve sparire dal mondo nella schermata Home
        del giocatore, senza toccare il personaggio (i dati restano, world_id compreso: la riga
        NON diventa "locale", è solo trattata diversamente in questa
        vista). Un'istanza archiviata non compare mai in `by_world` — un
        master che l'ha rimossa non deve rivederla nella Sezione Master, e
        un giocatore che l'ha ricevuta via resync non deve più vederla
        "attiva" in quel mondo sulla propria Home.

        Un'istanza di un altro giocatore, presente nello stesso DB solo
        perché condiviso (web mode multi-scheda), non compare mai qui: si
        confronta sempre `owner_device_id` con `self.device_id`, mai solo
        `world_id`.
        """
        locals_: list[Character] = []
        by_world: dict[str, list[Character]] = {}
        removed_from_world: list[Character] = []
        for c in characters:
            if not c.world_id:
                locals_.append(c)
            elif self.device_id and c.owner_device_id == self.device_id:
                if c.world_instance_archived:
                    removed_from_world.append(c)
                else:
                    by_world.setdefault(c.world_id, []).append(c)
        return locals_, by_world, removed_from_world

    def refresh(self, force: bool = True):
        """
        Ricarica la lista personaggi dal database.

        `force=False` (usato dal polling di sincronizzazione) ricostruisce le
        card SOLO se la firma della lista è cambiata, per evitare di sprecare
        lavoro e interrompere l'interazione dell'utente a metà quando nulla
        è cambiato.
        """
        with self._refresh_lock:
            characters = character_repo.get_all()
            signature = self._list_signature(characters)
            if not force and signature == self._last_signature:
                return False
            self._last_signature = signature

            self._char_list_column.controls.clear()

            if not characters:
                self._char_list_column.controls.append(self._empty_state())
            else:
                locals_, by_world, removed_from_world = self._partition_characters(characters)
                available_worlds = (
                    world_repo.get_worlds_for_device(self.device_id) if self.device_id else []
                )

                if not by_world and not removed_from_world:
                    # Nessuna istanza posseduta da questo dispositivo (o
                    # identità non ancora risolta): lista piatta identica a
                    # sempre, nessuna sezione — nessuna sorpresa visiva per
                    # chi non usa il Multiplayer.
                    for char in locals_:
                        self._char_list_column.controls.append(
                            self._character_card(char, available_worlds=available_worlds)
                        )
                else:
                    # Un mondo per sezione, il più recentemente attivo per
                    # primo (stesso ordine di world_repo.get_worlds_for_device).
                    ordered_world_ids = [w.id for w in available_worlds if w.id in by_world]
                    for world_id in ordered_world_ids:
                        world = next((w for w in available_worlds if w.id == world_id), None)
                        if world is None:
                            continue
                        conn_state = (None if world.is_local_host
                                      else self._world_connection_states.get(world_id, "connected"))
                        # Dopo un trasferimento di dispositivo (§11.9), il
                        # personaggio resta qui elencato (corretto: i dati restano
                        # intatti) ma va distinto da un normale mondo
                        # irraggiungibile — stessa targhetta già mostrata nel
                        # dettaglio della Sezione Mondi (`world_view.py::_world_card`),
                        # letta dallo stesso flag locale (nessun nuovo stato).
                        transferred = world_sync.is_world_transferred_away(world_id)
                        self._char_list_column.controls.append(
                            self._section_label(world.name, connection_state=conn_state,
                                                 transferred=transferred)
                        )
                        for char in by_world[world_id]:
                            self._char_list_column.controls.append(
                                self._character_card(char, is_instance=True)
                            )
                        self._char_list_column.controls.append(ft.Container(height=d.Space.MD))

                    if locals_:
                        self._char_list_column.controls.append(
                            self._section_label("Non in un mondo")
                        )
                        for char in locals_:
                            self._char_list_column.controls.append(
                                self._character_card(char, available_worlds=available_worlds)
                            )

                    if removed_from_world:
                        # Istanze rimosse dal master: niente
                        # "Aggiorna il mio foglio"/"Aggiungi a un mondo" —
                        # non sono più un'istanza attiva, ma niente è stato
                        # cancellato (Gioca/Esporta/Elimina restano).
                        self._char_list_column.controls.append(
                            self._section_label("Rimossi dai mondi")
                        )
                        self._char_list_column.controls.append(d.muted(
                            "Il master li ha rimossi dal mondo — i dati restano intatti.",
                        ))
                        self._char_list_column.controls.append(ft.Container(height=d.Space.XS))
                        for char in removed_from_world:
                            self._char_list_column.controls.append(
                                self._character_card(char, is_removed=True)
                            )

            # update() è valido solo dopo il mount sulla page
            try:
                self._char_list_column.update()
            except RuntimeError:
                pass  # chiamata da __init__, il render avviene con page.add()
            return True

    @staticmethod
    def _section_label(text: str, connection_state: str | None = None,
                        transferred: bool = False) -> ft.Control:
        """Intestazione di sezione leggera per il raggruppamento per mondo —
        non `design.section()` (pensato per pannelli a sé, troppo pesante
        ripetuto più volte in una lista che scorre).

        `connection_state` (vedi `design.connection_led`): passato solo per un
        gruppo-mondo REMOTO (non per "Non in un mondo"/"Rimossi dai mondi"),
        mostra il LED verde/rosso aggiornato ad ogni giro di
        `_start_world_sync`.

        `transferred`: stessa targhetta di `world_view.py::_world_card`
        per un mondo il cui personaggio è stato spostato su un altro
        dispositivo (§11.9) — distingue "disconnesso perché trasferito
        altrove" da "disconnesso perché irraggiungibile in questo momento"."""
        p = d.T()
        # Nessuna icona PUBLIC qui: sarebbe semanticamente sbagliata per
        # "Non in un mondo"/"Rimossi dai mondi" (quei due gruppi non sono un
        # mondo) e ridondante col testo per un vero nome di mondo.
        row_children: list[ft.Control] = [
            ft.Text(text.upper(), size=d.Size.LABEL, weight=ft.FontWeight.BOLD,
                    color=p.text_2, font_family=d.Font.BODY,
                    style=ft.TextStyle(letter_spacing=1.5)),
        ]
        if connection_state is not None:
            row_children.append(d.connection_led(connection_state))
        if transferred:
            row_children.append(d.chip("trasferito", "danger"))
        return ft.Container(
            content=ft.Row(
                row_children,
                spacing=d.Space.XS,
            ),
            padding=ft.Padding.only(top=d.Space.SM, bottom=d.Space.XS, left=d.Space.XS),
        )

    # ------------------------------------------------------------------
    # Card personaggio
    # ------------------------------------------------------------------

    def _character_card(
        self, char: Character, *,
        available_worlds: list[World] | None = None,
        is_instance: bool = False,
        is_removed: bool = False,
    ) -> ft.Container:
        """
        Card personaggio, costruita con le primitive di `ui/design.py`:
        ritratto più grande e arrotondato, ombra al posto del bordo 1px,
        chip semantici per livello/classe/razza, accento crimson sul bordo
        sinistro.

        `available_worlds`/`is_instance` (Multiplayer passo 3): un
        personaggio locale con almeno un mondo disponibile mostra "Aggiungi
        a un mondo"; un'istanza mostra invece "Aggiorna il mio foglio"
        (§6.1) — mai entrambe, un personaggio è l'uno o l'altro.
        """
        p = d.T()
        AV = 76

        # Ritratto (priorità: base64 in DB > percorso file > iniziali)
        if char.image_data:
            avatar: ft.Control = ft.Container(
                content=ft.Image(src=_data_uri(char.image_data),
                                 width=AV, height=AV, fit=ft.BoxFit.COVER),
                width=AV, height=AV, border_radius=d.Radius.MD,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                shadow=d.elevation(1),
            )
        elif char.image_path:
            avatar = ft.Container(
                content=ft.Image(src=char.image_path, width=AV, height=AV,
                                 fit=ft.BoxFit.COVER),
                width=AV, height=AV, border_radius=d.Radius.MD,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                shadow=d.elevation(1),
            )
        else:
            initials = "".join(w[0] for w in (char.name or "?").split()[:2]).upper() or "?"
            avatar = ft.Container(
                width=AV, height=AV,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                    colors=[p.surface_alt, p.bg_alt],
                ),
                border_radius=d.Radius.MD,
                content=ft.Text(initials, size=26, weight=ft.FontWeight.BOLD,
                                color=p.text_3, font_family=d.Font.DISPLAY),
                alignment=ft.Alignment.CENTER,
                shadow=d.elevation(1),
            )

        meta: list[ft.Control] = [d.chip(f"Liv. {char.level}", "primary", filled=True)]
        class_display = character_repo.get_class_display_string(char.id, char.class_name or "")
        if class_display:
            meta.append(d.chip(class_display, "magic"))
        if char.race:
            meta.append(d.chip(char.race, "neutral"))

        info = ft.Column(
            [
                ft.Text(char.name or "Senza nome", size=d.Size.SUBTITLE + 2,
                        weight=ft.FontWeight.BOLD, color=p.text,
                        font_family=d.Font.DISPLAY,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Row(meta, spacing=d.Space.XS, wrap=True),
                d.muted(char.background or "Nessun background"),
            ],
            spacing=d.Space.XS,
            expand=True,
        )

        action_controls: list[ft.Control] = [
            ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_color=p.primary_icon,
                          icon_size=30, tooltip="Gioca con questo personaggio",
                          on_click=lambda e, cid=char.id: self.on_select(cid)),
        ]
        if is_removed:
            pending_rejoin = world_repo.get_pending_rejoin_request_for_character(char.id)
            if pending_rejoin is not None:
                action_controls.append(ft.IconButton(
                    icon=ft.Icons.HOURGLASS_TOP, icon_color=p.text_3, disabled=True,
                    tooltip="Richiesta di rientro inviata — in attesa del master",
                ))
            else:
                action_controls.append(ft.IconButton(
                    icon=ft.Icons.PUBLIC, icon_color=p.magic,
                    tooltip="Richiedi rientro nel mondo",
                    on_click=lambda e, c=char: self._open_rejoin_request_dialog(c),
                ))
        elif is_instance:
            action_controls.append(ft.IconButton(
                icon=ft.Icons.SYNC, icon_color=p.magic,
                tooltip="Aggiorna il mio foglio personale da questa istanza",
                on_click=lambda e, c=char: self._open_refresh_dialog(c),
            ))
        elif available_worlds:
            action_controls.append(ft.IconButton(
                icon=ft.Icons.PUBLIC, icon_color=p.magic,
                tooltip="Aggiungi a un mondo",
                on_click=lambda e, c=char: self._open_add_to_world_dialog(c, available_worlds),
            ))
        action_controls += [
            ft.IconButton(icon=ft.Icons.IOS_SHARE, icon_color=p.text_3,
                          tooltip="Esporta personaggio (file .dndchar)",
                          on_click=lambda e, c=char: self._on_export_click(c)),
            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=p.danger_icon,
                          tooltip="Elimina personaggio",
                          on_click=lambda e, c=char: self._confirm_delete(c)),
        ]
        actions = ft.Row(action_controls, spacing=0, wrap=True,
                          alignment=ft.MainAxisAlignment.END)

        return d.card(
            # Riga superiore avatar+info, riga azioni separata sotto:
            # separando le azioni su una riga propria, `info` (nome/chip) è
            # squeezato solo dall'avatar (largo fisso, noto), mai anche
            # dalle fino a 4 IconButton non comprimibili delle azioni.
            #
            # NIENTE wrap=True sulla riga avatar+info: `info` ha
            # expand=True, e wrap=True su una Row con un figlio expand=True
            # produce un riquadro grigio senza errori Python (bug già
            # documentato in dnd_app/docs/regole_flet_api.md). `actions`
            # invece resta wrap=True (nessun figlio expand=True al suo
            # interno) — sicuro, ed è la riga che deve poter andare a capo
            # su più righe se anche da sola non basta lo spazio per 4 icone.
            ft.Column(
                [
                    ft.Row([avatar, ft.Container(width=d.Space.LG), info],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    actions,
                ],
                spacing=d.Space.SM,
            ),
            accent=p.magic if is_instance else p.primary,
            on_click=lambda e, cid=char.id: self.on_select(cid),
            tooltip="Apri la scheda",
        )

    # ------------------------------------------------------------------
    # Multiplayer passo 3 — aggiungi a un mondo / aggiorna il mio foglio
    # ------------------------------------------------------------------

    def _open_add_to_world_dialog(self, char: Character, worlds: list[World]):
        p = d.T()
        world_dd = ft.Dropdown(
            label="Mondo", value=worlds[0].id,
            options=[ft.DropdownOption(key=w.id, text=w.name) for w in worlds],
            **d.field_style(),
        )
        mode_dd = ft.Dropdown(
            label="Come entra", value="as_is",
            options=[
                ft.DropdownOption(key="as_is", text="Porta com'è (copia integrale)"),
                ft.DropdownOption(key="fresh", text="Ricomincia dal 1° livello"),
            ],
            **d.field_style(),
        )

        def _confirm(e):
            world_id = world_dd.value or worlds[0].id
            mode = mode_dd.value or "as_is"
            if self.device_id is None:
                self._show_error("Identità del dispositivo non ancora pronta — riprova tra poco.")
                return
            result = ci.create_or_resume_instance(world_id, char.id, self.device_id, mode=mode)
            self.page.pop_dialog()
            if result.archived:
                # Rimossa dal mondo in passato (§"Richiesta di rientro") —
                # MAI riprenderla in silenzio da qui: stesso flusso a
                # richiesta/approvazione dell'entry point in "Rimossi dai
                # mondi", `origin_character_id` è per costruzione `char.id`
                # stesso quindi "aggiorna allo stato attuale" è sempre
                # disponibile.
                instance = character_repo.get_by_id(result.character_id)
                if instance is not None:
                    self._open_rejoin_request_dialog(instance)
                return
            if not result.success:
                self._show_error(result.error or "Impossibile aggiungere il personaggio al mondo.")
                return
            self._push_instance_to_host(world_id, result.character_id)
            self.on_select(result.character_id)

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f'"{char.name}" entra in un mondo', ft.Icons.PUBLIC),
            content=ft.Column(
                [
                    d.muted(
                        "Il personaggio locale resta com'è: nasce una copia "
                        "indipendente dentro il mondo scelto (§6 del design "
                        "doc). I progressi nel mondo non si riflettono qui "
                        "finché non usi \"Aggiorna il mio foglio\".",
                    ),
                    ft.Container(height=d.Space.SM),
                    world_dd, mode_dd,
                ],
                tight=True, spacing=d.Space.SM,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Entra nel mondo", icon=ft.Icons.LOGIN, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _push_instance_to_host(self, world_id: str, character_id: str) -> None:
        """
        Se il player si unisce a un mondo LAN (non ospitato su questo
        dispositivo), `ci.create_or_resume_instance()` scrive SOLO sul DB
        locale: l'host non verrebbe mai informato, e la Sezione Master (che
        legge dal DB dell'host) risulterebbe vuota anche a ingresso
        riuscito.

        Qui si invia esplicitamente l'export integrale dell'istanza appena
        creata come comando `character_instance.sync`
        (`core/world_backend.py::_handle_character_instance_sync`), così
        l'host la scrive sulla propria copia autoritativa.

        Se il push fallisce (host momentaneamente irraggiungibile), il
        personaggio resta comunque creato in locale — non blocchiamo mai
        un'azione già riuscita per un problema di rete — ma lo segnaliamo
        con un avviso non bloccante e marchiamo l'istanza con
        `host_sync_pending=1`. Il loop di sync in background di `WorldsView`
        (`core/world_sync.py::push_pending_instances`) ritenta da solo
        quando l'host torna raggiungibile; l'utente può comunque forzare un
        tentativo immediato riaprendo questo stesso dialogo, che sovrascrive
        senza creare un duplicato: stesso `character_id`.
        """
        if self.device_id is None:
            logger.warning(
                "Registrazione istanza %s rifiutata: identità del dispositivo assente.",
                character_id,
            )
            return

        world = world_repo.get_world(world_id)
        if world is None or world.is_local_host:
            return  # Questo dispositivo ospita il mondo: nessun push necessario.

        # Anti-spam: stesso timer di 10s condiviso con i tentativi di
        # ingresso in WorldsView (`core.world_sync`), stato indipendente
        # perché questa è un'altra view. Il personaggio resta comunque
        # creato in locale: bloccare solo il PUSH, mai la creazione già
        # avvenuta.
        remaining = world_sync.instance_push_cooldown_remaining()
        if remaining > 0:
            character_repo.set_host_sync_pending(character_id, True)
            self._show_error(
                f"Personaggio creato. La registrazione sull'host partirà tra "
                f"{int(remaining) + 1} secondi (troppe richieste di rete ravvicinate)."
            )
            return
        world_sync.mark_instance_push()

        backend = world_sync.resolve_backend_for_world(
            world, self.device_id or "", LocalBackend(), {},
        )
        if backend is None:
            logger.warning(
                "Registrazione istanza %s sull'host del mondo %s non riuscita: "
                "backend non risolvibile (host irraggiungibile o sessione scaduta).",
                character_id, world_id,
            )
            character_repo.set_host_sync_pending(character_id, True)
            self._show_error(
                "Personaggio creato, ma non è stato possibile registrarlo subito "
                "sull'host — verrà registrato automaticamente non appena l'host "
                "torna raggiungibile."
            )
            return

        export_data = character_export.export_character(character_id)
        if export_data is None:
            logger.error("Export fallito per l'istanza %s appena creata.", character_id)
            return

        result = backend.send_command(
            world_id, self.device_id, perm.CMD_CHARACTER_INSTANCE_SYNC,
            {"export": export_data}, target_type="character", target_id=character_id,
        )
        if not result.success:
            logger.warning(
                "Registrazione istanza %s sull'host del mondo %s rifiutata: %s",
                character_id, world_id, result.error,
            )
            character_repo.set_host_sync_pending(character_id, True)
            self._show_error(
                f"Personaggio creato, ma la registrazione sull'host è fallita: "
                f"{result.error or 'errore sconosciuto'} — verrà ritentata "
                f"automaticamente quando l'host torna raggiungibile."
            )
        else:
            character_repo.set_host_sync_pending(character_id, False)

    def _open_refresh_dialog(self, instance: Character):
        p = d.T()
        preview = ci.preview_refresh(instance.id)
        if preview is None:
            self._show_error("Impossibile calcolare l'anteprima dell'aggiornamento.")
            return

        if preview.origin_exists:
            summary_lines = [
                f"Livello {preview.level_before} → {preview.level_after}",
                f"PE {preview.xp_before} → {preview.xp_after}",
                f"Oggetti/armi: {preview.item_count_before} → {preview.item_count_after}",
            ]
            body = ft.Column(
                [ft.Text(f'Il personaggio locale "{preview.origin_name}" verrà sovrascritto '
                         f"con lo stato di questa istanza:", size=13, color=p.text)]
                + [ft.Text(f"• {line}", size=12, color=p.text_2) for line in summary_lines],
                tight=True, spacing=4,
            )
            confirm_label = "Sovrascrivi il mio foglio"
        else:
            body = ft.Text(
                "Il personaggio locale di origine non esiste più: verrà creato "
                "un nuovo personaggio locale con lo stato attuale di questa istanza.",
                size=13, color=p.text,
            )
            confirm_label = "Crea personaggio locale"

        def _confirm(e):
            result = ci.apply_refresh(instance.id)
            self.page.pop_dialog()
            if not result.success:
                self._show_error(result.error or "Aggiornamento fallito.")
                return
            self.refresh()
            try:
                self.page.update()
            except RuntimeError:
                pass
            self._show_success("Foglio personale aggiornato.")

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Aggiorna il mio foglio", ft.Icons.SYNC),
            content=body,
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(confirm_label, icon=ft.Icons.SYNC, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary)),
            ]),
        )
        self.page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Richiesta di rientro — un personaggio rimosso dal mondo
    # (`world_instance_archived`) non torna mai visibile in automatico: il
    # giocatore deve chiedere, il master deve approvare (§"Richiesta di
    # rientro" in `core/world_backend.py`). Punto unico condiviso dai due
    # entry point (card in "Rimossi dai mondi" sopra, e il redirect da
    # "Aggiungi a un mondo" in `_open_add_to_world_dialog._confirm` sopra)
    # — nessuna logica di scelta-modalità/invio duplicata in due posti.
    # ------------------------------------------------------------------

    def _open_rejoin_request_dialog(self, instance: Character):
        p = d.T()

        pending = world_repo.get_pending_rejoin_request_for_character(instance.id)
        if pending is not None:
            self._show_error(
                "Hai già una richiesta di rientro in attesa di risposta del master "
                "per questo personaggio."
            )
            return

        origin = (character_repo.get_by_id(instance.origin_character_id)
                  if instance.origin_character_id else None)
        origin_available = origin is not None and not origin.world_id

        mode_options = [
            ft.DropdownOption(key="frozen", text="Riprendi lo stato con cui era stato rimosso"),
        ]
        if origin_available:
            mode_options.append(ft.DropdownOption(
                key="refresh_from_local",
                text="Aggiorna allo stato attuale della scheda locale",
            ))
        mode_dd = ft.Dropdown(
            label="Con quale stato rientra", value="frozen",
            options=mode_options, **d.field_style(),
        )
        reason_field = ft.TextField(
            label="Nota per il master (opzionale)", multiline=True, min_lines=1,
            max_lines=3, **d.field_style(),
        )

        content_controls: list[ft.Control] = [
            d.muted(
                'Il master dovrà approvare il rientro di "' + instance.name +
                '" nel mondo — non tornerà visibile finché non lo fa.',
            ),
            ft.Container(height=d.Space.SM),
            mode_dd,
        ]
        if not origin_available:
            content_controls.append(d.muted(
                "Il personaggio locale di origine non esiste più: disponibile solo "
                "lo stato con cui era stato rimosso.",
            ))
        content_controls.append(reason_field)

        def _confirm(e):
            mode = mode_dd.value or "frozen"
            reason = (reason_field.value or "").strip()
            self.page.pop_dialog()
            self._send_rejoin_request(instance, mode, reason)

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f'Richiedi rientro — "{instance.name}"', ft.Icons.PUBLIC),
            content=ft.Column(content_controls, tight=True, spacing=d.Space.SM),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Invia richiesta", icon=ft.Icons.SEND, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _send_rejoin_request(self, instance: Character, mode: str, reason: str):
        if self.device_id is None:
            self._show_error("Identità del dispositivo non ancora pronta — riprova tra poco.")
            return

        remaining = world_sync.network_request_cooldown_remaining()
        if remaining > 0:
            self._show_error(
                f"Troppe richieste ravvicinate — riprova tra {int(remaining) + 1} secondi."
            )
            return
        world_sync.mark_network_request()

        world = world_repo.get_world(instance.world_id)
        if world is None:
            self._show_error("Mondo non trovato.")
            return

        payload: dict = {"mode": mode}
        if mode == "refresh_from_local":
            export_data = character_export.export_character(instance.origin_character_id)
            if export_data is None:
                self._show_error("Esportazione del personaggio locale fallita.")
                return
            payload["export"] = export_data
        if reason:
            payload["reason"] = reason

        backend = world_sync.resolve_backend_for_world(
            world, self.device_id or "", LocalBackend(), {},
        )
        if backend is None:
            self._show_error(
                "Impossibile contattare l'host del mondo — riprova tra poco."
            )
            return

        result = backend.send_command(
            instance.world_id, self.device_id, perm.CMD_CHARACTER_REJOIN_REQUEST,
            payload, target_type="character", target_id=instance.id,
        )
        if not result.success:
            self._show_error(result.error or "Invio della richiesta fallito.")
            return
        self.refresh()
        try:
            self.page.update()
        except RuntimeError:
            pass
        self._show_success("Richiesta di rientro inviata al master.")

    # ------------------------------------------------------------------
    # Stato vuoto
    # ------------------------------------------------------------------

    def _empty_state(self) -> ft.Container:
        """Stato vuoto — primitiva condivisa `design.empty_state()`."""
        return d.empty_state(
            ft.Icons.SHIELD_OUTLINED,
            "Nessun personaggio",
            "Crea il tuo primo personaggio per iniziare l'avventura.",
            action=ft.Column(
                controls=cast(list[ft.Control], [
                    primary_button("Wizard guidato",
                                   on_click=lambda e: self.on_create_wizard(),
                                   icon=ft.Icons.AUTO_FIX_HIGH),
                    ghost_button("Creazione manuale",
                                 on_click=lambda e: self.on_create_manual()),
                    d.pill(ft.Icons.UPLOAD_FILE, "Importa personaggio",
                           color=d.T().magic, on_click=self._on_import_click),
                ]),
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=d.Space.MD,
            ),
        )

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _on_new_click(self, e):
        """Dialog per scegliere wizard o creazione manuale."""
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Nuovo Personaggio"),
            content=ft.Column(
                [
                    d.muted(
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
                                    bgcolor=d.T().magic,
                                    color=d.T().bg,
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
                                    color=d.T().magic,
                                    side=ft.BorderSide(1, d.T().magic),
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
                    style=ft.ButtonStyle(color=d.T().text_2),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _confirm_delete(self, char: Character):
        """Dialog di conferma eliminazione."""
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Elimina personaggio"),
            content=ft.Text(
                f'Sei sicuro di voler eliminare "{char.name}"?\nQuesta azione non può essere annullata.',
                color=d.T().text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: self._close_dialog(),
                    style=ft.ButtonStyle(color=d.T().text_2),
                ),
                ft.ElevatedButton(
                    "Elimina",
                    icon=ft.Icons.DELETE,
                    on_click=lambda e: self._do_delete(dlg, char.id),
                    style=ft.ButtonStyle(
                        bgcolor=d.T().danger_fill,
                        color=d.T().text,
                    ),
                ),
            ]),
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
        """Wrapper attorno a `ui.widgets.show_snack()` con tono "danger"."""
        show_snack(self.page, message, tone="danger")

    def _show_success(self, message: str):
        """Vedi `_show_error` sopra. Tono "magic" (non "success"): il
        colore usato qui è quello magico dell'app, non quello verde."""
        show_snack(self.page, message, tone="magic")

    # ------------------------------------------------------------------
    # Export / Import personaggio
    #
    # IMPORT (_on_mobile_import): usa una WebView locale
    # (ui/mobile_webview_picker.py) invece di ft.FilePicker. Motivo: su
    # questa build Android, pick_files()/save_file() arrivano al bridge
    # Dart ma vanno in TimeoutException — nessuna Activity nativa viene mai
    # avviata (diagnosi applicabile a QUALUNQUE uso di ft.FilePicker su
    # questa build). Un `await` corretto non basta se il controllo
    # sottostante non è utilizzabile affatto.
    #
    # EXPORT (_on_mobile_export): **NON ancora migrato**, resta su
    # ft.FilePicker.save_file() — un download via WebView richiede
    # intercettare un meccanismo diverso da quello usato per la selezione,
    # mai verificato. Per la stessa diagnosi di cui sopra è MOLTO PROBABILE
    # che vada in errore allo stesso modo (TimeoutException) su un vero
    # dispositivo — non ancora confermato con un log dedicato. Se fallisce,
    # il `try/except` già
    # presente lo intercetta e mostra un errore invece di bloccarsi in
    # silenzio, ma la funzionalità resta di fatto non disponibile su
    # mobile finché non viene affrontata a parte. Desktop e Web restano
    # pienamente implementati e testati per entrambi.
    # ------------------------------------------------------------------

    def _ensure_file_picker(self) -> ft.FilePicker | None:
        """
        Ritorna il FilePicker mobile — usato ORA SOLO da _on_mobile_export()
        (vedi nota sopra: _on_mobile_import() è passato a WebView e non lo
        usa più). Lo crea e registra al volo alla prima chiamata, se non
        esiste già (mai in did_mount(), vedi il docstring di did_mount()).
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
        # Un personaggio che è un'istanza di un mondo condiviso
        # (`char.world_id` valorizzato) perde SEMPRE il collegamento al
        # mondo alla normale importazione su un altro dispositivo
        # (`character_export.import_character()` azzera world_id/
        # origin_character_id/owner_device_id/is_replica/world_seq per
        # design, vedi il suo docstring — un file esportato da un'istanza
        # di mondo diventerebbe altrimenti una "replica" di un mondo
        # inesistente sul dispositivo di destinazione, bloccata in sola
        # lettura e non riparabile dall'interfaccia). Qui si avvisa PRIMA
        # di esportare — non blocca l'esportazione (resta comunque utile
        # per un backup locale o per stampare la scheda), solo la rende una
        # scelta informata. Nessun avviso per un personaggio locale
        # (`world_id == ""`, il caso comune): l'app deve restare rapida per
        # l'uso ordinario, non aggiungere un passaggio in più dove non serve.
        if char.world_id:
            self._confirm_export_world_linked(char)
            return
        self._proceed_export(char)

    def _confirm_export_world_linked(self, char: Character):
        page = self.page
        if page is None:
            return
        world = world_repo.get_world(char.world_id)
        world_name = world.name if world else "un mondo non più presente su questo dispositivo"
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Personaggio collegato a un mondo condiviso",
                                  ft.Icons.PUBLIC_OFF, tone="danger"),
            content=ft.Column(
                [
                    ft.Text(
                        f'"{char.name}" è un\'istanza del mondo condiviso "{world_name}".',
                        color=d.T().text, size=13,
                    ),
                    ft.Container(height=8),
                    d.muted(
                        "Il file esportato conterrà comunque il collegamento a questo "
                        "mondo, ma la normale importazione su un altro dispositivo lo "
                        "azzera sempre: il personaggio importato diventerà una copia "
                        "locale indipendente, scollegata dal mondo, dai progressi "
                        "condivisi e da questo dispositivo. Per far partecipare un altro "
                        "dispositivo allo stesso mondo, fallo entrare come una nuova "
                        "istanza dalla Sezione Mondi — non tramite questo file.",
                        size=12,
                    ),
                ],
                tight=True, spacing=0,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: page.pop_dialog(),
                    style=ft.ButtonStyle(color=d.T().text_2),
                ),
                ft.ElevatedButton(
                    "Esporta comunque",
                    icon=ft.Icons.WARNING_AMBER_ROUNDED,
                    on_click=lambda e: self._confirm_export_proceed(char),
                    style=ft.ButtonStyle(bgcolor=d.T().danger_fill, color=d.T().text),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _confirm_export_proceed(self, char: Character):
        if self.page is not None:
            self.page.pop_dialog()
        self._proceed_export(char)

    def _proceed_export(self, char: Character):
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
        Export su Android/iOS. `ft.FilePicker` in questa versione di Flet
        (0.85.3) NON ha alcun evento `on_result` (solo `on_upload`, per il
        progresso di un upload) —
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
        Modalità web: scrive il file in DUE posti — la cartella condivisa
        (`get_character_exports_path()`, bind mount Docker, accessibile via
        SSH/scp), e la sottocartella servita staticamente
        (`assets/exports/`, vedi `get_web_export_staging_path()`).
        Le due NON coincidono perché `assets_dir` è `dnd_app/assets/`
        (necessario per i font custom), quindi il file scaricabile va
        messo lì sotto — l'URL è `/exports/<filename>`, permettendo un download reale
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
        # Due destinazioni, due scopi diversi (vedi docstring sopra): la
        # cartella condivisa (bind mount Docker) resta la copia persistente
        # accessibile via SSH/scp; la sottocartella servita staticamente è
        # ciò che rende possibile il download reale dal browser.
        full_path = os.path.join(get_character_exports_path(), filename)
        staging_path = os.path.join(get_web_export_staging_path(), filename)
        written = False
        for path in (full_path, staging_path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(json_text)
                written = True
            except OSError as exc:
                logger.error(f"Errore scrittura file export ({path}): {exc}")
        if not written:
            self._show_error("Errore durante il salvataggio del file esportato.")
            return
        self._show_export_success_dialog(
            filename, full_path, system=None, download_url=f"/exports/{filename}",
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
          negati, ecc.) — DISTINTO da un annullamento pulito: un
          fallimento silenzioso (es. "System Events" senza permesso di
          Automazione su macOS) produrrebbe altrimenti esattamente lo
          stesso risultato di un Annulla — nessun file scritto, nessun
          errore mostrato, "il file sparisce nel nulla" dal punto di vista
          dell'utente.

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
                # causa un errore di coercizione AppleScript reale, non un
                # semplice difetto di stile: -1700 "Can't make ... into type
                # specifier", perché System Events prova a interpretare il
                # riferimento a un file NON ANCORA esistente (restituito da
                # "choose file name") con il proprio sistema di classi
                # invece di quello generico delle Standard Additions.
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

        `download_url` (SOLO export web): path relativo servito
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
                    bgcolor=d.T().magic,
                    color=d.T().bg,
                ),
            ))
        if system is not None:
            actions.append(ft.TextButton(
                "Mostra nel Finder" if system == "Darwin" else "Mostra nella cartella",
                icon=ft.Icons.FOLDER_OPEN, on_click=_reveal,
                style=ft.ButtonStyle(color=d.T().text_2),
            ))
        actions.append(ft.TextButton("OK", on_click=lambda e: page.pop_dialog(),
                                      style=ft.ButtonStyle(color=d.T().primary)))

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Personaggio esportato"),
            content=ft.Column([
                ft.Text(f'File salvato come "{filename}".',
                        color=d.T().text, size=13),
                ft.Container(height=6),
                ft.Text(path, color=d.T().text_3, size=11, selectable=True),
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
        Import su Android/iOS: prova PRIMA il selettore nativo
        (`ui/native_file_picker.py`, estensione `flet_file_picker`), poi
        ricade sulla WebView locale (`ui/mobile_webview_picker.py`) solo se
        il primo non è disponibile o fallisce.

        **Perché non `ft.FilePicker`**: su questa build Android,
        `pick_files()` arriva al bridge Dart ma va in `TimeoutException:
        Timeout waiting for invoke method listener` — nessuna Activity
        nativa viene mai avviata, indipendentemente dall'uso corretto di
        `await`. Il controllo `FilePicker` stesso non è utilizzabile su
        questa build, per qualunque suo metodo.

        **Perché non solo WebView**: il bypass WebView (`<input
        type=file>`) mostrato sotto è a sua volta confermato NON
        funzionante su Android reale — `webview_flutter` non implementa
        `WebChromeClient.onShowFileChooser`, il tap su "Scegli file" non
        apre nulla. Il selettore nativo (`flet_file_picker`) resta quindi
        il primo tentativo; il fallback WebView resta comunque presente
        per le piattaforme/versioni dove funziona.
        """
        page = self.page
        if page is None:
            return
        try:
            native_result = await pick_file_native(
                page, allowed_extensions=["dndchar", "json"],
            )
        except FilePickerUnavailable as exc:
            logger.warning(f"FilePicker nativo non disponibile, uso WebView: {exc}")
            # Il selettore nativo può fallire silenziosamente (es. su
            # tablet, dove anche il fallback WebView è noto rotto — vedi il
            # docstring sopra): un avviso non bloccante col testo reale
            # dell'eccezione rende il problema diagnosticabile senza dover
            # ricorrere a log `adb logcat` dal dispositivo.
            self._show_error(f"Selettore file nativo non disponibile: {exc}")
            native_result = None
            native_failed = True
        else:
            native_failed = False
        if native_failed:
            result = await pick_file_via_webview(
                page, accept=".dndchar,.json,application/json",
                title="Importa personaggio",
            )
            if result is None:
                return  # utente ha annullato, o errore già loggato nel modulo
            filename, b64_content = result
            try:
                raw = base64.b64decode(b64_content)
            except Exception as exc:
                logger.error(f"Import mobile: base64 non decodificabile: {exc}")
                self._show_error("File non valido. Riprova.")
                return
        else:
            if native_result is None:
                return  # utente ha annullato la selezione nativa
            filename, raw = native_result
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._show_error(
                f"Il file selezionato ({filename}) non è un file di testo "
                "valido (UTF-8 atteso)."
            )
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
        — vedi lì per il motivo (distinguere un annullamento pulito da un
        fallimento reale del dialogo).
        """
        import subprocess
        path: str | None = None
        error: str | None = None
        try:
            if system == "Darwin":
                # Stesso vincolo dell'export (vedi _save_dialog_native):
                # "choose file"/"POSIX path of" fuori
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
        direttamente con i byte già ottenuti dal selettore nativo o dalla
        WebView di fallback — su mobile non c'è mai bisogno di passare da
        un path (vedi nota lì).
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
        desktop/web, byte in memoria su mobile).
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

        # Vedi il commento gemello in `_on_export_click`:
        # stessa causa (`import_character()` azzera SEMPRE world_id/
        # origin_character_id/owner_device_id/is_replica/world_seq, per
        # design), stesso avviso speculare lato importazione. `world_id`
        # è una chiave semplice dentro `data["character"]` (la riga
        # `characters` esportata così com'è da `export_character()`, senza
        # alcun filtro), non serve toccare `peek_character_summary()` per
        # leggerlo qui.
        world_id = str((data.get("character") or {}).get("world_id") or "")
        if world_id:
            self._show_import_world_linked_warning(data, summary, world_id)
            return

        self._continue_import(data, summary)

    def _show_import_world_linked_warning(self, data: dict, summary: dict, world_id: str):
        page = self.page
        if page is None:
            return
        world = world_repo.get_world(world_id)
        world_name = world.name if world else "un mondo non più presente su questo dispositivo"
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Personaggio collegato a un mondo condiviso",
                                  ft.Icons.PUBLIC_OFF, tone="danger"),
            content=ft.Column(
                [
                    ft.Text(
                        f'"{summary.get("name") or "?"}" nel file è un\'istanza del '
                        f'mondo condiviso "{world_name}".',
                        color=d.T().text, size=13,
                    ),
                    ft.Container(height=8),
                    d.muted(
                        "Importandolo qui diventerà un personaggio locale indipendente: "
                        "il collegamento al mondo, ai progressi condivisi e al "
                        "dispositivo di origine andrà perso e non è recuperabile da "
                        "questa schermata. Per farlo partecipare di nuovo a quel mondo, "
                        "fallo entrare come una nuova istanza dalla Sezione Mondi — non "
                        "tramite questo file.",
                        size=12,
                    ),
                ],
                tight=True, spacing=0,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: page.pop_dialog(),
                    style=ft.ButtonStyle(color=d.T().text_2),
                ),
                ft.ElevatedButton(
                    "Importa comunque",
                    icon=ft.Icons.WARNING_AMBER_ROUNDED,
                    on_click=lambda e: self._confirm_import_world_linked(data, summary),
                    style=ft.ButtonStyle(bgcolor=d.T().danger_fill, color=d.T().text),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _confirm_import_world_linked(self, data: dict, summary: dict):
        if self.page is not None:
            self.page.pop_dialog()
        self._continue_import(data, summary)

    def _continue_import(self, data: dict, summary: dict):
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
            title=d.dialog_title("Personaggio già presente"),
            content=ft.Column(
                [
                    ft.Text(
                        f'Hai già un personaggio "{existing.get("name") or "?"}" '
                        f'(Lv.{existing.get("level", "?")} {existing.get("class_name", "")}) '
                        f'con lo stesso ID del file da importare '
                        f'("{new_summary.get("name") or "?"}", '
                        f'Lv.{new_summary.get("level", "?")} {new_summary.get("class_name", "")}).',
                        color=d.T().text, size=13,
                    ),
                    ft.Container(height=12),
                    d.muted("Cosa vuoi fare?", size=12),
                ],
                tight=True, spacing=0,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: page.pop_dialog(),
                    style=ft.ButtonStyle(color=d.T().text_2),
                ),
                ft.OutlinedButton(
                    "Crea copia",
                    icon=ft.Icons.CONTENT_COPY,
                    on_click=lambda e: self._confirm_import(data, "copy"),
                    style=ft.ButtonStyle(
                        color=d.T().magic,
                        side=ft.BorderSide(1, d.T().magic),
                    ),
                ),
                ft.ElevatedButton(
                    "Sovrascrivi",
                    icon=ft.Icons.WARNING_AMBER_ROUNDED,
                    on_click=lambda e: self._confirm_import(data, "overwrite"),
                    style=ft.ButtonStyle(
                        bgcolor=d.T().danger_fill,
                        color=d.T().text,
                    ),
                ),
            ]),
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
