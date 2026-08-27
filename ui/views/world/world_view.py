"""
Sezione «Mondi» — creazione e gestione di campagne condivise (Mondi
condivisi/LAN party, design completo in `dnd_app/docs/multiplayer_design.md`).

Indipendente da ogni personaggio, stesso principio di `master_view.py`:
raggiungibile dalla Home con una pillola sempre visibile (mai un'azione
nascosta in un menu, convenzione già stabilita nel progetto).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
from datetime import datetime

import flet as ft

from config.settings import DRACONIDE_ANCESTRIES
from core import character_instances
from core import world_permissions as perm
from core import world_sync
from core.world_backend import CommandResult, LocalBackend, RemoteBackend, WorldBackend
from data.database import get_character_exports_path, get_web_export_staging_path
from data.game_data.game_data_loader import GameDataLoader
from data.models import (
    Character, GameMap, LootStashEntry, World, WorldChangeRequest, WorldEvent, WorldMember,
    WorldRejoinRequest,
)
from data.repositories import (
    character_repo, loot_repo, maps_repo, master_repo, settings_repo, world_export, world_repo,
)
from network.host_server import HostServerSlot, PendingJoinRequest, WorldHostServer, local_ip_hint
from network.qr_join import build_join_text, build_transfer_text, generate_qr_png_base64
from ui.components.background_sync import BackgroundSyncLoop
from ui.components.map_drawing_canvas import MapDrawingCanvas, data_uri as _data_uri
from ui import file_export
from ui.mobile_webview_picker import pick_file_via_webview
from ui.native_file_picker import pick_file_native, FilePickerUnavailable
from ui.views.maps_view import _pick_desktop, _pick_from_library, _pick_mobile
from ui.views.master.master_loot_view import (
    _KIND_ICONS, _KIND_LABELS, _MAGIC_KINDS, _coin_summary, _mechanics_summary,
)
from ui.views.world.combat_status import wound_status_label
from ui.views.world.qr_scanner_view import QrScannerView, qr_scanner_supported
from ui.world_transfer import show_world_import_picker
from ui import design as d
from ui.device_identity import resolve_device_id
from ui.widgets import (CardPicker, ScrollMemoryColumn, responsive_dialog_width, show_snack,
                        spell_card_options, wrap_dialog_actions)

logger = logging.getLogger(__name__)

#: Etichette in italiano dei campi proponibili in una richiesta di modifica
#: (§7.1) — stesso elenco di `perm.CHANGE_REQUEST_ALLOWED_FIELDS`, qui solo
#: la presentazione: `core/*.py` non deve mai contenere testo destinato alla
#: UI (nessuna dipendenza inversa core -> ui).
_CHANGE_REQUEST_FIELD_LABELS: dict[str, str] = {
    "str_score": "Forza",
    "dex_score": "Destrezza",
    "con_score": "Costituzione",
    "int_score": "Intelligenza",
    "wis_score": "Saggezza",
    "cha_score": "Carisma",
    "level": "Livello",
    "fighting_style": "Stile di Combattimento",
    "totem_animal": "Animale Totem",
    "land_terrain": "Terreno (Circolo della Terra)",
    "pact_boon": "Dono del Patto",
    "dragon_ancestry": "Discendenza Draconica",
}

#: Le 6 caratteristiche + livello si modificano con un numero; le 5 scelte
#: di classe (il resto di `_CHANGE_REQUEST_FIELD_LABELS`) con un Dropdown
#: sulle opzioni PHB reali (§ eleggibilità in `_change_request_field_choices`).
_CHANGE_REQUEST_NUMERIC_FIELDS: frozenset[str] = frozenset({
    "str_score", "dex_score", "con_score", "int_score", "wis_score", "cha_score", "level",
})

#: Intervallo del thread di sincronizzazione in background della scheda
#: mondo aperta — stesso ordine di grandezza del polling già in uso in
#: `home_view.py` (5s, caso web multi-sessione); qui un po' più stretto
#: perché il caso d'uso (LAN, un tavolo di gioco) tollera un sovraccarico
#: di rete più basso e beneficia di più reattività.
_DETAIL_SYNC_INTERVAL_S = 2.0

#: Intervallo più stretto usato SOLO mentre un combattimento condiviso è
#: visibile (`_live_combat_section`) — è la sezione più "live" della
#: schermata (PF/turno che cambiano più volte al minuto durante un
#: incontro), a differenza di membri/richieste/mappe che cambiano di rado.
#: Fuori da un combattimento resta `_DETAIL_SYNC_INTERVAL_S`, per non
#: martellare rete/DB anche quando non serve.
_DETAIL_SYNC_INTERVAL_COMBAT_S = 0.75

#: Intervallo del polling automatico di `finish_pending_join()` mentre il
#: dialogo "Unisciti in LAN" è in stato "in attesa dell'approvazione":
#: `core.world_sync.finish_pending_join()` è per design puramente
#: passivo (legge lo stato corrente, non notifica) — serve quindi un
#: ciclo lato client che lo richiami periodicamente per far avanzare la
#: UI da sola quando il master approva (vedi
#: `_open_lan_join_dialog._poll_pending_join_loop`). Non condiviso con
#: `_DETAIL_SYNC_INTERVAL_S`: sono due cicli su oggetti diversi (un
#: dialogo transitorio vs. la scheda di un mondo aperta), un valore proprio
#: evita un accoppiamento accidentale se in futuro cambia l'uno o l'altro.
_PENDING_JOIN_POLL_INTERVAL_S = 3.0

#: Chiave `app_settings` per ricordare una richiesta di ingresso ancora in
#: sospeso ATTRAVERSO la chiusura del dialogo o il riavvio dell'app —
#: `pending_state` è solo una variabile locale della closure di
#: `_open_lan_join_dialog`, persa non appena l'utente chiude il dialogo;
#: senza questa chiave si potrebbe riaprirne uno nuovo e inviare un'altra
#: richiesta senza alcun ricordo della precedente. Chiave GLOBALE (non
#: per-mondo): un giocatore ha realisticamente una sola richiesta di
#: ingresso in sospeso alla volta.
_PENDING_JOIN_REQUEST_SETTING_KEY = "pending_join_request"

#: Intervallo di ridisegno della mappa condivisa aperta in sola lettura
#: (§6.4) — non serve un valore proprio più stretto: il DB locale
#: è già tenuto allineato da `_start_detail_sync` a `_DETAIL_SYNC_INTERVAL_S`
#: (sia in ricezione eventi su una replica, sia per lettura diretta se
#: questo dispositivo ospita), quindi interrogarlo più spesso non
#: produrrebbe dati più freschi — solo lavoro sprecato. Stesso valore,
#: nome separato per leggibilità nel punto in cui è usato.
_SHARED_MAP_REDRAW_INTERVAL_S = _DETAIL_SYNC_INTERVAL_S

#: Anti-spam su "Interviene a distanza"/ingresso-sincronizzazione: le
#: costanti (3s per-personaggio sul master, 10s condiviso su ingresso/
#: sync) e lo stato vivono in `core.world_permissions`/`core.world_sync`,
#: non qui — a livello di modulo, non di istanza, perché sopravvive alla
#: ricreazione della view, con granularità per-personaggio sul master.


class WorldsView(ft.Column):
    """
    Callbacks:
        on_back_to_home()              → torna alla Home
        on_toggle_theme(e)/theme_preference → stessa pillola tema delle altre sezioni
    """

    def __init__(self, on_back_to_home, on_toggle_theme=None, theme_preference: str = "system",
                 host_server_slot: HostServerSlot | None = None,
                 initial_world_id: str | None = None,
                 on_open_master=None, on_open_character=None):
        """
        `initial_world_id` (navigazione rapida): se valorizzato,
        apre direttamente il dettaglio di quel mondo invece dell'elenco —
        usato dai pulsanti "Vai al Mondo" in `SheetView`/`MasterView`
        (`ui/app.py::_show_worlds_view`). Risolto in `_init_identity()`
        (serve `device_id` per validare l'appartenenza), silenziosamente
        ignorato se il mondo non esiste più o questo dispositivo non ne fa
        più parte — stessa tolleranza già usata per `active_world_id` in
        `MasterView`.

        `on_open_master`/`on_open_character` (navigazione
        rapida): callback dal dettaglio di un mondo verso, rispettivamente,
        la Sezione Master su quel mondo (`(world_id) -> None`, mostrato solo
        a master/owner) e la scheda del personaggio posseduto in quel mondo
        da questo dispositivo (`(character_id) -> None`, mostrato solo se
        esiste un'istanza propria non archiviata). `None` (default) nasconde
        i rispettivi pulsanti — vedi `_render_detail()`.
        """
        super().__init__(expand=True, spacing=0)
        self.on_open_master = on_open_master
        self.on_open_character = on_open_character
        self.on_back_to_home = on_back_to_home
        self.on_toggle_theme = on_toggle_theme
        self.theme_preference = theme_preference
        self._initial_world_id = initial_world_id

        #: Backend "locale" — corretto SOLO per i mondi che QUESTO
        #: dispositivo ospita (`world.is_local_host`); per un mondo a cui ci
        #: si è uniti da remoto va risolto per-mondo con `_backend_for()`,
        #: mai usato direttamente (vedi `_backend_for`).
        self.backend = LocalBackend()
        self.device_id: str | None = None
        self._current_world: World | None = None  # None = elenco, valorizzato = dettaglio

        #: Al più un hosting attivo per volta in questa
        #: view — coerente con §11.5 ("due dispositivi non possono
        #: ospitare lo stesso mondo"). `self._host_server` è una property
        #: che legge/scrive `self._host_server_slot.server` invece di
        #: essere un attributo di istanza diretto — vedi il docstring di
        #: `HostServerSlot` per il perché (l'hosting non deve fermarsi da
        #: solo ad ogni navigazione) — un contenitore passato
        #: da `ui/app.py::DnDApp` che sopravvive alla ricreazione di
        #: questa view. Se non passato (es. un test che costruisce
        #: `WorldsView` direttamente, senza passare da `DnDApp`), se ne
        #: crea uno privato — stesso comportamento di prima per chi non
        #: ha bisogno di condividerlo.
        self._host_server_slot = host_server_slot if host_server_slot is not None \
            else HostServerSlot()

        #: Un `RemoteBackend` connesso per mondo non-ospitato, riusato tra
        #: un'azione e l'altra invece di riconnettersi ad ogni comando
        #: (vedi `_backend_for`).
        self._remote_backends: dict[str, RemoteBackend] = {}

        # NOTA: i timer anti-spam ("Interviene a distanza" + ingresso/sync)
        # NON vivono come attributi di istanza qui: le istanze di questa
        # view vengono ricreate ad ogni navigazione/cambio tema, uno stato
        # sull'istanza si azzererebbe ad ogni ricreazione — vivono invece a
        # livello di modulo in `core.world_sync`, richiamati direttamente
        # da `_send_remote_command`/`_network_cooldown_remaining`/
        # `_mark_network_request` qui sotto.

        #: Sincronizzazione in background della scheda mondo aperta
        #: (§9.2 "attesa lunga" lato client + rilettura locale
        #: periodica lato host — vedi `_start_detail_sync`): nessuna azione
        #: manuale dell'utente, l'app tira giù/rispecchia da sola gli eventi
        #: nuovi finché la scheda di un mondo resta aperta.
        self._detail_sync_loop_obj: BackgroundSyncLoop | None = None
        self._detail_signature: str | None = None
        #: Ultimo `RemoteBackend.connection_state()` osservato per il mondo
        #: nel dettaglio aperto — alimenta il LED in
        #: `_render_detail()`, aggiornato ad ogni giro di `_start_detail_sync`.
        self._detail_connection_state: str = "connected"
        #: Guardia contro ticker di countdown sovrapposti — vedi
        #: `_start_master_cooldown_ticker`.
        self._master_cooldown_ticker_running: bool = False
        #: Protegge la mutazione di `self._body.controls`, condivisa tra il
        #: thread Flet (azioni utente) e il thread di sync in background —
        #: stesso principio già in uso in `home_view.py::_refresh_lock`.
        self._render_lock = threading.Lock()

        #: FilePicker mobile per l'export di un mondo — stesso principio di
        #: `HomeView._file_picker`: creato/registrato
        #: al volo da `_ensure_file_picker()` se non già presente.
        self._file_picker: ft.FilePicker | None = None

        # `ScrollMemoryColumn`, non un `ft.Column` semplice: `_render()`
        # ricostruisce `.controls` da zero ad ogni ridisegno periodico
        # (`_start_detail_sync`, `_master_cooldown_ticker_loop`), un
        # `ft.Column` semplice perderebbe lo scroll ogni volta anche senza
        # alcuna azione dell'utente.
        self._body = ScrollMemoryColumn(spacing=d.Space.MD, scroll=ft.ScrollMode.AUTO, expand=True)

        # Container persistenti per le 4 sezioni "calde" (piano refresh
        # mirati, Fase 1c): permettono a un'azione locale di aggiornare SOLO
        # la sezione toccata (`_update_members_section()`/
        # `_update_shared_loot_section()`) senza ricostruire l'intero
        # `self._body`. Restano SEMPRE nell'albero prodotto da
        # `_render_detail()` — mai più un append condizionale — con
        # `.visible` a governarne la presenza, così un `.update()` mirato
        # non incontra mai un controllo non ancora montato. Il tick di sync
        # periodico (`_async_redraw_detail`) resta invariato: ricostruisce
        # ancora tutto tramite `_render_detail()`, che ripopola anche questi
        # container allo stesso modo — nessun percorso doppio da mantenere
        # allineato.
        self._members_container: ft.Container = ft.Container()
        self._live_combat_container: ft.Container = ft.Container(visible=False)
        self._shared_notes_container: ft.Container = ft.Container(visible=False)
        self._shared_loot_container: ft.Container = ft.Container(visible=False)

        self._build_shell()
        self._render_loading()

    @property
    def _host_server(self) -> WorldHostServer | None:
        return self._host_server_slot.server

    @_host_server.setter
    def _host_server(self, value: WorldHostServer | None) -> None:
        self._host_server_slot.server = value

    def did_mount(self):
        page = self.page
        if page is not None:
            page.run_task(self._init_identity)

    def will_unmount(self):
        self._stop_detail_sync()
        # QUI NON si ferma l'hosting eventualmente attivo: `ui/app.py::
        # _navigate()` ricrea l'intera pagina ad OGNI navigazione di primo
        # livello (Home, Modalità Master, cambio tema incluso), quindi
        # `will_unmount()` scatta ad ogni singola di quelle azioni, non
        # solo uscendo davvero dalla Sezione Mondi — fermare l'hosting qui
        # disconnetterebbe silenziosamente un giocatore connesso ogni
        # volta che il master apre un'altra schermata.
        # L'hosting vive in `self._host_server_slot` (vedi il
        # docstring di `HostServerSlot` in `network/host_server.py`), che
        # sopravvive alla ricreazione di questa view: si ferma SOLO
        # tramite `_stop_hosting()` (pulsante "Ferma hosting", azione
        # esplicita del master) o alla chiusura vera del processo (il
        # thread del server è `daemon=True`, nessun cleanup necessario
        # qui per quel caso).

    async def _init_identity(self):
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        world_id = self._initial_world_id
        self._initial_world_id = None  # una tantum: non riaprire il dettaglio ad ogni rebuild
        if world_id:
            world = world_repo.get_world(world_id)
            member = (world_repo.get_member(world_id, self.device_id)
                      if world is not None and self.device_id else None)
            if world is not None and member is not None:
                self._open_detail(world)
                return
        self._render()
        try:
            page.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------

    def _build_shell(self):
        p = d.T()
        header_actions: list[ft.Control] = [
            d.pill(ft.Icons.ARROW_BACK, "Home", color=p.text_2,
                   on_click=lambda e: self.on_back_to_home()),
        ]
        if self.on_toggle_theme is not None:
            from ui.widgets import theme_toggle_pill
            header_actions.append(theme_toggle_pill(self.theme_preference, self.on_toggle_theme))

        header = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [d.title("Mondi", color=p.text)],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=d.Space.SM),
                    ft.Row(header_actions, spacing=d.Space.SM, wrap=True,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=d.Space.XS),
                    d.muted("Crea o unisciti a una campagna condivisa: chi si "
                            "collega alla stessa rete locale vede mappe, note "
                            "e personaggi in tempo reale."),
                ],
                spacing=0, tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=d.Space.XL, vertical=d.Space.XL),
            bgcolor=p.surface,
            shadow=d.elevation(2),
        )
        body_container = ft.Container(
            content=self._body,
            expand=True,
            padding=ft.Padding.symmetric(horizontal=d.Space.XL, vertical=d.Space.XL),
            gradient=d.page_gradient(),
        )
        self.controls = [header, body_container]

    def _render_loading(self):
        self._body.controls = [d.empty_state(
            ft.Icons.HOURGLASS_TOP, "Risoluzione dell'identità del dispositivo…",
        )]

    def _render(self):
        # Con lock: questo metodo muta `self._body.controls` ed è chiamato
        # sia dal thread Flet (ogni azione utente) sia dal thread di sync in
        # background (`_detail_sync_loop`) — senza serializzare le due
        # scritture concorrenti su `self._body.controls` si rischierebbe una
        # ricostruzione a metà, stesso principio già in uso in
        # `home_view.py::_refresh_lock`.
        with self._render_lock:
            if self.device_id is None:
                self._render_loading()
                return
            if self._current_world is None:
                self._render_list()
            else:
                self._render_detail(self._current_world)

    # ------------------------------------------------------------------
    # Elenco mondi
    # ------------------------------------------------------------------

    def _render_list(self):
        p = d.T()
        assert self.device_id is not None
        worlds = world_repo.get_worlds_for_device(self.device_id)

        actions_row = ft.Row(
            [
                d.pill(ft.Icons.ADD, "Crea un mondo", filled=True, color=p.primary_fill,
                       on_click=lambda e: self._open_create_dialog()),
                d.pill(ft.Icons.MEETING_ROOM, "Unisciti con un codice", color=p.magic,
                       on_click=lambda e: self._open_join_dialog()),
                d.pill(ft.Icons.WIFI, "Unisciti in LAN", color=p.magic,
                       on_click=lambda e: self._open_lan_join_dialog()),
                d.pill(ft.Icons.UPLOAD_FILE, "Importa mondo", color=p.text_2,
                       on_click=self._on_import_world_click),
            ],
            spacing=d.Space.SM, wrap=True,
        )

        if not worlds:
            content: list[ft.Control] = [
                actions_row,
                ft.Container(height=d.Space.MD),
                d.empty_state(
                    ft.Icons.PUBLIC_OFF, "Nessun mondo",
                    "Crea un mondo come master, o uniscitene uno con il codice "
                    "a 6 caratteri che ti ha dato il master.",
                ),
            ]
        else:
            cards = [self._world_card(w) for w in worlds]
            content = [actions_row, ft.Container(height=d.Space.MD), *cards]

        self._body.controls = content

    def _world_card(self, world: World) -> ft.Control:
        p = d.T()
        assert self.device_id is not None
        member = world_repo.get_member(world.id, self.device_id)
        role = member.role if member else "?"
        role_tone: d.Tone = {"owner": "magic", "master": "primary", "player": "neutral"}.get(role, "neutral")
        members = world_repo.get_members(world.id)
        # §11.9: il personaggio di questo dispositivo è stato spostato altrove.
        transferred_away = world_sync.is_world_transferred_away(world.id)
        badges: list[ft.Control] = [d.chip(role, role_tone),
                                     d.muted(f"{len(members)} membri")]
        if transferred_away:
            badges.append(d.chip("trasferito", "danger"))
        row_children: list[ft.Control] = [
            ft.Column(
                [
                    ft.Text(world.name, size=d.Size.SUBTITLE, weight=ft.FontWeight.BOLD,
                            color=p.text, font_family=d.Font.DISPLAY),
                    ft.Row(badges, spacing=d.Space.SM, wrap=True),
                ],
                spacing=d.Space.XS, expand=True,
            ),
        ]
        # Nessun pulsante di riconnessione su un mondo trasferito: non esiste più
        # una sessione da riprendere, e offrirlo produrrebbe solo un errore.
        if not world.is_local_host and not transferred_away:
            # Riconnessione rapida: `_backend_for` riusa già
            # `world.session_token` (§9.4), qui lo si rende un'azione
            # ESPLICITA con un esito visibile invece di un side-effect
            # silenzioso alla prossima apertura del dettaglio.
            row_children.append(ft.IconButton(
                ft.Icons.WIFI_PROTECTED_SETUP, icon_color=p.magic,
                tooltip="Riconnettiti",
                on_click=lambda e, w=world: self._reconnect_world(w),
            ))
        if transferred_away:
            # Solo locale: non c'è alcun backend raggiungibile per un mondo
            # trasferito (`resolve_backend_for_world` ritorna sempre `None`,
            # vedi `core.world_sync`), quindi nessun comando da inviare — un
            # semplice `stop_propagation` evita che il click apra anche il
            # dettaglio sotto.
            row_children.append(ft.IconButton(
                ft.Icons.DELETE_OUTLINE, icon_color=p.danger_icon,
                tooltip="Rimuovi dalla lista",
                on_click=lambda e, w=world: self._confirm_remove_transferred(w),
            ))
        row_children.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, color=p.text_3))
        return d.card(
            ft.Row(
                row_children,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e, w=world: self._open_detail(w),
        )

    def _transferred_away_banner(self, world: World) -> ft.Control:
        """
        Avviso sul dettaglio di un mondo il cui personaggio è stato spostato su
        un altro dispositivo (§11.9).

        La replica NON viene cancellata da sola: contiene il giornale, le
        note condivise e le mappe ricevute, cioè la memoria della campagna
        vista da qui, e il diario del giocatore. Resta consultabile in sola
        lettura — è la stessa condizione di §11.3 ("scollegati, l'istanza è
        in sola lettura"), qui definitiva invece che temporanea — e si
        rimuove quando l'utente vuole, dal pulsante qui sotto.
        """
        p = d.T()
        return d.section(
            "Trasferito su un altro dispositivo",
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PHONELINK_ERASE, size=18, color=p.danger_icon),
                            ft.Text(
                                "Il personaggio di questo dispositivo è stato spostato "
                                "su un altro dispositivo.",
                                color=p.text, size=d.Size.BODY_SM, expand=True,
                            ),
                        ],
                        spacing=d.Space.XS,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    d.muted(
                        "Qui resta una copia di sola lettura: puoi consultare il "
                        "registro, le note e le mappe ricevute, ma non inviare più "
                        "nulla al master. Puoi rimuovere il mondo quando vuoi."
                    ),
                    ft.Row([d.pill(
                        ft.Icons.DELETE_OUTLINE, "Rimuovi mondo", color=p.danger,
                        on_click=lambda e, w=world: self._confirm_remove_transferred(w),
                    )], alignment=ft.MainAxisAlignment.END),
                ],
                spacing=d.Space.XS, tight=True,
            ),
        )

    def _reconnect_world(self, world: World) -> None:
        """Tentativo esplicito di riconnessione (pulsante sulla card del
        mondo) — stesso `_backend_for()` usato ovunque, con feedback
        immediato invece del side-effect silenzioso alla prossima apertura
        del dettaglio. Chiamata sincrona diretta nell'handler di click,
        stessa convenzione già in uso per `world_sync.start_lan_join()` nel
        dialogo "Unisciti in LAN" — una richiesta HTTP su rete locale con
        timeout breve, nessun thread dedicato necessario."""
        backend = self._backend_for(world)
        if backend is not None and (
            not isinstance(backend, RemoteBackend) or backend.connection_state() == "connected"
        ):
            show_snack(self.page, f"Riconnesso a «{world.name}».")
        else:
            show_snack(
                self.page,
                f"Impossibile riconnettersi a «{world.name}» — l'host potrebbe "
                "essere offline o il PIN potrebbe essere cambiato.",
                tone="danger",
            )
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass

    def _open_detail(self, world: World):
        self._current_world = world
        self._render()
        self._start_detail_sync(world.id)
        try:
            self.page.update()
        except RuntimeError:
            pass

    def _back_to_list(self):
        self._current_world = None
        self._stop_detail_sync()
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Dettaglio mondo
    # ------------------------------------------------------------------

    def _render_detail(self, world: World):
        p = d.T()
        assert self.device_id is not None
        # Rilettura fresca — un'azione appena eseguita può averlo cambiato.
        fresh = world_repo.get_world(world.id)
        if fresh is None:
            self._current_world = None
            self._render_list()
            return
        world = self._current_world = fresh

        my_member = world_repo.get_member(world.id, self.device_id)
        my_role = my_member.role if my_member else ""
        is_owner = my_role == perm.ROLE_OWNER

        # Momento tipografico dominante della schermata (Arcane Ledger,
        # `Size.HERO`): il nome del mondo è l'unico elemento "hero" del
        # dettaglio, MAX uno per schermata — vedi il docstring di
        # `design.hero_title()`.
        title_row: list[ft.Control] = [d.hero_title(world.name)]
        if not world.is_local_host:
            title_row.append(d.connection_led(self._detail_connection_state))
        sections: list[ft.Control] = [
            d.pill(ft.Icons.ARROW_BACK, "Tutti i mondi", color=p.text_2,
                   on_click=lambda e: self._back_to_list()),
            ft.Container(height=d.Space.SM),
            ft.Row(title_row, spacing=d.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]

        # Navigazione rapida: dalla sezione mondo del player porta alla
        # scheda del personaggio registrato in quel mondo, per il master
        # invece alla sezione master — una riga di pillole, mostrata solo se
        # il chiamante ha passato il relativo callback E c'è qualcosa da
        # mostrare (nessun pulsante fantasma per un ruolo che non lo usa).
        quick_nav: list[ft.Control] = []
        if self.on_open_master is not None and perm.can_perform(my_role, perm.CMD_XP_GRANT):
            quick_nav.append(d.pill(ft.Icons.CASTLE_OUTLINED, "Vai alla Sezione Master", color=p.magic,
                                     on_click=lambda e, wid=world.id: self.on_open_master(wid)))
        if self.on_open_character is not None:
            my_instance = next(
                (c for c in character_repo.get_all_instances_of_world(world.id)
                 if c.owner_device_id == self.device_id and not c.world_instance_archived),
                None,
            )
            if my_instance is not None:
                quick_nav.append(d.pill(
                    ft.Icons.PERSON, "Vai alla mia scheda", color=p.primary,
                    on_click=lambda e, cid=my_instance.id: self.on_open_character(cid),
                ))
        if quick_nav:
            sections.append(ft.Row(quick_nav, spacing=d.Space.SM, wrap=True))

        # Questo dispositivo è stato sostituito da un altro (§11.9):
        # va detto subito e in modo inequivocabile, prima di qualunque sezione
        # che invita ad agire — altrimenti il giocatore prova a mandare comandi
        # e li vede fallire senza capire perché.
        if world_sync.is_world_transferred_away(world.id):
            sections.append(self._transferred_away_banner(world))

        if is_owner:
            sections.append(self._rename_section(world))

        sections.append(self._join_code_section(world, is_owner))
        pending_requests_section = self._pending_change_requests_section(world)
        if pending_requests_section is not None:
            sections.append(pending_requests_section)
        if perm.can_perform(my_role, perm.CMD_CHARACTER_REJOIN_RESPOND):
            pending_rejoin_section = self._pending_rejoin_requests_section(world)
            if pending_rejoin_section is not None:
                sections.append(pending_rejoin_section)
        if is_owner and world.is_local_host:
            sections.append(self._hosting_section(world))
        self._live_combat_container.content = self._live_combat_section(world)
        self._live_combat_container.visible = self._live_combat_container.content is not None
        sections.append(self._live_combat_container)
        self._shared_notes_container.content = self._shared_notes_section(world)
        self._shared_notes_container.visible = self._shared_notes_container.content is not None
        sections.append(self._shared_notes_container)
        shared_maps_section = self._shared_maps_section(world, my_role)
        if shared_maps_section is not None:
            sections.append(shared_maps_section)
        self._shared_loot_container.content = self._shared_loot_section(world)
        self._shared_loot_container.visible = self._shared_loot_container.content is not None
        sections.append(self._shared_loot_container)
        if perm.can_perform(my_role, perm.CMD_XP_GRANT):
            sections.append(self._remote_actions_section(world))
            archived_section = self._archived_characters_section(world)
            if archived_section is not None:
                sections.append(archived_section)
        self._members_container.content = self._members_section(world, my_role)
        self._members_container.visible = True
        sections.append(self._members_container)
        sections.append(self._events_section(world))

        if is_owner:
            sections.append(self._backup_section(world))
            sections.append(self._danger_zone_section(world))

        self._body.controls = sections

    # ------------------------------------------------------------------
    # Routing dei comandi (§9.1).
    #
    # Ogni dialog di questa view deve passare da `_send_command`/
    # `_backend_for` invece di chiamare `self.backend.send_command(...)`
    # direttamente: `self.backend` è sempre `LocalBackend()`, va bene per
    # l'host (il suo DB locale È lo stato autoritativo) ma per un
    # dispositivo che si è unito in LAN (`is_local_host=False`) scriverebbe
    # SOLO sulla propria replica, senza mai raggiungere l'host — il comando
    # "riuscirebbe" a schermo (nessun errore) ma non lascerebbe mai quel
    # dispositivo.
    # ------------------------------------------------------------------

    def _backend_for(self, world: World) -> WorldBackend | None:
        """
        Risolve il backend giusto per QUESTO mondo su QUESTO dispositivo:
        `LocalBackend` se lo ospita, altrimenti un `RemoteBackend` connesso
        all'host (§9.4: riusa `world.session_token`, mai richiede di nuovo
        codice+PIN). Ritorna `None` se non è stato possibile stabilire una
        connessione valida — il chiamante deve mostrare un errore chiaro,
        mai fallire in silenzio.

        Logica vera e propria in `core.world_sync.resolve_backend_for_world`
        (serve identica anche a `ui/views/home_view.py`) — questo resta un
        sottile adattatore che passa `self._remote_backends` come cache
        persistente di questa view.
        """
        return world_sync.resolve_backend_for_world(
            world, self.device_id or "", self.backend, self._remote_backends,
        )

    def _send_command(self, world: World, kind: str, payload: dict, *,
                       target_type: str = "", target_id: str = "") -> CommandResult:
        """Punto unico di invio comandi per QUALSIASI mondo — sostituisce
        l'uso diretto di `self.backend.send_command(...)` in ogni dialog di
        questa view. Se il comando viaggia su un `RemoteBackend` riuscito,
        applica SUBITO l'evento di ritorno alla propria replica invece di
        aspettare il prossimo giro della sincronizzazione in background
        (`_apply_own_remote_result`): chi ha appena agito vede l'effetto
        senza percepibile ritardo."""
        assert self.device_id is not None
        backend = self._backend_for(world)
        if backend is None:
            return CommandResult(
                False,
                "Non connesso all'host di questo mondo — apri \"Unisciti in "
                "LAN\" per riconnetterti (il PIN potrebbe essere cambiato se "
                "l'host è stato riavviato).",
            )
        result = backend.send_command(world.id, self.device_id, kind, payload,
                                       target_type=target_type, target_id=target_id)
        if result.success and backend is not self.backend:
            self._apply_own_remote_result(world.id, backend, result)
        return result

    def _apply_own_remote_result(self, world_id: str, remote_backend: RemoteBackend,
                                  result: CommandResult) -> None:
        """Rimaterializza subito sulla propria replica l'evento appena
        prodotto da un comando andato a buon fine su `RemoteBackend` —
        `world_sync.sync_replica()` lo riscaricherebbe comunque al prossimo
        giro del thread di sincronizzazione, ma qui evitiamo l'attesa per
        chi ha appena premuto il pulsante. Sicuro da richiamare più volte
        sullo stesso evento (idempotente, stessa garanzia di
        `sync_replica()`): se il thread in background lo applica di nuovo
        poco dopo non succede nulla di diverso."""
        try:
            # `refresh_members` di default (True): un comando andato a buon
            # fine potrebbe essere proprio member.promote/demote/kick, per
            # cui l'elenco membri va rinfrescato insieme all'evento — costo
            # di una chiamata di rete in più, accettabile perché avviene
            # solo subito dopo un'azione, non ad ogni giro del polling.
            world_sync.sync_replica(remote_backend, world_id)
        except Exception as e:  # difesa in profondità: mai bloccare l'azione
            logger.debug("Sync immediata post-comando fallita per %s: %s", world_id, e)

    def _rename_section(self, world: World) -> ft.Control:
        field = ft.TextField(value=world.name, dense=True, expand=True, **d.field_style())

        def _save(e):
            result = self._send_command(
                world, perm.CMD_WORLD_RENAME, {"name": field.value},
            )
            if result.success:
                self._refresh_detail()
            else:
                self._show_error(result.error)

        return d.section(
            "Nome del mondo",
            ft.Row([field, ft.IconButton(ft.Icons.SAVE, tooltip="Rinomina", on_click=_save)]),
        )

    def _join_code_section(self, world: World, is_owner: bool) -> ft.Control:
        p = d.T()
        trailing = None
        if is_owner:
            trailing = d.pill(ft.Icons.REFRESH, "Rigenera", color=p.text_2,
                               on_click=lambda e: self._regenerate_join_code(world))
        return d.section(
            "Codice d'ingresso",
            ft.Row(
                [
                    ft.Text(world.join_code, size=24, weight=ft.FontWeight.BOLD,
                            color=p.magic, font_family=d.Font.MONO,
                            style=ft.TextStyle(letter_spacing=4)),
                ],
            ),
            trailing=trailing,
        )

    def _regenerate_join_code(self, world: World):
        result = self._send_command(world, perm.CMD_WORLD_JOIN_CODE_REGENERATE, {})
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

    def _members_section(self, world: World, my_role: str) -> ft.Control:
        members = world_repo.get_members(world.id)
        rows = [self._member_row(world, m, my_role) for m in members]
        return d.section("Membri", ft.Column(rows, spacing=d.Space.SM, tight=True),
                          density="dense")

    def _member_row(self, world: World, member: WorldMember, my_role: str) -> ft.Control:
        p = d.T()
        role_tone: d.Tone = {"owner": "magic", "master": "primary", "player": "neutral"}.get(
            member.role, "neutral")
        actions: list[ft.Control] = []
        is_me = member.device_id == self.device_id

        if perm.can_perform(my_role, perm.CMD_MEMBER_PROMOTE) and member.role == perm.ROLE_PLAYER:
            actions.append(ft.IconButton(
                ft.Icons.ARROW_UPWARD, tooltip="Promuovi a co-master",
                on_click=lambda e, m=member: self._member_command(
                    world, perm.CMD_MEMBER_PROMOTE, m),
            ))
        if perm.can_perform(my_role, perm.CMD_MEMBER_DEMOTE) and member.role == perm.ROLE_MASTER:
            actions.append(ft.IconButton(
                ft.Icons.ARROW_DOWNWARD, tooltip="Retrocedi a giocatore",
                on_click=lambda e, m=member: self._member_command(
                    world, perm.CMD_MEMBER_DEMOTE, m),
            ))
        if (perm.can_perform(my_role, perm.CMD_MEMBER_KICK)
                and member.role != perm.ROLE_OWNER and not is_me):
            actions.append(ft.IconButton(
                ft.Icons.PERSON_REMOVE, tooltip="Espelli dal mondo",
                icon_color=p.danger_icon,
                on_click=lambda e, m=member: self._confirm_kick(world, m),
            ))
        # Uscita volontaria: solo sul PROPRIO membro, mai sull'owner (deve
        # prima trasferire la proprietà, stesso blocco già applicato al kick).
        if is_me and member.role != perm.ROLE_OWNER:
            actions.append(ft.IconButton(
                ft.Icons.EXIT_TO_APP, tooltip="Esci dal mondo",
                icon_color=p.danger_icon,
                on_click=lambda e, m=member: self._confirm_leave(world, m),
            ))

        # Codice per il cambio dispositivo (§11.9). Visibile per il
        # PROPRIO membro (sto per cambiare telefono e ho ancora questo in mano)
        # e, se sono master/owner, anche per i giocatori (il loro telefono è
        # perso o rotto e non possono generarselo). Mai per l'owner: il suo
        # device_id è su `worlds.owner_device_id` e la sua via è l'export
        # `.dndworld` — l'handler lo rifiuta comunque, ma mostrare un pulsante
        # che porta solo a un errore sarebbe peggio che non mostrarlo.
        if (member.role != perm.ROLE_OWNER
                and perm.can_perform(my_role, perm.CMD_DEVICE_TRANSFER_ISSUE)
                and (is_me or perm.role_at_least(my_role, perm.ROLE_MASTER))):
            actions.append(ft.IconButton(
                ft.Icons.PHONELINK_SETUP,
                tooltip=("Cambio dispositivo: genera un codice per te"
                         if is_me else
                         f"Genera un codice di trasferimento per {member.display_name}"),
                on_click=lambda e, m=member: self._open_transfer_code_dialog(world, m),
            ))

        # Riga a due colonne di peso diverso (`asymmetric_row`), non una
        # singola `Row` con tutto in fila: fino a 3 pulsanti azione + chip
        # accanto al nome affollava la riga su schermi stretti — qui il
        # blocco identità (icona+nome) e quello azioni (chip+pulsanti)
        # tornano impilati sotto i 768px invece di comprimersi/traboccare.
        info = ft.Row(
            [
                d.icon_badge(ft.Icons.PERSON, tone="neutral", size=28),
                ft.Text(member.display_name + (" (tu)" if is_me else ""),
                        color=p.text, expand=True),
            ],
            spacing=d.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        trailing = ft.Row(
            [d.chip(member.role, role_tone), *actions],
            spacing=d.Space.XS, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return d.asymmetric_row(info, trailing)

    def _member_command(self, world: World, kind: str, member: WorldMember):
        result = self._send_command(world, kind, {"device_id": member.device_id})
        if result.success:
            # Promuovere/retrocedere/espellere non cambia altre sezioni del
            # dettaglio: aggiornamento mirato invece di `_refresh_detail()`
            # completo (piano refresh mirati, Fase 1c).
            assert self.device_id is not None
            my_member = world_repo.get_member(world.id, self.device_id)
            my_role = my_member.role if my_member else ""
            self._update_members_section(world, my_role)
        else:
            self._show_error(result.error)

    def _open_transfer_code_dialog(self, world: World, member: WorldMember):
        """
        Genera e mostra un codice di trasferimento per `member` (§11.9): il
        codice con cui un ALTRO dispositivo subentra a questo membro
        portandosi via i suoi personaggi.

        Il codice arriva in `CommandResult.data`, non nell'evento di giornale:
        `world_events.payload` viene trasmesso a ogni replica via `GET /events` e
        questo è un segreto per un solo membro (vedi
        `world_backend._handle_device_transfer_issue`).

        Il QR si può generare SOLO se questo dispositivo ospita il mondo: solo
        lì si conoscono indirizzo e porta da incorporarvi. Un master collegato a
        distanza vede il solo codice, che è comunque sufficiente.
        """
        p = d.T()
        is_me = member.device_id == self.device_id

        result = self._send_command(
            world, perm.CMD_DEVICE_TRANSFER_ISSUE, {"device_id": member.device_id},
        )
        if not result.success:
            self._show_error(result.error)
            return
        code = (result.data or {}).get("code", "")
        expires_at = (result.data or {}).get("expires_at", "")
        if not code:
            # L'host ha accettato il comando ma non ha restituito il codice:
            # succede solo parlando con un host di una versione che non conosce
            # il campo `data`. Dirlo, invece di mostrare un dialogo vuoto.
            self._show_error(
                "L'host ha generato il codice ma non lo ha restituito: "
                "probabilmente ha una versione dell'app più vecchia."
            )
            return

        body: list[ft.Control] = [
            ft.Text(
                (
                    "Usa questo codice sul nuovo dispositivo, nella schermata "
                    "«Unisciti in LAN», al posto del PIN."
                    if is_me else
                    f"Comunica questo codice a {member.display_name}: lo userà sul "
                    f"nuovo dispositivo al posto del PIN."
                ),
                color=p.text, size=d.Size.BODY_SM,
            ),
            ft.Container(height=d.Space.SM),
            ft.Row(
                [
                    ft.Text(code, size=22, weight=ft.FontWeight.BOLD, color=p.magic,
                            font_family=d.Font.MONO,
                            style=ft.TextStyle(letter_spacing=4)),
                ],
            ),
        ]

        if expires_at:
            try:
                scadenza = datetime.fromisoformat(expires_at)
                body.append(d.muted(
                    f"Valido fino al {scadenza.strftime('%d/%m/%Y alle %H:%M')}."
                ))
            except ValueError:
                pass

        body.append(d.muted(
            "Il master dovrà comunque approvare il nuovo dispositivo. "
            "Da quel momento questo dispositivo non farà più parte del mondo."
            if is_me else
            "Dovrai comunque approvare il nuovo dispositivo quando si presenta. "
            "Da quel momento il dispositivo attuale non farà più parte del mondo."
        ))

        # Il QR solo dall'host: altrove non conosciamo indirizzo e porta.
        if world.is_local_host and self._host_server is not None and self._host_server.is_running:
            try:
                qr_text = build_transfer_text(
                    world.name, local_ip_hint(), self._host_server.port,
                    world.join_code, code,
                )
                b64 = generate_qr_png_base64(qr_text)
                body.append(ft.Container(height=d.Space.SM))
                body.append(d.muted("Oppure inquadra questo QR dal nuovo dispositivo"))
                body.append(ft.Container(
                    content=ft.Image(src=f"data:image/png;base64,{b64}",
                                      width=170, height=170, fit=ft.BoxFit.CONTAIN),
                    bgcolor=ft.Colors.WHITE, padding=d.Space.SM,
                    border_radius=d.Radius.SM,
                ))
            except Exception as e:
                # Stessa scelta del QR d'ingresso (`_hosting_qr_image`): l'errore
                # va detto in UI, non solo loggato — un log su stderr non è
                # raggiungibile dall'app impacchettata. Il codice testuale sopra
                # basta comunque da solo.
                logger.error("Errore nella generazione del QR di trasferimento: %s", e)
                body.append(ft.Text(f"QR non generato: {e}", color=p.danger,
                                     size=d.Size.BODY_SM))

        def _revoke(e):
            self.page.pop_dialog()
            res = self._send_command(
                world, perm.CMD_DEVICE_TRANSFER_REVOKE, {"device_id": member.device_id},
            )
            if res.success:
                show_snack(self.page, "Codice di trasferimento revocato.")
            else:
                self._show_error(res.error)

        dlg = ft.AlertDialog(
            title=d.dialog_title("Cambio dispositivo", ft.Icons.PHONELINK_SETUP),
            content=ft.Column(body, spacing=d.Space.XS, tight=True,
                               scroll=ft.ScrollMode.AUTO),
            actions=wrap_dialog_actions([
                ft.TextButton("Revoca", icon=ft.Icons.BLOCK, on_click=_revoke,
                              style=ft.ButtonStyle(color=p.danger)),
                ft.ElevatedButton("Ho capito", on_click=lambda e: self.page.pop_dialog()),
            ]),
        )
        self.page.show_dialog(dlg)

    def _confirm_kick(self, world: World, member: WorldMember):
        p = d.T()
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Espelli membro", ft.Icons.PERSON_REMOVE, tone="danger"),
            content=ft.Text(f'Espellere "{member.display_name}" dal mondo?', color=p.text),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Espelli", icon=ft.Icons.PERSON_REMOVE,
                    on_click=lambda e: self._do_kick(world, member),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        self.page.show_dialog(dlg)

    def _do_kick(self, world: World, member: WorldMember):
        self.page.pop_dialog()
        self._member_command(world, perm.CMD_MEMBER_KICK, member)

    def _confirm_leave(self, world: World, member: WorldMember):
        p = d.T()
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Esci dal mondo", ft.Icons.EXIT_TO_APP, tone="danger"),
            content=ft.Text(
                f'Uscire da "{world.name}"? Il mondo sparirà dalla tua lista.',
                color=p.text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Esci", icon=ft.Icons.EXIT_TO_APP,
                    on_click=lambda e: self._do_leave(world),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        self.page.show_dialog(dlg)

    def _do_leave(self, world: World):
        """Primo passo dell'uscita dal mondo: se possiedo qui una o più
        istanze "porta com'è"/"dal 1° livello" che hanno ancora un'origine
        locale viva (`origin_character_id`), non si può decidere in
        automatico cosa farne — BUG FIX (2026-08-20): prima questa istanza
        diventava semplicemente un secondo personaggio locale accanto
        all'originale mai toccato (`detach_world_instances`), un duplicato
        agli occhi del giocatore. Ora si chiede, istanza per istanza: fondere
        la progressione fatta nel mondo nell'originale, o scartare la copia.
        Se nessuna istanza ha un'origine ancora viva (es. cancellata nel
        frattempo), non c'è nulla da chiedere: si passa dritti a
        `_finalize_leave` con le scelte vuote (fallback storico, l'istanza
        diventa lei stessa il personaggio locale)."""
        self.page.pop_dialog()
        pending = character_repo.get_owned_world_instances(world.id, self.device_id) if self.device_id else []
        mergeable = [
            c for c in pending
            if c.origin_character_id and character_repo.get_by_id(c.origin_character_id) is not None
        ]
        if mergeable:
            self._show_leave_merge_dialog(world, pending, mergeable)
            return
        self._finalize_leave(world, pending, {})

    def _show_leave_merge_dialog(self, world: World, pending: list[Character],
                                  mergeable: list[Character]):
        """Un pulsante Fondi/Elimina per ciascuna istanza in `mergeable`
        (default preselezionato: Fondi, l'opzione senza perdita di dati) —
        vedi `_do_leave` sopra per il perché esiste."""
        page = self.page
        if page is None:
            return
        p = d.T()
        choices: dict[str, str] = {c.id: "merge" for c in mergeable}
        rows: list[ft.Control] = [
            ft.Text(
                "Il tuo personaggio locale NON viene toccato in nessun caso: "
                "scegli solo cosa fare della copia usata in questo mondo.",
                color=p.text, size=d.Size.BODY_SM,
            ),
        ]
        merge_btns: dict[str, ft.ElevatedButton] = {}
        discard_btns: dict[str, ft.OutlinedButton] = {}

        def _style(selected: bool, danger: bool = False) -> ft.ButtonStyle:
            if not selected:
                return ft.ButtonStyle(bgcolor=p.surface_alt, color=p.text_2)
            if danger:
                return ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text)
            return ft.ButtonStyle(bgcolor=p.primary_fill, color=p.on_primary_fill)

        def _set_choice(cid: str, choice: str):
            choices[cid] = choice
            merge_btns[cid].style = _style(choice == "merge")
            discard_btns[cid].style = _style(choice == "discard", danger=True)
            page.update()

        for c in mergeable:
            origin = character_repo.get_by_id(c.origin_character_id)
            origin_name = origin.name if origin else c.name
            merge_btn = ft.ElevatedButton(
                "Fondi con il locale", icon=ft.Icons.MERGE_TYPE,
                style=_style(True),
            )
            discard_btn = ft.OutlinedButton(
                "Elimina copia del mondo", icon=ft.Icons.DELETE_OUTLINE,
                style=_style(False),
            )
            merge_btn.on_click = lambda e, cid=c.id: _set_choice(cid, "merge")
            discard_btn.on_click = lambda e, cid=c.id: _set_choice(cid, "discard")
            merge_btns[c.id] = merge_btn
            discard_btns[c.id] = discard_btn
            rows.append(ft.Column(
                [
                    ft.Text(
                        f'{c.name} (Liv. {c.level}, in "{world.name}") '
                        f'→ personaggio locale "{origin_name}"',
                        weight=ft.FontWeight.BOLD, color=p.text, size=d.Size.BODY_SM,
                    ),
                    ft.Row([merge_btn, discard_btn], spacing=d.Space.SM, wrap=True),
                ],
                spacing=d.Space.XS,
            ))

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Esci dal mondo", ft.Icons.EXIT_TO_APP, tone="danger"),
            content=ft.Container(
                width=responsive_dialog_width(page, 420),
                content=ft.Column(rows, spacing=d.Space.MD, tight=True, scroll=ft.ScrollMode.AUTO),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Conferma uscita", icon=ft.Icons.EXIT_TO_APP,
                    on_click=lambda e: self._finalize_leave(world, pending, choices),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _finalize_leave(self, world: World, pending: list[Character], choices: dict[str, str]):
        """Secondo passo dell'uscita dal mondo (o unico, se `_do_leave` non
        ha trovato nulla da chiedere): invia `CMD_MEMBER_LEAVE` (rimuove il
        membro sull'host, archivia le sue istanze — vedi
        `core.world_backend._handle_member_leave`), invalida la propria
        sessione (`RemoteBackend.leave()` — `POST /leave`), poi applica la
        scelta fatta in `_show_leave_merge_dialog` per ciascuna istanza
        posseduta qui:
        - "merge": ricopia la progressione sull'originale locale
          (`character_instances.apply_refresh`, stessa funzione già dietro
          "Aggiorna il mio foglio") e poi cancella la copia del mondo
          (`character_repo.delete`) — nessun duplicato, nessun dato perso.
        - "discard": cancella la copia del mondo, l'originale locale resta
          esattamente com'era.
        - nessuna scelta registrata (istanza senza un'origine locale viva):
          `character_repo.detach_world_instance`, fallback storico,
          l'istanza diventa lei stessa il personaggio locale.
        Infine rimuove la replica locale di QUESTO mondo
        (`world_repo.delete_world`) così sparisce dalla lista mondi di
        questo dispositivo."""
        self.page.pop_dialog()
        result = self._send_command(world, perm.CMD_MEMBER_LEAVE, {})
        if not result.success:
            self._show_error(result.error)
            return
        backend = self._remote_backends.pop(world.id, None)
        if isinstance(backend, RemoteBackend):
            backend.leave()
        for c in pending:
            choice = choices.get(c.id)
            if choice == "merge":
                character_instances.apply_refresh(c.id)
                character_repo.delete(c.id)
            elif choice == "discard":
                character_repo.delete(c.id)
            else:
                character_repo.detach_world_instance(c.id)
        world_repo.delete_world(world.id)
        self._current_world = None
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass

    def _confirm_remove_transferred(self, world: World):
        """Rimuove dalla lista un mondo "trasferito via" (§11.9 — il
        personaggio di questo dispositivo è stato spostato su un altro).
        Solo locale, mai un comando di rete: `resolve_backend_for_world`
        ritorna sempre `None` per un mondo in questo stato
        (`world_sync.is_world_transferred_away`), non c'è alcun host da
        notificare — a differenza di `_do_leave` sopra, che invece invia
        `CMD_MEMBER_LEAVE` perché lì il mondo è ancora raggiungibile."""
        p = d.T()
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Rimuovi mondo", ft.Icons.DELETE_OUTLINE, tone="danger"),
            content=ft.Text(
                f'Rimuovere "{world.name}" dalla tua lista? Questa copia locale '
                f"(registro, note, mappe ricevute) andrà persa — il mondo stesso, "
                f"sull'host, non viene toccato.",
                color=p.text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Rimuovi", icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda e: self._do_remove_transferred(world),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        self.page.show_dialog(dlg)

    def _do_remove_transferred(self, world: World):
        self.page.pop_dialog()
        world_repo.delete_world(world.id)
        self._current_world = None
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass

    def _live_combat_section(self, world: World) -> ft.Control | None:
        """
        Combattimento in corso, in sola lettura (§6.5, passo 7C) — visibile
        a QUALSIASI membro, mai su `can_perform`: è il Master a decidere se
        mostrarlo, con l'interruttore "Visibile ai giocatori" in
        `MasterEncounterView`, non un permesso di ruolo qui. Sull'host
        legge lo stato dal vivo (`get_encounter_members_resolved`); su una
        replica legge lo specchio scritto da
        `apply_event_to_replica`/`_finalize_join`
        (`get_replica_encounter_members`) — stesso incontro, fonte diversa,
        stessa forma di dati (`master_repo.resolved_members_to_dicts`).

        Personaggi giocanti (`source == "character"`) mostrano i PF esatti;
        mostri/PNG (`"npc"`/`"adhoc"`) mostrano solo lo stato descrittivo di
        `wound_status_label()` — mai i PF esatti (§6.5, convenzione
        dell'app, non una regola del manuale).
        """
        encounter = master_repo.get_visible_encounter_for_world(world.id)
        if encounter is None:
            return None
        if world.is_local_host:
            members = master_repo.resolved_members_to_dicts(
                master_repo.get_encounter_members_resolved(encounter.id),
            )
        else:
            members = master_repo.get_replica_encounter_members(encounter.id)
        if not members:
            return None

        p = d.T()
        rows: list[ft.Control] = []
        for idx, m in enumerate(members):
            is_current_turn = idx == encounter.current_turn_index
            if m.get("source") == "character":
                hp_text = f"{m.get('hp_current', 0)}/{m.get('hp_max', 0)} PF"
            else:
                hp_text = wound_status_label(
                    int(m.get("hp_current", 0) or 0), int(m.get("hp_max", 0) or 0),
                )
            rows.append(ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_ARROW, size=16, color=p.primary_icon) if is_current_turn
                    else ft.Container(width=16),
                    ft.Text(m.get("name", "?"), size=d.Size.BODY,
                            weight=ft.FontWeight.BOLD if is_current_turn else ft.FontWeight.NORMAL,
                            color=p.text, expand=True),
                    d.muted(hp_text),
                ],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ))

        # Unico elemento "hero" del dettaglio mondo (`hero=True`, bordo
        # pieno invece della barretta sinistra normale) — quando un
        # combattimento è visibile è di fatto
        # il dato più urgente della schermata per qualunque membro, non
        # solo una sezione informativa come le altre. Il nome del mondo in
        # cima usa `hero_title()`, un momento tipografico diverso: le due
        # cose convivono perché sono registri visivi distinti (testo vs.
        # silhouette della card), non due "hero" nello stesso senso.
        return d.section(
            "Combattimento in corso",
            ft.Column(
                [
                    ft.Text(f"Round {encounter.round_number}", size=d.Size.BODY_SM, color=p.text_2),
                    ft.Container(height=d.Space.XS),
                    ft.Column(rows, spacing=6, tight=True),
                ],
                spacing=0, tight=True,
            ),
            accent=p.primary,
            hero=True,
        )

    def _shared_notes_section(self, world: World) -> ft.Control | None:
        """
        Note di campagna condivise dal Master (§6.2, passo 7) — sola
        lettura, visibile a QUALSIASI membro (non solo master/owner, a
        differenza di `_remote_actions_section` sotto): sono le note che il
        Master ha esplicitamente reso visibili a tutti o a questo
        dispositivo. Le note `private` non compaiono mai qui —
        `master_repo.get_notes_visible_to()` le esclude già. Nessuna azione
        di modifica: la scrittura resta nella Sezione Master
        (`master_notes_view.py`).
        """
        assert self.device_id is not None
        notes = master_repo.get_notes_visible_to(world.id, self.device_id)
        if not notes:
            return None
        p = d.T()
        rows: list[ft.Control] = []
        for note in notes:
            rows.append(ft.Column(
                [
                    ft.Text(note.name or "Senza nome", size=d.Size.BODY,
                            weight=ft.FontWeight.BOLD, color=p.text),
                    ft.Text(note.description, size=d.Size.BODY_SM, color=p.text_2)
                    if note.description else ft.Container(height=0),
                ],
                spacing=2, tight=True,
            ))
        # Righe separate da un piccolo spazio invece di un Divider — coerente
        # con lo stile già usato altrove in questa view per liste brevi.
        spaced_rows: list[ft.Control] = []
        for i, row in enumerate(rows):
            if i > 0:
                spaced_rows.append(ft.Container(height=d.Space.SM))
            spaced_rows.append(row)
        return d.section(
            "Note condivise dal Master",
            ft.Column(spaced_rows, spacing=0, tight=True),
        )

    # ------------------------------------------------------------------
    # Mappe condivise (§6.4, passo 8) — pubblicazione + disegno dal vivo.
    #
    # Pubblicare/disegnare è limitato a master/owner CHE OSPITA il mondo
    # (`world.is_local_host`), non a "chiunque abbia il permesso" come le
    # altre azioni master di questa view: una mappa condivisa è sempre una
    # riga `game_maps` posseduta da un personaggio LOCALE di chi la
    # pubblica (`maps_repo.get_maps(character.id)`, mai sincronizzata di
    # per sé). Se un co-master non-host inviasse `CMD_MAP_PUBLISH` via
    # `RemoteBackend`, l'handler girerebbe sul DB dell'HOST, dove quella
    # riga semplicemente non esiste — fallirebbe con "Mappa non trovata",
    # non un bug silenzioso, ma un vicolo cieco evitabile nascondendo
    # subito i controlli di pubblicazione/disegno a chi non può usarli.
    # Un co-master non-host vede comunque le mappe già condivise, in sola
    # lettura, come un giocatore qualunque.
    # ------------------------------------------------------------------

    def _shared_maps_section(self, world: World, my_role: str) -> ft.Control | None:
        """
        Il master (host) vede TUTTE le mappe condivise, visibili o
        nascoste ai giocatori — nascondere non è ritirare, la mappa resta
        nella sezione apposita anche se non selezionata per la
        visualizzazione. Un giocatore (o un master non-host,
        sola lettura) vede solo quelle con `visible_to_players=True` —
        filtro qui in UI, in aggiunta a quello server-side su
        `GET /map/<id>/image` (§6.4): due strati, coerente con come già
        funziona il resto di questa sezione.
        """
        can_manage = perm.can_perform(my_role, perm.CMD_MAP_PUBLISH) and world.is_local_host
        shared = maps_repo.get_shared_maps(world.id)
        if not can_manage:
            shared = [m for m in shared if m.visible_to_players]
        if not shared and not can_manage:
            return None
        p = d.T()
        rows: list[ft.Control] = []
        for i, gm in enumerate(shared):
            if i > 0:
                rows.append(ft.Divider(height=1))
            rows.append(self._shared_map_row(world, gm, can_manage))
        if not shared:
            rows.append(d.muted("Nessuna mappa condivisa ancora."))
        trailing = None
        if can_manage:
            trailing = d.pill(ft.Icons.ADD_PHOTO_ALTERNATE, "+ Mappa", color=p.primary,
                               on_click=lambda e: self._open_add_map_dialog(world))
        return d.section(
            "Mappe condivise",
            ft.Column(rows, spacing=d.Space.SM, tight=True),
            trailing=trailing,
        )

    def _shared_loot_section(self, world: World) -> ft.Control | None:
        """
        Deposito del gruppo (passo 6 di `dnd_app/docs/loot_design.md` §6) —
        visibile a QUALSIASI membro: il forziere comune del tavolo,
        popolato dal Master dalla tab «Bottino» della Sezione Master
        (`master_loot_view.py`, `stash_kind="party"`).

        **Auto-servizio (2026-08-20, decisione di design di Davide che
        sostituisce la sola-lettura originale di §6, "è il master a
        distribuire")**: un membro con un proprio personaggio ATTIVO in
        questo mondo (non archiviato) può premere «Prendi» per spostare
        una voce direttamente sulla propria scheda, via
        `CMD_LOOT_STASH_CLAIM` — un solo comando lato host che applica
        l'oggetto/le monete E rimuove la voce dal deposito in un colpo
        solo (vedi il docstring dell'handler in `core/world_backend.py`).
        Un membro senza personaggio in questo mondo (es. un master puro)
        vede comunque il deposito, ma senza pulsante — non c'è una scheda
        su cui far arrivare la voce. Il Master mantiene comunque le sue
        azioni di assegnazione/spostamento/eliminazione dalla tab
        «Bottino» della Sezione Master, invariate.
        """
        entries = loot_repo.get_entries("party", world_id=world.id)
        if not entries:
            return None
        assert self.device_id is not None
        my_instance = next(
            (c for c in character_repo.get_all_instances_of_world(world.id)
             if c.owner_device_id == self.device_id and not c.world_instance_archived),
            None,
        )
        p = d.T()
        rows: list[ft.Control] = []
        for entry in entries:
            is_coins = entry.entry_kind == "coins"
            is_magic = entry.entry_kind in _MAGIC_KINDS
            title = "Monete" if is_coins else entry.name
            subtitle = _coin_summary(entry) if is_coins else (
                (entry.description or "").split("\n")[0][:110]
            )
            qty_bit = f" ×{entry.quantity}" if (not is_coins and entry.quantity != 1) else ""
            icon_color = p.magic if is_magic else p.primary
            card_children: list[ft.Control] = [
                ft.Row(
                    [
                        ft.Icon(_KIND_ICONS.get(entry.entry_kind, ft.Icons.BACKPACK_OUTLINED),
                                size=16, color=icon_color),
                        ft.Container(width=8),
                        ft.Text(f"{title}{qty_bit}", size=13, weight=ft.FontWeight.BOLD,
                                color=p.text, expand=True, no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS),
                        d.chip(_KIND_LABELS.get(entry.entry_kind, entry.entry_kind),
                               "magic" if is_magic else "neutral"),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(subtitle, size=11, color=p.text_2) if subtitle else ft.Container(height=0),
                ft.Text(_mechanics_summary(entry), size=11, color=p.primary_icon,
                        weight=ft.FontWeight.W_600) if _mechanics_summary(entry) else ft.Container(height=0),
            ]
            if my_instance is not None:
                card_children.append(ft.Row(
                    [ft.OutlinedButton(
                        "Prendi", icon=ft.Icons.BACK_HAND_OUTLINED,
                        on_click=lambda e, en=entry, ch=my_instance: self._confirm_claim_loot(world, ch, en),
                    )],
                    spacing=6,
                ))
            rows.append(d.card(
                ft.Column(card_children, spacing=4),
                accent=p.magic if is_magic else None,
                density="dense",
            ))
        return d.section(
            "Deposito del Gruppo",
            ft.Column(rows, spacing=d.Space.SM, tight=True),
        )

    def _confirm_claim_loot(self, world: World, character: Character, entry: LootStashEntry) -> None:
        p = d.T()
        title = "le monete" if entry.entry_kind == "coins" else f"«{entry.name}»"
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Prendi dal deposito", ft.Icons.BACK_HAND_OUTLINED),
            content=ft.Text(
                f"Prendere {title}? Andrà subito sulla scheda di {character.name} "
                f"e sparirà dal deposito del gruppo per tutti.",
                color=p.text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Prendi", icon=ft.Icons.BACK_HAND_OUTLINED,
                    on_click=lambda e: self._do_claim_loot(world, character, entry),
                    style=ft.ButtonStyle(bgcolor=p.primary_fill, color=p.on_primary_fill),
                ),
            ]),
        )
        self.page.show_dialog(dlg)

    def _do_claim_loot(self, world: World, character: Character, entry: LootStashEntry) -> None:
        self.page.pop_dialog()
        result = self._send_command(
            world, perm.CMD_LOOT_STASH_CLAIM, {"entry_id": entry.id},
            target_type="character", target_id=character.id,
        )
        if not result.success:
            self._show_error(result.error)
            return
        # "Prendi" tocca solo il deposito condiviso (sparisce da lì) e la
        # scheda del personaggio (non mostrata qui): aggiornamento mirato
        # invece di `_refresh_detail()` completo.
        self._update_shared_loot_section(world)

    def _shared_map_row(self, world: World, gm: GameMap, can_manage: bool) -> ft.Control:
        p = d.T()
        if gm.image_data:
            thumb: ft.Control = ft.Container(
                content=ft.Image(src=_data_uri(gm.image_data), fit=ft.BoxFit.COVER),
                width=56, height=42, border_radius=d.Radius.SM,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )
        else:
            thumb = ft.Container(
                content=ft.Icon(ft.Icons.MAP_OUTLINED, size=20, color=p.text_3),
                width=56, height=42, border_radius=d.Radius.SM,
                bgcolor=p.surface_alt, alignment=ft.Alignment.CENTER,
            )
        n_strokes = len([s for s in json.loads(gm.annotations or "[]")
                         if s.get("type") == "stroke"])
        status_bits = [f"{n_strokes} tratti" if n_strokes else "Nessun tratto ancora"]
        if can_manage and not gm.visible_to_players:
            status_bits.append("nascosta ai giocatori")
        actions: list[ft.Control] = [
            ft.IconButton(ft.Icons.OPEN_IN_FULL, tooltip="Apri", icon_size=18,
                          icon_color=p.text_2,
                          on_click=lambda e, m=gm: self._open_shared_map(world, m, can_manage)),
        ]
        if can_manage:
            actions.append(ft.IconButton(
                ft.Icons.VISIBILITY_OFF if gm.visible_to_players else ft.Icons.VISIBILITY,
                tooltip=("Nascondi ai giocatori" if gm.visible_to_players
                         else "Mostra ai giocatori"),
                icon_size=18, icon_color=p.text_2,
                on_click=lambda e, m=gm: self._toggle_map_visibility(world, m),
            ))
            actions.append(ft.IconButton(
                ft.Icons.DELETE_OUTLINE, tooltip="Elimina", icon_size=18,
                icon_color=p.danger_icon,
                on_click=lambda e, m=gm: self._confirm_delete_map(world, m),
            ))
        return ft.Row(
            [
                thumb,
                ft.Column(
                    [
                        ft.Text(gm.name or "Mappa senza nome", size=d.Size.BODY,
                                weight=ft.FontWeight.BOLD, color=p.text),
                        d.muted(" · ".join(status_bits)),
                    ],
                    spacing=0, expand=True, tight=True,
                ),
                *actions,
            ],
            spacing=d.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _open_add_map_dialog(self, world: World):
        """
        Scelta tra le due sorgenti di una mappa condivisa: una già salvata
        sotto un personaggio locale (`_open_publish_map_dialog`, clona), o
        un'immagine nuova scelta al volo dal dispositivo
        (`_open_upload_map_dialog`).
        """
        page = self.page
        if page is None:
            return
        p = d.T()

        def _choose_existing(e=None):
            page.pop_dialog()
            self._open_publish_map_dialog(world)

        def _choose_upload(e=None):
            page.pop_dialog()
            self._open_upload_map_dialog(world)

        page.show_dialog(ft.AlertDialog(
            title=d.dialog_title("Aggiungi una mappa", ft.Icons.MAP),
            content=ft.Container(
                width=responsive_dialog_width(page, 360),
                content=ft.Column(
                    [
                        ft.OutlinedButton(
                            "Pubblica una mappa già salvata", icon=ft.Icons.MAP_OUTLINED,
                            on_click=_choose_existing,
                            style=ft.ButtonStyle(side=ft.BorderSide(1, p.border),
                                                 color=p.text_2),
                        ),
                        ft.OutlinedButton(
                            "Carica una mappa nuova", icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                            on_click=_choose_upload,
                            style=ft.ButtonStyle(side=ft.BorderSide(1, p.border),
                                                 color=p.text_2),
                        ),
                    ],
                    spacing=d.Space.SM, tight=True,
                ),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
            ]),
        ))

    def _open_publish_map_dialog(self, world: World):
        page = self.page
        if page is None:
            return
        candidates: list[tuple[Character, GameMap]] = []
        for c in character_repo.get_all():
            for gm in maps_repo.get_maps(c.id):
                if not gm.is_shared:
                    candidates.append((c, gm))

        def _do_publish(map_id: str):
            page.pop_dialog()
            result = self._send_command(
                world, perm.CMD_MAP_PUBLISH, {"map_id": map_id},
            )
            if result.success:
                self._refresh_detail()
            else:
                self._show_error(result.error)

        p = d.T()
        if not candidates:
            content: ft.Control = d.muted(
                "Nessuna mappa locale disponibile — creane una nella Sezione Mappe di "
                "un personaggio, poi torna qui per condividerla (oppure carica subito "
                "una mappa nuova).",
            )
        else:
            rows: list[ft.Control] = []
            for c, gm in candidates:
                rows.append(ft.Row(
                    [
                        d.icon_badge(ft.Icons.MAP_OUTLINED, tone="neutral", size=28),
                        ft.Column(
                            [
                                ft.Text(gm.name or "Mappa senza nome", color=p.text,
                                        weight=ft.FontWeight.BOLD, size=d.Size.BODY_SM),
                                d.muted(c.name),
                            ],
                            spacing=0, expand=True, tight=True,
                        ),
                        ft.TextButton("Pubblica",
                                      on_click=lambda e, mid=gm.id: _do_publish(mid)),
                    ],
                    spacing=d.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ))
            content = ft.Column(rows, spacing=d.Space.SM, tight=True, scroll=ft.ScrollMode.AUTO)

        page.show_dialog(ft.AlertDialog(
            title=d.dialog_title("Pubblica una mappa esistente", ft.Icons.MAP),
            content=ft.Container(content=content, width=responsive_dialog_width(page, 380)),
            actions=wrap_dialog_actions([
                ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
            ]),
        ))

    def _open_upload_map_dialog(self, world: World):
        """Carica un'immagine nuova direttamente nel mondo (`CMD_MAP_UPLOAD`)
        — stessi tre rami di selezione immagine già usati
        da `ui/views/maps_view.py` (web/mobile/desktop), riusati da qui
        (`_pick_from_library`/`_pick_mobile` prendono ora una `Page`
        direttamente, non più un `MapsView` — vedi il loro docstring)."""
        page = self.page
        if page is None:
            return
        p = d.T()

        name_tf = ft.TextField(label="Nome mappa", **d.field_style())
        img_data: list[str] = [""]
        img_label = ft.Text("Nessuna immagine", size=11, color=p.text_3)
        img_preview = ft.Container(
            content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=40, color=p.border),
            width=100, height=70, bgcolor=p.surface_alt,
            border_radius=d.Radius.MD, alignment=ft.Alignment.CENTER,
        )
        visible_state = [True]
        visible_switch = ft.Switch(
            value=True, active_color=p.primary_fill,
            on_change=lambda e: visible_state.__setitem__(0, bool(e.control.value)),
        )
        error_text = ft.Text("", size=11, color=p.danger)

        def pick_image(ev):
            if page.web:
                _pick_from_library(page, img_data, img_label, img_preview)
            elif page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
                page.run_task(_pick_mobile, page, img_data, img_label, img_preview)
            else:
                import platform as _sys
                threading.Thread(
                    target=_pick_desktop,
                    args=(_sys.system(), img_data, img_label, img_preview, page),
                    daemon=True,
                ).start()

        def on_upload(ev):
            name = (name_tf.value or "").strip()
            if not name:
                error_text.value = "Il nome è obbligatorio"
                error_text.update()
                return
            if not img_data[0]:
                error_text.value = "Scegli un'immagine"
                error_text.update()
                return
            page.pop_dialog()
            result = self._send_command(world, perm.CMD_MAP_UPLOAD, {
                "name": name, "image_data": img_data[0],
                "visible_to_players": visible_state[0],
            })
            if result.success:
                self._refresh_detail()
            else:
                self._show_error(result.error)

        page.show_dialog(ft.AlertDialog(
            title=d.dialog_title("Carica una mappa nuova", ft.Icons.ADD_PHOTO_ALTERNATE),
            content=ft.Container(
                width=responsive_dialog_width(page, 380),
                content=ft.Column(
                    [
                        name_tf,
                        ft.Row(
                            [
                                img_preview,
                                ft.Column([
                                    ft.OutlinedButton(
                                        "Scegli immagine…", icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                                        on_click=pick_image,
                                        style=ft.ButtonStyle(side=ft.BorderSide(1, p.border),
                                                             color=p.text_2),
                                    ),
                                    img_label,
                                ], spacing=6),
                            ],
                            spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [visible_switch, ft.Text("Visibile subito ai giocatori",
                                                      color=p.text, size=d.Size.BODY_SM)],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        error_text,
                    ],
                    spacing=10, tight=True,
                ),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Carica", on_click=on_upload,
                                  style=ft.ButtonStyle(bgcolor=p.primary_fill, color=p.on_primary_fill)),
            ]),
        ))

    def _toggle_map_visibility(self, world: World, gm: GameMap):
        result = self._send_command(world, perm.CMD_MAP_VISIBILITY, {
            "map_id": gm.id, "visible_to_players": not gm.visible_to_players,
        })
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

    def _confirm_delete_map(self, world: World, gm: GameMap):
        page = self.page
        if page is None:
            return
        p = d.T()
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Elimina mappa", ft.Icons.DELETE_OUTLINE, tone="danger"),
            content=ft.Text(
                f'Eliminare "{gm.name or "Mappa senza nome"}" dalla condivisione? '
                "Sparirà anche dal tuo elenco — l'eventuale mappa personale di origine "
                "non viene toccata.", color=p.text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda e: self._do_delete_map(world, gm),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _do_delete_map(self, world: World, gm: GameMap):
        page = self.page
        if page is not None:
            page.pop_dialog()
        result = self._send_command(world, perm.CMD_MAP_DELETE, {"map_id": gm.id})
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

    def _open_shared_map(self, world: World, gm: GameMap, can_manage: bool):
        """
        Overlay (`page.overlay`, stesso idioma di
        `ui.views.maps_view.MapsView._open_fullscreen`) invece di una
        sezione dentro `self._body`: `_render_detail` ricostruisce
        `self._body.controls` da zero ad ogni giro del ciclo di
        sincronizzazione in background (`_DETAIL_SYNC_INTERVAL_S`, 2s) — un
        canvas di disegno dentro quel corpo verrebbe rimontato a metà
        tratto. Un overlay separato sopravvive a quei refresh, esattamente
        come già fa lo schermo intero delle mappe locali.
        """
        page = self.page
        if page is None:
            return

        # Prima apertura su una replica: l'immagine non arriva mai via
        # evento/snapshot (§6.4) — un fetch pigro una tantum, poi in cache
        # locale come qualunque altra mappa.
        if not gm.image_data and not world.is_local_host:
            backend = self._backend_for(world)
            if isinstance(backend, RemoteBackend):
                raw = backend.fetch_map_image(gm.id)
                if raw:
                    gm.image_data = base64.b64encode(raw).decode("ascii")
                    maps_repo.update_map(gm.id, image_data=gm.image_data)

        closed = [False]

        def _sync_to_world(batch: list[dict]) -> None:
            """Invia il pacchetto SOLO come evento — mai una scorciatoia
            di scrittura diretta (§9.1, la stessa lezione già imparata più
            volte in questo progetto): `can_manage` implica
            `world.is_local_host`, quindi qui `self.backend` è sempre
            `LocalBackend` e la chiamata è comunque locale/sincrona, non
            una vera richiesta di rete."""
            result = self._send_command(
                world, perm.CMD_MAP_DRAW, {"map_id": gm.id, "strokes": batch},
            )
            if not result.success:
                logger.warning("map.draw non riuscito per %s: %s", gm.id, result.error)

        canvas = MapDrawingCanvas(
            gm, on_batch=_sync_to_world if can_manage else None, can_manage=can_manage,
            page=page,
        )
        draw_area = canvas.build_draw_area(is_fs=True)
        toolbar_row: ft.Control | None = None
        toolbar_body: ft.Container | None = None
        if can_manage:
            toolbar_row, toolbar_body = canvas.build_toolbar(is_fs=True)

        overlay_list: list[ft.Control] = []

        def _close(e=None):
            closed[0] = True
            if overlay_list and overlay_list[0] in page.overlay:
                page.overlay.remove(overlay_list[0])
            canvas.teardown_fullscreen()
            try:
                page.update()
            except RuntimeError:
                pass

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Text(gm.name or "Mappa", size=16, color=d.CHROME.text,
                            weight=ft.FontWeight.BOLD, expand=True,
                            no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    d.chip("disegna" if can_manage else "sola lettura",
                           "primary" if can_manage else "neutral"),
                    ft.IconButton(ft.Icons.CLOSE, icon_color=d.CHROME.text, on_click=_close),
                ],
                spacing=d.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=d.CHROME.backdrop,
        )

        legacy_banner = canvas.build_legacy_banner()
        body: list[ft.Control] = [header]
        if legacy_banner is not None:
            body.append(legacy_banner)
        body.append(
            ft.Container(expand=True, content=draw_area,
                         on_size_change=lambda e: canvas.on_box_resize(True, e)),
        )
        if can_manage and toolbar_row is not None and toolbar_body is not None:
            body.append(ft.Container(
                content=ft.Column([toolbar_row, toolbar_body], spacing=0),
                bgcolor=d.CHROME.bg,
                border_radius=ft.BorderRadius.only(
                    top_left=d.Radius.LG, top_right=d.Radius.LG),
                shadow=ft.BoxShadow(blur_radius=18, spread_radius=0,
                                    offset=ft.Offset(0, -4),
                                    color=ft.Colors.with_opacity(0.45, d.CHROME.canvas)),
            ))

        overlay = ft.Container(
            expand=True, bgcolor=d.CHROME.canvas,
            content=ft.Column(body, spacing=0, expand=True),
        )
        overlay_list.append(overlay)
        page.overlay.append(overlay)
        page.update()

        if not can_manage:
            # Sola lettura: nessun evento in arrivo aggiorna questo overlay
            # da solo (non fa parte di `self._body`, quindi il refresh
            # periodico di `_render_detail` non lo tocca) — un piccolo
            # ciclo dedicato, stesso principio di `_poll_pending_join_loop`
            # più sotto in questo file: si ferma da solo alla chiusura.
            async def _watch_loop():
                import asyncio
                while not closed[0]:
                    await asyncio.sleep(_SHARED_MAP_REDRAW_INTERVAL_S)
                    if closed[0]:
                        return
                    fresh = maps_repo.get_map(gm.id)
                    if fresh is None:
                        continue
                    try:
                        fresh_strokes = json.loads(fresh.annotations or "[]")
                    except (json.JSONDecodeError, TypeError):
                        fresh_strokes = []
                    canvas.refresh_strokes(fresh_strokes)

            page.run_task(_watch_loop)

    def _events_section(self, world: World) -> ft.Control:
        events = world_repo.get_events_since(world.id, 0, limit=200)
        events = list(reversed(events))  # più recenti in cima
        if not events:
            rows: list[ft.Control] = [d.muted("Nessun evento ancora.")]
        else:
            rows = [self._event_row(ev) for ev in events[:50]]
        return d.section(
            "Registro",
            ft.Column(rows, spacing=d.Space.XS, tight=True),
            density="dense",
        )

    def _event_row(self, event: WorldEvent) -> ft.Control:
        p = d.T()
        return ft.Row(
            [
                ft.Icon(ft.Icons.HISTORY, size=14, color=p.text_3),
                ft.Text(event.summary or event.kind, color=p.text_2, size=d.Size.BODY_SM,
                        expand=True),
                d.muted(event.created_at[:19].replace("T", " ")),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    # ------------------------------------------------------------------
    # Interviene a distanza (passo 6, §7 del design doc) — master/owner.
    #
    # Sostituisce la vecchia scrittura diretta `character_repo.add_xp()`
    # (Fase 4, "prima e unica scrittura del master su un personaggio
    # giocante") con la pipeline comando → validazione → evento: risolve
    # "il problema di partenza" (§1 di multiplayer_design.md) — il master
    # non aveva alcun modo di intervenire su una scheda che vive su un
    # ALTRO dispositivo. Ogni azione qui passa da `self.backend.
    # send_command()`, mai da una scrittura diretta sul personaggio: è
    # l'unico modo per cui l'evento finisce nel Registro E raggiunge la
    # replica del giocatore via `core.world_sync` quando è connesso in LAN.
    # ------------------------------------------------------------------

    def _remote_actions_section(self, world: World) -> ft.Control:
        characters = character_repo.get_master_visible_characters(world.id)
        if not characters:
            return d.section(
                "Interviene a distanza",
                d.muted(
                    "Nessun personaggio in questo mondo — compariranno qui dopo che "
                    "un giocatore avrà aggiunto la propria scheda dalla Home.",
                ),
            )
        rows: list[ft.Control] = []
        for i, character in enumerate(characters):
            if i > 0:
                rows.append(ft.Divider(height=1))
            rows.append(self._remote_character_row(world, character))
        return d.section(
            "Interviene a distanza",
            ft.Column(rows, spacing=d.Space.SM, tight=True),
            density="dense",
        )

    def _remote_character_row(self, world: World, character: Character) -> ft.Control:
        p = d.T()

        # Countdown visivo: se QUESTO personaggio è in
        # cooldown, tutte le sue azioni (pillole + la "x" di rimozione
        # condizione qui sotto) diventano disabilitate (nessun on_click,
        # colore smorzato) e mostrano i secondi rimanenti invece
        # dell'etichetta normale — al posto del solo messaggio d'errore
        # reattivo al click. Il tick che tiene aggiornato il countdown è
        # `_start_detail_sync`/`_any_master_cooldown_active` (thread di
        # sync già esistente, nessun timer nuovo).
        cooldown_remaining = world_sync.master_action_cooldown_remaining(character.id)
        on_cooldown = cooldown_remaining > 0
        cooldown_suffix = f" ({int(cooldown_remaining) + 1}s)" if on_cooldown else ""
        muted_color = p.text_3

        conditions = character_repo.get_conditions(character.id)
        loader = GameDataLoader()
        condition_chips: list[ft.Control] = []
        for cond in conditions:
            cond_data = loader.get_condition(cond.condition_key) or {}
            cond_name = cond_data.get("name", cond.condition_key)
            condition_chips.append(ft.Container(
                content=ft.Row(
                    [
                        ft.Text(cond_name, size=11, color=p.on_accent),
                        ft.IconButton(
                            ft.Icons.CLOSE, icon_size=12, icon_color=p.on_accent,
                            tooltip=(f"Aspetta {int(cooldown_remaining) + 1}s" if on_cooldown
                                     else "Rimuovi condizione"),
                            disabled=on_cooldown,
                            on_click=(None if on_cooldown else
                                      lambda e, w=world, c=character, cid=cond.id:
                                          self._send_remote_command(
                                              w, c, perm.CMD_CONDITION_REMOVE,
                                              {"condition_id": cid})),
                        ),
                    ],
                    spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=p.danger_fill, border_radius=d.Radius.SM,
                padding=ft.Padding.only(left=8, right=2),
            ))

        def _pill(icon: ft.IconData, label: str, color: str, handler) -> ft.Control:
            if on_cooldown:
                return d.pill(icon, label + cooldown_suffix, color=muted_color, on_click=None)
            return d.pill(icon, label, color=color, on_click=handler)

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(character.name, weight=ft.FontWeight.BOLD, color=p.text,
                                expand=True),
                        d.muted(f"PF {character.hp_current}/{character.hp_max} · "
                                f"{character.xp:,} PE".replace(",", ".")),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(condition_chips, spacing=d.Space.XS, wrap=True) if condition_chips
                else ft.Container(height=0),
                ft.Row(
                    [
                        _pill(ft.Icons.STARS, "PE", p.success,
                              lambda e, w=world, c=character: self._open_xp_dialog(w, c)),
                        _pill(ft.Icons.FAVORITE_BORDER, "Danno", p.danger,
                              lambda e, w=world, c=character: self._open_damage_dialog(w, c)),
                        _pill(ft.Icons.HEALING, "Cura", p.primary,
                              lambda e, w=world, c=character: self._open_heal_dialog(w, c)),
                        _pill(ft.Icons.SICK, "Condizione", p.magic,
                              lambda e, w=world, c=character: self._open_condition_dialog(w, c)),
                        _pill(ft.Icons.AUTO_AWESOME, "Abilità", p.magic,
                              lambda e, w=world, c=character: self._open_custom_ability_dialog(w, c)),
                        _pill(ft.Icons.MENU_BOOK, "Incantesimo", p.magic,
                              lambda e, w=world, c=character: self._open_bonus_spell_dialog(w, c)),
                        _pill(ft.Icons.EDIT_NOTE, "Diario", p.text_2,
                              lambda e, w=world, c=character: self._open_diary_entry_dialog(w, c)),
                        _pill(ft.Icons.GAVEL, "Proponi modifica", p.warning,
                              lambda e, w=world, c=character: self._open_change_request_dialog(w, c)),
                        _pill(ft.Icons.PERSON_REMOVE, "Rimuovi dal mondo", p.danger,
                              lambda e, w=world, c=character: self._confirm_remove_character(w, c)),
                    ],
                    spacing=d.Space.XS, wrap=True,
                ),
            ],
            spacing=d.Space.XS, tight=True,
        )

    def _confirm_remove_character(self, world: World, character: Character):
        """
        Rimuove UN personaggio dal mondo — DISTINTA da "Espelli membro"
        nella sezione Membri, che rimuove l'intero dispositivo e archivia
        TUTTE le sue istanze. Qui il giocatore resta membro, solo questo
        personaggio sparisce dalla Sezione Master. Stessa non-distruttività
        dell'espulsione: archiviato, non cancellato — il giocatore può poi
        chiedere il rientro (§"Richiesta di rientro"), che tu dovrai
        approvare tu qui in "Richieste di rientro": non torna mai visibile
        in automatico.
        """
        page = self.page
        if page is None:
            return
        p = d.T()
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Rimuovi personaggio dal mondo", ft.Icons.PERSON_REMOVE,
                                 tone="danger"),
            content=ft.Text(
                f'Rimuovere "{character.name}" da questo mondo? Il giocatore resta membro — '
                "sparisce solo questo personaggio dalla Sezione Master. I suoi dati non "
                "vengono persi, si riattiva da solo se il giocatore lo risincronizza.",
                color=p.text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Rimuovi", icon=ft.Icons.PERSON_REMOVE,
                    on_click=lambda e: self._do_remove_character(world, character),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _do_remove_character(self, world: World, character: Character):
        page = self.page
        if page is not None:
            page.pop_dialog()
        # `_send_remote_command`, non `_send_command` diretto: è il punto
        # unico di invio di OGNI azione di questa riga (vedi il suo
        # docstring) — applica lo stesso timer anti-spam per personaggio
        # delle altre pillole, e imposta target_type/target_id.
        self._send_remote_command(world, character, perm.CMD_CHARACTER_INSTANCE_REMOVE, {})

    # ------------------------------------------------------------------
    # Anti-spam sulle richieste di rete "semplici", stesso principio del
    # timer sul master ma per tutte le richieste online da sincronizzare.
    # Copre `_open_join_dialog._join`,
    # `_open_lan_join_dialog._attempt`/`_retry` qui sotto, e
    # `HomeView._push_instance_to_host` (stesso valore di cooldown,
    # `core.world_permissions.NETWORK_REQUEST_COOLDOWN_S`, ma stato
    # indipendente — vedi il docstring di `core.world_sync` per l'elenco
    # completo e cosa NE resta fuori).
    # Due metodi separati (non uno solo che controlla-e-mostra-l'errore)
    # perché i chiamanti mostrano l'esito in due modi diversi già esistenti
    # in questa view: `_join` con `_show_error` (snackbar), `_attempt`/
    # `_retry` con `status_text` inline (stesso stile già in uso per i loro
    # altri errori di validazione) — replicare quella scelta, non
    # introdurne una terza.
    # ------------------------------------------------------------------

    def _network_cooldown_remaining(self) -> float:
        return world_sync.network_request_cooldown_remaining()

    def _mark_network_request(self) -> None:
        # Registrato SUBITO, prima di conoscere l'esito — stesso principio
        # del timer del master: anche un tentativo fallito ha già generato
        # traffico di rete, non è aggirabile martellando durante un errore.
        world_sync.mark_network_request()

    def _start_network_cooldown_ticker(self, btn: ft.Control, base_label: str) -> None:
        """
        Countdown visivo sul pulsante `btn` di un
        dialogo di ingresso: mentre il timer di rete è attivo, il pulsante
        resta disabilitato mostrando i secondi rimanenti nell'etichetta,
        invece del solo messaggio reattivo al click. Da richiamare
        all'apertura del dialogo (se il timer è già attivo da un tentativo
        precedente) e subito dopo ogni `_mark_network_request()` riuscito.

        Ciclo `async` schedulato con `page.run_task()` (stesso meccanismo
        già in uso per `_init_identity`/`_async_redraw_detail` in questo
        file) — MAI un `threading.Thread`: qui si gira già dentro il loop
        asyncio della sessione, `page.update()` è sempre sicuro senza
        bisogno di un ponte verso un altro thread.

        Si ferma da solo quando il cooldown scende a zero (scrive lo stato
        "riabilitato" una volta e ritorna) o quando `page.update()` fallisce
        (il dialogo è stato chiuso, il controllo non è più agganciato alla
        pagina) — **non** tenta di rilevare "il dialogo è ancora aperto"
        leggendo `dlg.open`: `dnd_app/docs/regole_flet_api.md` documenta
        che in questa versione di Flet i dialoghi si gestiscono con
        `page.show_dialog()`/`page.pop_dialog()`, non più con
        `dlg.open = True/False` — quel flag non è garantito riflettere lo
        stato reale. Nessun rischio di ciclo infinito comunque: la durata
        massima è già limitata da `NETWORK_REQUEST_COOLDOWN_S` (~10
        iterazioni da 1s), un residuo di ciclo dopo la chiusura del
        dialogo si esaurisce da solo entro quella finestra.
        """
        page = self.page
        if page is None:
            return
        page.run_task(self._network_cooldown_ticker_loop, btn, base_label)

    async def _network_cooldown_ticker_loop(self, btn: ft.Control, base_label: str) -> None:
        import asyncio

        while True:
            remaining = self._network_cooldown_remaining()
            if remaining <= 0:
                btn.disabled = False
                btn.text = base_label
                try:
                    self.page.update()
                except RuntimeError:
                    pass
                return
            btn.disabled = True
            btn.text = f"{base_label} ({int(remaining) + 1}s)"
            try:
                self.page.update()
            except RuntimeError:
                return  # dialogo chiuso — il ciclo termina qui, nessun altro giro
            await asyncio.sleep(1.0)

    def _send_remote_command(self, world: World, character: Character, kind: str,
                              payload: dict) -> None:
        """Punto unico di invio per OGNI azione di "Interviene a distanza"
        (PE/danno/cura/condizione/abilità/incantesimo/diario/proponi
        modifica — vedi `_remote_character_row`) — qui, e solo qui, si
        applica il timer anti-spam del master, PER PERSONAGGIO: un solo
        timer per l'intera sezione costringerebbe il master ad aspettare
        3s tra un personaggio e l'altro anche con un'area su 4 PG — a
        granularità per-personaggio il limite blocca solo il martellare
        ripetuto sullo STESSO personaggio."""
        remaining = world_sync.master_action_cooldown_remaining(character.id)
        if remaining > 0:
            self._show_error(
                f"Aspetta {int(remaining) + 1} secondi prima della prossima azione su "
                f"{character.name}."
            )
            return
        # L'istante si registra SUBITO, prima ancora di conoscere l'esito:
        # anche un tentativo fallito (es. host momentaneamente irraggiungibile)
        # ha già generato traffico di rete verso l'host — non deve essere
        # possibile aggirare il limite martellando durante un errore.
        world_sync.mark_master_action(character.id)
        self._start_master_cooldown_ticker(world)

        result = self._send_command(
            world, kind, payload, target_type="character", target_id=character.id,
        )
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

    def _start_master_cooldown_ticker(self, world: World) -> None:
        """
        Countdown affidabile dei pulsanti "Interviene a distanza": non basta
        affidarsi al poll di `_should_redraw_anyway`/`_any_master_cooldown_
        active`, che dipende dal ciclo a `_DETAIL_SYNC_INTERVAL_S=2.0` di
        `_start_detail_sync` — con un cooldown di 3.0s il tick di sblocco
        può cadere in un istante non osservato da un poll così largo, e si
        rischia di perderlo comunque su ritardi del thread. Stesso
        principio, PIÙ affidabile, di `_network_cooldown_ticker_loop` qui
        sopra: un `async` dedicato schedulato con `page.run_task()`
        (nessun `threading.Thread`: gira già nel loop asyncio della
        sessione), a 1s invece di 2s, che si ferma da solo non appena
        nessun personaggio del mondo è più in cooldown.

        `_master_cooldown_ticker_running` evita tanti cicli sovrapposti se
        il master invia più azioni ravvicinate su personaggi diversi —
        innocuo comunque (ogni ciclo si fermerebbe da solo), solo spreco
        evitabile.
        """
        if self._master_cooldown_ticker_running:
            return
        try:
            page = self.page
        except RuntimeError:
            return  # controllo non ancora agganciato alla pagina (es. test)
        if page is None or not hasattr(page, "run_task"):
            return
        self._master_cooldown_ticker_running = True
        page.run_task(self._master_cooldown_ticker_loop, world.id)

    async def _master_cooldown_ticker_loop(self, world_id: str) -> None:
        import asyncio

        try:
            while True:
                world = world_repo.get_world(world_id)
                if (world is None or self._current_world is None
                        or self._current_world.id != world_id
                        or not self._any_master_cooldown_active(world)):
                    if world is not None and self._current_world is not None \
                            and self._current_world.id == world_id:
                        self._render()
                        try:
                            self.page.update()
                        except RuntimeError:
                            pass
                        self._body.restore_scroll()
                    return
                self._render()
                try:
                    self.page.update()
                except RuntimeError:
                    return  # scheda mondo chiusa — nessun altro giro
                self._body.restore_scroll()
                await asyncio.sleep(1.0)
        finally:
            self._master_cooldown_ticker_running = False

    def _open_xp_dialog(self, world: World, character: Character):
        p = d.T()
        amount_field = ft.TextField(
            label="PE (negativo per togliere)", dense=True, value="0",
            keyboard_type=ft.KeyboardType.NUMBER, **d.field_style(),
        )

        def _confirm(e):
            try:
                amount = int((amount_field.value or "0").strip())
            except ValueError:
                self._show_error("Il valore deve essere un numero intero.")
                return
            if amount == 0:
                self._show_error("La quantità di PE non può essere zero.")
                return
            self.page.pop_dialog()
            self._send_remote_command(world, character, perm.CMD_XP_GRANT, {"amount": amount})

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Assegna PE — {character.name}", ft.Icons.STARS),
            content=ft.Column([amount_field], tight=True),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Conferma", icon=ft.Icons.CHECK, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.success, color=p.on_accent)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _open_damage_dialog(self, world: World, character: Character):
        """Il dialog stesso vive in
        `ui.components.remote_action_dialogs` (condiviso con
        `MasterEncounterView`, che invia la stessa azione dal tracker di
        combattimento) — qui resta solo "cosa fare col payload validato"."""
        from ui.components.remote_action_dialogs import show_damage_dialog
        show_damage_dialog(
            self.page, character.name,
            lambda payload: self._send_remote_command(world, character, perm.CMD_HP_DAMAGE, payload),
        )

    def _open_heal_dialog(self, world: World, character: Character):
        from ui.components.remote_action_dialogs import show_heal_dialog
        show_heal_dialog(
            self.page, character.name,
            lambda payload: self._send_remote_command(world, character, perm.CMD_HP_HEAL, payload),
        )

    def _open_condition_dialog(self, world: World, character: Character):
        from ui.components.remote_action_dialogs import show_condition_dialog
        show_condition_dialog(
            self.page, character.name,
            lambda payload: self._send_remote_command(world, character, perm.CMD_CONDITION_APPLY, payload),
        )

    def _open_custom_ability_dialog(self, world: World, character: Character):
        """Concede un'abilità speciale personalizzata (§7) — `custom_abilities`,
        puramente additiva, mai in sostituzione di una feature PHB."""
        p = d.T()
        category_dd = ft.Dropdown(
            label="Categoria",
            options=[
                ft.DropdownOption(key="esplorazione", text="Esplorazione"),
                ft.DropdownOption(key="combattimento", text="Combattimento"),
            ],
            value="esplorazione", dense=True, **d.field_style(),
        )
        name_field = ft.TextField(label="Nome dell'abilità", dense=True, **d.field_style())
        description_field = ft.TextField(
            label="Descrizione", dense=True, multiline=True, min_lines=2, max_lines=6,
            **d.field_style(),
        )

        def _confirm(e):
            name = (name_field.value or "").strip()
            if not name:
                self._show_error("Il nome dell'abilità è obbligatorio.")
                return
            self.page.pop_dialog()
            self._send_remote_command(
                world, character, perm.CMD_CUSTOM_ABILITY_GRANT,
                {"category": category_dd.value, "name": name,
                 "description": (description_field.value or "").strip()},
            )

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Concedi abilità speciale — {character.name}",
                                  ft.Icons.AUTO_AWESOME, tone="magic"),
            content=ft.Column([category_dd, name_field, description_field], tight=True,
                               spacing=d.Space.SM),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Concedi", icon=ft.Icons.CHECK, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_accent)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _open_bonus_spell_dialog(self, world: World, character: Character):
        """
        Concede un incantesimo bonus (§7, `known_spells.is_bonus`) — stesso
        picker a due livelli (classe -> CardPicker sugli incantesimi reali
        del JSON) già usato in `spells_view.py._open_add_bonus_spell_dialog`
        per il caso locale: mai un campo di testo libero, il nome
        dell'incantesimo deve sempre venire dai dati PHB già caricati.
        """
        page = self.page
        loader = GameDataLoader()
        class_names = loader.get_spellcasting_class_names()
        if not class_names:
            self._show_error("Nessuna lista di incantesimi disponibile.")
            return
        default_class = character.class_name if character.class_name in class_names else class_names[0]

        # Nomi già posseduti (incantesimi normali, bonus già concessi in
        # passato, o aggiunti manualmente dal giocatore) — vedi
        # `spell_card_options(known_names=...)`. Calcolato fresco
        # all'apertura del dialog: sufficiente, il dialog è a vita breve.
        known_names = {s.name for s in character_repo.get_known_spells(character.id)}

        class_dd = ft.Dropdown(
            label="Lista incantesimi", value=default_class,
            options=[ft.DropdownOption(key=n, text=n) for n in class_names],
            dense=True, **d.field_style(),
        )
        error_text = ft.Text("", size=12, color=d.T().danger)

        def _spells_for(cls: str) -> list[dict]:
            return sorted(loader.get_spells(cls), key=lambda s: (s.get("level", 0), s.get("name", "")))

        spell_picker = CardPicker(
            options=spell_card_options(_spells_for(default_class), known_names=known_names)
        )

        def _refresh_spell_options(ev=None):
            opts = _spells_for(class_dd.value or default_class)
            spell_picker.options = spell_card_options(opts, known_names=known_names)
            spell_picker.value = opts[0]["name"] if opts else None
            spell_picker.update()

        class_dd.on_select = _refresh_spell_options
        _refresh_spell_options()

        def _confirm(e):
            cls = class_dd.value or default_class
            name = spell_picker.value
            if not name:
                error_text.value = "Scegli un incantesimo."
                error_text.update()
                return
            spell = next((s for s in loader.get_spells(cls) if s.get("name") == name), None)
            if spell is None:
                error_text.value = "Incantesimo non trovato."
                error_text.update()
                return
            comps = spell.get("components", [])
            comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
            if spell.get("material"):
                comp_str += f" ({spell['material']})"
            self.page.pop_dialog()
            self._send_remote_command(
                world, character, perm.CMD_BONUS_SPELL_GRANT,
                {
                    "name": spell.get("name", name), "level": spell.get("level", 0),
                    "school": spell.get("school", ""), "casting_time": spell.get("casting_time", ""),
                    "spell_range": spell.get("range", ""), "components": comp_str,
                    "duration": spell.get("duration", ""), "description": spell.get("description", ""),
                    "higher_levels": spell.get("higher_levels", "") or "", "class_list": cls,
                },
            )

        p = d.T()
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Concedi incantesimo bonus — {character.name}",
                                  ft.Icons.MENU_BOOK, tone="magic"),
            content=ft.Container(
                content=ft.Column(
                    [class_dd, spell_picker.control, error_text],
                    spacing=10, scroll=ft.ScrollMode.AUTO,
                ),
                width=responsive_dialog_width(page, 340),
                height=460,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Concedi", icon=ft.Icons.CHECK, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_accent)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _open_diary_entry_dialog(self, world: World, character: Character):
        """
        Scrive una voce sul diario del personaggio (§6.2/§7: "scrive, non
        guarda") — asimmetria garantita dall'handler stesso
        (`_handle_diary_add_entry` non espone alcun comando di lettura),
        qui rispecchiata semplicemente non offrendo alcuna vista sulle voci
        esistenti.
        """
        p = d.T()
        title_field = ft.TextField(label="Titolo", dense=True, **d.field_style())
        date_field = ft.TextField(
            label="Data / Sessione  (es. «Sessione 3», «15 Olarune 998»)",
            dense=True, **d.field_style(),
        )
        content_field = ft.TextField(
            label="Contenuto", dense=True, multiline=True, min_lines=4, max_lines=10,
            **d.field_style(),
        )

        def _confirm(e):
            title = (title_field.value or "").strip()
            content = (content_field.value or "").strip()
            if not title or not content:
                self._show_error("Titolo e contenuto sono obbligatori.")
                return
            self.page.pop_dialog()
            self._send_remote_command(
                world, character, perm.CMD_DIARY_ADD_ENTRY,
                {"title": title, "content": content,
                 "session_date": (date_field.value or "").strip()},
            )

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Scrivi sul diario — {character.name}", ft.Icons.EDIT_NOTE),
            content=ft.Column([title_field, date_field, content_field], tight=True,
                               spacing=d.Space.SM, scroll=ft.ScrollMode.AUTO, height=320),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Scrivi", icon=ft.Icons.CHECK, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.primary_fill, color=p.on_primary_fill)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _change_request_field_choices(self, character: Character, field: str) -> list[str]:
        """
        Opzioni PHB reali per un campo "scelta di classe" della richiesta di
        modifica — stessa fonte dati di `profilo_tab.py._open_class_choices_edit`
        (mai un valore inventato, sempre letto dai JSON di classe).
        """
        loader = GameDataLoader()
        if field == "fighting_style":
            return loader.get_fighting_styles(character.class_name)
        if field == "totem_animal":
            return loader.get_totem_animals()
        if field == "land_terrain":
            return loader.get_land_terrains()
        if field == "pact_boon":
            return loader.get_pact_boons()
        if field == "dragon_ancestry":
            return list(DRACONIDE_ANCESTRIES)
        return []

    def _open_change_request_dialog(self, world: World, character: Character):
        """
        §7.1 — l'unico modo per toccare i campi vietati a chiunque tranne il
        giocatore (punteggi, livello, scelte di classe): propone soltanto,
        non applica nulla. Il giocatore proprietario accetta o rifiuta da
        `_pending_change_requests_section`. Una scelta di classe (stile di
        combattimento, totem, ecc.) compare solo se il personaggio la ha
        già — stessa regola di eleggibilità di "Modifica Scelte di Classe"
        in profilo_tab.py: non si propone di cambiare qualcosa che il
        personaggio non ha mai scelto.
        """
        p = d.T()
        page = self.page
        field_controls: dict[str, tuple[ft.Checkbox, ft.Control]] = {}
        rows: list[ft.Control] = []

        # Ordine esplicito, non quello (non deterministico tra un avvio e
        # l'altro, per via dell'hash randomization delle stringhe in Python)
        # dell'iterazione diretta su un frozenset: `_CHANGE_REQUEST_FIELD_LABELS`
        # è un dict, che mantiene l'ordine di inserimento già scelto sopra.
        for field in _CHANGE_REQUEST_FIELD_LABELS:
            assert field in perm.CHANGE_REQUEST_ALLOWED_FIELDS, (
                f"campo {field!r} non presente in CHANGE_REQUEST_ALLOWED_FIELDS")
            current = getattr(character, field, None)
            label = _CHANGE_REQUEST_FIELD_LABELS.get(field, field)
            if field in _CHANGE_REQUEST_NUMERIC_FIELDS:
                checkbox = ft.Checkbox(label=f"{label}  (attuale: {current})", value=False)
                input_ctrl: ft.Control = ft.TextField(
                    label="Nuovo valore", dense=True, value=str(current),
                    keyboard_type=ft.KeyboardType.NUMBER, **d.field_style(),
                )
            else:
                if not current:
                    continue  # scelta di classe mai fatta da questo personaggio
                options = self._change_request_field_choices(character, field)
                if not options:
                    continue
                checkbox = ft.Checkbox(label=f"{label}  (attuale: {current})", value=False)
                input_ctrl = ft.Dropdown(
                    label="Nuovo valore", dense=True,
                    value=current if current in options else options[0],
                    options=[ft.DropdownOption(key=o, text=o) for o in options],
                    **d.field_style(),
                )
            field_controls[field] = (checkbox, input_ctrl)
            rows.append(ft.Column(
                [checkbox, ft.Container(input_ctrl, padding=ft.Padding.only(left=32))],
                spacing=2, tight=True,
            ))

        reason_field = ft.TextField(
            label="Motivazione (il giocatore la legge prima di decidere)",
            dense=True, multiline=True, min_lines=2, max_lines=4, **d.field_style(),
        )

        def _confirm(e):
            changes: dict[str, int | str] = {}
            for field, (checkbox, input_ctrl) in field_controls.items():
                if not checkbox.value:
                    continue
                if isinstance(input_ctrl, ft.Dropdown):
                    value = input_ctrl.value
                    if not value:
                        continue
                    changes[field] = value
                else:
                    raw = (input_ctrl.value or "").strip()
                    try:
                        changes[field] = int(raw)
                    except ValueError:
                        self._show_error(
                            f"{_CHANGE_REQUEST_FIELD_LABELS.get(field, field)}: "
                            f"il valore deve essere un numero intero.")
                        return
            if not changes:
                self._show_error("Seleziona almeno un campo da modificare.")
                return
            reason = (reason_field.value or "").strip()
            if not reason:
                self._show_error("La richiesta di modifica deve avere una motivazione.")
                return
            self.page.pop_dialog()
            self._send_remote_command(
                world, character, perm.CMD_CHANGE_REQUEST_PROPOSE,
                {"changes": changes, "reason": reason},
            )

        if not rows:
            rows.append(d.muted(
                "Nessun campo proponibile per questo personaggio — le scelte di "
                "classe compaiono solo se il personaggio le ha già.",
            ))

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Proponi modifica — {character.name}", ft.Icons.GAVEL,
                                  tone="warning"),
            content=ft.Container(
                content=ft.Column(
                    [d.muted(
                        "Spunta i campi da proporre e indica il nuovo valore: il "
                        "giocatore vedrà sempre il valore attuale e quello proposto.",
                    )] + rows + [reason_field],
                    spacing=d.Space.SM, scroll=ft.ScrollMode.AUTO,
                ),
                width=responsive_dialog_width(page, 380),
                height=440,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Invia proposta", icon=ft.Icons.SEND, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.warning, color=p.on_accent)),
            ]),
        )
        self.page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Richieste in sospeso (passo 6, §7.1) — visibile a QUALSIASI membro,
    # non solo master/owner: è la controparte lato giocatore di "Proponi
    # modifica" sopra. Filtrata qui solo per presentazione (mostra le
    # richieste sui personaggi di cui SONO proprietario); il controllo che
    # conta davvero resta comunque `perm.is_character_owner()` dentro
    # `_handle_change_request_respond` — un client modificato che nascondesse
    # questo filtro non guadagnerebbe nulla.
    # ------------------------------------------------------------------

    def _pending_change_requests_section(self, world: World) -> ft.Control | None:
        my_characters = {
            c.id: c for c in character_repo.get_master_visible_characters(world.id)
            if c.owner_device_id == self.device_id
        }
        if not my_characters:
            return None
        pending = [
            req for req in world_repo.get_pending_change_requests(world.id)
            if req.character_id in my_characters
        ]
        if not pending:
            return None

        rows: list[ft.Control] = []
        for i, req in enumerate(pending):
            if i > 0:
                rows.append(ft.Divider(height=1))
            rows.append(self._pending_change_request_row(world, my_characters[req.character_id], req))
        return d.section(
            "Richieste in sospeso",
            ft.Column(rows, spacing=d.Space.SM, tight=True),
            accent=d.tone_color("warning"),
        )

    def _pending_change_request_row(self, world: World, character: Character,
                                     request: WorldChangeRequest) -> ft.Control:
        p = d.T()
        try:
            changes: dict = json.loads(request.payload or "{}")
        except (json.JSONDecodeError, TypeError):
            changes = {}
        diff_lines: list[ft.Control] = []
        for field, new_value in changes.items():
            label = _CHANGE_REQUEST_FIELD_LABELS.get(field, field)
            current = getattr(character, field, "?")
            diff_lines.append(ft.Text(f"{label}: {current} → {new_value}",
                                       size=d.Size.BODY_SM, color=p.text))

        return ft.Column(
            [
                ft.Text(f"{character.name} — proposta del master", weight=ft.FontWeight.BOLD,
                        color=p.text),
                d.muted(f"«{request.reason}»"),
                ft.Column(diff_lines, spacing=2, tight=True),
                ft.Row(
                    [
                        d.pill(ft.Icons.CHECK, "Accetta", color=p.success, filled=True,
                               on_click=lambda e: self._respond_change_request(world, request, True)),
                        d.pill(ft.Icons.CLOSE, "Rifiuta", color=p.danger,
                               on_click=lambda e: self._respond_change_request(world, request, False)),
                    ],
                    spacing=d.Space.XS,
                ),
            ],
            spacing=d.Space.XS, tight=True,
        )

    def _respond_change_request(self, world: World, request: WorldChangeRequest, accept: bool):
        assert self.device_id is not None
        result = self._send_command(
            world, perm.CMD_CHANGE_REQUEST_RESPOND,
            {"request_id": request.id, "accept": accept},
            target_type="character", target_id=request.character_id,
        )
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

    # ------------------------------------------------------------------
    # Richieste di rientro — verso opposto delle richieste di
    # modifica sopra: qui propone il giocatore, risponde SOLO master/owner
    # (a differenza di "Richieste in sospeso", non visibile a un giocatore
    # qualunque — è il master a dover decidere, non il proprietario del
    # personaggio, che è già chi ha inviato la richiesta).
    # ------------------------------------------------------------------

    def _pending_rejoin_requests_section(self, world: World) -> ft.Control | None:
        pending = world_repo.get_pending_rejoin_requests(world.id)
        if not pending:
            return None
        rows: list[ft.Control] = []
        for i, req in enumerate(pending):
            character = character_repo.get_by_id(req.character_id)
            if character is None:
                continue  # difensivo: non dovrebbe accadere, mai bloccare l'intera sezione
            if i > 0:
                rows.append(ft.Divider(height=1))
            rows.append(self._pending_rejoin_request_row(world, character, req))
        if not rows:
            return None
        return d.section(
            "Richieste di rientro",
            ft.Column(rows, spacing=d.Space.SM, tight=True),
            accent=d.tone_color("magic"),
        )

    def _pending_rejoin_request_row(self, world: World, character: Character,
                                     request: WorldRejoinRequest) -> ft.Control:
        p = d.T()
        if request.mode == "refresh_from_local":
            try:
                export_char = json.loads(request.payload or "{}").get("export", {}).get(
                    "character", {},
                )
            except (json.JSONDecodeError, TypeError, AttributeError):
                export_char = {}
            level = export_char.get("level", "?")
            mode_label = f"Aggiorna allo stato attuale della scheda del giocatore (Liv. {level})"
        else:
            mode_label = "Riprende lo stato con cui era stato rimosso"

        cooldown_remaining = world_sync.master_action_cooldown_remaining(character.id)
        on_cooldown = cooldown_remaining > 0
        cooldown_suffix = f" ({int(cooldown_remaining) + 1}s)" if on_cooldown else ""
        muted_color = p.text_3

        def _pill(icon: ft.IconData, label: str, color: str, accept: bool) -> ft.Control:
            if on_cooldown:
                return d.pill(icon, label + cooldown_suffix, color=muted_color, on_click=None)
            return d.pill(icon, label, color=color,
                          on_click=lambda e: self._respond_rejoin_request(world, character,
                                                                           request, accept))

        content: list[ft.Control] = [
            ft.Text(f"{character.name} — richiesta di {request.requester_name or 'un giocatore'}",
                    weight=ft.FontWeight.BOLD, color=p.text),
            d.muted(mode_label),
        ]
        if request.reason:
            content.append(d.muted(f"«{request.reason}»"))
        content.append(ft.Row(
            [
                _pill(ft.Icons.CHECK, "Accetta", p.success, True),
                _pill(ft.Icons.CLOSE, "Rifiuta", p.danger, False),
            ],
            spacing=d.Space.XS,
        ))
        return ft.Column(content, spacing=d.Space.XS, tight=True)

    def _respond_rejoin_request(self, world: World, character: Character,
                                 request: WorldRejoinRequest, accept: bool):
        self._send_remote_command(
            world, character, perm.CMD_CHARACTER_REJOIN_RESPOND,
            {"request_id": request.id, "accept": accept},
        )

    # ------------------------------------------------------------------
    # Personaggi Archiviati — gap segnalato da Davide: un personaggio che
    # esce/viene espulso dal mondo (`world_instance_archived=1`) prima non
    # era consultabile da nessuna vista Master, `get_master_visible_
    # characters()` lo esclude sempre. Card di sola lettura (nessuna scheda
    # editabile: il master non deve poter modificare un personaggio che non
    # sta più giocando in questo mondo), stesso gate di permesso di
    # `_remote_actions_section` (solo chi può intervenire a distanza).
    # ------------------------------------------------------------------

    def _archived_characters_section(self, world: World) -> ft.Control | None:
        archived = character_repo.get_archived_world_instances(world.id)
        if not archived:
            return None
        rows: list[ft.Control] = []
        for i, character in enumerate(archived):
            if i > 0:
                rows.append(ft.Divider(height=1))
            rows.append(self._archived_character_row(character))
        return d.section(
            "Personaggi Archiviati",
            ft.Column(rows, spacing=d.Space.SM, tight=True),
        )

    def _archived_character_row(self, character: Character) -> ft.Control:
        p = d.T()
        # BUG FIX (2026-08-24, stesso giro di audit multiclasse del fix
        # export/import): usava solo characters.class_name/subclass, quindi
        # un personaggio multiclasse archiviato mostrava solo la classe
        # primaria — stessa causa di fondo (un campo legacy usato al posto
        # di get_class_display_string()) della card "Test Sweep" con solo
        # "Monaco" trovata testando l'import di un file .dndchar.
        class_line = character_repo.get_class_display_string(
            character.id, fallback_class_name=character.class_name,
        )
        if character.subclass and " / " not in class_line:
            class_line += f" ({character.subclass})"
        archived_on = (character.updated_at or "")[:10]
        return d.asymmetric_row(
            ft.Column(
                [
                    ft.Text(character.name, weight=ft.FontWeight.BOLD, color=p.text),
                    d.muted(f"{class_line} · Liv. {character.level} · {character.race}"),
                    d.muted(f"Archiviato il {archived_on}" if archived_on else "Archiviato"),
                ],
                spacing=0, tight=True,
            ),
            d.pill(ft.Icons.VISIBILITY, "Vedi dettagli", color=p.text_2,
                   on_click=lambda e: self._open_archived_character_dialog(character)),
            ratio=(8, 4),
        )

    def _open_archived_character_dialog(self, character: Character):
        """Riepilogo di sola lettura — NON la scheda editabile completa
        (`SheetView`, mai raggiungibile per un personaggio altrui, vedi
        `_render_detail`): stesso principio del dialog di dettaglio
        mostro/NPC in Sezione Incontri (`master_encounter_view.py::
        _open_stat_block_click`), qui applicato a un personaggio."""
        page = self.page
        if page is None:
            return
        p = d.T()
        weapons = character_repo.get_weapons(character.id, equipped_only=False)
        inventory = character_repo.get_inventory(character.id)
        spells = character_repo.get_known_spells(character.id)
        class_line = character.class_name
        if character.subclass:
            class_line += f" ({character.subclass})"
        race_line = character.race
        if character.subrace:
            race_line += f" ({character.subrace})"
        lines = [
            ("Classe", class_line),
            ("Razza", race_line),
            ("Livello", str(character.level)),
            ("Background", character.background or "—"),
            ("PF", f"{character.hp_current} / {character.hp_max}"),
            ("Armi", str(len(weapons))),
            ("Oggetti in inventario", str(len(inventory))),
            ("Incantesimi conosciuti", str(len(spells))),
        ]
        content = ft.Column(
            [
                ft.Row(
                    [ft.Text(k, color=p.text_2, size=d.Size.BODY_SM),
                     ft.Text(v, color=p.text, weight=ft.FontWeight.BOLD, size=d.Size.BODY_SM)],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
                for k, v in lines
            ],
            spacing=d.Space.XS, tight=True,
        )
        page.show_dialog(ft.AlertDialog(
            title=d.dialog_title(character.name, ft.Icons.PERSON_OFF),
            content=ft.Container(content=content, width=responsive_dialog_width(page, 360)),
            actions=wrap_dialog_actions([
                ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
            ]),
        ))

    # ------------------------------------------------------------------
    # Hosting LAN (passo 4) — solo owner, solo sul mondo che ospita
    # ------------------------------------------------------------------

    def _hosting_section(self, world: World) -> ft.Control:
        p = d.T()
        if self._host_server is None or self._host_server.world_id != world.id:
            return d.section(
                "Ospita in LAN",
                ft.Column(
                    [
                        d.muted(
                            "Avvia un piccolo server sulla rete locale: i giocatori si "
                            "uniscono da un altro dispositivo con indirizzo, codice e PIN. "
                            "Solo HTTP in chiaro (§9.4 del design doc) — usalo sulla rete di "
                            "casa o di un tavolo fidato, mai su una rete pubblica.",
                        ),
                        ft.Container(height=d.Space.XS),
                        d.pill(ft.Icons.WIFI_TETHERING, "Avvia hosting", filled=True,
                               color=p.magic, on_click=lambda e: self._start_hosting(world)),
                    ],
                    spacing=d.Space.XS,
                ),
            )

        host = self._host_server
        ip = local_ip_hint()
        pending = host.list_pending()

        # Coppia maggiore/minore (`asymmetric_row`, non due blocchi impilati
        # a prescindere): indirizzo+PIN sono il dato testuale da leggere,
        # il QR è la scorciatoia visiva — affiancarli su schermi larghi ha
        # senso, sotto i 768px tornano impilati da soli (stesso principio
        # già in uso per HP-block+statistiche).
        connection_info = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.WIFI_TETHERING, color=p.magic, size=18),
                        ft.Text(f"In ascolto su {ip}:{host.port}", color=p.text,
                                font_family=d.Font.MONO, size=d.Size.BODY_SM),
                    ],
                    spacing=d.Space.XS,
                ),
                ft.Row(
                    [
                        d.muted("PIN di ingresso"),
                        ft.Text(host.pin, size=22, weight=ft.FontWeight.BOLD, color=p.magic,
                                font_family=d.Font.MONO, style=ft.TextStyle(letter_spacing=4)),
                    ],
                    spacing=d.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=d.Space.SM, tight=True,
        )

        rows: list[ft.Control] = [
            d.asymmetric_row(connection_info, self._hosting_qr_image(world, host, ip)),
        ]

        if pending:
            rows.append(ft.Container(height=d.Space.SM))
            rows.append(d.muted(f"{len(pending)} richiesta/e in attesa di approvazione:"))
            for req in pending:
                rows.append(self._pending_request_row(world, req))
        else:
            rows.append(ft.Container(height=d.Space.SM))
            rows.append(d.muted("Nessuna richiesta di ingresso in attesa."))

        rows.append(ft.Container(height=d.Space.SM))
        rows.append(ft.Row(
            [
                d.pill(ft.Icons.REFRESH, "Aggiorna richieste", color=p.text_2,
                       on_click=lambda e: self._refresh_detail()),
                d.pill(ft.Icons.WIFI_OFF, "Ferma hosting", color=p.danger,
                       on_click=lambda e: self._stop_hosting(world)),
            ],
            spacing=d.Space.SM, wrap=True,
        ))

        return d.section("Ospita in LAN", ft.Column(rows, spacing=d.Space.XS, tight=True))

    def _hosting_qr_image(self, world: World, host: WorldHostServer, ip: str) -> ft.Control:
        """
        QR con indirizzo, porta, codice e PIN già incorporati — per non
        dover leggere/digitare a mano quei 4 dati. Contenuto e generazione
        in `network/qr_join.py`; la scansione lato giocatore resta manuale
        (nessuno scanner in-app, vedi il docstring di quel modulo).

        Errore mostrato IN UI, non solo loggato: il log su stderr non è
        raggiungibile da un'app impacchettata, quindi un log da solo non è
        "diagnosticabile" se nessuno può leggerlo. Il PIN testuale sopra
        resta comunque sufficiente da solo per entrare anche quando il QR
        fallisce.
        """
        p = d.T()
        try:
            text = build_join_text(world.name, ip, host.port, world.join_code, host.pin)
            b64 = generate_qr_png_base64(text)
        except Exception as e:
            logger.error("Errore nella generazione del QR d'ingresso: %s", e)
            return ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=16, color=p.danger_icon),
                    ft.Text(f"QR non generato: {e}", color=p.danger, size=d.Size.BODY_SM,
                            expand=True),
                ],
                spacing=d.Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        return ft.Column(
            [
                d.muted("Inquadra per compilare i campi d'ingresso"),
                ft.Container(
                    content=ft.Image(
                        src=f"data:image/png;base64,{b64}",
                        width=180, height=180, fit=ft.BoxFit.CONTAIN,
                    ),
                    bgcolor=ft.Colors.WHITE,
                    padding=d.Space.SM,
                    border_radius=d.Radius.SM,
                ),
            ],
            spacing=d.Space.XS,
        )

    def _pending_request_row(self, world: World, req: PendingJoinRequest) -> ft.Control:
        p = d.T()
        # Un trasferimento NON è un giocatore nuovo che entra (§11.9):
        # è uno scambio di identità, e approvarlo fa smettere di
        # funzionare il vecchio dispositivo. Il master deve poterlo capire dalla
        # riga, non dopo — icona e testo diversi, e un chip che lo dichiara.
        is_transfer = bool(req.transfer_id)
        if is_transfer:
            nome = req.transfer_member_name or req.display_name
            testo = (
                f"«{req.display_name}» vuole spostare il personaggio di "
                f"{nome} su un nuovo dispositivo"
            )
        else:
            testo = req.display_name

        return ft.Row(
            [
                d.icon_badge(ft.Icons.PHONELINK_SETUP if is_transfer else ft.Icons.PERSON_ADD,
                             tone="magic" if is_transfer else "neutral", size=28),
                ft.Column(
                    [
                        ft.Text(testo, color=p.text, size=d.Size.BODY_SM),
                        *([d.muted(
                            "Il dispositivo attuale perderà l'accesso al mondo."
                        )] if is_transfer else []),
                    ],
                    spacing=0, tight=True, expand=True,
                ),
                ft.IconButton(
                    ft.Icons.CHECK, icon_color=p.primary_icon,
                    tooltip="Approva il trasferimento" if is_transfer else "Approva ingresso",
                    on_click=lambda e, r=req: self._approve_join(world, r.id)),
                ft.IconButton(
                    ft.Icons.CLOSE, icon_color=p.danger_icon,
                    tooltip="Rifiuta il trasferimento" if is_transfer else "Rifiuta ingresso",
                    on_click=lambda e, r=req: self._reject_join(world, r.id)),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _start_hosting(self, world: World):
        if self._host_server is not None:
            self._host_server.stop()
        server = WorldHostServer(world.id)
        try:
            server.start()
        except RuntimeError as e:
            self._show_error(str(e))
            return
        self._host_server = server
        self._refresh_detail()

    def _stop_hosting(self, world: World):
        if self._host_server is not None:
            self._host_server.stop()
            self._host_server = None
        self._refresh_detail()

    def _approve_join(self, world: World, request_id: str):
        if self._host_server is not None:
            if not self._host_server.approve(request_id):
                self._show_error("Approvazione fallita — la richiesta potrebbe essere scaduta.")
        self._refresh_detail()

    def _reject_join(self, world: World, request_id: str):
        if self._host_server is not None:
            self._host_server.reject(request_id)
        self._refresh_detail()

    # ------------------------------------------------------------------
    # Backup del mondo — esportazione/importazione
    # (`dnd_app/docs/multiplayer_design.md` §6.3) — stesso identico
    # meccanismo di Import/Export personaggio (`.dndchar`), esteso a un
    # intero mondo (`.dndworld`): `data/repositories/world_export.py` per
    # la logica dati, `ui/file_export.py` per i dialoghi nativi del SO
    # (estratti da `home_view.py` senza toccarlo — vedi il docstring di
    # quel modulo). Solo owner: un backup/trasferimento dell'INTERO mondo
    # (ogni personaggio, il giornale, il bottino) è un'operazione sensibile,
    # stesso livello della "Zona pericolosa" qui sotto.
    # ------------------------------------------------------------------

    def _ensure_file_picker(self) -> ft.FilePicker | None:
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

    def _backup_section(self, world: World) -> ft.Control:
        """
        Promemoria periodico: conta gli eventi di giornale dall'ultimo export riuscito
        (`world.last_export_seq`) e mostra un avviso non bloccante —
        MAI un dialog che interrompe il flusso — quando supera
        `EXPORT_REMINDER_EVENT_THRESHOLD`. Un mondo mai esportato ha
        `last_export_seq=0`: conta dalla nascita del mondo.
        """
        p = d.T()
        events_since = world_repo.count_events_since(world.id, world.last_export_seq)
        reminder: list[ft.Control] = []
        if events_since >= world_export.EXPORT_REMINDER_EVENT_THRESHOLD:
            reminder = [
                ft.Container(height=d.Space.XS),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=p.warning, size=16),
                        ft.Text(
                            f"Sono successe {events_since} cose in questo mondo da quando "
                            "l'hai esportato l'ultima volta — considera un nuovo backup.",
                            size=12, color=p.warning,
                        ),
                    ],
                    spacing=d.Space.XS,
                ),
            ]
        return d.section(
            "Backup del mondo",
            ft.Column(
                [
                    d.muted(
                        "Esporta l'intero mondo (membri, personaggi, giornale, bottino, "
                        "note e mappe condivise) in un file .dndworld — per non perdere "
                        "tutto se questo dispositivo si rompe, o per passare la campagna "
                        "a un altro master.",
                    ),
                    ft.Container(height=d.Space.XS),
                    d.pill(ft.Icons.DOWNLOAD, "Esporta mondo", filled=True, color=p.magic,
                           on_click=lambda e: self._on_export_world_click(world)),
                    *reminder,
                ],
                spacing=d.Space.XS,
            ),
        )

    # --- Export -----------------------------------------------------------

    def _on_export_world_click(self, world: World):
        page = self.page
        if page is None:
            return
        if page.web:
            self._export_world_web(world)
            return
        platform = page.platform
        if platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            page.run_task(self._on_mobile_export_world, world)
            return
        import platform as sys_platform
        system = sys_platform.system()
        threading.Thread(target=self._export_world_desktop, args=(world, system),
                          daemon=True).start()

    async def _on_mobile_export_world(self, world: World):
        """Export su Android/iOS — stesso meccanismo di
        `HomeView._on_mobile_export` (`FilePicker.save_file()` scrive
        anche il contenuto su questa build, a differenza di `pick_files()`
        che non funziona affatto — vedi il docstring gemello lì)."""
        picker = self._ensure_file_picker()
        if picker is None:
            return
        json_text = world_export.export_to_json_string(world.id)
        if json_text is None:
            self._show_error("Errore durante l'esportazione del mondo.")
            return
        filename = world_export.suggested_export_filename(world.id)
        try:
            result_path = await picker.save_file(
                dialog_title="Esporta mondo",
                file_name=filename,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["dndworld"],
                src_bytes=json_text.encode("utf-8"),
            )
        except Exception as exc:
            logger.error(f"Errore FilePicker.save_file (mobile, mondo): {exc}")
            self._show_error(f"Errore durante l'esportazione:\n{exc}")
            return
        if not result_path:
            return
        self._show_export_world_success_dialog(world.id, filename, result_path, system=None)

    def _export_world_web(self, world: World):
        """Stesso doppio-destinazione di `HomeView._export_web`: la
        cartella condivisa (SSH/scp) e la sottocartella servita
        staticamente per il download diretto dal browser."""
        json_text = world_export.export_to_json_string(world.id)
        if json_text is None:
            self._show_error("Errore durante l'esportazione del mondo.")
            return
        filename = world_export.suggested_export_filename(world.id)
        full_path = os.path.join(get_character_exports_path(), filename)
        staging_path = os.path.join(get_web_export_staging_path(), filename)
        written = False
        for path in (full_path, staging_path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(json_text)
                written = True
            except OSError as exc:
                logger.error(f"Errore scrittura file export mondo ({path}): {exc}")
        if not written:
            self._show_error("Errore durante il salvataggio del file esportato.")
            return
        self._show_export_world_success_dialog(
            world.id, filename, full_path, system=None, download_url=f"/exports/{filename}",
        )

    def _export_world_desktop(self, world: World, system: str):
        """Chiamato in un thread separato — dialogo nativo di salvataggio."""
        json_text = world_export.export_to_json_string(world.id)
        if json_text is None:
            self._show_error("Errore durante l'esportazione del mondo.")
            return
        default_name = world_export.suggested_export_filename(world.id)
        path, error = file_export.native_save_dialog(
            system, dialog_title="Esporta mondo", default_name=default_name,
            filter_label="File Mondo D&D", filter_ext=".dndworld",
        )
        if error:
            logger.error(f"Dialogo salvataggio nativo fallito ({system}, mondo): {error}")
            self._show_error(
                "Non è stato possibile aprire la finestra di salvataggio del sistema:\n"
                f"{error}\n\n"
                "Su macOS potrebbe essere necessario autorizzare l'automazione: "
                "Impostazioni di Sistema → Privacy e Sicurezza → Automazione."
            )
            return
        if not path:
            return
        if not path.lower().endswith((".dndworld", ".json")):
            path += ".dndworld"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(json_text)
        except OSError as exc:
            logger.error(f"Errore scrittura file export mondo ({path}): {exc}")
            self._show_error(f"Errore durante il salvataggio del file:\n{path}\n{exc}")
            return
        if not os.path.isfile(path):
            logger.error(f"File export mondo non trovato dopo la scrittura: {path}")
            self._show_error(
                f"Il file non risulta presente dopo il salvataggio:\n{path}\n"
                "Riprova, oppure scegli un'altra cartella."
            )
            return
        self._show_export_world_success_dialog(world.id, os.path.basename(path), path,
                                                system=system)

    def _show_export_world_success_dialog(
        self, world_id: str, filename: str, path: str, system: str | None,
        download_url: str | None = None,
    ):
        # Registra il promemoria SOLO qui, dopo che il file è
        # stato scritto/scaricato con successo — un export fallito prima di
        # questo punto non deve mai spegnere l'avviso. Sola scrittura DB
        # (nessun `page.update()`/ri-render qui): questo metodo è chiamato
        # anche da un thread in background (`_export_world_desktop`), e
        # `page.update()` da un thread qualunque invece di `page.run_task()`
        # non è sicuro (vedi CLAUDE.md) — non farlo qui. La
        # sezione "Backup del mondo" si aggiorna comunque al prossimo giro
        # della sincronizzazione in background già attiva su questa scheda.
        world_repo.mark_world_exported(world_id, world_repo.get_latest_event_seq(world_id))

        page = self.page
        if page is None:
            return
        p = d.T()

        def _reveal(e):
            threading.Thread(target=file_export.reveal_in_file_manager,
                              args=(path, system), daemon=True).start()

        actions = []
        if download_url is not None:
            actions.append(ft.ElevatedButton(
                "Scarica", icon=ft.Icons.DOWNLOAD,
                url=ft.Url(url=download_url, target=ft.UrlTarget.BLANK),
                style=ft.ButtonStyle(bgcolor=p.magic, color=p.bg),
            ))
        if system is not None:
            actions.append(ft.TextButton(
                "Mostra nel Finder" if system == "Darwin" else "Mostra nella cartella",
                icon=ft.Icons.FOLDER_OPEN, on_click=_reveal,
                style=ft.ButtonStyle(color=p.text_2),
            ))
        actions.append(ft.TextButton("OK", on_click=lambda e: page.pop_dialog(),
                                      style=ft.ButtonStyle(color=p.primary)))

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Mondo esportato"),
            content=ft.Column([
                ft.Text(f'File salvato come "{filename}".', color=p.text, size=13),
                ft.Container(height=6),
                ft.Text(path, color=p.text_3, size=11, selectable=True),
            ], tight=True, spacing=0),
            actions=actions,
        ))

    # --- Import -------------------------------------------------------

    def _on_import_world_click(self, e=None):
        page = self.page
        if page is None:
            return
        if page.web:
            show_world_import_picker(page, on_select=self._do_import_world_from_path)
            return
        platform = page.platform
        if platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            page.run_task(self._on_mobile_import_world)
            return
        import platform as sys_platform
        system = sys_platform.system()
        threading.Thread(target=self._import_world_pick_desktop, args=(system,),
                          daemon=True).start()

    async def _on_mobile_import_world(self):
        """Import su Android/iOS: prova PRIMA il selettore nativo
        (`ui/native_file_picker.py`, estensione `flet_file_picker`), poi
        ricade sulla WebView locale — stesso meccanismo e stesso ordine di
        `HomeView._on_mobile_import` (vedi il docstring gemello lì per il
        perché di entrambi i bypass: `ft.FilePicker.pick_files()` e la
        WebView con `<input type=file>` sono entrambi confermati non
        funzionanti su questa build Android)."""
        page = self.page
        if page is None:
            return
        try:
            native_result = await pick_file_native(
                page, allowed_extensions=["dndworld", "json"],
            )
        except FilePickerUnavailable as exc:
            logger.warning(f"FilePicker nativo non disponibile, uso WebView: {exc}")
            native_result = None
            native_failed = True
        else:
            native_failed = False
        if native_failed:
            result = await pick_file_via_webview(
                page, accept=".dndworld,.json,application/json", title="Importa mondo",
            )
            if result is None:
                return
            filename, b64_content = result
            try:
                raw = base64.b64decode(b64_content)
            except Exception as exc:
                logger.error(f"Import mobile mondo: base64 non decodificabile: {exc}")
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
        self._do_import_world_from_text(text)

    def _import_world_pick_desktop(self, system: str):
        path, error = file_export.native_open_dialog(
            system, dialog_title="Importa mondo", filter_label="File Mondo D&D",
            filter_ext=".dndworld",
        )
        if error:
            logger.error(f"Dialogo apertura nativo fallito ({system}, mondo): {error}")
            self._show_error(
                "Non è stato possibile aprire la finestra di selezione del sistema:\n"
                f"{error}\n\n"
                "Su macOS potrebbe essere necessario autorizzare l'automazione: "
                "Impostazioni di Sistema → Privacy e Sicurezza → Automazione."
            )
            return
        if path:
            self._do_import_world_from_path(path)

    def _do_import_world_from_path(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            logger.error(f"Errore lettura file import mondo ({path}): {exc}")
            self._show_error(f"Impossibile leggere il file:\n{path}")
            return
        self._do_import_world_from_text(text)

    def _do_import_world_from_text(self, text: str):
        data = world_export.load_json_string(text)
        if data is None:
            self._show_error("Il file selezionato non è un JSON valido.")
            return
        err = world_export.validate_export_data(data)
        if err:
            self._show_error(err)
            return
        summary = world_export.peek_world_summary(data)
        if summary is None:
            self._show_error("Impossibile leggere i dati del mondo dal file.")
            return

        self._prompt_importer_name(data, summary)

    def _prompt_importer_name(self, data: dict, summary: dict):
        """
        Chiede il nome del master PRIMA di procedere — questo dispositivo
        diventerà l'owner/host del mondo importato (§6.3), e il registro
        deve poter mostrare chi è (stesso principio già applicato in
        "Crea un mondo"/"Unisciti con un codice" e in `_open_join_dialog`:
        mai un default silenzioso come "Master" per tutti).
        """
        page = self.page
        if page is None:
            return
        p = d.T()
        display_field = ft.TextField(label="Il tuo nome (per il registro)", dense=True,
                                      **d.field_style())

        def _continue(e):
            display_name = (display_field.value or "").strip()
            if not display_name:
                self._show_error("Inserisci il tuo nome prima di importare il mondo.")
                return
            page.pop_dialog()
            if world_export.world_id_exists(summary["id"]):
                self._show_import_world_conflict_dialog(data, summary, display_name)
            else:
                self._run_import_world(data, "new", display_name)

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f'Importa "{summary["name"]}"', ft.Icons.PUBLIC),
            content=ft.Column(
                [
                    d.muted(
                        f'{summary["member_count"]} membri · {summary["character_count"]} '
                        f'personaggi. Diventerai tu l\'owner e l\'host di questo mondo.',
                    ),
                    ft.Container(height=d.Space.SM),
                    display_field,
                ],
                tight=True, spacing=0,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Continua", icon=ft.Icons.ARROW_FORWARD, on_click=_continue,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary)),
            ]),
        )
        page.show_dialog(dlg)

    def _show_import_world_conflict_dialog(self, data: dict, new_summary: dict, display_name: str):
        """Il mondo nel file ha lo stesso ID di uno già presente su questo
        dispositivo — chiede esplicitamente come procedere (stesso pattern
        di `HomeView._show_import_conflict_dialog` per un personaggio)."""
        page = self.page
        if page is None:
            return
        p = d.T()
        existing = world_repo.get_world(new_summary["id"])
        existing_name = existing.name if existing else "?"

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Mondo già presente"),
            content=ft.Column(
                [
                    ft.Text(
                        f'Hai già un mondo "{existing_name}" con lo stesso ID del file da '
                        f'importare ("{new_summary["name"]}", {new_summary["character_count"]} '
                        f'personaggi).',
                        color=p.text, size=13,
                    ),
                    ft.Container(height=12),
                    d.muted("Cosa vuoi fare?"),
                ],
                tight=True, spacing=0,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.OutlinedButton(
                    "Crea copia", icon=ft.Icons.CONTENT_COPY,
                    on_click=lambda e: self._confirm_import_world(data, "copy", display_name),
                    style=ft.ButtonStyle(color=p.magic, side=ft.BorderSide(1, p.magic)),
                ),
                ft.ElevatedButton(
                    "Sovrascrivi", icon=ft.Icons.WARNING_AMBER_ROUNDED,
                    on_click=lambda e: self._confirm_import_world(data, "overwrite", display_name),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _confirm_import_world(self, data: dict, mode: str, display_name: str):
        if self.page is not None:
            self.page.pop_dialog()
        self._run_import_world(data, mode, display_name)

    def _run_import_world(self, data: dict, mode: str, display_name: str):
        if self.device_id is None:
            self._show_error("Identità del dispositivo non ancora pronta — riprova tra poco.")
            return
        new_id = world_export.import_world(data, mode, self.device_id, display_name)
        if new_id is None:
            self._show_error("Errore durante l'importazione del mondo.")
            return
        self._current_world = None
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass
        show_snack(self.page, "Mondo importato correttamente — ora lo ospiti tu.")

    def _danger_zone_section(self, world: World) -> ft.Control:
        p = d.T()
        # level=0 (nessuna ombra) invece del
        # default 1 — distingue questa sezione dalle altre ~11 nel dettaglio
        # mondo per ASSENZA di elevazione (segnale sobrio, coerente con
        # "manuale non poster") invece che per un colore diverso, dato che
        # `primary`/`danger` sono di proposito lo stesso accento (vedi
        # Palette in ui/design.py) — il colore da solo non basterebbe a
        # distinguerla da un'eventuale altra sezione con accento primario.
        return d.section(
            "Zona pericolosa",
            d.pill(ft.Icons.DELETE_FOREVER, "Elimina mondo", color=p.danger,
                   on_click=lambda e: self._confirm_delete(world)),
            accent=p.danger_fill,
            level=0,
        )

    def _confirm_delete(self, world: World):
        p = d.T()
        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Elimina mondo", ft.Icons.DELETE_FOREVER, tone="danger"),
            content=ft.Text(
                f'Eliminare definitivamente "{world.name}"? Il giornale e tutti i membri '
                f"andranno persi. Questa azione non può essere annullata.",
                color=p.text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_FOREVER,
                    on_click=lambda e: self._do_delete(world),
                    style=ft.ButtonStyle(bgcolor=p.danger_fill, color=p.text),
                ),
            ]),
        )
        self.page.show_dialog(dlg)

    def _do_delete(self, world: World):
        self.page.pop_dialog()
        result = self._send_command(world, perm.CMD_WORLD_DELETE, {})
        if result.success:
            self._current_world = None
            self._render()
            try:
                self.page.update()
            except RuntimeError:
                pass
        else:
            self._show_error(result.error)

    def _refresh_detail(self):
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Aggiornamenti mirati per sezione "calda" (piano refresh mirati,
    # Fase 1c) — ognuno rilegge SEMPRE `world` fresco dal DB (mai un
    # oggetto Python già in memoria, stesso motivo per cui
    # `_resync_character_from_host()` rimaterializza l'intero personaggio
    # ad ogni evento: vedi `core/world_sync.py`) e sostituisce SOLO il
    # contenuto del proprio container persistente — mai `_render_detail()`
    # per intero. Usare solo quando l'azione non cambia quali sezioni
    # esistono/il loro ordine (regola guida del piano). Il tick di sync
    # periodico (`_async_redraw_detail`) resta sul percorso completo,
    # invariato in questa fase.
    # ------------------------------------------------------------------

    def _update_members_section(self, world: World, my_role: str) -> None:
        fresh = world_repo.get_world(world.id)
        if fresh is None:
            return
        self._members_container.content = self._members_section(fresh, my_role)
        try:
            self._members_container.update()
        except RuntimeError:
            pass

    def _update_shared_loot_section(self, world: World) -> None:
        fresh = world_repo.get_world(world.id)
        if fresh is None:
            return
        self._shared_loot_container.content = self._shared_loot_section(fresh)
        self._shared_loot_container.visible = self._shared_loot_container.content is not None
        try:
            self._shared_loot_container.update()
        except RuntimeError:
            pass

    def _update_shared_notes_section(self, world: World) -> None:
        """Predisposto per la Fase 2: oggi nessuna azione LOCALE di
        `WorldsView` tocca le note condivise (cambiano solo da
        `MasterNotesView`), quindi arrivano solo tramite il tick di sync —
        vedi il piano, Fase 1c passo 4."""
        fresh = world_repo.get_world(world.id)
        if fresh is None:
            return
        self._shared_notes_container.content = self._shared_notes_section(fresh)
        self._shared_notes_container.visible = self._shared_notes_container.content is not None
        try:
            self._shared_notes_container.update()
        except RuntimeError:
            pass

    def _update_live_combat_section(self, world: World) -> None:
        """Predisposto per la Fase 2, stesso motivo di
        `_update_shared_notes_section` — il combattimento live cambia solo
        da `MasterEncounterView`."""
        fresh = world_repo.get_world(world.id)
        if fresh is None:
            return
        self._live_combat_container.content = self._live_combat_section(fresh)
        self._live_combat_container.visible = self._live_combat_container.content is not None
        try:
            self._live_combat_container.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Sincronizzazione automatica in background — nessuna
    # azione manuale richiesta: finché la scheda di UN mondo resta aperta,
    # un thread dedicato la tiene allineata da sola, sia per gli "arrivi"
    # (richieste di modifica proposte dal master, abilità/incantesimi/
    # diario concessi, danni/cure/condizioni) sia per le risposte del
    # giocatore che il master deve vedere. Nessuna dipendenza nuova: solo
    # `threading` di libreria standard, stesso pattern già in produzione in
    # `home_view.py` per il polling web multi-sessione.
    # ------------------------------------------------------------------

    def _start_detail_sync(self, world_id: str):
        """
        Delega a `ui.components.background_sync.BackgroundSyncLoop`
        (condiviso con `MasterEncounterView` — vedi il docstring del
        modulo): questo metodo resta il punto in cui vive la logica di DOMINIO (cosa
        scaricare, cosa costituisce "stato cambiato"), il thread e il
        ponte verso il loop asyncio di Flet sono ora responsabilità
        dell'helper condiviso, comportamento invariato rispetto a prima
        dell'estrazione.

        - mondo NON ospitato da questo dispositivo: `apply_fn` scarica gli
          eventi nuovi dall'host via `world_sync.sync_replica()` e li
          applica alla replica locale (comandi del master, risposte di
          altri dispositivi).
        - mondo ospitato: `apply_fn` non ha nulla da fare — il DB locale È
          già lo stato autoritativo, aggiornato all'istante da ogni
          comando ricevuto (anche da un altro dispositivo, via
          `WorldHostServer`); la sola lettura di `signature_fn` basta a
          riflettere sullo schermo ciò che è già vero nel DB.
        """
        self._stop_detail_sync()
        world = world_repo.get_world(world_id)
        self._detail_signature = self._detail_signature_of(world) if world else None
        self._detail_connection_state = "connected"

        def _apply() -> None:
            world = world_repo.get_world(world_id)
            if world is None or world.is_local_host:
                return
            backend = self._backend_for(world)
            if backend is not None:
                if isinstance(backend, RemoteBackend):
                    self._detail_connection_state = backend.connection_state()
                # BUG FIX (2026-08-24): va PRIMA di `sync_replica()`, non
                # dopo com'era — un evento mutante non correlato scaricato da
                # `sync_replica()` prima che una scrittura self-service
                # ancora in coda venga spedita fa scattare
                # `_resync_character_from_host()`, che rimaterializza
                # l'intero personaggio dall'host (che non ha ancora quella
                # scrittura) cancellandola. Stesso backend appena verificato
                # raggiungibile da `_backend_for()` sopra.
                if self.device_id:
                    # Ritenta il push di eventuali istanze create mentre
                    # l'host era offline (`host_sync_pending=1` — vedi
                    # `HomeView._push_instance_to_host`).
                    world_sync.push_pending_instances(backend, world_id, self.device_id)
                    # Stesso principio, generalizzato a QUALSIASI comando
                    # self-service rimasto in coda (nota/arma/oggetto/
                    # incantesimo/... salvato mentre l'host era offline —
                    # BUG FIX 2026-08-20, vedi il docstring di
                    # `push_pending_self_commands`).
                    world_sync.push_pending_self_commands(backend, world_id, self.device_id)
                world_sync.sync_replica(backend, world_id)
            else:
                self._detail_connection_state = "disconnected"

        def _signature() -> str | None:
            world = world_repo.get_world(world_id)
            if world is None:
                return None
            return f"{self._detail_signature_of(world)}|{self._detail_connection_state}"

        # Cattura la transizione "era in cooldown, ora non più": il
        # cooldown (`MASTER_ACTION_COOLDOWN_S=3.0`) e il poll di
        # questo loop (`_DETAIL_SYNC_INTERVAL_S=2.0`) hanno periodi diversi,
        # quindi lo scadere del cooldown può cadere TRA due tick. Se
        # `_any_master_cooldown_active` torna già `False` al tick in cui lo
        # sblocco dovrebbe apparire, nessun ridisegno viene programmato (la
        # firma di stato non cambia da un timer locale che scade) e il
        # pulsante resta bloccato sull'ultimo countdown disegnato finché non
        # arriva un evento reale o il master naviga via e ritorna. Tenendo
        # traccia dello stato del giro precedente si garantisce SEMPRE un
        # ridisegno extra esattamente nel tick in cui il cooldown passa da
        # attivo a scaduto — quello che riabilita il pulsante a schermo.
        cooldown_was_active = [False]

        def _should_redraw_anyway() -> bool:
            world = world_repo.get_world(world_id)
            active = self._any_master_cooldown_active(world) if world is not None else False
            was_active = cooldown_was_active[0]
            cooldown_was_active[0] = active
            return active or was_active

        async def _redraw() -> None:
            await self._async_redraw_detail(world_id)

        def _interval() -> float:
            if master_repo.get_visible_encounter_for_world(world_id) is not None:
                return _DETAIL_SYNC_INTERVAL_COMBAT_S
            return _DETAIL_SYNC_INTERVAL_S

        loop = BackgroundSyncLoop(
            get_page=lambda: self.page,
            signature_fn=_signature,
            async_redraw_fn=_redraw,
            apply_fn=_apply,
            should_redraw_anyway_fn=_should_redraw_anyway,
            interval_s=_interval,
            thread_name=f"world-sync-{world_id[:8]}",
        )
        self._detail_sync_loop_obj = loop
        loop.start()

    def _stop_detail_sync(self):
        loop = getattr(self, "_detail_sync_loop_obj", None)
        if loop is not None:
            loop.stop()
        self._detail_sync_loop_obj = None
        self._detail_signature = None

    def _detail_signature_of(self, world: World) -> str:
        """Firma economica dello stato rilevante di UN mondo: qualunque
        mutazione passa da `world_backend.py`, che scrive SEMPRE un evento
        (§5) — `get_latest_seq()` da solo intercetta quindi la stragrande
        maggioranza dei cambiamenti. Membri e richieste in sospeso restano
        comunque nella firma per coprire i casi limite in cui quelle
        tabelle cambiano senza un `world_events.seq` osservabile qui
        (es. `member.kick` tocca `world_members`, non i campi di `world`).

        Le richieste di ingresso in
        sospeso (`PendingJoinRequest`) NON vivono in nessuna tabella del
        DB — sono stato in memoria su `WorldHostServer._pending` (§9.4,
        mai persistito: sono per definizione una fase transitoria prima
        che il dispositivo diventi membro vero). La firma sopra, basata
        solo su letture `world_repo`, non poteva quindi MAI cambiare
        quando arrivava una nuova richiesta di ingresso — architetturalmente
        invisibile al ciclo di sync in background, a differenza di ogni
        altro tipo di richiesta (§7.1) che invece passa dal DB. Qui si
        interroga direttamente `self._host_server` (stesso processo:
        nessuna chiamata di rete, `list_pending()` è già protetto dal
        proprio lock interno) SOLO quando questo dispositivo ospita
        `world` — lo stesso identico controllo già usato da
        `_hosting_section()` per decidere se mostrarle."""
        latest_seq = world_repo.get_latest_seq(world.id)
        members = world_repo.get_members(world.id)
        member_sig = "|".join(f"{m.device_id}:{m.role}:{int(m.is_connected)}" for m in members)
        pending = world_repo.get_pending_change_requests(world.id)
        pending_sig = "|".join(f"{r.id}:{r.status}" for r in pending)
        host_pending_sig = ""
        if self._host_server is not None and self._host_server.world_id == world.id:
            host_pending_sig = "|".join(
                f"{r.id}:{r.status}" for r in self._host_server.list_pending()
            )
        return f"{world.updated_at}|{latest_seq}|{member_sig}|{pending_sig}|{host_pending_sig}"

    def _any_master_cooldown_active(self, world: World) -> bool:
        if self.device_id is None:
            return False
        my_member = world_repo.get_member(world.id, self.device_id)
        my_role = my_member.role if my_member else ""
        if not perm.can_perform(my_role, perm.CMD_XP_GRANT):
            return False  # un giocatore semplice non vede la sezione: nulla da far scendere a schermo
        characters = character_repo.get_master_visible_characters(world.id)
        return any(world_sync.master_action_cooldown_remaining(c.id) > 0 for c in characters)

    async def _async_redraw_detail(self, world_id: str) -> None:
        """Eseguito sul loop asyncio della sessione (via `page.run_task()`,
        schedulato da `ui.components.background_sync.BackgroundSyncLoop` nel
        thread di sync in background avviato da `_start_detail_sync`) — qui,
        e solo qui, è sicuro toccare `self._body`/`page.update()`."""
        if self._current_world is None or self._current_world.id != world_id:
            return
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass
        self._body.restore_scroll()

    # ------------------------------------------------------------------
    # Crea / unisciti
    # ------------------------------------------------------------------

    def _open_create_dialog(self):
        p = d.T()
        name_field = ft.TextField(label="Nome del mondo", dense=True, **d.field_style())
        display_field = ft.TextField(label="Il tuo nome (per il registro)", dense=True,
                                      **d.field_style())

        def _create(e):
            if not name_field.value or not name_field.value.strip():
                self._show_error("Il nome del mondo è obbligatorio.")
                return
            world = world_repo.create_world(
                name_field.value.strip(), self.device_id,
                display_field.value.strip() or "Master",
            )
            self.page.pop_dialog()
            if world is None:
                self._show_error("Creazione del mondo fallita.")
                return
            self._open_detail(world)

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Crea un mondo", ft.Icons.PUBLIC),
            content=ft.Column([name_field, display_field], tight=True, spacing=d.Space.MD),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Crea", icon=ft.Icons.ADD, on_click=_create,
                                  style=ft.ButtonStyle(bgcolor=p.primary_fill, color=p.on_primary_fill)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _open_join_dialog(self):
        p = d.T()
        code_field = ft.TextField(label="Codice a 6 caratteri", dense=True,
                                   max_length=6, **d.field_style())
        display_field = ft.TextField(label="Il tuo nome", dense=True, **d.field_style())

        def _join(e):
            code = (code_field.value or "").strip()
            display_name = (display_field.value or "").strip()
            if not code:
                self._show_error("Inserisci il codice d'ingresso.")
                return
            # Stesso controllo di `_attempt()` nel dialogo LAN qui sotto:
            # `join_world_by_code()` ignora già `display_name` se questo
            # `device_id` è già membro del mondo (vedi il suo docstring) —
            # nessuna chiamata di rete qui, stesso DB, quindi il controllo
            # è locale e immediato.
            existing_world = world_repo.get_world_by_join_code(code)
            already_member = (
                existing_world is not None
                and world_repo.get_member(existing_world.id, self.device_id) is not None
            )
            if not display_name and not already_member:
                # Obbligatorio per un ingresso NUOVO (senza, nel registro/
                # Sezione Master diventa impossibile distinguere due
                # giocatori entrambi "senza nome"), nessun ripiego
                # silenzioso — non serve invece per chi è già membro.
                self._show_error("Inserisci il tuo nome prima di entrare nel mondo.")
                return
            remaining = self._network_cooldown_remaining()
            if remaining > 0:
                self._show_error(
                    f"Aspetta {int(remaining) + 1} secondi prima di riprovare a entrare "
                    f"in un mondo."
                )
                return
            self._mark_network_request()
            self._start_network_cooldown_ticker(join_btn, "Unisciti")
            result = world_repo.join_world_by_code(code, self.device_id, display_name)
            self.page.pop_dialog()
            if result is None:
                self._show_error("Nessun mondo trovato con questo codice.")
                return
            world, _member = result
            self._open_detail(world)

        join_btn = ft.ElevatedButton("Unisciti", icon=ft.Icons.LOGIN, on_click=_join,
                                      style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary))

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Unisciti a un mondo", ft.Icons.MEETING_ROOM),
            content=ft.Column([code_field, display_field], tight=True, spacing=d.Space.MD),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                join_btn,
            ]),
        )
        self.page.show_dialog(dlg)
        # Riflette subito un eventuale cooldown già attivo da un tentativo
        # precedente (altro dialogo, QR, ecc.) — se non è attivo il ciclo
        # esce da solo alla prima iterazione, vedi _start_network_cooldown_ticker.
        self._start_network_cooldown_ticker(join_btn, "Unisciti")

    def _open_lan_join_dialog(self):
        """
        Ingresso in un mondo ospitato da un altro dispositivo (§9.3/§9.4)
        — a differenza di "Unisciti con un codice" (che scrive
        direttamente nello STESSO database, valido solo se questo
        dispositivo lo condivide già col mondo: web mode multi-scheda),
        questa parla via rete con `core.world_sync.start_lan_join()`.

        Un dispositivo nuovo resta in attesa dell'approvazione del master:
        il dialogo passa in uno stato "in attesa" con un pulsante
        "Controlla di nuovo" invece di chiudersi, così l'utente non deve
        reinserire indirizzo/codice/PIN una seconda volta.
        """
        p = d.T()
        host_field = ft.TextField(label="Indirizzo IP dell'host", dense=True,
                                   hint_text="es. 192.168.1.7", **d.field_style())
        port_field = ft.TextField(label="Porta", dense=True, value="8765", **d.field_style())
        code_field = ft.TextField(label="Codice a 6 caratteri", dense=True,
                                   max_length=6, **d.field_style())
        pin_field = ft.TextField(label="PIN a 6 cifre", dense=True,
                                  max_length=6, **d.field_style())
        display_field = ft.TextField(label="Il tuo nome", dense=True, **d.field_style())
        # In modalità trasferimento il campo nome resta facoltativo (vedi
        # il commento su `display_name`/`transfer_mode["on"]` in `_attempt()`
        # più sotto) — l'host conserva SEMPRE il nome del membro originale
        # a prescindere da cosa arriva qui, quindi il campo viene nascosto
        # e sostituito da questa spiegazione invece di suggerire all'utente
        # di dover scegliere un nome nuovo.
        display_hint = d.muted(
            "Il tuo nome nel mondo resta quello di sempre — non serve reinserirlo."
        )
        display_hint.visible = False
        status_text = ft.Text("", color=p.danger, size=12)

        # Modalità "cambio dispositivo" (§11.9): il codice di
        # trasferimento prende il posto del PIN. Nasconde il campo PIN invece di
        # limitarsi ad affiancarlo, così non resta ambiguo quale dei due conta.
        transfer_mode: dict = {"on": False}
        transfer_field = ft.TextField(
            label="Codice di trasferimento", dense=True, max_length=8,
            visible=False, **d.field_style(),
        )
        transfer_hint = d.muted(
            "Con il codice di trasferimento non serve il PIN. Il master deve "
            "comunque approvare, e il dispositivo che aveva il personaggio "
            "perderà l'accesso al mondo."
        )
        transfer_hint.visible = False
        retry_btn = ft.TextButton("Controlla di nuovo", icon=ft.Icons.REFRESH,
                                   visible=False)
        # Annulla richiesta — vedi `_PENDING_JOIN_REQUEST_SETTING_KEY`.
        cancel_btn = ft.TextButton("Annulla richiesta", icon=ft.Icons.CANCEL_OUTLINED,
                                    visible=False,
                                    style=ft.ButtonStyle(color=p.danger))
        #: "polling_started": evita di avviare più cicli
        #: di polling automatico sovrapposti se lo stato "in attesa" viene
        #: rientrato più volte (es. `_attempt()` seguito da un
        #: `_retry()` manuale mentre il polling è già in corso) — vedi
        #: `_report()`/`_poll_pending_join_loop` più sotto.
        pending_state: dict = {
            "backend": None, "request_id": "", "host_port": "", "polling_started": False,
        }

        def _save_pending_join() -> None:
            """Persiste `pending_state` in `app_settings` — sopravvive alla
            chiusura del dialogo e al riavvio dell'app, vedi il commento su
            `_PENDING_JOIN_REQUEST_SETTING_KEY`."""
            if not pending_state["request_id"] or not self.device_id:
                return
            settings_repo.set_setting(_PENDING_JOIN_REQUEST_SETTING_KEY, json.dumps({
                "host_port": pending_state["host_port"],
                "request_id": pending_state["request_id"],
                "device_id": self.device_id,
            }))

        def _clear_pending_join() -> None:
            settings_repo.set_setting(_PENDING_JOIN_REQUEST_SETTING_KEY, "")

        def _load_pending_join() -> dict | None:
            """Richiesta salvata da un giro precedente di QUESTO dispositivo
            — `None` se assente, malformata, o di un altro dispositivo
            (cambio identità raro ma non impossibile, es. dopo una
            reinstallazione)."""
            raw = settings_repo.get_setting(_PENDING_JOIN_REQUEST_SETTING_KEY, "")
            if not raw:
                return None
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
            if not isinstance(data, dict) or data.get("device_id") != self.device_id:
                return None
            if not data.get("host_port") or not data.get("request_id"):
                return None
            return data

        discovery_results = ft.Column(spacing=d.Space.XS, tight=True)
        discovery_status = ft.Text("", color=p.text_2, size=12)

        def _pick_discovered(world) -> None:
            host_field.value = world.host
            port_field.value = str(world.port)
            discovery_status.color = p.text_2
            discovery_status.value = (
                f'Rete "{world.name}" selezionata — inserisci ancora codice e PIN.'
            )
            try:
                self.page.update()
            except RuntimeError:
                pass

        def _discovered_row(world) -> ft.Control:
            note = "" if world.accepting else " (non accetta ingressi ora)"
            return ft.Row(
                [
                    d.icon_badge(ft.Icons.WIFI_TETHERING, tone="magic", size=28),
                    ft.Text(f"{world.name} — {world.host}:{world.port}{note}",
                            color=p.text, size=d.Size.BODY_SM, expand=True),
                    ft.TextButton("Usa", on_click=lambda e, w=world: _pick_discovered(w)),
                ],
                spacing=d.Space.XS, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        def _search_nearby(e):
            # Bloccante per la durata della ricerca (§9.3), stesso stile
            # sincrono già usato da _attempt()/_retry() in questo dialogo:
            # nessuna dipendenza async nuova solo per questo pulsante.
            discovery_status.color = p.text_2
            discovery_status.value = "Ricerca in corso…"
            discovery_results.controls = []
            try:
                self.page.update()
            except RuntimeError:
                pass

            from network.discovery import discover_worlds
            found = discover_worlds(timeout=2.5)

            if not found:
                discovery_status.value = (
                    "Nessuna rete trovata nelle vicinanze — verifica di essere sulla "
                    "stessa rete Wi-Fi, o inserisci indirizzo/porta a mano qui sotto."
                )
                discovery_results.controls = []
            else:
                discovery_status.value = f"{len(found)} rete/i trovata/e:"
                discovery_results.controls = [_discovered_row(w) for w in found]
            try:
                self.page.update()
            except RuntimeError:
                pass

        def _report(result, keep_dialog_open_on_pending: bool = True):
            if result.success:
                pending_state["backend"] = None  # ferma il polling automatico, vedi sotto
                _clear_pending_join()
                self.page.pop_dialog()
                assert result.world is not None
                self._open_detail(result.world)
                return
            if result.pending_request_id and keep_dialog_open_on_pending:
                pending_state["backend"] = result.backend
                pending_state["request_id"] = result.pending_request_id
                _save_pending_join()
                status_text.color = p.text_2
                status_text.value = result.error or "In attesa dell'approvazione del master…"
                retry_btn.visible = True
                cancel_btn.visible = True
                # Avvia il polling automatico UNA sola volta per questo
                # dialogo, non ad ogni giro che conferma "ancora in attesa" —
                # così il giocatore non deve premere "Controlla di nuovo"
                # a mano per vedere l'approvazione del master.
                if not pending_state["polling_started"]:
                    pending_state["polling_started"] = True
                    self.page.run_task(_poll_pending_join_loop)
            else:
                # Stato TERMINALE (rifiutato, o un errore che non ha
                # prodotto un nuovo `pending_request_id`): azzerare
                # `pending_state["backend"]` è anche il segnale che ferma
                # `_poll_pending_join_loop` al suo prossimo giro (vedi
                # sotto) — senza, un rifiuto esplicito del master
                # lascerebbe comunque il ciclo attivo a interrogare
                # `poll_join_status` su una richiesta ormai chiusa.
                status_text.color = p.danger
                status_text.value = result.error or "Ingresso fallito."
                retry_btn.visible = False
                cancel_btn.visible = False
                pending_state["backend"] = None
                pending_state["polling_started"] = False
                _clear_pending_join()
            try:
                self.page.update()
            except RuntimeError:
                pass

        async def _poll_pending_join_loop():
            """
            Vedi il docstring di `_PENDING_JOIN_POLL_
            INTERVAL_S`. Ciclo `async` schedulato con `page.run_task()`
            (mai un `threading.Thread`: già dentro il loop asyncio della
            sessione, stesso principio di `_network_cooldown_ticker_loop`
            in questo stesso file), che richiama `finish_pending_join()`
            a intervalli finché lo stato resta "in attesa" — senza
            richiedere all'utente di premere "Controlla di nuovo".

            DELIBERATAMENTE non passa da `_network_cooldown_remaining()`/
            `_mark_network_request()`: quel cancello anti-spam (10s)
            protegge i TENTATIVI di ingresso (`POST /join`, che consumano
            una riga `PendingJoinRequest` sull'host e potrebbero essere
            usati per martellare PIN diversi — vedi `WorldHostServer.
            _check_join_rate_limit`), non un polling passivo di stato
            (`GET /join/status`, che l'host stesso non sottopone a
            nessun limite, per lo stesso motivo: economico e in sola
            lettura — coerenza tra i due lati, stessa scelta già presa
            per `WorldHostServer.join_status()`). Un utente che intanto
            preme "Controlla di nuovo" a mano resta comunque soggetto al
            cooldown come prima: qui si tratta solo il ciclo automatico
            dell'app, non l'azione esplicita dell'utente.

            Si ferma da solo quando `pending_state["backend"]` torna
            `None` — impostato da `_report()` su un esito finale
            (successo/rifiuto/errore) o dal pulsante "Annulla" qui sotto —
            o quando `page.update()` fallisce (dialogo chiuso in altro
            modo). Nessun rischio di ciclo infinito "orfano": è sempre
            legato al ciclo di vita di QUESTO dialogo, non un timer
            globale dell'app.
            """
            while True:
                await asyncio.sleep(_PENDING_JOIN_POLL_INTERVAL_S)
                if pending_state["backend"] is None:
                    return
                # `world_sync.finish_pending_join()` è una chiamata SINCRONA
                # (rete + parecchie scritture SQLite in `_finalize_join()`,
                # una per ogni nota/mappa/personaggio dello snapshot) — se
                # chiamata direttamente dentro questa coroutine, che gira
                # sull'UNICO loop asyncio di Flet, blocca l'INTERA pagina
                # (bottoni compresi) per tutta la sua durata, non solo questo
                # dialogo: su un mondo con tanta storia accumulata la somma
                # di più scritture (ciascuna eventualmente in attesa di un
                # lock SQLite già preso da un altro ciclo di sync in
                # background) può sommarsi a un blocco di parecchi secondi.
                # `asyncio.to_thread` sposta la chiamata bloccante su un
                # thread separato, lasciando il loop (e quindi i bottoni)
                # libero di rispondere nel frattempo — stesso principio già
                # usato da `BackgroundSyncLoop`
                # (`ui/components/background_sync.py`) per lo stesso
                # identico motivo.
                # Senza questo try/except, QUALSIASI eccezione sollevata da
                # `finish_pending_join` — o da `_report`/`_open_detail` dopo un
                # esito riuscito — ucciderebbe questa coroutine in silenzio:
                # `page.run_task()` non ha alcun gestore che la mostri, e il
                # dialogo resterebbe fermo su "In attesa dell'approvazione
                # del master…" per sempre, senza né successo né errore,
                # mentre il mondo risulterebbe comunque registrato al
                # riavvio dell'app perché `_finalize_join()` avrebbe già
                # salvato la replica prima dell'eccezione.
                try:
                    result = await asyncio.to_thread(
                        world_sync.finish_pending_join,
                        pending_state["backend"], pending_state["request_id"],
                        pending_state["host_port"],
                    )
                    _report(result)
                except Exception as ex:
                    logger.exception("Ingresso nel mondo: errore non gestito nel polling")
                    pending_state["backend"] = None
                    pending_state["polling_started"] = False
                    status_text.color = p.danger
                    status_text.value = (
                        f"Errore durante l'ingresso: {type(ex).__name__}: {ex}"
                    )
                    retry_btn.visible = False
                    try:
                        self.page.update()
                    except RuntimeError:
                        pass
                    return
                if pending_state["backend"] is None:
                    return  # _report ha appena risolto lo stato: un giro basta

        def _attempt(e):
            host_addr = (host_field.value or "").strip()
            if not host_addr:
                status_text.color = p.danger
                status_text.value = "Inserisci l'indirizzo dell'host."
                self.page.update()
                return
            try:
                port = int((port_field.value or "8765").strip())
            except ValueError:
                status_text.color = p.danger
                status_text.value = "La porta deve essere un numero."
                self.page.update()
                return
            transfer_code = ((transfer_field.value or "").strip().upper()
                              if transfer_mode["on"] else "")
            if transfer_mode["on"] and not transfer_code:
                status_text.color = p.danger
                status_text.value = "Inserisci il codice di trasferimento."
                self.page.update()
                return
            display_name = (display_field.value or "").strip()
            # Sonda leggera (`GET
            # /world`, nessun side-effect, stesso identico primo passo che
            # `world_sync.start_lan_join()` rifà comunque subito dopo) per
            # sapere se questo dispositivo è già un membro noto di quel
            # mondo PRIMA di obbligare il nome: lato server `handle_join()`
            # ignora comunque `display_name` per un device_id già in
            # `world_members` (rientro immediato, nessuna approvazione), qui
            # si evita solo di bloccare inutilmente la UI su un dato che il
            # server non userebbe.
            already_member = False
            if self.device_id:
                probe = RemoteBackend(host_addr, port, self.device_id)
                info = probe.check_world()
                probed_world_id = str(info.get("world_id", "")) if info else ""
                if probed_world_id:
                    already_member = world_repo.get_member(
                        probed_world_id, self.device_id) is not None
            # In modalità trasferimento il nome NON è obbligatorio (§11.9):
            # si subentra a un membro che ha già un nome, e l'host lo
            # conserva quando il campo arriva vuoto (`display_name or
            # member.display_name` in `_handle_transfer_join`) — cambiare
            # dispositivo non è un rinomino. Se l'utente scrive un nome quello
            # vince: è una scelta esplicita, non un ripiego silenzioso.
            if not display_name and not already_member and not transfer_mode["on"]:
                # Stesso principio di _open_join_dialog qui sopra:
                # obbligatorio senza ripiego silenzioso per un ingresso
                # NUOVO. Protegge anche l'ingresso via QR (_on_qr_scanned
                # chiama questa stessa funzione): se il nome non è ancora
                # stato scritto, l'inquadratura del QR non entra in
                # silenzio come "Giocatore", mostra questo stesso errore —
                # a meno che (sopra) il dispositivo non sia già membro noto
                # di questo mondo, nel qual caso il nome non serve affatto.
                status_text.color = p.danger
                status_text.value = "Inserisci il tuo nome prima di entrare nel mondo."
                self.page.update()
                return
            remaining = self._network_cooldown_remaining()
            if remaining > 0:
                status_text.color = p.danger
                status_text.value = (
                    f"Aspetta {int(remaining) + 1} secondi prima di riprovare a entrare "
                    f"in un mondo."
                )
                self.page.update()
                return
            self._mark_network_request()
            self._start_network_cooldown_ticker(enter_btn, "Entra")
            self._start_network_cooldown_ticker(retry_btn, "Controlla di nuovo")
            pending_state["host_port"] = f"{host_addr}:{port}"
            result = world_sync.start_lan_join(
                host_addr, port, (code_field.value or "").strip(),
                "" if transfer_mode["on"] else (pin_field.value or "").strip(),
                self.device_id or "", display_name,
                transfer_code=transfer_code,
            )
            _report(result)

        async def _retry(e):
            if pending_state["backend"] is None:
                return
            remaining = self._network_cooldown_remaining()
            if remaining > 0:
                status_text.color = p.danger
                status_text.value = (
                    f"Aspetta {int(remaining) + 1} secondi prima di controllare di nuovo."
                )
                self.page.update()
                return
            self._mark_network_request()
            self._start_network_cooldown_ticker(enter_btn, "Entra")
            self._start_network_cooldown_ticker(retry_btn, "Controlla di nuovo")
            # Stesso motivo di `_poll_pending_join_loop`
            # qui sopra: `finish_pending_join()` è sincrona e bloccante,
            # `async def` + `asyncio.to_thread` (Flet chiama direttamente
            # gli handler `async def`, vedi `base_control.py`) evita che un
            # click su "Controlla di nuovo" congeli l'intera pagina per
            # tutta la sua durata.
            # Stesso try/except di `_poll_pending_join_loop` e per lo stesso
            # motivo: un'eccezione in un handler `async def` non arriva a
            # schermo da sola, e lascerebbe il pulsante "Controlla di nuovo"
            # apparentemente senza effetto.
            try:
                result = await asyncio.to_thread(
                    world_sync.finish_pending_join,
                    pending_state["backend"], pending_state["request_id"],
                    pending_state["host_port"],
                )
                _report(result)
            except Exception as ex:
                logger.exception("Ingresso nel mondo: errore non gestito in «Controlla di nuovo»")
                status_text.color = p.danger
                status_text.value = f"Errore durante l'ingresso: {type(ex).__name__}: {ex}"
                try:
                    self.page.update()
                except RuntimeError:
                    pass

        retry_btn.on_click = _retry

        async def _do_cancel(e):
            """Annulla la richiesta in sospeso — riporta il
            dialogo al modulo vuoto invece di chiuderlo, così l'utente può
            inviarne subito una nuova (nome corretto, host diverso...) senza
            doverlo riaprire."""
            backend = pending_state["backend"]
            request_id = pending_state["request_id"]
            pending_state["backend"] = None  # ferma _poll_pending_join_loop
            pending_state["polling_started"] = False
            if backend is not None and request_id:
                try:
                    await asyncio.to_thread(backend.cancel_join_request, request_id)
                except Exception as ex:
                    logger.warning("Annullamento richiesta di ingresso fallito: %s", ex)
            _clear_pending_join()
            pending_state["request_id"] = ""
            pending_state["host_port"] = ""
            status_text.value = ""
            retry_btn.visible = False
            cancel_btn.visible = False
            try:
                self.page.update()
            except RuntimeError:
                pass

        cancel_btn.on_click = _do_cancel

        # Richiesta in sospeso da un giro precedente — riaprendo il
        # dialogo (o riavviando l'app) si ripristina lo stato "in attesa"
        # invece di offrire subito un modulo vuoto, che avrebbe permesso
        # di spammarne una seconda senza ricordo della prima.
        _resumed = _load_pending_join()
        if _resumed is not None and self.device_id:
            host_addr, _, port_text = _resumed["host_port"].rpartition(":")
            host_field.value = host_addr
            port_field.value = port_text
            pending_state["host_port"] = _resumed["host_port"]
            pending_state["request_id"] = _resumed["request_id"]
            pending_state["backend"] = RemoteBackend(
                host_addr, int(port_text) if port_text.isdigit() else 8765,
                self.device_id, world_id="",
            )
            status_text.color = p.text_2
            status_text.value = "Hai già una richiesta di ingresso in sospeso per questo host."
            retry_btn.visible = True
            cancel_btn.visible = True
            pending_state["polling_started"] = True
            self.page.run_task(_poll_pending_join_loop)

        def _set_transfer_mode(on: bool) -> None:
            """
            Entra/esce dalla modalità "cambio dispositivo". Il campo PIN e quello
            del codice di trasferimento si escludono a vicenda: mostrarli
            entrambi lascerebbe ambiguo quale dei due l'host guarderà.
            """
            transfer_mode["on"] = on
            transfer_field.visible = on
            transfer_hint.visible = on
            pin_field.visible = not on
            display_field.visible = not on
            display_hint.visible = on
            transfer_toggle.text = (
                "Torna all'ingresso normale (con PIN)" if on
                else "Ho già un personaggio in questo mondo (cambio dispositivo)"
            )
            try:
                self.page.update()
            except RuntimeError:
                pass

        transfer_toggle = ft.TextButton(
            "Ho già un personaggio in questo mondo (cambio dispositivo)",
            icon=ft.Icons.PHONELINK_SETUP,
            on_click=lambda e: _set_transfer_mode(not transfer_mode["on"]),
            style=ft.ButtonStyle(color=p.text_2),
        )

        def _on_qr_scanned(parsed: dict):
            # Il QR non porta il nome del giocatore (§7 di build_join_text:
            # solo i 4 dati tecnici) — display_field resta quello che
            # l'utente ha già scritto, se l'ha scritto. Compila e tenta
            # subito l'ingresso: "inquadri e sei dentro", non solo
            # "inquadri e poi premi Entra".
            self.page.pop_dialog()  # chiude lo scanner, il dialogo LAN resta sotto
            host_field.value = parsed["host"]
            port_field.value = str(parsed["port"])
            code_field.value = parsed["join_code"]
            # Due formati di QR possibili (§11.9), distinti da `kind`
            # (vedi `network.qr_join.parse_any_join_text`): quello d'ingresso
            # porta il PIN, quello di trasferimento porta il codice di
            # trasferimento e attiva da sé la modalità corrispondente — così
            # "inquadri e sei dentro" vale anche per il cambio dispositivo,
            # senza dover prima premere il pulsante giusto.
            if parsed.get("kind") == "transfer":
                _set_transfer_mode(True)
                transfer_field.value = parsed["transfer_code"]
            else:
                _set_transfer_mode(False)
                pin_field.value = parsed["pin"]
            try:
                self.page.update()
            except RuntimeError:
                pass
            _attempt(None)

        def _on_qr_cancel():
            self.page.pop_dialog()  # chiude solo lo scanner, il dialogo LAN resta sotto

        def _open_qr_scan(e):
            scan_dlg = ft.AlertDialog(
                modal=True,
                title=d.dialog_title("Scansiona QR", ft.Icons.QR_CODE_SCANNER, tone="magic"),
                content=ft.Container(
                    content=QrScannerView(on_scanned=_on_qr_scanned, on_cancel=_on_qr_cancel),
                    width=340,
                ),
            )
            self.page.show_dialog(scan_dlg)

        qr_row: list[ft.Control] = []
        if qr_scanner_supported(self.page):
            qr_row.append(
                d.pill(ft.Icons.QR_CODE_SCANNER, "Scansiona QR", filled=True, color=p.magic,
                       on_click=_open_qr_scan),
            )

        enter_btn = ft.ElevatedButton("Entra", icon=ft.Icons.WIFI, on_click=_attempt,
                                       style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary))

        def _cancel(e):
            # Azzerare `pending_state["backend"]` PRIMA di
            # chiudere il dialogo è ciò che ferma `_poll_pending_join_loop`
            # al suo prossimo risveglio (entro `_PENDING_JOIN_POLL_
            # INTERVAL_S`) — senza, il ciclo continuerebbe a interrogare
            # l'host per una richiesta il cui dialogo l'utente ha già
            # chiuso (innocuo — `page.update()` fallirebbe comunque con
            # `RuntimeError`, già gestito — ma un giro di rete evitabile).
            pending_state["backend"] = None
            self.page.pop_dialog()

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Unisciti in LAN", ft.Icons.WIFI),
            content=ft.Column(
                [
                    d.muted(
                        "Chiedi al master l'indirizzo IP, la porta (di norma 8765), il "
                        "codice a 6 caratteri del mondo e il PIN mostrato sul suo schermo — "
                        "oppure inquadra il suo QR d'ingresso.",
                    ),
                    *qr_row,
                    d.pill(ft.Icons.WIFI_FIND, "Cerca reti nelle vicinanze", color=p.magic,
                           on_click=_search_nearby),
                    discovery_status,
                    discovery_results,
                    ft.Divider(height=1),
                    host_field, port_field, code_field,
                    pin_field, transfer_field, transfer_hint, transfer_toggle,
                    display_field, display_hint,
                    status_text, retry_btn, cancel_btn,
                ],
                tight=True, spacing=d.Space.SM, scroll=ft.ScrollMode.AUTO,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=_cancel,
                              style=ft.ButtonStyle(color=p.text_2)),
                enter_btn,
            ]),
        )
        self.page.show_dialog(dlg)
        # Stesso principio di _open_join_dialog: riflette subito un
        # eventuale cooldown già attivo (es. appena usciti dall'altro
        # dialogo di ingresso) — esce da solo se non c'è nulla da mostrare.
        self._start_network_cooldown_ticker(enter_btn, "Entra")
        self._start_network_cooldown_ticker(retry_btn, "Controlla di nuovo")

    # ------------------------------------------------------------------
    # Errori
    # ------------------------------------------------------------------

    def _show_error(self, message: str):
        """Riusa `ui.widgets.show_snack()`, che centralizza questo stesso
        pattern anche in `home_view.py` — un solo posto dove il pattern
        SnackBar può disallinearsi."""
        show_snack(self.page, message, tone="danger")
