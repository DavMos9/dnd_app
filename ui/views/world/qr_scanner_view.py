"""
Scansione QR per l'ingresso in un mondo LAN — passo 5 di
`dnd_app/docs/multiplayer_design.md` §9.3 ("Scoperta e comodità"),
2026-08-06, sessione successiva a quella che aveva implementato solo la
GENERAZIONE lato host (`network/qr_join.py`).

Richiesta esplicita di Davide: "inquadri il QR code e sei dentro" — un
vero mirino live con riconoscimento automatico, non uno scatto singolo.
Reso possibile da due pacchetti UFFICIALI del team Flet (non un'estensione
scritta per questo progetto, a differenza di `flet_image_picker`):

- `flet-camera` — anteprima live + streaming dei fotogrammi
  (`start_image_stream()`/`on_stream_image`), potenza del pacchetto
  Flutter ufficiale `camera`. Copertura piattaforma: iOS + Android + Web,
  NON Windows/macOS/Linux (verificato su PyPI/flet.dev prima di scrivere
  questo modulo) — per questo il pulsante che apre questa view va mostrato
  SOLO su Android/iOS (`page.platform`), mai su desktop: vedi
  `ui/views/world/world_view.py::_open_lan_join_dialog`.
- `pyzbar` — decodifica QR dei singoli fotogrammi JPEG. Scelto (invece di
  scrivere un'estensione nativa attorno a `mobile_scanner`, l'alternativa
  valutata) perché elencato tra i pacchetti binari GIÀ pre-compilati per
  Android/iOS su pypi.flet.dev (dipendenza nativa `flet-libzbar`,
  verificato su https://flet.dev/docs/reference/binary-packages-android-ios
  prima di sceglierlo) — nessuna incognita di packaging nativo come lo era
  stata `flet_image_picker` (due giri di build CI falliti prima di
  funzionare, vedi changelog_storico.md).

Il permesso fotocamera è richiesto a runtime con `flet-permission-handler`
(pacchetto ufficiale a sé, la documentazione di flet-camera lo raccomanda
esplicitamente prima di inizializzare il controllo).

⚠️ Non verificabile da questo sandbox: nessuna fotocamera reale, nessun
toolchain di build Android/iOS, e `pyzbar` richiede la libreria nativa
`libzbar` che qui non è installabile (l'ambiente non ha permessi di root).
Il parsing del testo QR (`network.qr_join.parse_any_join_text`, che riconosce
sia il QR d'ingresso sia quello di trasferimento del personaggio su un altro
dispositivo — §11.9) è testato in isolamento in `test_scoperta_lan.py` e
`test_trasferimento_dispositivo.py`; il ciclo vero fotocamera → pyzbar →
ingresso può essere verificato solo da Davide su un dispositivo Android/iOS
reale — è esattamente il tipo di limite già documentato per il resto del
Multiplayer (§15 del design doc).
"""

from __future__ import annotations

import io
import logging

import flet as ft

from network.qr_join import parse_any_join_text
from ui import design as d

logger = logging.getLogger(__name__)

try:
    import flet_camera as fc
except ImportError:  # pragma: no cover — pacchetto non installato in questo ambiente
    fc = None  # type: ignore[assignment]

try:
    import flet_permission_handler as fph
except ImportError:  # pragma: no cover
    fph = None  # type: ignore[assignment]


def qr_scanner_supported(page: ft.Page) -> bool:
    """
    True solo se questa piattaforma può davvero mostrare il mirino live
    (Android/iOS, `flet-camera` non supporta desktop) E i due pacchetti
    sono importabili — usata da `world_view.py` per decidere se mostrare
    il pulsante "Scansiona QR", mai un pulsante che apre una view destinata
    a fallire subito.
    """
    if fc is None or fph is None:
        return False
    return page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)


