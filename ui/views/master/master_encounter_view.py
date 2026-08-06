"""
Tracker di combattimento a schermo intero per un singolo incontro della
Modalità Master — round/turno, lista combattenti ordinata per iniziativa
(evidenziato quello di turno), aggiunta di Personaggio Giocante/NPC dalla
Rubrica/Mostro dal Bestiario/Creazione Rapida, gestione PF (solo per
npc/adhoc — i PG restano sempre gestiti dal giocatore sulla propria
scheda), Calcolatore Difficoltà Incontro. Vedi
`dnd_app/docs/master_section_design.md` per il design completo e
`core/encounter_calculator.py` per la logica pura del calcolo.

Instanziata da `MasterEncounterListView` quando il Master apre un
incontro — non gestisce da sola la navigazione verso la lista, delega a
`on_back_to_list()`.
"""

import logging
from typing import Any

import flet as ft

from core import dice as dice_engine
from config.settings import ABILITY_KEYS, get_level_from_xp
from core.character_stats import RollSpec, ability_abbr, ability_label
from core.encounter_calculator import calculate_difficulty, DIFFICULTY_LABELS
from data.game_data.game_data_loader import parse_monster_xp
from data.models import MasterEncounter
from data.repositories import character_repo, master_repo
from ui.components.monster_picker import (
    creature_entry_dict, load_monsters, monster_display_name,
    show_monster_picker, show_stat_block_dialog,
)
from ui.components.roll_panel import show_roll
from ui.theme import title_text, muted_text, primary_button
from ui import design
from ui.widgets import wrap_dialog_actions, responsive_dialog_width, show_snack

logger = logging.getLogger(__name__)

#: Abbreviazione italiana stampata nello stat block (es. "Cos", "Sag") → chiave
#: interna usata da `core.character_stats` — case-insensitive al confronto.
_ABBR_TO_ABILITY_KEY: dict[str, str] = {
    "FOR": "str", "DES": "dex", "COS": "con", "INT": "int", "SAG": "wis", "CAR": "cha",
}


def _ability_key_from_abbr(abbr: str) -> str:
    return _ABBR_TO_ABILITY_KEY.get((abbr or "").strip().upper(), "")


