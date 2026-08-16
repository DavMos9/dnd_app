"""
dice_view.py — Roller visivo per dadi D&D 5e.

Sezione standalone: nessun DB, stato solo in sessione.
Dadi supportati: d4, d6, d8, d10, d12, d20, d100.
"""

from __future__ import annotations

import random
import logging
from typing import Any

import flet as ft
from ui.theme import title_text, label_text, section_header
from ui import design

logger = logging.getLogger(__name__)

_DICE = [4, 6, 8, 10, 12, 20, 100]

_ADV_LABELS = {
    "normal":       "Normale",
    "advantage":    "Vantaggio",
    "disadvantage": "Svantaggio",
}


class DiceView(ft.Column):
    """
    Vista roller dadi.
    Input:  nessuno (standalone).
    Output: risultati in sessione (nessun DB).
    """

    def __init__(self) -> None:
        super().__init__(
            expand=True,
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        )
        # Stato
        self._selected_die: int = 20
        self._count: int = 1
        self._modifier: int = 0
        self._adv_mode: str = "normal"
        self._history: list[dict[str, Any]] = []

        # Widget refs aggiornabili
        self._die_buttons: dict[int, ft.ElevatedButton] = {}
        self._count_label  = ft.Text("1",  size=26, weight=ft.FontWeight.BOLD, color=design.T().text)
        self._mod_label    = ft.Text("+0", size=26, weight=ft.FontWeight.BOLD, color=design.T().text)
        self._adv_btns:    dict[str, ft.TextButton] = {}
        self._adv_row:     ft.Row | None = None
        self._result_text  = ft.Text("—",  size=80, weight=ft.FontWeight.BOLD, color=design.T().primary)
        self._detail_text  = ft.Text("",   size=14, color=design.T().text_2, italic=True)
        self._history_col  = ft.Column(spacing=4)

        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # --- Dado selector ---
        die_row_controls: list[ft.Control] = []
        for d in _DICE:
            btn = ft.ElevatedButton(
                f"d{d}",
                on_click=lambda e, die=d: self._select_die(die),
                style=self._die_style(d),
            )
            self._die_buttons[d] = btn
            die_row_controls.append(btn)

        # --- Vantaggio/Svantaggio (d20 only) ---
        adv_controls: list[ft.Control] = []
        for mode, label in _ADV_LABELS.items():
            btn = ft.TextButton(
                label,
                on_click=lambda e, m=mode: self._set_adv(m),
                style=self._adv_style(mode),
            )
            self._adv_btns[mode] = btn
            adv_controls.append(btn)

        self._adv_row = ft.Row(
            adv_controls,
            alignment=ft.MainAxisAlignment.CENTER,
            visible=(self._selected_die == 20),
            wrap=True,
        )

        # --- Layout principale ---
        self.controls.clear()
        self.controls.append(
            ft.Container(
                expand=True,
                bgcolor=design.T().bg,
                padding=ft.Padding.all(24),
                content=ft.Column(
                    [
                        # Titolo
                        ft.Container(
                            content=title_text("Lancia i Dadi", size=22),
                            padding=ft.Padding.only(bottom=16),
                        ),

                        # Selezione dado
                        section_header("Tipo di Dado"),
                        ft.Container(height=10),
                        ft.Row(die_row_controls, wrap=True, spacing=8),
                        ft.Container(height=20),

                        # Numero dadi + modificatore — wrap=True: su schermi stretti/
                        # smartphone i due blocchi vanno a capo invece di uscire dal
                        # bordo della finestra (bug report Davide, 2026-07-24).
                        ft.Row(
                            [
                                self._spinner_block("Numero Dadi", self._count_label,
                                                    lambda e: self._change_count(-1),
                                                    lambda e: self._change_count(1)),
                                self._spinner_block("Modificatore", self._mod_label,
                                                    lambda e: self._change_mod(-1),
                                                    lambda e: self._change_mod(1)),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=32,
                            wrap=True,
                        ),
                        ft.Container(height=12),

                        # Vantaggio (solo d20)
                        self._adv_row,
                        ft.Container(height=20),

                        # Pulsante Lancia
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "🎲   LANCIA",
                                    on_click=self._roll,
                                    style=ft.ButtonStyle(
                                        bgcolor=design.T().primary_fill,
                                        color=design.T().on_primary_fill,
                                        padding=ft.Padding.symmetric(horizontal=48, vertical=18),
                                    ),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.Container(height=28),

                        # Risultato
                        ft.Row(
                            [
                                ft.Column(
                                    [self._result_text, self._detail_text],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.Divider(color=design.T().border, height=32),

                        # Cronologia
                        section_header("Cronologia Sessione"),
                        ft.Container(height=8),
                        self._history_col,
                        ft.Container(height=24),
                    ],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
            )
        )

    # ------------------------------------------------------------------
    # Interazioni
    # ------------------------------------------------------------------

    def _select_die(self, die: int) -> None:
        old = self._selected_die
        self._selected_die = die
        self._die_buttons[old].style = self._die_style(old)
        self._die_buttons[die].style = self._die_style(die)
        try:
            self._die_buttons[old].update()
            self._die_buttons[die].update()
        except RuntimeError:
            pass
        # Mostra/nasconde riga vantaggio
        if self._adv_row is not None:
            self._adv_row.visible = (die == 20)
            try:
                self._adv_row.update()
            except RuntimeError:
                pass

    def _change_count(self, delta: int) -> None:
        self._count = max(1, min(20, self._count + delta))
        self._count_label.value = str(self._count)
        try:
            self._count_label.update()
        except RuntimeError:
            pass

    def _change_mod(self, delta: int) -> None:
        self._modifier = max(-20, min(20, self._modifier + delta))
        sign = "+" if self._modifier >= 0 else ""
        self._mod_label.value = f"{sign}{self._modifier}"
        try:
            self._mod_label.update()
        except RuntimeError:
            pass

    def _set_adv(self, mode: str) -> None:
        self._adv_mode = mode
        for m, btn in self._adv_btns.items():
            btn.style = self._adv_style(m)
            try:
                btn.update()
            except RuntimeError:
                pass

    def _roll(self, e: Any) -> None:
        d = self._selected_die
        total: int
        label: str
        detail: str
        result_color: str

        if d == 20 and self._adv_mode != "normal":
            r1, r2 = random.randint(1, 20), random.randint(1, 20)
            if self._adv_mode == "advantage":
                chosen = max(r1, r2)
                adv_str = f"vant. ({r1}, {r2})"
            else:
                chosen = min(r1, r2)
                adv_str = f"svant. ({r1}, {r2})"
            total = chosen + self._modifier
            mod_str = (f" {'+' if self._modifier > 0 else ''}{self._modifier}"
                       if self._modifier != 0 else "")
            detail = f"{adv_str}{mod_str}"
            label = f"1d20 [{_ADV_LABELS[self._adv_mode][:4]}]{mod_str}"
            result_color = (design.T().success if chosen == 20
                            else design.T().primary if chosen == 1
                            else design.T().text)
        else:
            rolls = [random.randint(1, d) for _ in range(self._count)]
            total = sum(rolls) + self._modifier
            mod_str = (f" {'+' if self._modifier > 0 else ''}{self._modifier}"
                       if self._modifier != 0 else "")
            rolls_str = ", ".join(str(r) for r in rolls)
            detail = f"({rolls_str}){mod_str}"
            label = (f"{self._count}d{d}{mod_str}" if self._count > 1
                     else f"d{d}{mod_str}")
            # Critico/fallimento critico solo su d20 singolo
            if d == 20 and self._count == 1:
                result_color = (design.T().success if rolls[0] == 20
                                else design.T().primary if rolls[0] == 1
                                else design.T().text)
            else:
                result_color = design.T().text

        self._result_text.value = str(total)
        self._result_text.color = result_color
        self._detail_text.value = f"{label}  →  {detail}"
        try:
            self._result_text.update()
            self._detail_text.update()
        except RuntimeError:
            pass

        # Aggiorna cronologia
        self._history.insert(0, {"label": label, "total": total, "detail": detail})
        if len(self._history) > 15:
            self._history.pop()
        self._rebuild_history()

    # ------------------------------------------------------------------
    # Helpers UI
    # ------------------------------------------------------------------

    def _rebuild_history(self) -> None:
        self._history_col.controls.clear()
        for entry in self._history:
            self._history_col.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(entry["label"], size=13,
                                    color=design.T().text_2, expand=True),
                            ft.Text(str(entry["total"]), size=16,
                                    weight=ft.FontWeight.BOLD, color=design.T().text),
                            ft.Text(f"  {entry['detail']}", size=11,
                                    color=design.T().text_3),
                        ],
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                    bgcolor=design.T().surface,
                    shadow=design.elevation(1),
                    border_radius=ft.BorderRadius.all(4),
                    margin=ft.Margin.only(bottom=4),
                )
            )
        try:
            self._history_col.update()
        except RuntimeError:
            pass

    @staticmethod
    def _spinner_block(
        title: str,
        value_widget: ft.Text,
        on_minus: Any,
        on_plus: Any,
    ) -> ft.Column:
        return ft.Column(
            [
                label_text(title, size=11),
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                      icon_size=22, icon_color=design.T().text_2,
                                      on_click=on_minus),
                        value_widget,
                        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE,
                                      icon_size=22, icon_color=design.T().text_2,
                                      on_click=on_plus),
                    ],
                    spacing=4,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        )

    def _die_style(self, d: int) -> ft.ButtonStyle:
        """
        Tasti dado (Fase E.4): quello attivo è pieno e in rilievo, gli altri
        piatti sulla superficie alternativa — prima si distinguevano solo per un
        bordo da 1px. Cifre in font monospaziato, così i "d4 d6 d8…" si allineano.
        """
        p = design.T()
        active = (d == self._selected_die)
        return ft.ButtonStyle(
            bgcolor=p.primary_fill if active else p.surface_alt,
            color=p.on_primary_fill if active else p.text_2,
            elevation=3 if active else 0,
            shadow_color=p.shadow,
            side=ft.BorderSide(0 if active else 1, p.border),
            shape=ft.RoundedRectangleBorder(radius=design.Radius.MD),
            padding=ft.Padding.symmetric(horizontal=design.Space.LG,
                                         vertical=design.Space.MD),
            text_style=ft.TextStyle(size=15, weight=ft.FontWeight.BOLD,
                                    font_family=design.Font.MONO),
        )

    def _adv_style(self, mode: str) -> ft.ButtonStyle:
        """Vantaggio/Svantaggio come segmenti: l'attivo ha un fondo tinto."""
        p = design.T()
        active = (mode == self._adv_mode)
        return ft.ButtonStyle(
            color=p.primary if active else p.text_3,
            bgcolor=(ft.Colors.with_opacity(0.12, p.primary_fill) if active
                     else ft.Colors.TRANSPARENT),
            shape=ft.RoundedRectangleBorder(radius=design.Radius.PILL),
            padding=ft.Padding.symmetric(horizontal=design.Space.LG,
                                         vertical=design.Space.SM),
            text_style=ft.TextStyle(size=13,
                                    weight=ft.FontWeight.BOLD if active
                                    else ft.FontWeight.W_500,
                                    font_family=design.Font.BODY),
        )