class QrScannerView(ft.Column):
    """
    Mirino live per l'ingresso in un mondo LAN via QR.

    Callbacks:
        on_scanned(parsed: dict)  → un QR valido è stato letto (stessa forma di
                                     ritorno di
                                     `network.qr_join.parse_any_join_text`,
                                     quindi con `kind` = "join" | "transfer").
                                     Il chiamante decide cosa farne (di
                                     norma: chiudere il dialogo, compilare
                                     i campi, avviare l'ingresso) — questa
                                     view non conosce il resto del dialogo.
        on_cancel()                → l'utente ha annullato, torna al form manuale.
    """

    def __init__(self, on_scanned, on_cancel):
        super().__init__(expand=True, spacing=d.Space.SM, tight=True)
        self.on_scanned = on_scanned
        self.on_cancel = on_cancel

        self._camera: "fc.Camera | None" = None
        self._permission_handler: "fph.PermissionHandler | None" = None
        self._stream_started = False
        self._decoding = False
        self._done = False

        p = d.T()
        self._status = ft.Text("Avvio della fotocamera…", size=d.Size.BODY_SM, color=p.text_2)
        self._preview_overlay = ft.Container(
            alignment=ft.Alignment.CENTER,
            content=ft.ProgressRing(color=p.magic, width=32, height=32),
        )
        self._build()

    # ------------------------------------------------------------------
    # Ciclo di vita
    # ------------------------------------------------------------------

    def did_mount(self):
        page = self.page
        if page is not None:
            page.run_task(self._start)

    def will_unmount(self):
        # La fotocamera va sempre rilasciata esplicitamente all'uscita da
        # questa view (annullamento, scansione riuscita, o semplice
        # chiusura del dialogo) — altrimenti resta occupata anche dopo,
        # bloccando un tentativo successivo. `page.run_task` è "fire and
        # forget": non c'è più una page a cui attendere una risposta a
        # questo punto del ciclo di vita.
        page = self.page
        if page is not None and self._camera is not None:
            try:
                page.run_task(self._stop_stream)
            except RuntimeError:
                pass

    def _build(self):
        p = d.T()
        self.controls = [
            ft.Container(
                height=320,
                bgcolor=ft.Colors.BLACK,
                border_radius=d.Radius.MD,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Stack([]),  # popolato in _start() con fc.Camera
            ),
            self._status,
            ft.Row(
                [d.pill(ft.Icons.CLOSE, "Annulla", color=p.text_2,
                        on_click=lambda e: self.on_cancel())],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]

    def _set_status(self, text: str, *, is_error: bool = False):
        p = d.T()
        self._status.value = text
        self._status.color = p.danger if is_error else p.text_2
        try:
            self.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Avvio fotocamera
    # ------------------------------------------------------------------

    async def _start(self):
        page = self.page
        if page is None:
            return

        if fc is None or fph is None:
            self._set_status(
                "Scanner QR non disponibile in questa build (pacchetti mancanti).",
                is_error=True,
            )
            return

        # Permesso a runtime — richiesto esplicitamente prima di
        # inizializzare il controllo, come raccomandato dalla
        # documentazione ufficiale di flet-camera.
        self._permission_handler = fph.PermissionHandler()
        try:
            status = await self._permission_handler.request(fph.Permission.CAMERA)
        except Exception as e:
            logger.error("Richiesta permesso fotocamera fallita: %s", e)
            self._set_status(f"Permesso fotocamera non ottenuto: {e}", is_error=True)
            return
        if status != fph.PermissionStatus.GRANTED:
            self._set_status(
                "Permesso fotocamera negato — consentilo nelle impostazioni "
                "del telefono per usare lo scanner, oppure inserisci i dati a mano.",
                is_error=True,
            )
            return

        camera = fc.Camera(expand=True, preview_enabled=True, content=self._preview_overlay)
        camera.on_state_change = self._on_state_change
        camera.on_stream_image = self._on_frame
        self._camera = camera

        container = self.controls[0]
        container.content = ft.Stack([camera])
        try:
            self.update()
        except RuntimeError:
            pass

        try:
            cameras = await camera.get_available_cameras()
        except Exception as e:
            logger.error("Enumerazione fotocamere fallita: %s", e)
            self._set_status(f"Impossibile accedere alla fotocamera: {e}", is_error=True)
            return
        if not cameras:
            self._set_status("Nessuna fotocamera trovata su questo dispositivo.", is_error=True)
            return

        chosen = next(
            (c for c in cameras if c.lens_direction == fc.CameraLensDirection.BACK),
            cameras[0],
        )

        try:
            await camera.initialize(
                description=chosen,
                resolution_preset=fc.ResolutionPreset.MEDIUM,
                enable_audio=False,
                image_format_group=fc.ImageFormatGroup.JPEG,
            )
        except Exception as e:
            logger.error("Inizializzazione fotocamera fallita: %s", e)
            self._set_status(f"Inizializzazione della fotocamera fallita: {e}", is_error=True)
            return

        try:
            supports_streaming = await camera.supports_image_streaming()
        except Exception as e:
            logger.error("supports_image_streaming() fallita: %s", e)
            supports_streaming = False
        if not supports_streaming:
            self._set_status(
                "Questo dispositivo non supporta la scansione live — "
                "inserisci i dati a mano.",
                is_error=True,
            )
            return

        try:
            await camera.start_image_stream()
        except Exception as e:
            logger.error("Avvio dello stream fotocamera fallito: %s", e)
            self._set_status(f"Avvio della scansione fallito: {e}", is_error=True)
            return

        self._stream_started = True
        self._set_status("Inquadra il codice QR mostrato dal master.")

    async def _stop_stream(self):
        if self._camera is None or not self._stream_started:
            return
        try:
            await self._camera.stop_image_stream()
        except Exception as e:
            logger.debug("stop_image_stream() (ignorato, probabile già fermo): %s", e)
        self._stream_started = False

    def _on_state_change(self, e: "fc.CameraStateEvent"):
        if self._done:
            return
        if getattr(e, "has_error", False):
            self._set_status(f"Errore fotocamera: {e.error_description}", is_error=True)

    # ------------------------------------------------------------------
    # Decodifica dei fotogrammi
    # ------------------------------------------------------------------

    def _on_frame(self, e: "fc.CameraImageEvent"):
        if self._done or self._decoding:
            return  # scarta il fotogramma: una decodifica è già in corso
        if getattr(e, "encoded_format", "") not in ("jpeg", "jpg"):
            return  # formato inatteso per questo fotogramma, salta senza errore

        self._decoding = True
        try:
            parsed = self._try_decode(e.bytes)
        finally:
            self._decoding = False

        if parsed is not None and not self._done:
            self._done = True
            page = self.page
            if page is not None:
                page.run_task(self._stop_stream)
            self.on_scanned(parsed)

    @staticmethod
    def _try_decode(raw: bytes) -> dict | None:
        """
        Pura funzione di decodifica — nessuno stato di `self`, testabile a
        parte se in futuro serve un test con un vero fotogramma sintetico
        (oggi non testabile in questo sandbox: `pyzbar` richiede la
        libreria nativa `libzbar`, non installabile qui senza permessi di
        root — vedi il docstring del modulo).
        """
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode as zbar_decode
        except ImportError as e:
            logger.error("pyzbar/Pillow non disponibili per la decodifica QR: %s", e)
            return None

        try:
            img = Image.open(io.BytesIO(raw))
        except Exception:
            return None  # fotogramma non decodificabile come JPEG, salta

        try:
            results = zbar_decode(img)
        except Exception as e:
            logger.debug("Decodifica QR del fotogramma fallita: %s", e)
            return None

        for result in results:
            try:
                text = result.data.decode("utf-8", errors="replace")
            except Exception:
                continue
            # `parse_any_join_text` (2026-08-17, §11.9) riconosce sia il QR
            # d'ingresso normale sia quello di trasferimento del personaggio su
            # un altro dispositivo, e dichiara quale ha letto in `kind`. Un QR
            # di nessuno dei due formati continua a dare None → "QR non
            # riconosciuto", comportamento invariato.
            parsed = parse_any_join_text(text)
            if parsed is not None:
                return parsed
        return None