def _strip_copy_suffix(name: str) -> str:
    """"Goblin 2" → "Goblin": toglie il numero progressivo aggiunto quando si
    creano più copie dello stesso mostro/NPC in un colpo solo, per poter
    risalire al nome originale nel bestiario o in rubrica."""
    parts = (name or "").rsplit(" ", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else (name or "")


def _dice_chip(label: str, on_click) -> ft.Control:
    """Bottone di tiro — stessa forma in tutto il dialog "Dadi"."""
    return ft.OutlinedButton(
        label, icon=ft.Icons.CASINO_OUTLINED, on_click=on_click,
        style=ft.ButtonStyle(color=design.T().primary, side=ft.BorderSide(1, design.T().primary)),
    )



def _int_or(text: str | None, default: int) -> int:
    if text is None:
        return default
    t = text.strip()
    if not t:
        return default
    try:
        return int(t)
    except ValueError:
        try:
            return int(float(t))
        except ValueError:
            return default


# ---------------------------------------------------------------------------
# Iniziativa automatica (Fase 4, feature 4a)
# ---------------------------------------------------------------------------


def _mod_from_score(score: Any) -> int:
    """Modificatore di caratteristica da un punteggio dello stat block."""
    try:
        return (int(score) - 10) // 2
    except (TypeError, ValueError):
        return 0


def _roll_initiative(dex_mod: int) -> int:
    """d20 + modificatore di Destrezza (PHB Cap. 9)."""
    return dice_engine.roll_d20(modifier=dex_mod).total


def _initiative_options() -> tuple[ft.Checkbox, ft.Checkbox, ft.Control]:
    """
    I due interruttori dell'iniziativa automatica, identici nei tre dialog di
    aggiunta combattente.

    Il default è "tira automaticamente": aggiungere 5 goblin significava prima
    compilare 5 campi a mano, mentre il modificatore di Destrezza è già nello
    stat block di tutti i 444 mostri. "Gruppi identici tirano insieme" è la
    variante DMG (un solo tiro per l'intero gruppo): è una scelta del master,
    non una regola fissa, quindi resta spenta di default.
    """
    auto_cb = ft.Checkbox(label="Tira l'iniziativa (d20 + DES)", value=True)
    group_cb = ft.Checkbox(label="Gruppi identici tirano insieme", value=False)
    help_txt = ft.Text(
        "Con il tiro automatico il campo Iniziativa viene ignorato.",
        size=11, color=design.T().text_3, italic=True,
    )
    return auto_cb, group_cb, help_txt


class MasterEncounterView(ft.Column):
    def __init__(self, encounter_id: str, on_back_to_list, world_id: str = ""):
        super().__init__(expand=True, spacing=0)
        self.encounter_id = encounter_id
        self.on_back_to_list = on_back_to_list
        #: Mondo correntemente selezionato in `MasterView` (2026-08-06) — ""
        #: per la modalità locale. Determina quali PG compaiono nel picker
        #: "Personaggio Giocante" (_open_add_character_dialog).
        self._world_id = world_id
        self._page: ft.Page | None = None
        self.encounter: MasterEncounter | None = None
        self._members: list[dict] = []  # resolved, vedi master_repo.get_encounter_members_resolved
        self._header_area = ft.Container()
        self._list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self._build()
        self.refresh()

    def did_mount(self):
        self._page = self.page

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    def _build(self):
        self.controls.clear()
        self.controls.append(self._header_area)
        self.controls.append(
            ft.Container(content=self._list_col, expand=True, padding=ft.Padding.all(16))
        )
        self.controls.append(
            ft.Container(
                content=primary_button(
                    "+ Aggiungi Combattente", icon=ft.Icons.PERSON_ADD,
                    on_click=self._on_add_combatant_click,
                ),
                padding=ft.Padding.only(left=16, right=16, bottom=16),
            )
        )

    def refresh(self):
        self.encounter = master_repo.get_encounter_by_id(self.encounter_id)
        self._members = master_repo.get_encounter_members_resolved(self.encounter_id, active_only=True)
        self._header_area.content = self._build_header()
        self._populate_list()
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_header(self) -> ft.Control:
        enc = self.encounter
        if enc is None:
            return ft.Container(
                content=ft.Text("Incontro non trovato.", color=design.T().text_3),
                padding=ft.Padding.all(16),
            )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK, icon_color=design.T().text_2,
                                tooltip="Torna alla lista incontri",
                                on_click=lambda e: self.on_back_to_list(),
                            ),
                            ft.Column(
                                [
                                    title_text(enc.name or "(senza nome)", size=18),
                                    design.chip(f"Round {enc.round_number}", "primary",
                                                icon=ft.Icons.REPLAY),
                                ],
                                spacing=design.Space.XS,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # Azioni sempre visibili come pillole con etichetta, non più
                    # nascoste dietro un'icona MORE_VERT (2026-07-24, redesign su
                    # richiesta di Davide, stesso pattern di master_view.py).
                    # `wrap=True`: su schermi stretti (smartphone) vanno a capo
                    # invece di traboccare fuori dalla finestra.
                    ft.Row(
                        [
                            self._action_pill(
                                ft.Icons.CASINO_OUTLINED, "Tira iniziativa", design.T().primary,
                                lambda e: self._on_roll_all_initiative(),
                            ),
                            self._action_pill(
                                ft.Icons.ANALYTICS_OUTLINED, "Difficoltà", design.T().magic,
                                self._on_difficulty_click,
                            ),
                            self._action_pill(
                                ft.Icons.STARS_OUTLINED, "Assegna PE", design.T().success,
                                lambda e: self._on_award_xp_click(),
                            ),
                            self._action_pill(
                                ft.Icons.FLAG_OUTLINED, "Termina Incontro", design.T().text_2,
                                self._on_end_encounter_click,
                            ),
                            ft.ElevatedButton(
                                "Prossimo Turno", icon=ft.Icons.SKIP_NEXT,
                                on_click=self._on_next_turn_click,
                                style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary),
                            ),
                        ],
                        spacing=8, wrap=True,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=design.Space.LG,
                                         vertical=design.Space.MD),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
        )

    @staticmethod
    def _action_pill(icon, label: str, color: str, on_click) -> ft.Control:
        """Pillola dalla primitiva condivisa (stessa forma di Home e Master)."""
        return design.pill(icon, label, color=color, on_click=on_click)

    def _populate_list(self):
        self._list_col.controls.clear()
        if not self._members:
            self._list_col.controls.append(self._empty_state())
            return
        current_idx = self.encounter.current_turn_index if self.encounter else 0
        for i, resolved in enumerate(self._members):
            self._list_col.controls.append(
                self._member_card(resolved, is_current=(i == current_idx))
            )

    def _empty_state(self) -> ft.Control:
        return design.empty_state(
            ft.Icons.GROUPS_OUTLINED,
            "Nessun combattente",
            "Aggiungi personaggi, NPC o mostri per tracciare iniziativa e PF.",
        )

    def _member_card(self, resolved: dict, is_current: bool) -> ft.Control:
        m = resolved["member"]
        name = resolved["name"]
        ac = resolved["ac"]
        hp_current = resolved["hp_current"]
        hp_max = resolved["hp_max"]
        source = resolved["source"]

        icon = {
            "character": ft.Icons.PERSON,
            "npc": ft.Icons.SHIELD,
            "adhoc": ft.Icons.BOLT,
        }.get(source, ft.Icons.HELP_OUTLINE)
        icon_color = {
            "character": design.T().magic,
            "npc": design.T().primary,
            "adhoc": design.T().text_3,
        }.get(source, design.T().text_3)

        hp_ratio = (hp_current / hp_max) if hp_max else 0
        hp_color = design.T().text
        if hp_max:
            if hp_ratio <= 0:
                hp_color = design.T().danger
            elif hp_ratio < 0.5:
                hp_color = design.T().alert

        stats_row: list[ft.Control] = [
            design.chip(f"CA {ac}", "neutral", icon=ft.Icons.SHIELD_OUTLINED),
        ]
        if source == "character":
            stats_row.append(design.chip(f"PF {hp_current}/{hp_max} · giocatore", "magic"))
        else:
            stats_row.append(
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_size=16,
                                      icon_color=design.T().text_3,
                                      on_click=lambda e, mm=m: self._on_hp_delta(mm, -1)),
                        ft.Text(f"PF {hp_current}/{hp_max}", size=12, color=hp_color, weight=ft.FontWeight.W_600),
                        ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_size=16,
                                      icon_color=design.T().text_3,
                                      on_click=lambda e, mm=m: self._on_hp_delta(mm, 1)),
                    ],
                    spacing=0, tight=True,
                )
            )
            if resolved.get("xp"):
                stats_row.append(design.chip(f"{resolved['xp']} PE", "neutral"))

        # "Vedi scheda"/"Tira dadi" hanno senso solo per npc/adhoc: i PG restano
        # gestiti dal giocatore sulla propria scheda (regola del progetto).
        extra_actions: list[ft.Control] = []
        if source in ("npc", "adhoc"):
            extra_actions.append(ft.IconButton(
                icon=ft.Icons.MENU_BOOK_OUTLINED, icon_color=design.T().text_3, icon_size=18,
                tooltip="Vedi scheda", on_click=lambda e, r=resolved: self._open_stat_block_click(r),
            ))
            extra_actions.append(ft.IconButton(
                icon=ft.Icons.CASINO_OUTLINED, icon_color=design.T().text_3, icon_size=18,
                tooltip="Tira dadi", on_click=lambda e, r=resolved: self._open_dice_click(r),
            ))

        close_btn = ft.IconButton(
            icon=ft.Icons.CLOSE, icon_color=design.T().text_3, icon_size=18,
            tooltip="Rimuovi dall'incontro",
            on_click=lambda e, mm=m: self._on_remove_member(mm),
        )

        # NOTA (2026-08-06, bug report Davide su smartphone reale —
        # screenshot: "il nome non si legge, le icone si sovrappongono"):
        # la card era UNA sola Row con badge iniziativa + icona tipo + nome
        # (in una Column expand=True) + fino a 3 IconButton azione (Vedi
        # scheda/Tira dadi/Rimuovi, nessuno dei quali si restringe mai sotto
        # la propria area di tocco minima ~40px) tutti sulla stessa riga.
        # Su schermi larghi il totale delle parti a larghezza fissa
        # (badge+icona+2-3 pulsanti ≈ 190-240px) lasciava comunque spazio a
        # nome/chip; su uno smartphone stretto quel margine si azzera o va
        # negativo, e Flet/Flutter non "restringe" ulteriormente un
        # IconButton oltre la sua area minima — il risultato è un vero
        # overflow della Row (non solo testo troncato), che in release si
        # traduce in elementi disegnati oltre il bordo reale, sovrapposti.
        # Fix STRUTTURALE (non un ennesimo `wrap=True` sulla singola Row,
        # già presente altrove e insufficiente qui): due righe invece di
        # una. Riga 1 = SOLO badge + icona + nome (tre elementi, margine
        # ampio anche su schermi stretti, nome sempre leggibile con
        # ellissi). Riga 2 = chip statistiche + pulsanti azione + Rimuovi,
        # in un'unica Row con `wrap=True` che ora può davvero andare a capo
        # (nessun'altra Row/Column senza vincoli di larghezza in mezzo,
        # stesso principio già verificato per il fix dell'header di
        # ProfiloTab lo stesso giorno).
        top_row = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("INIZIATIVA", size=8, weight=ft.FontWeight.W_600,
                                color=design.T().text_3, text_align=ft.TextAlign.CENTER),
                        ft.Container(
                            content=ft.Text(str(m.initiative), size=15, weight=ft.FontWeight.BOLD,
                                             color=design.T().on_primary if is_current else design.T().text,
                                             text_align=ft.TextAlign.CENTER),
                            width=38, height=38, alignment=ft.Alignment.CENTER,
                            bgcolor=design.T().primary if is_current else design.T().surface_alt,
                            border_radius=design.Radius.PILL,
                            shadow=design.elevation(1) if is_current else None,
                            on_click=lambda e, mm=m: self._on_edit_initiative(mm),
                            tooltip="Modifica iniziativa",
                            ink=True,
                        ),
                    ],
                    spacing=2, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=design.Space.MD),
                ft.Icon(icon, color=icon_color, size=20),
                ft.Container(width=design.Space.SM),
                ft.Text(name, size=15, weight=ft.FontWeight.BOLD,
                        color=design.T().text, font_family=design.Font.DISPLAY,
                        no_wrap=True, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        bottom_row = ft.Row(
            [*stats_row, *extra_actions, close_btn],
            spacing=design.Space.SM, wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=ft.Column([top_row, ft.Container(height=design.Space.SM), bottom_row], spacing=0),
            padding=ft.Padding.all(design.Space.MD),
            bgcolor=design.T().surface,
            # Il combattente di turno è l'unico con accento pieno e ombra più
            # marcata: si trova a colpo d'occhio scorrendo l'ordine d'iniziativa.
            border=ft.Border.only(left=ft.BorderSide(
                4 if is_current else 3,
                design.T().primary if is_current else icon_color)),
            shadow=design.elevation(2 if is_current else 1),
            border_radius=design.Radius.MD,
            animate=ft.Animation(design.Duration.BASE, design.CURVE),
        )

    # ------------------------------------------------------------------
    # Scheda / dadi del mostro (2026-08-03, richiesta di Davide: dentro
    # l'incontro non si poteva consultare lo stat block di un npc/mostro né
    # tirare i suoi dadi, a differenza della scheda del personaggio).
    # ------------------------------------------------------------------

    def _resolve_monster_stat_block(self, resolved: dict) -> dict | None:
        """
        Stat block "risolto" (forma di `build_stat_block_column`) per un
        membro npc/adhoc, o `None` se non risolvibile — mai inventato:

          * kind="npc": legge `master_npcs` per `npc_id`, solo se
            `has_stat_block` (un NPC di solo ruolo non ha altro da mostrare);
          * kind="adhoc" da "Mostro dal Bestiario": il nome (al netto del
            suffisso numerico delle copie multiple) risolve in `monsters.json`,
            stessa tecnica di `master_forest_encounters_dialog._resolve_creature`;
          * kind="adhoc" da "Creazione Rapida": nessuno stat block esiste da
            nessuna parte, `None`.
        """
        m = resolved["member"]
        if resolved["source"] == "npc" and m.npc_id:
            npc = master_repo.get_npc_by_id(m.npc_id)
            if npc and npc.has_stat_block:
                return creature_entry_dict(npc)
            return None
        if resolved["source"] == "adhoc":
            base = _strip_copy_suffix(m.display_name).strip().lower()
            if not base:
                return None
            for mon in load_monsters():
                if str(mon.get("name", "")).strip().lower() == base:
                    return mon
        return None

    def _open_stat_block_click(self, resolved: dict):
        if not self._page:
            return
        page = self._page
        m = resolved["member"]
        data = self._resolve_monster_stat_block(resolved)
        if data is not None:
            show_stat_block_dialog(page, resolved["name"], data)
            return
        # Nessuno stat block risolvibile — tipicamente un combattente creato
        # con "Creazione Rapida": si mostrano solo i pochi dati tracciati,
        # niente viene inventato per riempire il vuoto.
        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(resolved["name"]),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Nessuna scheda completa disponibile: questo combattente "
                            "è stato creato con «Creazione Rapida» e non ha uno stat "
                            "block del bestiario o della Rubrica NPC collegato.",
                            size=12, color=design.T().text_2,
                        ),
                        ft.Divider(height=1, color=design.T().border),
                        ft.Text(f"CA {resolved['ac']}", size=13, color=design.T().text),
                        ft.Text(f"PF {resolved['hp_current']}/{resolved['hp_max']}",
                                size=13, color=design.T().text),
                        ft.Text(f"Mod. Destrezza {dice_engine.format_modifier(int(getattr(m, 'dex_mod', 0) or 0))}",
                                size=13, color=design.T().text),
                        ft.Text(f"PE {resolved.get('xp', 0)}", size=13, color=design.T().text),
                    ],
                    spacing=8, tight=True,
                ),
                width=responsive_dialog_width(page, 320),
            ),
            actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
        ))

    def _open_dice_click(self, resolved: dict):
        """
        Dialog "Dadi — {nome}": riusa lo stesso motore della scheda del
        personaggio (`core/dice.py` + `RollSpec` + il pannello persistente
        `ui/components/roll_panel.py`) invece di duplicarlo. Le prove/i TS/le
        abilità usano **solo i valori già stampati** nello stat block (mai
        ricalcolati dal GS): un tiro salvezza non stampato equivale alla prova
        di caratteristica corrispondente, per regolamento (PHB).

        Gli attacchi/danni restano testo libero nello stat block (mai un
        numero strutturato in `monsters.json`): il campo "Tiro personalizzato"
        copre quel caso senza inventare un parser di prosa italiana.
        """
        if not self._page:
            return
        page = self._page
        name = resolved["name"]
        m = resolved["member"]
        data = self._resolve_monster_stat_block(resolved)

        def _roll_now(spec: RollSpec):
            show_roll(page, spec)

        sections: list[ft.Control] = []

        if data is not None:
            ability_row = ft.Row(spacing=6, wrap=True)
            for key in ABILITY_KEYS:
                score = int(data.get(f"{key}_score", 10) or 10)
                mod = _mod_from_score(score)
                spec = RollSpec(
                    kind="ability", label=f"{name} — Prova di {ability_label(key)}",
                    modifier=mod, ability=key,
                    note=f"{ability_abbr(key)} {dice_engine.format_modifier(mod)}",
                )
                ability_row.controls.append(_dice_chip(
                    f"{ability_abbr(key)} {dice_engine.format_modifier(mod)}",
                    lambda e, s=spec: _roll_now(s),
                ))
            sections.append(ft.Text("Prove di Caratteristica", size=12,
                                     weight=ft.FontWeight.BOLD, color=design.T().primary))
            sections.append(ability_row)

            st_dict = data.get("saving_throws", {}) or {}
            save_row = ft.Row(spacing=6, wrap=True)
            if isinstance(st_dict, dict):
                for abbr_key, printed in st_dict.items():
                    ability_key = _ability_key_from_abbr(abbr_key)
                    if not ability_key:
                        continue
                    try:
                        mod = int(str(printed).strip())
                    except ValueError:
                        continue
                    spec = RollSpec(
                        kind="save", label=f"{name} — TS {ability_label(ability_key)}",
                        modifier=mod, ability=ability_key, proficient=True,
                        note=f"TS {ability_abbr(ability_key)} {dice_engine.format_modifier(mod)} (competente)",
                    )
                    save_row.controls.append(_dice_chip(
                        f"TS {ability_abbr(ability_key)} {dice_engine.format_modifier(mod)}",
                        lambda e, s=spec: _roll_now(s),
                    ))
            if save_row.controls:
                sections.append(ft.Divider(height=1, color=design.T().border))
                sections.append(ft.Text("Tiri Salvezza (competenti)", size=12,
                                         weight=ft.FontWeight.BOLD, color=design.T().primary))
                sections.append(save_row)
                sections.append(ft.Text(
                    "Gli altri tiri salvezza non stampati equivalgono alla prova "
                    "di caratteristica qui sopra (nessun bonus di competenza).",
                    size=10, italic=True, color=design.T().text_3,
                ))

            sk_dict = data.get("skills", {}) or {}
            skill_row = ft.Row(spacing=6, wrap=True)
            if isinstance(sk_dict, dict):
                for skill_name, printed in sk_dict.items():
                    try:
                        mod = int(str(printed).strip())
                    except ValueError:
                        continue
                    spec = RollSpec(
                        kind="skill", label=f"{name} — {skill_name}",
                        modifier=mod, note=f"{skill_name} {dice_engine.format_modifier(mod)}",
                    )
                    skill_row.controls.append(_dice_chip(
                        f"{skill_name} {dice_engine.format_modifier(mod)}",
                        lambda e, s=spec: _roll_now(s),
                    ))
            if skill_row.controls:
                sections.append(ft.Divider(height=1, color=design.T().border))
                sections.append(ft.Text("Abilità", size=12, weight=ft.FontWeight.BOLD,
                                         color=design.T().primary))
                sections.append(skill_row)
        else:
            dex_mod = int(getattr(m, "dex_mod", 0) or 0)
            sections.append(ft.Text(
                "Nessuno stat block collegato: qui è tirabile solo il "
                "modificatore di Destrezza tracciato per questo combattente.",
                size=12, color=design.T().text_2,
            ))
            spec_ability = RollSpec(
                kind="ability", label=f"{name} — Prova di Destrezza",
                modifier=dex_mod, ability="dex",
                note=f"DES {dice_engine.format_modifier(dex_mod)}",
            )
            spec_save = RollSpec(
                kind="save", label=f"{name} — TS Destrezza",
                modifier=dex_mod, ability="dex",
                note=f"DES {dice_engine.format_modifier(dex_mod)} (competenza non nota)",
            )
            sections.append(ft.Row(
                [
                    _dice_chip(f"Prova DES {dice_engine.format_modifier(dex_mod)}",
                               lambda e: _roll_now(spec_ability)),
                    _dice_chip(f"TS DES {dice_engine.format_modifier(dex_mod)}",
                               lambda e: _roll_now(spec_save)),
                ],
                spacing=6, wrap=True,
            ))

        formula_tf = ft.TextField(label="Formula (es. 1d20+5, 2d6+3)", dense=True,
                                   **design.field_style())

        def _on_custom_roll(_e: Any):
            text = (formula_tf.value or "").strip()
            if not text:
                return
            try:
                dice_engine.parse_formula(text)
            except ValueError:
                show_snack(page, f"Formula non valida: {text!r}", tone="warning")
                return
            _roll_now(RollSpec(kind="custom", label=f"{name} — tiro personalizzato", formula=text))

        sections.append(ft.Divider(height=1, color=design.T().border))
        sections.append(ft.Text(
            "Tiro personalizzato — per attacchi e danni: leggi il bonus o i "
            "dadi già stampati nell'azione e digitali qui.",
            size=10, italic=True, color=design.T().text_3,
        ))
        sections.append(ft.Row(
            [
                ft.Container(content=formula_tf, expand=True),
                ft.IconButton(ft.Icons.CASINO, icon_color=design.T().primary,
                              tooltip="Tira", on_click=_on_custom_roll),
            ],
            spacing=8,
        ))

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(f"Dadi — {name}"),
            content=ft.Container(
                content=ft.Column(sections, spacing=8, scroll=ft.ScrollMode.AUTO, tight=True),
                width=responsive_dialog_width(page, 380), height=420,
            ),
            actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
        ))

    # ------------------------------------------------------------------
    # Azioni header
    # ------------------------------------------------------------------

    def _on_next_turn_click(self, e: Any):
        master_repo.advance_turn(self.encounter_id)
        self.refresh()

    def _on_end_encounter_click(self, e: Any):
        if not self._page:
            return
        page = self._page

        def _do_end(_e: Any):
            master_repo.archive_encounter(self.encounter_id, archived=True)
            page.pop_dialog()
            self.on_back_to_list()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Termina Incontro?"),
            content=ft.Text(
                "L'incontro verrà archiviato e non comparirà più nella lista attiva "
                "(resta comunque conservato nello storico del database).",
                size=12, color=design.T().text_2,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Termina", icon=ft.Icons.FLAG, on_click=_do_end,
                    style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary),
                ),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Iniziativa di tutti i mostri (Fase 4, feature 4a)
    # ------------------------------------------------------------------

    def _on_roll_all_initiative(self):
        """
        Ritira l'iniziativa di tutti i combattenti `npc`/`adhoc` attivi.

        **I personaggi giocanti non vengono toccati**, coerente con la regola
        del progetto "il master non scrive mai sui PG": al tavolo tira il
        giocatore e comunica il valore, che resta modificabile a mano.
        """
        if not self._page:
            return
        page = self._page

        members = master_repo.get_encounter_members(self.encounter_id, active_only=True)
        rollable = [m for m in members if m.kind in ("npc", "adhoc")]
        players = [m for m in members if m.kind == "character"]

        if not rollable:
            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title("Nessun mostro da tirare"),
                content=ft.Text(
                    "In questo incontro non ci sono NPC o mostri: l'iniziativa dei "
                    "personaggi giocanti la tirano i giocatori.",
                    size=12, color=design.T().text_2,
                ),
                actions=wrap_dialog_actions([
                    ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
                ]),
            ))
            return

        # Opzione "gruppi identici": stesso tiro per membri con lo stesso nome
        # a meno del numero progressivo ("Goblin 1", "Goblin 2" → "Goblin").
        group_cb = ft.Checkbox(label="Gruppi identici tirano insieme", value=False)

        def _do_roll(_e: Any):
            shared: dict[str, int] = {}
            for m in rollable:
                if group_cb.value:
                    key = _strip_copy_suffix(m.display_name)
                    if key not in shared:
                        shared[key] = _roll_initiative(m.dex_mod)
                    value = shared[key]
                else:
                    value = _roll_initiative(m.dex_mod)
                master_repo.update_member_initiative(m.id, value)
            page.pop_dialog()
            self.refresh()

        note = ft.Text(
            f"Verranno tirati {len(rollable)} combattenti."
            + (f" I {len(players)} personaggi giocanti non vengono toccati."
               if players else ""),
            size=12, color=design.T().text_2,
        )

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Tira l'iniziativa"),
            content=ft.Container(
                content=ft.Column([note, group_cb], spacing=8, tight=True),
                width=responsive_dialog_width(page, 340),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Tira", icon=ft.Icons.CASINO_OUTLINED, on_click=_do_roll,
                    style=ft.ButtonStyle(bgcolor=design.T().primary,
                                         color=design.T().on_primary),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Assegnazione dei PE (Fase 4, feature 4b)
    # ------------------------------------------------------------------

    def _on_award_xp_click(self):
        """
        Assegna i PE dell'incontro ai personaggi giocanti presenti.

        **È l'unica scrittura del master su una scheda giocante in tutto il
        progetto** (autorizzata da Davide il 2026-07-30), e per questo:
          * ogni mostro ha una casella, pre-spuntata se è a 0 PF o è stato
            rimosso dall'incontro — un nemico in fuga o aggirato lo decide il
            master, non un'euristica;
          * il totale a testa resta modificabile a mano (la DMG prevede PE
            bonus per obiettivi narrativi);
          * il dialog di conferma mostra, per ciascun PG, quanti PE ha ora,
            quanti ne avrà e se questo lo porta a un nuovo livello;
          * **nessun level-up automatico**: sale il giocatore dalla propria
            scheda, dove sceglie HP/ASI/incantesimi.
        """
        if not self._page:
            return
        page = self._page

        members = master_repo.get_encounter_members(self.encounter_id, active_only=False)
        monsters = [m for m in members if m.kind in ("npc", "adhoc")]
        player_members = [m for m in members
                          if m.kind == "character" and m.character_id and m.is_active]

        if not monsters or not player_members:
            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title("Impossibile assegnare i PE"),
                content=ft.Text(
                    "Servono almeno un mostro e un personaggio giocante "
                    "nell'incontro." if not monsters else
                    "Nessun personaggio giocante in questo incontro: aggiungine "
                    "uno per poter assegnare i PE.",
                    size=12, color=design.T().text_2,
                ),
                actions=wrap_dialog_actions([
                    ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
                ]),
            ))
            return

        players = [character_repo.get_by_id(m.character_id) for m in player_members]
        players = [p for p in players if p is not None]

        # Pre-spunta: sconfitto = a 0 PF oppure rimosso dall'incontro.
        boxes: list[tuple[Any, ft.Checkbox]] = []
        for m in monsters:
            defeated = (m.hp_current <= 0) or (not m.is_active)
            label = f"{m.display_name or '(senza nome)'} — {m.xp} PE"
            if not m.is_active:
                label += " (rimosso)"
            elif m.hp_current <= 0:
                label += " (a 0 PF)"
            boxes.append((m, ft.Checkbox(label=label, value=defeated)))

        total_txt = ft.Text("", size=13, weight=ft.FontWeight.BOLD,
                            color=design.T().text)
        each_tf = ft.TextField(label="PE a testa", value="0", dense=True, width=140,
                               keyboard_type=ft.KeyboardType.NUMBER,
                               **design.field_style())

        def _recalc(_e: Any = None):
            total = sum(m.xp for m, cb in boxes if cb.value)
            each = total // len(players) if players else 0
            total_txt.value = (f"{total} PE totali ÷ {len(players)} personaggi "
                               f"= {each} a testa")
            each_tf.value = str(each)
            for ctl in (total_txt, each_tf):
                try:
                    ctl.update()
                except (RuntimeError, AssertionError):
                    pass

        for _m, cb in boxes:
            cb.on_change = _recalc
        _recalc()

        def _confirm(_e: Any):
            each = max(0, _int_or(each_tf.value, 0))
            page.pop_dialog()
            if each <= 0:
                return
            self._confirm_award_xp(players, each)

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Assegna PE"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Chi è stato sconfitto?", size=12,
                                color=design.T().text_2),
                        *[cb for _m, cb in boxes],
                        ft.Divider(height=1, color=design.T().border),
                        total_txt,
                        each_tf,
                        ft.Text(
                            "Il totale a testa è modificabile: la DMG prevede PE "
                            "bonus per obiettivi narrativi.",
                            size=11, color=design.T().text_3, italic=True),
                    ],
                    spacing=6, tight=True, scroll=ft.ScrollMode.AUTO,
                ),
                width=responsive_dialog_width(page, 380), height=420,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Continua", icon=ft.Icons.ARROW_FORWARD, on_click=_confirm,
                    style=ft.ButtonStyle(bgcolor=design.T().success,
                                         color=design.T().on_accent),
                ),
            ]),
        ))

    def _confirm_award_xp(self, players: list[Any], each: int):
        """Secondo passo: mostra chi riceve quanto e il livello risultante."""
        page = self._page
        if page is None:
            return

        rows: list[ft.Control] = []
        for p in players:
            before = int(p.xp or 0)
            after = before + each
            lvl_before = get_level_from_xp(before)
            lvl_after = get_level_from_xp(after)
            line = f"{p.name}: {before:,} → {after:,} PE".replace(",", ".")
            if lvl_after > lvl_before:
                line += f"  ·  sale al livello {lvl_after}"
            rows.append(ft.Text(
                line, size=12,
                color=design.T().success if lvl_after > lvl_before else design.T().text,
                weight=ft.FontWeight.BOLD if lvl_after > lvl_before else None,
            ))

        def _do(_e: Any):
            written = 0
            for p in players:
                if character_repo.add_xp(p.id, each) is not None:
                    written += 1
            page.pop_dialog()
            self.refresh()
            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title("PE assegnati"),
                content=ft.Text(
                    f"{each} PE assegnati a {written} personagg"
                    f"{'io' if written == 1 else 'i'}.\n"
                    "Il livello non è stato toccato: sale il giocatore dalla "
                    "propria scheda, dove sceglie punti ferita, ASI e incantesimi.",
                    size=12, color=design.T().text,
                ),
                actions=wrap_dialog_actions([
                    ft.TextButton("OK", on_click=lambda e: page.pop_dialog()),
                ]),
            ))

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Confermi l'assegnazione?"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"{each} PE a ciascun personaggio:", size=13,
                                color=design.T().text_2),
                        *rows,
                        ft.Text(
                            "Questa è l'unica modifica che la Modalità Master "
                            "applica a una scheda giocante.",
                            size=11, color=design.T().text_3, italic=True),
                    ],
                    spacing=6, tight=True, scroll=ft.ScrollMode.AUTO,
                ),
                width=responsive_dialog_width(page, 360),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Assegna", icon=ft.Icons.STARS, on_click=_do,
                    style=ft.ButtonStyle(bgcolor=design.T().success,
                                         color=design.T().on_accent),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Calcolatore Difficoltà
    # ------------------------------------------------------------------

    def _on_difficulty_click(self, e: Any):
        if not self._page:
            return
        page = self._page

        party_levels: list[int] = []
        for resolved in self._members:
            if resolved["source"] != "character":
                continue
            m = resolved["member"]
            ch = character_repo.get_by_id(m.character_id) if m.character_id else None
            party_levels.append(ch.level if ch else 1)

        monster_xp = [
            int(resolved.get("xp", 0) or 0)
            for resolved in self._members
            if resolved["source"] in ("npc", "adhoc")
        ]

        ghost_levels: list[int] = []
        result_col = ft.Column([], spacing=6)
        ghost_row = ft.Row([], spacing=6, wrap=True)
        ghost_tf = ft.TextField(label="Livello PG fantasma", value="1", width=140, dense=True,
                                 border_radius=design.Radius.SM, keyboard_type=ft.KeyboardType.NUMBER, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])

        def _recompute():
            levels = party_levels + ghost_levels
            res = calculate_difficulty(monster_xp, levels)
            diff_key = res["difficulty"]
            diff_label = DIFFICULTY_LABELS.get(diff_key, diff_key)
            diff_color = design.difficulty_color(diff_key)
            thr = res["thresholds"]
            result_col.controls.clear()
            result_col.controls.extend([
                ft.Text(
                    f"Gruppo: {res['party_size']} personaggi (livelli {', '.join(str(l) for l in levels) or '—'})",
                    size=12, color=design.T().text_2,
                ),
                ft.Text(
                    f"Mostri/NPC: {res['monster_count']} · PE totali {res['monster_xp_total']} "
                    f"× {res['multiplier']:g} = PE modificato {res['adjusted_xp']}",
                    size=12, color=design.T().text_2,
                ),
                ft.Container(height=6),
                ft.Container(
                    content=ft.Text(diff_label.upper(), size=16, weight=ft.FontWeight.BOLD, color=design.T().on_primary,
                                     text_align=ft.TextAlign.CENTER),
                    bgcolor=diff_color, border_radius=design.Radius.MD, padding=ft.Padding.symmetric(vertical=8),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Container(height=6),
                ft.Text(
                    f"Soglie di gruppo — Facile {thr['facile']} · Medio {thr['medio']} · "
                    f"Difficile {thr['difficile']} · Letale {thr['letale']}",
                    size=11, color=design.T().text_3,
                ),
            ])
            try:
                result_col.update()
            except RuntimeError:
                pass

        def _add_ghost(_e: Any):
            lvl = max(1, min(20, _int_or(ghost_tf.value, 1)))
            ghost_levels.append(lvl)
            _rebuild_ghost_row()
            _recompute()

        def _remove_ghost(idx: int):
            if 0 <= idx < len(ghost_levels):
                ghost_levels.pop(idx)
            _rebuild_ghost_row()
            _recompute()

        def _rebuild_ghost_row():
            ghost_row.controls.clear()
            for i, lvl in enumerate(ghost_levels):
                ghost_row.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(f"Lv.{lvl}", size=11, color=design.T().text_2),
                                ft.IconButton(ft.Icons.CLOSE, icon_size=12, icon_color=design.T().text_3,
                                              on_click=lambda e, ix=i: _remove_ghost(ix)),
                            ],
                            spacing=0, tight=True,
                        ),
                        padding=ft.Padding.symmetric(horizontal=6),
                        border=ft.Border.all(1, design.T().border), border_radius=12,
                    )
                )
            try:
                ghost_row.update()
            except RuntimeError:
                pass

        _recompute()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Calcolatore Difficoltà Incontro"),
            content=ft.Container(
                content=ft.Column(
                    [
                        muted_text(
                            "Aggiungi \"PG fantasma\" per pianificare con personaggi non ancora "
                            "presenti nell'incontro (i livelli non vengono salvati).", size=11,
                        ),
                        ft.Row([ghost_tf, ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=design.T().magic,
                                                        on_click=_add_ghost)], spacing=6),
                        ghost_row,
                        ft.Divider(height=14, color=design.T().border),
                        result_col,
                    ],
                    spacing=6, scroll=ft.ScrollMode.AUTO, tight=True,
                ),
                width=responsive_dialog_width(page, 340), height=420,
            ),
            actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # PF / Iniziativa / Rimozione membro
    # ------------------------------------------------------------------

    def _on_hp_delta(self, member, delta: int):
        new_hp = max(0, member.hp_current + delta)
        master_repo.update_member_hp(member.id, new_hp)
        self.refresh()

    def _on_edit_initiative(self, member):
        if not self._page:
            return
        page = self._page
        init_tf = ft.TextField(label="Iniziativa", value=str(member.initiative), dense=True,
                                border_radius=design.Radius.SM, autofocus=True, keyboard_type=ft.KeyboardType.NUMBER, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])

        def _do_save(_e: Any):
            master_repo.update_member_initiative(member.id, _int_or(init_tf.value, member.initiative))
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Modifica Iniziativa"),
            content=ft.Container(content=init_tf, width=responsive_dialog_width(page, 200)),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Salva", icon=ft.Icons.SAVE, on_click=_do_save,
                                   style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary)),
            ]),
        )
        page.show_dialog(dlg)

    def _on_remove_member(self, member):
        master_repo.remove_member(member.id)
        self.refresh()

    # ------------------------------------------------------------------
    # Aggiungi Combattente — dialog a 4 scelte
    # ------------------------------------------------------------------

    def _next_order_index(self) -> int:
        existing = master_repo.get_encounter_members(self.encounter_id, active_only=False)
        return (max((m.order_index for m in existing), default=-1) + 1)

    def _on_add_combatant_click(self, e: Any):
        if not self._page:
            return
        page = self._page

        def _go(fn):
            def _inner(_e: Any):
                page.pop_dialog()
                fn()
            return _inner

        dlg = ft.AlertDialog(
            title=design.dialog_title("Aggiungi Combattente"),
            content=ft.Column(
                [
                    ft.OutlinedButton(
                        "Personaggio Giocante", icon=ft.Icons.PERSON_OUTLINE,
                        on_click=_go(self._open_add_character_dialog),
                        style=ft.ButtonStyle(color=design.T().magic, side=ft.BorderSide(1, design.T().magic)),
                    ),
                    ft.Container(height=6),
                    ft.OutlinedButton(
                        "NPC dalla Rubrica", icon=ft.Icons.GROUPS_OUTLINED,
                        on_click=_go(self._open_add_npc_dialog),
                        style=ft.ButtonStyle(color=design.T().primary, side=ft.BorderSide(1, design.T().primary)),
                    ),
                    ft.Container(height=6),
                    ft.OutlinedButton(
                        "Mostro dal Bestiario", icon=ft.Icons.MENU_BOOK_OUTLINED,
                        on_click=_go(self._open_add_monster_dialog),
                        style=ft.ButtonStyle(color=design.T().primary, side=ft.BorderSide(1, design.T().primary)),
                    ),
                    ft.Container(height=6),
                    ft.OutlinedButton(
                        "Creazione Rapida", icon=ft.Icons.BOLT,
                        on_click=_go(self._open_add_adhoc_dialog),
                        style=ft.ButtonStyle(color=design.T().text_2, side=ft.BorderSide(1, design.T().border)),
                    ),
                ],
                tight=True,
            ),
            actions=[ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog())],
        )
        page.show_dialog(dlg)

    def _open_add_character_dialog(self):
        if not self._page:
            return
        page = self._page
        chars = character_repo.get_master_visible_characters(self._world_id)
        already_ids = {
            resolved["member"].character_id for resolved in
            master_repo.get_encounter_members_resolved(self.encounter_id, active_only=False)
            if resolved["source"] == "character"
        }
        available = [c for c in chars if c.id not in already_ids]

        if not available:
            dlg = ft.AlertDialog(
                title=design.dialog_title("Nessun personaggio disponibile"),
                content=ft.Text(
                    "Tutti i personaggi esistenti sono già in questo incontro, oppure non ne hai ancora creato uno.",
                    size=12, color=design.T().text_2,
                ),
                actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
            )
            page.show_dialog(dlg)
            return

        char_dd = ft.Dropdown(
            label="Personaggio",
            options=[ft.DropdownOption(key=c.id, text=f"{c.name} (Lv.{c.level} {c.class_name})") for c in available],
            value=available[0].id, dense=True, border_radius=design.Radius.SM,
            border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=120,
                                keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())

        def _do_add(_e: Any):
            ch = next((c for c in available if c.id == char_dd.value), available[0])
            master_repo.add_member(
                encounter_id=self.encounter_id, kind="character", character_id=ch.id,
                display_name=ch.name, initiative=_int_or(init_tf.value, 10),
                order_index=self._next_order_index(),
            )
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Aggiungi Personaggio Giocante"),
            content=ft.Container(
                content=ft.Column([char_dd, ft.Container(height=8), init_tf], tight=True), width=responsive_dialog_width(page, 300),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Aggiungi", icon=ft.Icons.ADD, on_click=_do_add,
                                   style=ft.ButtonStyle(bgcolor=design.T().magic, color=design.T().on_accent)),
            ]),
        )
        page.show_dialog(dlg)

    def _open_add_npc_dialog(self):
        if not self._page:
            return
        page = self._page
        npcs = master_repo.get_npcs()

        if not npcs:
            dlg = ft.AlertDialog(
                title=design.dialog_title("Nessun NPC in rubrica"),
                content=ft.Text(
                    "Crea prima un NPC dalla tab \"Rubrica NPC\", poi torna qui per aggiungerlo.",
                    size=12, color=design.T().text_2,
                ),
                actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
            )
            page.show_dialog(dlg)
            return

        npc_dd = ft.Dropdown(
            label="NPC",
            options=[ft.DropdownOption(key=n.id, text=n.name or "(senza nome)") for n in npcs],
            value=npcs[0].id, dense=True, border_radius=design.Radius.SM,
            border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=100,
                                keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        qty_tf = ft.TextField(label="Quantità", value="1", dense=True, width=90,
                               keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        auto_cb, group_cb, init_help = _initiative_options()

        def _do_add(_e: Any):
            npc = next((n for n in npcs if n.id == npc_dd.value), npcs[0])
            qty = max(1, _int_or(qty_tf.value, 1))
            base_idx = self._next_order_index()
            dex_mod = _mod_from_score(getattr(npc, "dex_score", 10))
            shared = _roll_initiative(dex_mod) if (auto_cb.value and group_cb.value) else None
            for i in range(qty):
                name = f"{npc.name} {i + 1}" if qty > 1 else npc.name
                if auto_cb.value:
                    init_val = shared if shared is not None else _roll_initiative(dex_mod)
                else:
                    init_val = _int_or(init_tf.value, 10)
                master_repo.add_member(
                    encounter_id=self.encounter_id, kind="npc", npc_id=npc.id,
                    display_name=name, ac=npc.ac, hp_current=npc.hp_max, hp_max=npc.hp_max,
                    xp=npc.xp, initiative=init_val, order_index=base_idx + i,
                    dex_mod=dex_mod,
                )
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Aggiungi NPC dalla Rubrica"),
            content=ft.Container(
                content=ft.Column([npc_dd, ft.Row([init_tf, qty_tf], spacing=8),
                                   auto_cb, group_cb, init_help], spacing=8, tight=True),
                width=responsive_dialog_width(page, 300),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Aggiungi", icon=ft.Icons.ADD, on_click=_do_add,
                                   style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary)),
            ]),
        )
        page.show_dialog(dlg)

    def _open_add_monster_dialog(self):
        if not self._page:
            return
        page = self._page
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=110,
                                keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        qty_tf = ft.TextField(label="Quantità", value="1", dense=True, width=90,
                               keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        save_cb = ft.Checkbox(label="Salva anche in Rubrica NPC", value=False)
        auto_cb, group_cb, init_help = _initiative_options()

        def _open_picker(_e: Any):
            page.pop_dialog()
            pool = load_monsters()

            def _on_select(m: dict):
                page.pop_dialog()
                qty = max(1, _int_or(qty_tf.value, 1))
                base_idx = self._next_order_index()
                disp = monster_display_name(m.get("name", ""))
                dex_mod = _mod_from_score(m.get("dex_score", 10))
                shared = _roll_initiative(dex_mod) if (auto_cb.value and group_cb.value) else None
                for i in range(qty):
                    name = f"{disp} {i + 1}" if qty > 1 else disp
                    if auto_cb.value:
                        init_val = shared if shared is not None else _roll_initiative(dex_mod)
                    else:
                        init_val = _int_or(init_tf.value, 10)
                    master_repo.add_member(
                        encounter_id=self.encounter_id, kind="adhoc",
                        display_name=name, ac=int(m.get("ac", 10)),
                        hp_current=int(m.get("hp_max", 1)), hp_max=int(m.get("hp_max", 1)),
                        xp=parse_monster_xp(m.get("xp", 0)), initiative=init_val,
                        order_index=base_idx + i, dex_mod=dex_mod,
                    )
                if save_cb.value:
                    master_repo.create_npc_from_monster(m)
                self.refresh()

            show_monster_picker(
                page, "Mostro dal Bestiario", pool, existing_names=set(), on_select=_on_select,
                select_label="Aggiungi all'incontro", select_color=design.T().primary,
            )

        dlg = ft.AlertDialog(
            title=design.dialog_title("Aggiungi Mostro dal Bestiario"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row([init_tf, qty_tf], spacing=8),
                        auto_cb, group_cb, init_help,
                        save_cb,
                        muted_text("Il nome, CA, PF e PE verranno importati automaticamente dal mostro scelto.",
                                   size=11),
                    ],
                    spacing=8, tight=True,
                ),
                width=responsive_dialog_width(page, 300),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Scegli Mostro...", icon=ft.Icons.MENU_BOOK_OUTLINED, on_click=_open_picker,
                                   style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary)),
            ]),
        )
        page.show_dialog(dlg)

    def _open_add_adhoc_dialog(self):
        if not self._page:
            return
        page = self._page
        name_tf = ft.TextField(label="Nome *", dense=True, border_radius=design.Radius.SM, autofocus=True, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        ac_tf = ft.TextField(label="CA", value="10", dense=True, width=90,
                              keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        hp_tf = ft.TextField(label="PF", value="10", dense=True, width=90,
                              keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        xp_tf = ft.TextField(label="PE", value="0", dense=True, width=90,
                              keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        auto_cb = ft.Checkbox(label="Tira l'iniziativa (d20 + DES)", value=True)
        init_tf = ft.TextField(label="Iniziativa", value="10", dense=True, width=110,
                                keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        # Un combattente creato a mano non ha uno stat block da cui leggere la
        # Destrezza: il modificatore si dichiara qui, e serve anche a "Tira
        # iniziativa per tutti" nei turni successivi.
        dex_tf = ft.TextField(label="Mod. DES", value="0", dense=True, width=100,
                               keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
        error_text = ft.Text("", size=12, color=design.T().danger)

        def _do_add(_e: Any):
            name = (name_tf.value or "").strip()
            if not name:
                error_text.value = "Il nome è obbligatorio."
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return
            hp = _int_or(hp_tf.value, 10)
            dex_mod = _int_or(dex_tf.value, 0)
            init_val = (_roll_initiative(dex_mod) if auto_cb.value
                        else _int_or(init_tf.value, 10))
            master_repo.add_member(
                encounter_id=self.encounter_id, kind="adhoc", display_name=name,
                ac=_int_or(ac_tf.value, 10), hp_current=hp, hp_max=hp,
                xp=_int_or(xp_tf.value, 0), initiative=init_val,
                order_index=self._next_order_index(), dex_mod=dex_mod,
            )
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Creazione Rapida"),
            content=ft.Container(
                content=ft.Column(
                    [name_tf, ft.Row([ac_tf, hp_tf, xp_tf], spacing=8),
                     ft.Row([init_tf, dex_tf], spacing=8), auto_cb, error_text],
                    spacing=8, tight=True,
                ),
                width=responsive_dialog_width(page, 320),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton("Aggiungi", icon=ft.Icons.ADD, on_click=_do_add,
                                   style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary)),
            ]),
        )
        page.show_dialog(dlg)
