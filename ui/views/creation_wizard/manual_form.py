"""
Form di creazione manuale del personaggio.
Permette di inserire direttamente tutti i campi senza il wizard guidato.
Utile per chi ha già un personaggio e vuole importarlo nell'app.
"""

import flet as ft
from config.settings import *
from data.models import Character
from data.repositories import character_repo
from ui.theme import (
    title_text, body_text, muted_text, label_text,
    fantasy_card, section_header, primary_button, ghost_button,
)


class ManualCreationForm(ft.Column):
    """
    Form scrollabile diviso in sezioni coerenti con la scheda personaggio.

    Callback:
        on_complete(character_id: str)  → il personaggio è stato salvato
        on_cancel()                     → torna alla Home
    """

    def __init__(self, on_complete, on_cancel):
        super().__init__(expand=True, spacing=0)
        self.on_complete = on_complete
        self.on_cancel = on_cancel

        self._fields: dict[str, ft.Control] = {}
        self._skill_checkboxes: dict[str, ft.Checkbox] = {}
        self._save_checkboxes: dict[str, ft.Checkbox] = {}

        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        icon_color=COLOR_TEXT_SECONDARY,
                        on_click=lambda e: self.on_cancel(),
                        tooltip="Torna indietro",
                    ),
                    ft.Column(
                        [
                            title_text("Creazione Manuale", size=22),
                            muted_text("Compila i campi del tuo personaggio", size=13),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=16),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

        form_body = ft.Column(
            [
                self._section_identita(),
                self._section_caratteristiche(),
                self._section_combattimento(),
                self._section_competenze(),
                self._section_fisica(),
                self._section_personalita(),
            ],
            spacing=20,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        footer = ft.Container(
            content=ft.Row(
                [
                    ghost_button("Annulla", on_click=lambda e: self.on_cancel()),
                    primary_button(
                        "Salva Personaggio",
                        on_click=self._on_save,
                        icon=ft.Icons.SAVE,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=12,
            ),
            padding=ft.padding.symmetric(horizontal=32, vertical=16),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.border.only(top=ft.BorderSide(1, COLOR_BORDER)),
        )

        self.controls = [
            header,
            ft.Container(content=form_body, expand=True, padding=32),
            footer,
        ]

    # ------------------------------------------------------------------
    # Sezioni del form
    # ------------------------------------------------------------------

    def _section_identita(self) -> ft.Control:
        name        = self._text_field("name", "Nome Personaggio*")
        player_name = self._text_field("player_name", "Nome Giocatore")
        class_dd    = self._dropdown("class_name", "Classe*", list(CLASSES.keys()))
        subclass    = self._text_field("subclass", "Sottoclasse")
        level       = self._number_field("level", "Livello*", value="1", min_val=1, max_val=20)
        race        = self._dropdown("race", "Razza*", RACES)
        subrace     = self._text_field("subrace", "Sottorazza")
        background  = self._text_field("background", "Background")
        alignment   = self._dropdown("alignment", "Allineamento", ALIGNMENTS)
        xp          = self._number_field("xp", "Punti Esperienza", value="0")

        return fantasy_card(ft.Column([
            section_header("Identità"),
            ft.Row([name, player_name], spacing=12),
            ft.Row([class_dd, subclass, level], spacing=12),
            ft.Row([race, subrace], spacing=12),
            ft.Row([background, alignment, xp], spacing=12),
        ], spacing=12))

    def _section_caratteristiche(self) -> ft.Control:
        fields = []
        for key, label in zip(ABILITY_KEYS, ABILITY_SCORES):
            f = self._number_field(f"{key}_score", label, value="10", min_val=1, max_val=30)
            fields.append(f)

        return fantasy_card(ft.Column([
            section_header("Caratteristiche"),
            muted_text("Inserisci i punteggi base (senza bonus razziali)", size=12),
            ft.Container(height=8),
            ft.Row(fields, spacing=12),
        ], spacing=8))

    def _section_combattimento(self) -> ft.Control:
        hp_max   = self._number_field("hp_max", "HP Massimi*", value="0")
        hp_curr  = self._number_field("hp_current", "HP Attuali*", value="0")
        hp_temp  = self._number_field("hp_temp", "HP Temporanei", value="0")
        ac       = self._number_field("ac", "Classe Armatura*", value="10")
        speed    = self._number_field("speed", "Velocità (m)", value="9")
        hd_type  = self._dropdown("hit_dice_type", "Tipo Dado Vita", ["6","8","10","12"])
        hd_total = self._number_field("hit_dice_total", "Dadi Vita Totali", value="1")
        hd_rem   = self._number_field("hit_dice_remaining", "Dadi Vita Rimanenti", value="1")

        # Caratteristica da incantatore (opzionale)
        spell_ability_options = ["", "Intelligenza (int)", "Saggezza (wis)", "Carisma (cha)"]
        spell_ability = self._dropdown("spellcasting_ability", "Caratteristica da Incantatore", spell_ability_options)

        return fantasy_card(ft.Column([
            section_header("Combattimento"),
            ft.Row([hp_max, hp_curr, hp_temp], spacing=12),
            ft.Row([ac, speed], spacing=12),
            ft.Row([hd_type, hd_total, hd_rem], spacing=12),
            ft.Row([spell_ability], spacing=12),
        ], spacing=12))

    def _section_competenze(self) -> ft.Control:
        # Tiri salvezza
        save_boxes = []
        for key, label in zip(ABILITY_KEYS, ABILITY_SCORES):
            cb = ft.Checkbox(
                label=label,
                value=False,
                active_color=COLOR_ACCENT_GOLD,
                label_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=13),
            )
            self._save_checkboxes[key] = cb
            save_boxes.append(cb)

        # Abilità
        skill_boxes = []
        for skill_name in SKILLS.keys():
            cb = ft.Checkbox(
                label=skill_name,
                value=False,
                active_color=COLOR_ACCENT_GOLD,
                label_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=13),
            )
            self._skill_checkboxes[skill_name] = cb
            skill_boxes.append(cb)

        # Divide le abilità in 3 colonne
        col_size = len(skill_boxes) // 3 + 1
        skill_cols = ft.Row(
            [
                ft.Column(skill_boxes[0:col_size], spacing=4),
                ft.Column(skill_boxes[col_size:col_size*2], spacing=4),
                ft.Column(skill_boxes[col_size*2:], spacing=4),
            ],
            spacing=24,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        other = self._multiline_field("other_proficiencies", "Altre competenze e linguaggi", lines=3)

        return fantasy_card(ft.Column([
            section_header("Competenze"),
            label_text("Tiri Salvezza"),
            ft.Container(height=4),
            ft.Row(save_boxes, wrap=True, spacing=12),
            ft.Container(height=12),
            label_text("Abilità"),
            ft.Container(height=4),
            skill_cols,
            ft.Container(height=12),
            other,
        ], spacing=8))

    def _section_fisica(self) -> ft.Control:
        age    = self._text_field("age", "Età")
        height = self._text_field("height", "Altezza")
        weight = self._text_field("weight", "Peso")
        eyes   = self._text_field("eyes", "Occhi")
        skin   = self._text_field("skin", "Carnagione")
        hair   = self._text_field("hair", "Capelli")

        return fantasy_card(ft.Column([
            section_header("Aspetto Fisico"),
            ft.Row([age, height, weight], spacing=12),
            ft.Row([eyes, skin, hair], spacing=12),
        ], spacing=12))

    def _section_personalita(self) -> ft.Control:
        traits  = self._multiline_field("personality_traits", "Tratti Caratteriali", lines=3)
        ideals  = self._multiline_field("ideals", "Ideali", lines=3)
        bonds   = self._multiline_field("bonds", "Legami", lines=3)
        flaws   = self._multiline_field("flaws", "Difetti", lines=3)
        story   = self._multiline_field("backstory", "Storia del Personaggio", lines=5)
        allies  = self._multiline_field("allies_organizations", "Alleati e Organizzazioni", lines=3)
        traits2 = self._multiline_field("additional_traits", "Privilegi e Tratti Aggiuntivi", lines=3)

        return fantasy_card(ft.Column([
            section_header("Personalità e Background"),
            ft.Row([traits, ideals], spacing=12),
            ft.Row([bonds, flaws], spacing=12),
            story,
            ft.Row([allies, traits2], spacing=12),
        ], spacing=12))

    # ------------------------------------------------------------------
    # Helper: factory campi
    # ------------------------------------------------------------------

    def _text_field(self, key: str, label: str, value: str = "") -> ft.TextField:
        tf = ft.TextField(
            label=label,
            value=value,
            expand=True,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY, size=12),
            text_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=14),
            bgcolor=COLOR_BG_SECONDARY,
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            border_radius=6,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
        )
        self._fields[key] = tf
        return tf

    def _number_field(self, key: str, label: str,
                      value: str = "0", min_val: int = 0, max_val: int = 9999) -> ft.TextField:
        tf = ft.TextField(
            label=label,
            value=value,
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY, size=12),
            text_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=14),
            bgcolor=COLOR_BG_SECONDARY,
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            border_radius=6,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
        )
        self._fields[key] = tf
        return tf

    def _dropdown(self, key: str, label: str, options: list[str]) -> ft.Dropdown:
        dd = ft.Dropdown(
            label=label,
            options=[ft.dropdown.Option(o) for o in options],
            expand=True,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY, size=12),
            text_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=14),
            bgcolor=COLOR_BG_SECONDARY,
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            border_radius=6,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
        )
        self._fields[key] = dd
        return dd

    def _multiline_field(self, key: str, label: str, lines: int = 3) -> ft.TextField:
        tf = ft.TextField(
            label=label,
            multiline=True,
            min_lines=lines,
            max_lines=lines + 2,
            expand=True,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY, size=12),
            text_style=ft.TextStyle(color=COLOR_TEXT_PRIMARY, size=14),
            bgcolor=COLOR_BG_SECONDARY,
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            border_radius=6,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=10),
        )
        self._fields[key] = tf
        return tf

    def _get_value(self, key: str, default="") -> str:
        ctrl = self._fields.get(key)
        if ctrl is None:
            return default
        return ctrl.value or default

    def _get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self._get_value(key, str(default)))
        except (ValueError, TypeError):
            return default

    # ------------------------------------------------------------------
    # Salvataggio
    # ------------------------------------------------------------------

    def _on_save(self, e):
        # Validazione campi obbligatori
        name = self._get_value("name")
        if not name.strip():
            self._show_error("Il nome del personaggio è obbligatorio.")
            return
        if not self._get_value("class_name"):
            self._show_error("Seleziona una classe.")
            return
        if not self._get_value("race"):
            self._show_error("Seleziona una razza.")
            return

        # Mappa caratteristica incantatore
        spell_raw = self._get_value("spellcasting_ability", "")
        spell_map = {
            "Intelligenza (int)": "int",
            "Saggezza (wis)": "wis",
            "Carisma (cha)": "cha",
        }
        spell_ability = spell_map.get(spell_raw, "")

        # Tipo dado vita
        hd_raw = self._get_value("hit_dice_type", "6")
        try:
            hd_type = int(hd_raw)
        except ValueError:
            hd_type = 6

        char = Character(
            name=name.strip(),
            player_name=self._get_value("player_name"),
            class_name=self._get_value("class_name"),
            subclass=self._get_value("subclass"),
            level=max(1, min(20, self._get_int("level", 1))),
            race=self._get_value("race"),
            subrace=self._get_value("subrace"),
            background=self._get_value("background"),
            alignment=self._get_value("alignment"),
            xp=self._get_int("xp", 0),
            str_score=self._get_int("str_score", 10),
            dex_score=self._get_int("dex_score", 10),
            con_score=self._get_int("con_score", 10),
            int_score=self._get_int("int_score", 10),
            wis_score=self._get_int("wis_score", 10),
            cha_score=self._get_int("cha_score", 10),
            hp_max=self._get_int("hp_max", 0),
            hp_current=self._get_int("hp_current", 0),
            hp_temp=self._get_int("hp_temp", 0),
            ac=self._get_int("ac", 10),
            speed=self._get_int("speed", 9),
            hit_dice_type=hd_type,
            hit_dice_total=self._get_int("hit_dice_total", 1),
            hit_dice_remaining=self._get_int("hit_dice_remaining", 1),
            spellcasting_ability=spell_ability,
            age=self._get_value("age"),
            height=self._get_value("height"),
            weight=self._get_value("weight"),
            eyes=self._get_value("eyes"),
            skin=self._get_value("skin"),
            hair=self._get_value("hair"),
            personality_traits=self._get_value("personality_traits"),
            ideals=self._get_value("ideals"),
            bonds=self._get_value("bonds"),
            flaws=self._get_value("flaws"),
            backstory=self._get_value("backstory"),
            allies_organizations=self._get_value("allies_organizations"),
            additional_traits=self._get_value("additional_traits"),
        )

        if character_repo.create(char):
            # Salva competenze abilità e tiri salvezza
            self._save_proficiencies(char.id)
            self.on_complete(char.id)
        else:
            self._show_error("Errore durante il salvataggio. Riprova.")

    def _save_proficiencies(self, character_id: str):
        """Salva le competenze selezionate nei checkbox."""
        from data.database import get_connection
        conn = get_connection()
        import uuid

        # Tiri salvezza
        for key, cb in self._save_checkboxes.items():
            if cb.value:
                stat_label = ABILITY_SCORES[ABILITY_KEYS.index(key)]
                conn.execute(
                    "INSERT INTO character_proficiencies VALUES (?,?,?,?,?)",
                    (str(uuid.uuid4()), character_id, "save", stat_label, 0)
                )

        # Abilità
        for skill_name, cb in self._skill_checkboxes.items():
            if cb.value:
                conn.execute(
                    "INSERT INTO character_proficiencies VALUES (?,?,?,?,?)",
                    (str(uuid.uuid4()), character_id, "skill", skill_name, 0)
                )

        # Altre competenze come testo libero
        other = self._get_value("other_proficiencies")
        if other.strip():
            conn.execute(
                "INSERT INTO character_proficiencies VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), character_id, "other", other.strip(), 0)
            )

        conn.commit()
        conn.close()

    def _show_error(self, message: str):
        snack = ft.SnackBar(
            content=ft.Text(message, color=COLOR_TEXT_PRIMARY),
            bgcolor=COLOR_ACCENT_RED,
        )
        self.page.snack_bar = snack
        snack.open = True
        self.page.update()
