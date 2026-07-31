"""
Pannello dei tiri di dado — componente condiviso da tutta la scheda.

Fase 4, feature 1 (vedi `docs/feature_design_2026_07_26.md`). Rende tirabile
qualunque valore già mostrato sulla scheda: abilità, tiri salvezza, prove di
caratteristica, attacchi e danni delle armi, iniziativa, TS contro morte, dadi
vita, attacco con incantesimo.

**Perché un pannello e non un dialog**: al tavolo serve vedere l'ultimo tiro
mentre si continua a leggere la scheda. Un `AlertDialog` è modale e va chiuso
prima di poter fare altro. Il pannello vive invece in `page.overlay` come
`ft.Container` **posizionato** (`right`/`bottom`, verificati esistenti su
`flet==0.85.3`): occupa solo il proprio riquadro in basso a destra, quindi il
resto della scheda resta cliccabile, e sopravvive alla ricostruzione delle view
perché è agganciato alla pagina, non all'albero della vista.

**Storico solo in sessione** (scelta di Davide, 2026-07-30): nessuna tabella,
nessun DB che cresce a ogni tiro. Gli ultimi tiri restano finché l'app è aperta.

Vantaggio e svantaggio non si scelgono *prima* del tiro: si tira normale (il
caso di gran lunga più frequente, un click) e il pannello offre "Ritira con
vantaggio"/"con svantaggio" — così non c'è uno stato da ricordarsi di
riportare a Normale, e non si deve decidere prima di sapere se serve.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import flet as ft

from core import dice as dice_engine
from core.character_stats import RollSpec
from ui import design as d

logger = logging.getLogger(__name__)

#: Numero di tiri mostrati nello storico del pannello.
_HISTORY_LIMIT = 6

#: Un pannello per pagina. Chiave: `id(page)` — le sessioni web hanno pagine
#: distinte e non devono condividere lo storico.
_PANELS: dict[int, "RollPanel"] = {}


class RollPanel:
    """Pannello persistente in `page.overlay`. Non è un `ft.Control`."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.history: list[tuple[RollSpec, dice_engine.RollResult]] = []
        self._last_spec: RollSpec | None = None
        self._on_result: Callable[[RollSpec, dice_engine.RollResult], None] | None = None
        self._body = ft.Column(spacing=d.Space.SM, tight=True)
        self.container = ft.Container(
            content=self._body,
            right=16, bottom=16, width=300,
            padding=d.Space.LG,
            bgcolor=d.T().surface,
            border_radius=d.Radius.LG,
            shadow=d.elevation(3),
            border=ft.Border.only(left=ft.BorderSide(3, d.T().primary)),
            visible=False,
            animate_opacity=ft.Animation(d.Duration.FAST, d.CURVE),
        )

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def roll(self, spec: RollSpec, advantage: str = "normal",
             on_result: Callable[[RollSpec, dice_engine.RollResult], None] | None = None
             ) -> dice_engine.RollResult | None:
        """
        Esegue il tiro descritto da `spec` e lo mostra. Ritorna il risultato,
        o `None` se la formula non è interpretabile (caso che può nascere solo
        da un dato di gioco malformato, es. un'arma homebrew con un dado
        scritto a mano: si logga e non si rompe la scheda).
        """
        try:
            result = dice_engine.roll(spec.formula, advantage=advantage,
                                      modifier=spec.modifier)
        except ValueError as e:
            logger.error(f"Formula non tirabile per {spec.label!r}: {e}")
            return None

        self._last_spec = spec
        self._on_result = on_result
        self.history.insert(0, (spec, result))
        del self.history[_HISTORY_LIMIT:]
        self._render(spec, result)
        if on_result is not None:
            try:
                on_result(spec, result)
            except Exception as e:   # un side effect rotto non deve mangiare il tiro
                logger.error(f"Effetto collaterale del tiro {spec.label!r} fallito: {e}")
        return result

    def close(self, e: Any = None):
        self.container.visible = False
        _safe_update(self.container)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, spec: RollSpec, result: dice_engine.RollResult):
        p = d.T()
        total_color = p.text
        badge: ft.Control | None = None
        # Con un 1 o un 20 naturale il modificatore non viene sommato: il tiro
        # è già deciso, e mostrare "1 +7 = 8" sarebbe fuorviante. Si mostra il
        # dado naturale e lo si etichetta (richiesta di Davide, 2026-07-30).
        shown_total = result.total
        if result.is_crit:
            total_color = p.success
            badge = d.chip("SUCCESSO CRITICO", "success")
            shown_total = 20
        elif result.is_crit_fail:
            total_color = p.danger
            badge = d.chip("FALLIMENTO CRITICO", "danger")
            shown_total = 1

        adv_label = ""
        if result.advantage != "normal":
            adv_label = dice_engine.ADVANTAGE_LABELS[result.advantage]

        header = ft.Row(
            [
                ft.Icon(ft.Icons.CASINO, size=16, color=p.primary),
                ft.Container(width=d.Space.SM),
                ft.Container(
                    content=ft.Text(spec.label, size=d.Size.BODY_SM,
                                    weight=ft.FontWeight.BOLD, color=p.text,
                                    font_family=d.Font.BODY, no_wrap=True,
                                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    expand=True,
                ),
                ft.IconButton(ft.Icons.CLOSE, icon_size=16, icon_color=p.text_3,
                              tooltip="Chiudi", on_click=self.close),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        total_row = ft.Row(
            [
                ft.Text(str(shown_total), size=44, weight=ft.FontWeight.BOLD,
                        color=total_color, font_family=d.Font.MONO),
                ft.Container(width=d.Space.MD),
                ft.Column(
                    [c for c in (
                        badge,
                        ft.Text(adv_label, size=d.Size.LABEL, color=p.magic,
                                weight=ft.FontWeight.BOLD) if adv_label else None,
                    ) if c is not None],
                    spacing=2, tight=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0,
        )

        lines: list[ft.Control] = [header, total_row]

        formula_txt = spec.formula
        if spec.modifier:
            formula_txt += f" {spec.modifier_str}"
        if result.is_crit or result.is_crit_fail:
            detail_txt = (f"{formula_txt}  →  dado naturale {shown_total} "
                          "(il modificatore non si applica)")
        else:
            detail_txt = f"{formula_txt}  →  {result.detail()}"
        lines.append(ft.Text(detail_txt, size=d.Size.LABEL, color=p.text_2,
                             font_family=d.Font.MONO))
        if spec.note:
            lines.append(ft.Text(spec.note, size=d.Size.LABEL, color=p.text_3,
                                 italic=True))
        if spec.dc and not (result.is_crit or result.is_crit_fail):
            ok = result.total >= spec.dc
            lines.append(ft.Text(
                f"CD {spec.dc} — {'successo' if ok else 'fallimento'}",
                size=d.Size.BODY_SM, weight=ft.FontWeight.BOLD,
                color=p.success if ok else p.danger,
            ))
        if spec.damage_type:
            lines.append(ft.Text(f"Danni: {spec.damage_type}", size=d.Size.LABEL,
                                 color=p.text_3))

        # Vantaggio/svantaggio solo dove ha senso (PHB: tiri di d20).
        if spec.is_d20:
            lines.append(ft.Row(
                [
                    ft.TextButton("Vantaggio", icon=ft.Icons.ARROW_UPWARD,
                                  on_click=lambda e: self.roll(spec, "advantage",
                                                               self._on_result)),
                    ft.TextButton("Svantaggio", icon=ft.Icons.ARROW_DOWNWARD,
                                  on_click=lambda e: self.roll(spec, "disadvantage",
                                                               self._on_result)),
                ],
                spacing=0, wrap=True,
            ))

        if len(self.history) > 1:
            lines.append(ft.Divider(height=1, color=p.border))
            for hs, hr in self.history[1:]:
                h_total = 20 if hr.is_crit else (1 if hr.is_crit_fail else hr.total)
                lines.append(ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(hs.label, size=d.Size.LABEL,
                                            color=p.text_3, no_wrap=True,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS),
                            expand=True,
                        ),
                        ft.Text(str(h_total), size=d.Size.LABEL,
                                weight=ft.FontWeight.BOLD,
                                color=(p.success if hr.is_crit else
                                       p.danger if hr.is_crit_fail else p.text_2),
                                font_family=d.Font.MONO),
                    ],
                    spacing=d.Space.SM,
                ))

        self._body.controls.clear()
        self._body.controls.extend(lines)
        # I colori vengono da `d.T()` alla costruzione: riallineo il contenitore
        # a ogni tiro, così il pannello segue anche un cambio di tema.
        self.container.bgcolor = p.surface
        self.container.border = ft.Border.only(left=ft.BorderSide(3, p.primary))
        self.container.shadow = d.elevation(3)
        self.container.visible = True
        _safe_update(self.container)


# ---------------------------------------------------------------------------
# API di modulo
# ---------------------------------------------------------------------------


def get_panel(page: ft.Page | None) -> RollPanel | None:
    """Pannello della pagina, creandolo e montandolo in overlay al primo uso."""
    if page is None:
        return None
    key = id(page)
    panel = _PANELS.get(key)
    if panel is None or panel.container not in getattr(page, "overlay", []):
        panel = RollPanel(page)
        _PANELS[key] = panel
        try:
            page.overlay.append(panel.container)
            page.update()
        except Exception as e:
            logger.error(f"Impossibile montare il pannello dei tiri: {e}")
            return None
    return panel


def show_roll(page: ft.Page | None, spec: RollSpec, advantage: str = "normal",
              on_result: Callable[[RollSpec, dice_engine.RollResult], None] | None = None
              ) -> dice_engine.RollResult | None:
    """Tira e mostra. Sicura anche se la pagina non è ancora disponibile."""
    panel = get_panel(page)
    if panel is None:
        return None
    return panel.roll(spec, advantage, on_result)


def roll_button(spec_factory: Callable[[], RollSpec | None],
                page_getter: Callable[[], ft.Page | None],
                *, tooltip: str | None = None, icon_size: int = 17,
                color: str | None = None,
                on_result: Callable[[RollSpec, dice_engine.RollResult], None] | None = None
                ) -> ft.IconButton:
    """
    Pulsantino dado da affiancare a un valore già mostrato sulla scheda.

    `spec_factory` è una funzione e non un `RollSpec` già pronto: i modificatori
    cambiano quando il giocatore modifica le caratteristiche o equipaggia
    un'arma, e la riga potrebbe non essere ricostruita nel frattempo — così il
    tiro usa sempre i valori attuali.

    Scelta deliberata di un pulsante dedicato invece di rendere cliccabile
    l'intera riga: molte righe hanno già un `on_click` proprio (modifica,
    dettaglio), e un'icona esplicita rispetta la regola "nulla di nascosto".
    """
    def _do(e: Any):
        spec = spec_factory()
        if spec is None:
            return
        show_roll(page_getter(), spec, "normal", on_result)

    return ft.IconButton(
        ft.Icons.CASINO_OUTLINED,
        icon_size=icon_size,
        icon_color=color or d.T().primary,
        tooltip=tooltip or "Tira",
        on_click=_do,
        padding=ft.Padding.all(2),
    )


def _safe_update(control: ft.Control) -> None:
    """`.update()` con guardia: il controllo può non essere ancora montato."""
    try:
        control.update()
    except (RuntimeError, AssertionError):
        pass
