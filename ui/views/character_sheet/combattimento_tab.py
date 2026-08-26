"""
Tab Combattimento della scheda personaggio.

Struttura (ListView scrollabile):
  - HP Tracker        — barra HP colorata, danno/cura, HP temp,
                        tiri salvezza morte (sempre visibili)
  - Statistiche       — CA, Velocità, Iniziativa (calcolata), Ispirazione toggle
  - Indebolimento     — livello Exhaustion 0-6 (counter −/+), effetti
                        cumulativi testuali PHB, nessun enforcement automatico
  - Azioni Turno      — Azione / Azione Bonus / Reazione + tracker movimento
                        Nuovo Turno (snapshot per undo) + Annulla
  - Tiri Salvezza & Abilità — riferimento rapido con competenze evidenziate
  - Armi Equipaggiate — nome, danno, bonus al tiro, proprietà, note magiche
  - Magia             — caratteristica, CD, bonus attacco, slot BG3-style,
                        incantesimi preparati per livello
  - Dadi Vita         — cerchietti + Riposo Breve
  - Riposo Lungo      — ripristina tutto

Nota movimento: stored come int (metri interi). Il passo 1.5m usa delta=2.
"""

import flet as ft
import json
import logging
from typing import Any, Callable, cast
from config.settings import *
from config.settings import get_race_display_traits
from data.models import Character, SpellSlot, CharacterProficiency, Weapon, KnownSpell, ClassResource, CreatureEntry, CustomAbility, InventoryItem, CharacterClass
import data.repositories.character_repo as character_repo
from data.game_data.game_data_loader import GameDataLoader
from ui.theme import section_header, muted_text, show_error_dialog
from ui.widgets import (CardPicker, ScrollMemoryListView, wrap_dialog_actions,
                        responsive_dialog_width)
from core.weapon_calculator import AttackContext, compute_attack_total, compute_damage_formula
from core.damage_rules import apply_damage, apply_heal
import core.character_stats as cs
from core.character_stats import RollSpec
from ui.components.roll_panel import show_roll
from ui.components.monster_picker import (
    load_monsters,
    show_monster_picker,
    creature_entry_dict,
    show_stat_block_dialog,
)
from ui import design

_loader = GameDataLoader()

logger = logging.getLogger(__name__)

# Nomi ordinali per i livelli slot
_SLOT_NAMES = ["1°", "2°", "3°", "4°", "5°", "6°", "7°", "8°", "9°"]


class CombattimentoTab(ScrollMemoryListView):
    """
    Tab combattimento: HP, azioni turno, slot, dadi vita, riposi.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.
    """

    def __init__(self, character: Character, on_refresh: Callable[[], None] | None = None):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None
        # Invio automatico dei PF verso il mondo (vedi
        # `_schedule_hp_world_sync()`) — solo per un'istanza
        # di mondo (`character.world_id`), risolto in modo asincrono in
        # `did_mount()` come già fatto altrove per `device_id`
        # (`ui/device_identity.py`). `_hp_sync_generation` è il "token" del
        # debounce: ogni chiamata a `_schedule_hp_world_sync()` lo incrementa,
        # il ciclo asincrono programmato controlla di essere ancora quello
        # più recente prima di inviare — così una raffica di click ravvicinati
        # (es. -1 PF più volte di fila) produce UN SOLO invio con l'ultimo
        # valore, non uno per click.
        self._device_id: str | None = None
        self._hp_sync_generation: int = 0
        #: Cache del device id per il push best-effort delle abilità
        #: personalizzate (`_push_custom_ability_to_world`,
        #: `core.world_sync.push_character_self_command`) — dict separato da
        #: `self._device_id` sopra perché quella funzione condivisa lo tiene
        #: in un dict passato dal chiamante, non su un attributo dedicato.
        self._device_id_cache: dict = {}
        # Mistificatore Arcano (Ladro)/Cavaliere Mistico (Guerriero): sync
        # difensivo ad ogni apertura tab, stesso principio di
        # init_class_resources() più sotto — no-op per qualunque altra
        # classe/sottoclasse. Necessario anche per personaggi la cui
        # sottoclasse era già stata scelta in precedenza: senza questa
        # chiamata resterebbero con spellcasting_ability/slot vuoti finché
        # non affrontano un level-up/level-down.
        character_repo.sync_borrowed_spellcasting_ability(character)
        character_repo.init_borrowed_caster_slots(
            character.id, character.class_name or "", character.subclass or "", character.level
        )
        self._slots: list[SpellSlot] = character_repo.get_spell_slots(character.id)
        # Auto-init slot PHB se il personaggio è un incantatore e non ha ancora slot configurati
        if character.spellcasting_ability and all(s.total == 0 for s in self._slots):
            character_repo.auto_init_spell_slots(
                character.id, character.class_name or "", character.level
            )
            self._slots = character_repo.get_spell_slots(character.id)
        self._profs: list[CharacterProficiency] = character_repo.get_proficiencies(character.id)
        self._weapons: list[Weapon] = character_repo.get_weapons(character.id)
        # Condizioni attive + i loro effetti uniti. Gli effetti servono solo
        # ai promemoria in sola lettura: l'app segnala "svantaggio" accanto
        # ai tiri, non lo applica mai da sola.
        self._conditions = character_repo.get_conditions(character.id)
        self._cond_effects = character_repo.condition_effects(character.id)
        # Armature/scudi equipaggiati: gli effetti magici di armature/scudi
        # vengono mostrati anche in Combattimento, non solo per le armi.
        self._armor_items: list[InventoryItem] = [
            it for it in character_repo.get_inventory(character.id)
            if it.category == "armor" and it.is_equipped
        ]
        self._prepared: list[KnownSpell] = character_repo.get_prepared_spells(character.id)
        self._resources: list[ClassResource] = character_repo.get_class_resources(character.id)
        # Sync automatico a ogni apertura della tab: aggiunge risorse nuove, aggiorna
        # i pool massimi in base al livello corrente (es. Furia che scala nel tempo) e
        # rimuove risorse non più applicabili (es. sottoclasse cambiata) — idempotente,
        # non tocca current_value oltre al clamp al nuovo massimo.
        if character.class_name:
            character_repo.init_class_resources(
                character.id, character.class_name, character.level, character
            )
            self._resources = character_repo.get_class_resources(character.id)
        self._features: list[dict] = self._load_class_features(character)
        self._race_traits: dict = get_race_display_traits(
            character.race or "", character.subrace or ""
        )
        # Forme selvatiche e evocazioni
        self._forme: list[CreatureEntry] = character_repo.get_creature_entries(
            character.id, entry_type="forma"
        )
        self._evocazioni: list[CreatureEntry] = character_repo.get_creature_entries(
            character.id, entry_type="evocazione"
        )
        # Abilità Speciali custom di combattimento: abilità concesse dal
        # master o annotazioni aggiuntive — puramente additivo, mai in
        # sostituzione delle feature JSON ufficiali già mostrate sopra in
        # "Abilità di Classe"/"Tratti di Razza".
        self._custom_abilities: list[CustomAbility] = character_repo.get_custom_abilities(
            character.id, "combattimento"
        )
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)
        if self.character.world_id and self._page is not None:
            self._page.run_task(self._init_device_identity)

    # ------------------------------------------------------------------
    # Invio automatico dei PF verso il mondo
    #
    # I PF che un giocatore si segna da solo (danno subito, cura, riposo,
    # tiri salvezza contro morte, modifica manuale) vengono inviati al
    # mondo/incontro in tempo reale, così come le azioni dirette del
    # master ("Interviene a distanza", `hp.damage`/`hp.heal`). Distinto
    # dall'"Aggiorna il mio foglio" manuale (§6.1), che resta per il
    # resync COMPLETO del personaggio, non per i soli PF.
    #
    # Principi seguiti, tutti con un precedente già nel progetto:
    #   * MAI bloccante — la scheda locale si aggiorna e basta, l'invio è
    #     "best effort" in background (stesso principio di
    #     `HomeView._push_instance_to_host`); un fallimento (host
    #     irraggiungibile, cooldown) non mostra alcun errore all'utente, il
    #     prossimo invio porterà comunque lo stato più recente.
    #   * Valori ASSOLUTI, mai un delta (`hp_current`/`hp_temp`/tiri
    #     salvezza contro morte così come sono DOPO la modifica locale):
    #     un invio perso non lascia nulla di incoerente da recuperare,
    #     idempotente per costruzione.
    #   * Debounce lato client (token `_hp_sync_generation`) + cooldown
    #     dedicato (`core.world_sync.HP_SELF_UPDATE_COOLDOWN_S`, PIÙ CORTO
    #     di quello del master perché qui non c'è alcuna attesa percepita
    #     da minimizzare, è tutto invisibile) + difesa in profondità lato
    #     host (`core.world_backend._check_rate_limit`) — stessa architettura
    #     a tre livelli già in uso per ogni altro comando di rete.
    # ------------------------------------------------------------------

    async def _init_device_identity(self) -> None:
        page = self._page
        if page is None:
            return
        from ui.device_identity import resolve_device_id
        self._device_id = await resolve_device_id(page)

    def _schedule_hp_world_sync(self) -> None:
        """Da richiamare SUBITO dopo ogni scrittura locale di PF/PF
        temporanei/tiri salvezza contro morte di questo personaggio — vedi
        il commento sopra. No-op silenzioso se il personaggio non è
        un'istanza di un mondo: la stragrande maggioranza dei personaggi
        (gioco in locale) non deve mai nemmeno considerare la rete."""
        if not self.character.world_id:
            return
        page = self._page
        if page is None:
            return
        self._hp_sync_generation += 1
        page.run_task(self._push_hp_to_world, self._hp_sync_generation)

    async def _push_hp_to_world(self, generation: int) -> None:
        import asyncio

        from core import world_permissions as perm
        from core import world_sync

        # Debounce: aspetta che l'utente smetta di toccare i PF prima di
        # spedire — se nel frattempo è arrivata una chiamata più recente
        # (generation è cambiato), questa si ferma qui: se ne occuperà
        # quella più recente, che porta comunque il valore più aggiornato.
        await asyncio.sleep(perm.HP_SELF_UPDATE_COOLDOWN_S)
        if generation != self._hp_sync_generation:
            return

        if self._device_id is None:
            page = self._page
            if page is None:
                return
            from ui.device_identity import resolve_device_id
            self._device_id = await resolve_device_id(page)
        if not self._device_id:
            return

        remaining = world_sync.hp_self_update_cooldown_remaining(self.character.id)
        if remaining > 0:
            # Non riprova da sola: la PROSSIMA modifica dei PF (se ce n'è
            # una) richiamerà comunque `_schedule_hp_world_sync()` e quindi
            # un nuovo debounce — nessun invio è "perso" nel senso che
            # conta, perché i valori sono assoluti, non un delta.
            return

        from core.world_backend import LocalBackend
        from data.repositories import world_repo
        world = world_repo.get_world(self.character.world_id)
        if world is None:
            return
        backend = world_sync.resolve_backend_for_world(
            world, self._device_id, LocalBackend(), {},
        )
        if backend is None:
            return

        world_sync.mark_hp_self_update(self.character.id)
        c = self.character
        try:
            backend.send_command(
                world.id, self._device_id or "", perm.CMD_HP_SELF_UPDATE,
                {
                    "hp_current": c.hp_current, "hp_temp": c.hp_temp,
                    "death_saves_success": c.death_saves_success,
                    "death_saves_failure": c.death_saves_failure,
                },
                target_type="character", target_id=c.id,
            )
        except Exception as e:
            # Best effort per definizione (vedi il commento sopra): logga e
            # basta, non deve mai interrompere l'esperienza sulla scheda.
            logger.warning("Invio hp.self_update fallito per %s: %s", c.id, e)

    # ------------------------------------------------------------------
    # Condizioni — invio automatico verso il mondo (estensione di
    # hp.self_update, così che la scheda del giocatore resti sincronizzata
    # con quella del master). A differenza dei PF non serve alcun debounce
    # con "generation": aggiungere/rimuovere una condizione è già un'azione
    # discreta e deliberata (un dialog di conferma esplicito), non un
    # flusso continuo di piccoli cambiamenti — un invio per azione.
    # ------------------------------------------------------------------

    def _schedule_condition_apply_sync(self, condition_key: str, source: str, note: str) -> None:
        """Da richiamare SUBITO dopo aver aggiunto una condizione sulla
        propria scheda. No-op silenzioso se il personaggio non è un'istanza
        di un mondo — stesso principio di `_schedule_hp_world_sync()`."""
        if not self.character.world_id:
            return
        page = self._page
        if page is None:
            return
        page.run_task(self._push_condition_to_world, "apply", condition_key, source, note, "")

    def _schedule_condition_remove_sync(self, condition_key: str) -> None:
        """Da richiamare SUBITO dopo aver rimosso una condizione dalla
        propria scheda. Identifica per `condition_key` (cosa la condizione
        È), MAI per l'id della riga locale — vedi il docstring di
        `core.world_backend._handle_condition_self_remove` per il perché
        (un id di replica non ha significato sull'host)."""
        if not self.character.world_id:
            return
        page = self._page
        if page is None:
            return
        page.run_task(self._push_condition_to_world, "remove", condition_key, "", "", "")

    async def _push_condition_to_world(self, action: str, condition_key: str, source: str,
                                        note: str, _unused: str = "") -> None:
        from core import world_permissions as perm
        from core import world_sync

        if self._device_id is None:
            page = self._page
            if page is None:
                return
            from ui.device_identity import resolve_device_id
            self._device_id = await resolve_device_id(page)
        if not self._device_id:
            return

        remaining = world_sync.condition_self_update_cooldown_remaining(self.character.id)
        if remaining > 0:
            # Nessun retry automatico, stesso principio di
            # `_push_hp_to_world`: qui però un invio saltato non verrà
            # "recuperato" da un'azione successiva come i PF (non c'è un
            # valore assoluto continuamente risincronizzato) — accettabile
            # per un limite pensato contro click ripetuti accidentali, non
            # contro l'uso normale (un giocatore non applica/rimuove
            # condizioni più volte al secondo nel gioco reale).
            return

        from core.world_backend import LocalBackend
        from data.repositories import world_repo
        world = world_repo.get_world(self.character.world_id)
        if world is None:
            return
        backend = world_sync.resolve_backend_for_world(
            world, self._device_id, LocalBackend(), {},
        )
        if backend is None:
            return

        world_sync.mark_condition_self_update(self.character.id)
        if action == "apply":
            kind = perm.CMD_CONDITION_SELF_APPLY
            payload = {"condition_key": condition_key, "source": source, "note": note}
        else:
            kind = perm.CMD_CONDITION_SELF_REMOVE
            payload = {"condition_key": condition_key}
        try:
            backend.send_command(
                world.id, self._device_id or "", kind, payload,
                target_type="character", target_id=self.character.id,
            )
        except Exception as e:
            # Best effort per definizione: logga e basta, non deve mai
            # interrompere l'esperienza sulla scheda.
            logger.warning("Invio condition.self_%s fallito per %s: %s",
                           action, self.character.id, e)

    def _push_custom_ability_to_world(self, action: str, fields: dict) -> None:
        """Invia l'abilità personalizzata (categoria "combattimento") appena
        creata/modificata verso l'host, best effort — no-op se il
        personaggio non è un'istanza di un mondo. Vedi
        `core.world_sync.push_character_self_command`."""
        if not self.character.world_id or self._page is None:
            return
        from core import world_permissions as perm
        from core import world_sync
        kind = (
            perm.CMD_CUSTOM_ABILITY_SELF_CREATE if action == "create"
            else perm.CMD_CUSTOM_ABILITY_SELF_UPDATE
        )
        self._page.run_task(
            world_sync.push_character_self_command,
            self._page, self.character, self._device_id_cache, kind, fields,
        )

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        c = self.character
        # Riferimenti salvati come attributi: `_refresh_hp_only()` e
        # `_refresh_slots_only()` li mutano in-place invece di passare da
        # `_refresh()` pieno (`self.controls.clear()` + `self._build()`),
        # che ricostruendo tutta la tab vanificava l'`animate=` già presente
        # su `design.hp_bar()`/`design.dot_button()` — vedi il piano
        # "Fluidità transizioni e animazioni".
        self._hp_stats_row = design.asymmetric_row(
            self._section_hp(c), self._section_stats(c), ratio=(7, 5))
        self._spell_slots_ref = self._section_spell_slots(c)
        controls: list[ft.Control] = [
            # HP è l'unico elemento "hero" del tab (numero grande, colore
            # dinamico, bottoni Danno/Cura) — affiancarlo alle statistiche di
            # combattimento invece di impilarle rompe la colonna singola
            # meccanica del resto del tab e rispecchia quanto sono
            # effettivamente consultati insieme in combattimento.
            # `section_header("Statistiche di Combattimento")` rimosso:
            # l'accoppiamento visivo con l'HP rende il titolo ridondante, il
            # contenuto (CA/velocità/iniziativa/ispirazione) resta
            # autoesplicativo dalle etichette dei singoli riquadri.
            self._hp_stats_row,
            section_header("Indebolimento"),
            self._section_exhaustion(c),
            section_header("Condizioni"),
            self._section_conditions(),
        ]
        if (c.concentrating_spell or "").strip():
            controls += [
                section_header("Concentrazione", design.T().magic),
                self._section_concentration(c),
            ]
        controls += [
            section_header("Azioni Turno"),
            self._section_turn(c),
            section_header("Tiri Salvezza e Abilità"),
            *([hint2] if (hint2 := self._condition_hint(
                "ability_check_disadvantage", "save_disadvantage",
                "auto_fail_saves")) else []),
            self._section_saves_skills(c),
            section_header("Armi Equipaggiate"),
            *([hint] if (hint := self._condition_hint(
                "attack_disadvantage", "attack_advantage",
                "attacked_advantage", "attacked_disadvantage")) else []),
            self._section_weapons(),
            section_header("Armatura e Scudo Equipaggiati"),
            self._section_armor(),
            section_header("Magia"),
            self._spell_slots_ref,
        ]
        if self._resources:
            self._class_resources_ref = self._section_class_resources()
            controls += [
                section_header("Risorse di Classe"),
                self._class_resources_ref,
            ]
        else:
            self._class_resources_ref = None
        if self._features:
            controls += [
                section_header("Abilità di Classe"),
                self._section_class_features(),
            ]
        _rt = self._race_traits
        if _rt["resistances"] or _rt["advantage_saves"]:
            controls += [
                section_header("Tratti di Razza"),
                self._section_racial_traits(),
            ]
        # Stile di Combattimento — sola consultazione: visibile anche in
        # Combattimento pur restando scelto in Profilo, stesso principio già
        # usato per Abilità di Classe/Tratti di Razza — nessuna duplicazione
        # della scelta, solo lettura.
        if (self.character.fighting_style or "").strip():
            controls += [
                section_header("Stile di Combattimento"),
                self._section_fighting_style(),
            ]
        # Suppliche Occulte (Warlock) — stesso principio di sola lettura.
        if any(p.proficiency_type == "invocation" for p in self._profs):
            controls += [
                section_header("Suppliche Occulte"),
                self._section_invocations(),
            ]
        controls += [
            self._section_custom_abilities_header(),
            self._section_custom_abilities(),
        ]
        # Forme selvatiche — solo Druido
        if (c.class_name or "").lower() == "druido":
            controls += [
                section_header("Forme Selvatiche"),
                self._section_forme(),
            ]
        # Evocazioni — tutti i personaggi
        controls += [
            section_header("Evocazioni"),
            self._section_evocazioni(),
        ]
        controls += [
            section_header("Dadi Vita"),
            self._section_hit_dice(c),
            self._section_riposo_lungo(c),
        ]
        self.controls = controls

    # ------------------------------------------------------------------
    # Sezione HP
    # ------------------------------------------------------------------

    def _section_hp(self, c: Character) -> ft.Container:
        hp_ratio = (c.hp_current / c.hp_max) if c.hp_max > 0 else 0.0
        hp_ratio = max(0.0, min(1.0, hp_ratio))

        if hp_ratio > 0.5:
            hp_color = design.T().success
        elif hp_ratio > 0.25:
            hp_color = design.T().warning
        else:
            hp_color = design.T().danger

        p = design.T()
        hp_label = ft.Row(
            [
                ft.Text(str(c.hp_current), size=42, weight=ft.FontWeight.BOLD,
                        color=hp_color, font_family=design.Font.MONO),
                ft.Text(f"/{c.hp_max}", size=18, color=p.text_3,
                        font_family=design.Font.MONO),
                ft.Container(width=design.Space.SM),
                design.label("punti ferita"),
                ft.Container(expand=True),
                # Riquadro HP temporanei: cliccabile in modo autonomo rispetto
                # alla matita degli HP max (regola "nessuna azione nascosta")
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("HP TEMP", size=design.Size.LABEL,
                                            color=p.text_3, weight=ft.FontWeight.BOLD,
                                            font_family=design.Font.BODY),
                                    ft.Icon(ft.Icons.EDIT, size=9, color=p.text_3),
                                ],
                                spacing=2, tight=True,
                            ),
                            ft.Text(
                                f"+{c.hp_temp}" if c.hp_temp else "—",
                                size=16, font_family=design.Font.MONO,
                                color=p.magic if c.hp_temp else p.text_3,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=1, tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    on_click=self._on_edit_temp_hp_click,
                    tooltip="Modifica HP Temporanei",
                    ink=True,
                    bgcolor=(ft.Colors.with_opacity(0.10, p.magic) if c.hp_temp
                             else p.surface_alt),
                    border_radius=design.Radius.SM,
                    padding=ft.Padding.symmetric(horizontal=design.Space.MD, vertical=4),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        bar = design.hp_bar(c.hp_current, c.hp_max, c.hp_temp)

        btn_damage = ft.ElevatedButton(
            "Danno",
            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
            on_click=self._on_damage_click,
            expand=True,
            style=ft.ButtonStyle(
                bgcolor=p.danger_fill, color=p.on_primary_fill, elevation=2,
                shadow_color=p.shadow,
                shape=ft.RoundedRectangleBorder(radius=design.Radius.SM),
                padding=ft.Padding.symmetric(vertical=design.Space.MD),
                text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD,
                                        font_family=design.Font.BODY),
            ),
        )
        btn_heal = ft.ElevatedButton(
            "Cura",
            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
            on_click=self._on_heal_click,
            expand=True,
            style=ft.ButtonStyle(
                bgcolor=p.success, color=p.on_accent, elevation=2,
                shadow_color=p.shadow,
                shape=ft.RoundedRectangleBorder(radius=design.Radius.SM),
                padding=ft.Padding.symmetric(vertical=design.Space.MD),
                text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD,
                                        font_family=design.Font.BODY),
            ),
        )
        edit_btn = ft.TextButton(
            "✎ HP Max / Temp",
            on_click=self._on_edit_hp_click,
            style=ft.ButtonStyle(color=p.text_3),
        )

        rows: list[ft.Control] = [
            hp_label,
            ft.Container(height=design.Space.SM),
            bar,
            ft.Container(height=design.Space.MD),
            ft.Row([btn_damage, ft.Container(width=design.Space.MD), btn_heal], spacing=0),
            ft.Row([edit_btn], alignment=ft.MainAxisAlignment.END),
            ft.Divider(color=ft.Colors.with_opacity(0.6, p.border)),
            self._build_death_saves(c),
        ]

        # HP è l'unico elemento "hero" del tab (vedi commento in _build) —
        # `card(hero=True, ...)` invece di un `ft.Container` a mano: stesso
        # ruolo di "elemento più consultato della schermata" già codificato
        # in `design.card()` (level 2, Space.XL, bordo pieno nell'accento)
        # invece di reinventarlo qui a valori sciolti. Il colore resta
        # quello dinamico dello stato di salute (success/warning/danger),
        # non un accento fisso: è più informativo di un rosso statico.
        # `layered_shadow()` (chiamato internamente da `card()`) aggiunge un
        # alone colorato attorno alla card SOLO in tema scuro: un'ombra nera
        # non si vede quasi contro un fondo già scuro, vedi il docstring di
        # `accent_glow()` per il perché non si schiarisce invece `bgcolor`.
        return design.card(
            ft.Column(rows, spacing=4),
            accent=hp_color,
            hero=True,
        )

    def _build_death_saves(self, c: Character) -> ft.Column:
        """
        Tiri salvezza contro morte — sempre visibili.
        Grigi e inattivi quando HP > 0; colorati e interattivi quando HP = 0.
        """
        active = (c.hp_current <= 0)
        succ_color = design.T().success if active else design.T().text_3
        fail_color = design.T().danger  if active else design.T().text_3
        label_color = design.T().text_3

        def _circles(filled: int, color: str, on_click_fn) -> ft.Row:
            chips = []
            for i in range(3):
                is_filled = i < filled
                chips.append(design.dot_button(
                    is_filled,
                    tone=("danger" if color == design.T().danger else "success"),
                    size=18,
                    dim=not active,
                    on_click=(lambda e, n=i + 1: on_click_fn(n)) if active else None,
                    tooltip=(f"Imposta a {i + 1}" if active else "Attivo solo a 0 HP"),
                ))
            return ft.Row(chips, spacing=4)

        def set_success(n: int):
            c.death_saves_success = n if c.death_saves_success != n else n - 1
            character_repo.update_death_saves(c.id, c.death_saves_success, c.death_saves_failure)
            self._schedule_hp_world_sync()
            self._refresh_hp_only()

        def set_failure(n: int):
            c.death_saves_failure = n if c.death_saves_failure != n else n - 1
            character_repo.update_death_saves(c.id, c.death_saves_success, c.death_saves_failure)
            self._schedule_hp_world_sync()
            self._refresh_hp_only()

        status_label = (
            ft.Text("PERSONAGGIO INCONSCIO", size=9, color=design.T().danger,
                    weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
            if active else
            ft.Text("TIRI SALVEZZA MORTE", size=9, color=label_color,
                    weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
        )

        rows: list[ft.Control] = [
            status_label,
            ft.Row([
                ft.Text("Successi:", size=12, color=succ_color, width=80),
                _circles(c.death_saves_success, succ_color, set_success),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([
                ft.Text("Fallimenti:", size=12, color=fail_color, width=80),
                _circles(c.death_saves_failure, fail_color, set_failure),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]

        # Tiro del TS contro morte con applicazione automatica ai pallini.
        # Offerto solo a 0 PF: fuori da quella condizione il tiro non ha
        # senso e segnerebbe pallini a vuoto.
        if active:
            rows.append(
                ft.Row([
                    ft.ElevatedButton(
                        "Tira TS contro morte",
                        icon=ft.Icons.CASINO_OUTLINED,
                        on_click=lambda e: self._roll_death_save(),
                        bgcolor=design.T().danger_fill,
                        color=design.T().on_primary_fill,
                    ),
                ], wrap=True)
            )

        return ft.Column(rows, spacing=4)

    def _roll_death_save(self) -> None:
        """
        Tira il TS contro morte e ne applica subito l'esito (PHB p.197):
          * 20 naturale → il personaggio riprende i sensi con 1 PF;
          * 1 naturale  → vale come **due** fallimenti;
          * ≥10 successo, <10 fallimento;
          * al terzo successo si stabilizza, al terzo fallimento muore.
        Ogni applicazione automatica è accompagnata da un avviso esplicito:
        l'app non deve mai modificare la scheda in silenzio.
        """
        c = self.character

        def _apply(spec, result) -> None:
            nat = result.groups[0].kept[0] if result.groups and result.groups[0].kept else result.total
            title = "Tiro salvezza contro morte"

            if nat == 20:
                c.death_saves_success = 0
                c.death_saves_failure = 0
                c.hp_current = 1
                character_repo.update_death_saves(c.id, 0, 0)
                character_repo.update_hp(c.id, 1)
                self._show_rule_notice(
                    title,
                    "20 naturale: il personaggio riprende i sensi con 1 punto "
                    "ferita e i tiri salvezza contro morte si azzerano.\nPHB p.197.",
                )
            elif nat == 1:
                c.death_saves_failure = min(3, (c.death_saves_failure or 0) + 2)
                character_repo.update_death_saves(c.id, c.death_saves_success,
                                                  c.death_saves_failure)
                msg = ("1 naturale: vale come DUE tiri salvezza falliti "
                       f"({c.death_saves_failure}/3).\nPHB p.197.")
                if c.death_saves_failure >= 3:
                    msg = ("1 naturale: due fallimenti, il terzo è stato "
                           "raggiunto — il personaggio muore.\nPHB p.197.")
                self._show_rule_notice(title, msg)
            elif result.total >= spec.dc:
                c.death_saves_success = min(3, (c.death_saves_success or 0) + 1)
                character_repo.update_death_saves(c.id, c.death_saves_success,
                                                  c.death_saves_failure)
                msg = f"Successo ({result.total} ≥ CD 10): {c.death_saves_success}/3."
                if c.death_saves_success >= 3:
                    msg += ("\nTerzo successo: il personaggio si stabilizza "
                            "(resta a 0 PF, ma non tira più).\nPHB p.197.")
                self._show_rule_notice(title, msg)
            else:
                c.death_saves_failure = min(3, (c.death_saves_failure or 0) + 1)
                character_repo.update_death_saves(c.id, c.death_saves_success,
                                                  c.death_saves_failure)
                msg = f"Fallimento ({result.total} < CD 10): {c.death_saves_failure}/3."
                if c.death_saves_failure >= 3:
                    msg += "\nTerzo fallimento: il personaggio muore.\nPHB p.197."
                self._show_rule_notice(title, msg)

            self._schedule_hp_world_sync()
            self._refresh()

        show_roll(self._page, cs.death_save_roll(), on_result=_apply)

    # ------------------------------------------------------------------
    # Condizioni (Appendice A del PHB)
    # ------------------------------------------------------------------

    def _condition_hint(self, *keys: str) -> ft.Control | None:
        """
        Promemoria contestuale di una condizione attiva, in **sola lettura**.

        L'app mostra l'effetto dove serve — es. "svantaggio" accanto ai tiri
        per colpire se il personaggio è Avvelenato — ma non lo applica mai
        da sola. Ritorna `None` se nessuna delle condizioni indicate è
        attiva, così i chiamanti possono ignorarlo.
        """
        labels = {
            "attack_disadvantage": "Svantaggio ai tiri per colpire",
            "attack_advantage": "Vantaggio ai tiri per colpire",
            "attacked_advantage": "Vantaggio a chi ti attacca",
            "attacked_disadvantage": "Svantaggio a chi ti attacca",
            "ability_check_disadvantage": "Svantaggio alle prove di caratteristica",
            "save_disadvantage": "Svantaggio ai tiri salvezza su Destrezza",
            "auto_fail_saves": "Fallisci automaticamente i TS su Forza e Destrezza",
            "speed_zero": "Velocità 0",
            "incapacitated": "Incapacitato: niente azioni né reazioni",
        }
        eff = self._cond_effects
        chips: list[ft.Control] = []
        for k in keys:
            if not eff.get(k):
                continue
            sources = eff.get("_sources", {}).get(k, [])
            text = labels.get(k, k)
            if sources:
                text += f" — {', '.join(dict.fromkeys(sources))}"
            chips.append(design.chip(text, "warning",
                                     icon=ft.Icons.WARNING_AMBER_OUTLINED))
        if not chips:
            return None
        return ft.Row(chips, spacing=6, wrap=True)

    def _section_conditions(self) -> ft.Container:
        p = design.T()
        rows: list[ft.Control] = []

        if self._conditions:
            chips: list[ft.Control] = []
            for cond in self._conditions:
                data = _loader.get_condition(cond.condition_key) or {}
                name = data.get("name", cond.condition_key)
                label = f"{name} · {cond.source}" if cond.source else name
                chips.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(label, size=12, weight=ft.FontWeight.BOLD,
                                        color=p.on_accent, font_family=design.Font.BODY),
                                ft.Icon(ft.Icons.CLOSE, size=13, color=p.on_accent),
                            ],
                            spacing=6, tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        bgcolor=p.warning,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                        border_radius=design.Radius.PILL,
                        on_click=(lambda e, cc=cond: self._on_condition_click(cc)),
                        ink=True,
                        tooltip=f"{name} — clicca per il testo o per rimuoverla",
                    )
                )
            rows.append(ft.Row(chips, spacing=6, wrap=True))
        else:
            rows.append(ft.Text("Nessuna condizione attiva.", size=12,
                                color=p.text_3, italic=True))

        rows.append(ft.Row([
            ft.TextButton("+ Aggiungi condizione", icon=ft.Icons.ADD,
                          on_click=lambda e: self._open_condition_picker()),
        ], wrap=True))

        return ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor=p.surface,
            padding=12,
            border=ft.Border.only(left=ft.BorderSide(3, p.warning)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _on_condition_click(self, cond) -> None:
        """Mostra il testo integrale della condizione e offre di rimuoverla."""
        page = self._page
        if page is None:
            return
        data = _loader.get_condition(cond.condition_key) or {}
        name = data.get("name", cond.condition_key)

        def _remove(_e):
            character_repo.remove_condition(cond.id)
            self._schedule_condition_remove_sync(cond.condition_key)
            page.pop_dialog()
            self._refresh()

        body: list[ft.Control] = []
        if cond.source:
            body.append(ft.Text(f"Fonte: {cond.source}", size=12,
                                color=design.T().text_2, italic=True))
        body.append(ft.Text(data.get("description", ""), size=13,
                            color=design.T().text, selectable=True))
        body.append(ft.Text("Manuale del Giocatore, Appendice A.", size=11,
                            color=design.T().text_3, italic=True))

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(name, icon=ft.Icons.WARNING_AMBER_OUTLINED),
            content=ft.Container(
                content=ft.Column(body, spacing=8, scroll=ft.ScrollMode.AUTO,
                                  tight=True),
                width=responsive_dialog_width(page, 380),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Rimuovi", icon=ft.Icons.CHECK, on_click=_remove,
                    style=ft.ButtonStyle(bgcolor=design.T().success,
                                         color=design.T().on_accent),
                ),
            ]),
        ))

    def _open_condition_picker(self) -> None:
        """
        Picker delle 14 condizioni con la descrizione visibile PRIMA di
        scegliere — stesso `CardPicker` già adottato per incantesimi e talenti.
        """
        page = self._page
        if page is None:
            return
        conditions = _loader.get_conditions()
        picker = CardPicker(
            options=[{"key": c["key"], "title": c["name"],
                      "body": c.get("description", "")} for c in conditions],
        )
        if conditions:
            picker.value = conditions[0]["key"]
        source_tf = ft.TextField(label="Fonte (facoltativa)", dense=True,
                                 hint_text="es. Incantesimo Spavento del Bardo",
                                 **design.field_style())

        def _add(_e):
            key = picker.value
            if not key:
                return
            source = (source_tf.value or "").strip()
            character_repo.add_condition(self.character.id, key, source)
            self._schedule_condition_apply_sync(key, source, "")
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Aggiungi condizione"),
            content=ft.Container(
                content=ft.Column([source_tf, picker.control], spacing=10,
                                  scroll=ft.ScrollMode.AUTO),
                width=responsive_dialog_width(page, 380), height=460,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Aggiungi", icon=ft.Icons.ADD, on_click=_add,
                    style=ft.ButtonStyle(bgcolor=design.T().warning,
                                         color=design.T().on_accent),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Concentrazione (PHB p.203-204)
    # ------------------------------------------------------------------

    def _section_concentration(self, c: Character) -> ft.Container:
        """Riquadro dell'incantesimo su cui il personaggio si sta concentrando."""
        spell = (c.concentrating_spell or "").strip()
        p = design.T()
        return ft.Container(
            content=ft.Row(
                [
                    # Icona CENTER_FOCUS_STRONG rimossa: puramente decorativa
                    # — il nome dell'incantesimo sotto è già titolato dalla
                    # sezione "Concentrazione" (section_header sopra questa
                    # card), l'icona non aggiungeva alcuna informazione in
                    # più.
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(spell, size=14, weight=ft.FontWeight.BOLD,
                                        color=p.text, font_family=design.Font.BODY),
                                ft.Text(
                                    "Interrompere non richiede alcuna azione (PHB p.203).",
                                    size=11, color=p.text_3, italic=True),
                            ],
                            spacing=2, tight=True,
                        ),
                        expand=True,
                    ),
                    ft.TextButton("Interrompi", icon=ft.Icons.CLOSE,
                                  on_click=lambda e: self._end_concentration()),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
            bgcolor=p.surface,
            padding=12,
            border=ft.Border.only(left=ft.BorderSide(3, p.magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _end_concentration(self) -> None:
        character_repo.clear_concentration(self.character.id)
        self.character.concentrating_spell = ""
        self.character.concentrating_since = ""
        self._refresh()

    def _prompt_concentration_save(self, spell_name: str, damage: int) -> None:
        """
        Propone il TS di Costituzione per mantenere la concentrazione.

        PHB p.203: "Ogni volta che l'incantatore subisce danni mentre si
        concentra su un incantesimo, deve effettuare un tiro salvezza su
        Costituzione per mantenere la sua concentrazione. La CD è pari a 10 o
        alla metà dei danni subiti (si sceglie il valore più alto)."

        Il tiro non è obbligatorio da fare qui: il dialog ha anche "Interrompi"
        e "Ho superato il tiro", perché al tavolo il dado può averlo già tirato
        il giocatore.
        """
        page = self._page
        if page is None:
            return
        c = self.character
        dc = cs.concentration_save_dc(damage)
        base = cs.save_roll(c, self._profs, "con")
        spec = RollSpec(
            kind="save", label=f"Concentrazione — TS Costituzione (CD {dc})",
            modifier=base.modifier, ability="con", proficient=base.proficient,
            note=base.note, dc=dc,
        )

        def _keep(_e):
            page.pop_dialog()

        def _break(_e):
            page.pop_dialog()
            self._end_concentration()

        def _do_roll(_e):
            page.pop_dialog()

            def _apply(_spec, result):
                # Coerente con il pannello dei tiri: un 1 o un 20 naturale
                # decidono da soli l'esito, senza sommare il modificatore.
                # Nota: il PHB 2014 non prevede critici sui tiri salvezza —
                # è una convenzione applicata qui perché l'app mostri sempre
                # la stessa cosa.
                if result.is_crit_fail:
                    self._end_concentration()
                    self._show_rule_notice(
                        "Concentrazione interrotta",
                        f"1 naturale: «{spell_name}» termina.",
                        design.T().magic,
                    )
                elif result.is_crit:
                    self._show_rule_notice(
                        "Concentrazione mantenuta",
                        f"20 naturale: «{spell_name}» resta attivo.",
                        design.T().success,
                    )
                elif result.total >= dc:
                    self._show_rule_notice(
                        "Concentrazione mantenuta",
                        f"{result.total} ≥ CD {dc}: «{spell_name}» resta attivo.",
                        design.T().success,
                    )
                else:
                    self._end_concentration()
                    self._show_rule_notice(
                        "Concentrazione interrotta",
                        f"{result.total} < CD {dc}: «{spell_name}» termina.\n"
                        "PHB p.203.",
                        design.T().magic,
                    )

            show_roll(self._page, spec, on_result=_apply)

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Mantenere la concentrazione?"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            f"«{spell_name}» richiede concentrazione e hai subito "
                            f"{damage} danni.",
                            size=13, color=design.T().text),
                        ft.Text(
                            f"Tiro salvezza su Costituzione, CD {dc} "
                            f"(10 oppure metà dei danni, il maggiore).",
                            size=12, color=design.T().text_2),
                        ft.Text("PHB p.203.", size=11, color=design.T().text_3,
                                italic=True),
                    ],
                    spacing=6, tight=True,
                ),
                width=responsive_dialog_width(page, 320),
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Interrompi", on_click=_break),
                ft.TextButton("Ho superato il tiro", on_click=_keep),
                ft.ElevatedButton(
                    "Tira", icon=ft.Icons.CASINO_OUTLINED, on_click=_do_roll,
                    style=ft.ButtonStyle(bgcolor=design.T().magic,
                                         color=design.T().on_accent),
                ),
            ]),
        ))

    def _roll_weapon(self, weapon_id: str, what: str) -> None:
        """Tira attacco o danni dell'arma indicata, rileggendola dallo stato."""
        weapon = next((w for w in self._weapons if w.id == weapon_id), None)
        if weapon is None:
            return
        spec = (cs.attack_roll(self.character, weapon, self._profs) if what == "attack"
                else cs.damage_roll(self.character, weapon))
        show_roll(self._page, spec)

    # ------------------------------------------------------------------
    # HP dialogs
    # ------------------------------------------------------------------

    def _show_rule_notice(self, title: str, message: str,
                          accent: str | None = None) -> None:
        """
        Avviso informativo su una regola applicata automaticamente dall'app
        (es. tiri salvezza contro morte, morte istantanea, indebolimento al
        riposo lungo). Sempre esplicito: l'app non deve mai modificare la
        scheda in silenzio.
        """
        page = self._page
        if page is None:
            return
        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(title),
            content=ft.Text(message, size=13, color=design.T().text),
            actions=[ft.TextButton("OK", on_click=lambda ev: page.pop_dialog())],
        ))

    def _on_damage_click(self, e):
        if not self._page:
            return
        page = self._page
        field_style = design.field_style()
        field_style["focused_border_color"] = design.T().danger
        field = ft.TextField(
            label="Quantità danno", keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True, text_align=ft.TextAlign.CENTER,
            **field_style)
        # PHB p.197 "Danni a 0 punti ferita": un colpo critico subito a 0 PF
        # equivale a DUE tiri salvezza contro morte falliti invece di uno.
        crit_cb = ft.Checkbox(
            label="Colpo critico",
            value=False,
            label_style=ft.TextStyle(size=12, color=design.T().text_2),
            active_color=design.T().danger_fill,
        )

        def apply(ev):
            if page is None:
                return
            try:
                amt = max(0, int(field.value or 0))
            except ValueError:
                return
            c = self.character
            # Regole PHB (assorbimento HP temp, morte istantanea, TS contro
            # morte a 0 PF, concentrazione) vivono in core/damage_rules.py,
            # condivise con il comando remoto del master.
            outcome = apply_damage(c, amt, is_critical=bool(crit_cb.value))

            character_repo.update_hp(c.id, c.hp_current, c.hp_temp)
            if outcome.death_note:
                character_repo.update_death_saves(
                    c.id, c.death_saves_success, c.death_saves_failure
                )
            if outcome.concentration_broken:
                character_repo.clear_concentration(c.id)

            self._schedule_hp_world_sync()
            page.pop_dialog()
            if outcome.concentration_broken:
                # La sezione "Concentrazione" compare/scompare in _build()
                # in base a c.concentrating_spell: cambiamento strutturale,
                # serve il rebuild pieno (vedi _refresh_hp_only()).
                self._refresh()
            else:
                self._refresh_hp_only()
            if outcome.death_note:
                self._show_rule_notice(
                    "Tiri Salvezza contro Morte", outcome.death_note, design.T().danger
                )
            elif outcome.concentration_broken:
                self._show_rule_notice(
                    "Concentrazione interrotta",
                    f"«{outcome.concentration_spell}» termina: a 0 punti ferita il "
                    "personaggio è incapacitato.\nPHB p.204 — «Incantatore "
                    "incapacitato o ucciso».",
                    design.T().magic,
                )
            if outcome.concentration_check_needed:
                self._prompt_concentration_save(outcome.concentration_spell, outcome.amount_to_hp)

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Applica Danno"),
            content=ft.Column([field, crit_cb], width=240, spacing=4, tight=True),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Applica", on_click=apply,
                                  style=ft.ButtonStyle(bgcolor=design.T().danger_fill, color=design.T().on_primary_fill)),
            ]),
        ))

    def _on_heal_click(self, e):
        if not self._page:
            return
        page = self._page
        field_style = design.field_style()
        field_style["focused_border_color"] = design.T().success
        field = ft.TextField(
            label="Quantità cura", keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True, text_align=ft.TextAlign.CENTER,
            **field_style)

        def apply(ev):
            if page is None:
                return
            try:
                amt = max(0, int(field.value or 0))
            except ValueError:
                return
            c = self.character
            # PHB p.197: "Il numero di entrambi i tipi torna a zero quando il
            # personaggio recupera dei punti ferita o diventa stabile" — e
            # "Il personaggio riprende i sensi se recupera un qualsiasi
            # ammontare di punti ferita". Vedi core/damage_rules.py.
            outcome = apply_heal(c, amt)
            character_repo.update_hp(c.id, c.hp_current, c.hp_temp)
            if outcome.death_saves_reset:
                character_repo.update_death_saves(c.id, 0, 0)
            self._schedule_hp_world_sync()
            page.pop_dialog()
            self._refresh_hp_only()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Applica Cura"),
            content=ft.Column([field], width=240, spacing=0),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Cura", on_click=apply,
                                  style=ft.ButtonStyle(bgcolor=design.T().success, color=design.T().on_primary)),
            ]),
        ))

    def _on_edit_temp_hp_click(self, e: Any) -> None:
        """
        Click diretto sul box "HP TEMP" — imposta i punti ferita temporanei
        senza passare dal dialog combinato "✎ HP Max / Temp" (che tocca
        anche HP Max e HP Attuali). Permette di modificare gli HP
        temporanei senza toccare gli altri campi; il pulsante "✎ HP Max /
        Temp" resta invariato per quando serve modificare più campi insieme.
        """
        page = self._page
        if page is None:
            return
        c = self.character

        field = ft.TextField(
            label="HP Temporanei", value=str(c.hp_temp or 0),
            keyboard_type=ft.KeyboardType.NUMBER, autofocus=True,
            text_align=ft.TextAlign.CENTER,
            **design.field_style())

        def apply(ev: Any) -> None:
            if page is None:
                return
            try:
                c.hp_temp = max(0, int(field.value or 0))
            except ValueError:
                return
            if not character_repo.update_hp(c.id, c.hp_current, c.hp_temp):
                show_error_dialog(page, "Impossibile salvare gli HP temporanei.")
                return
            self._schedule_hp_world_sync()
            page.pop_dialog()
            self._refresh_hp_only()

        def reset(ev: Any) -> None:
            if page is None:
                return
            c.hp_temp = 0
            if not character_repo.update_hp(c.id, c.hp_current, c.hp_temp):
                show_error_dialog(page, "Impossibile salvare gli HP temporanei.")
                return
            self._schedule_hp_world_sync()
            page.pop_dialog()
            self._refresh_hp_only()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("HP Temporanei"),
            content=ft.Column([field], width=240, spacing=0),
            actions=wrap_dialog_actions([
                ft.TextButton("Azzera", on_click=reset),
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Applica", on_click=apply,
                                  style=ft.ButtonStyle(bgcolor=design.T().magic, color=design.T().on_accent)),
            ]),
        ))

    def _on_edit_hp_click(self, e):
        page = self._page
        if page is None:
            return
        c = self.character

        def _num_field(label: str, value: int) -> ft.TextField:
            return ft.TextField(
                label=label, value=str(value),
                keyboard_type=ft.KeyboardType.NUMBER,
                **design.field_style())

        f_max  = _num_field("HP Max", c.hp_max)
        f_curr = _num_field("HP Attuali", c.hp_current)
        f_temp = _num_field("HP Temporanei", c.hp_temp or 0)

        def save(ev):
            if page is None:
                return
            try:
                c.hp_max     = max(1, int(f_max.value or c.hp_max))
                c.hp_current = max(0, min(c.hp_max, int(f_curr.value or c.hp_current)))
                c.hp_temp    = max(0, int(f_temp.value or 0))
            except ValueError:
                return
            character_repo.update_hp(c.id, c.hp_current, c.hp_temp)
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            self._schedule_hp_world_sync()
            page.pop_dialog()
            self._refresh_hp_only()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Modifica HP"),
            content=ft.Column([f_max, f_curr, f_temp], spacing=10),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Salva", on_click=save,
                                  style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill)),
            ]),
        ))

    # ------------------------------------------------------------------
    # Statistiche di combattimento
    # ------------------------------------------------------------------

    def _section_stats(self, c: Character) -> ft.Container:
        # Iniziativa da core/character_stats (unica fonte).
        init_spec = cs.initiative_roll(c)
        init_str = init_spec.modifier_str

        # Velocità effettiva: base (razza + override manuale + Talento Mobile)
        # + bonus dinamico di classe non equipaggiato (Monaco/Barbaro, Categoria B)
        effective_speed = character_repo.get_effective_speed(c)
        speed_bonus_active = effective_speed != (c.speed or 0)
        speed_label = "VELOCITÀ" if not speed_bonus_active else "VELOCITÀ ✦"

        def _stat_box(label: str, value: str, accent: str | None = None,
                      on_click=None, tooltip: str | None = None,
                      rollable: bool = False) -> ft.Container:
            accent = accent or design.T().text
            value_row: ft.Control = ft.Text(
                value, size=22, color=accent, weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER, font_family=design.Font.MONO)
            if rollable:
                value_row = ft.Row(
                    [
                        value_row,
                        ft.Icon(ft.Icons.CASINO_OUTLINED, size=12, color=accent),
                    ],
                    spacing=4, tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(label, size=9, color=design.T().text_3,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                        value_row,
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=design.T().surface,
                padding=ft.Padding.symmetric(vertical=10, horizontal=8),
                shadow=design.elevation(1),
                border_radius=design.Radius.MD,
                expand=True,
                on_click=on_click,
                ink=bool(on_click),
                tooltip=tooltip,
            )

        ispir_active = bool(c.inspiration)
        ispir_color  = design.T().warning if ispir_active else design.T().text_3
        ispir_icon   = ft.Icons.STAR if ispir_active else ft.Icons.STAR_BORDER
        ispir_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text("ISPIR.", size=9, color=design.T().text_3,
                            weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Icon(ispir_icon, size=22, color=ispir_color),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(vertical=10, horizontal=8),
            border=ft.Border.all(1, ispir_color),
            border_radius=design.Radius.MD,
            expand=True,
            on_click=self._toggle_inspiration,
            ink=True,
            tooltip="Attiva / disattiva ispirazione",
        )

        # Box CA cliccabile — mostra bonus temporaneo se attivo
        ca_bonus = c.ca_bonus
        ca_total = c.ac + ca_bonus
        ca_label = "CA" if ca_bonus == 0 else f"CA (+{ca_bonus})" if ca_bonus > 0 else f"CA ({ca_bonus})"
        ca_color = design.T().magic if ca_bonus > 0 else (design.T().primary if ca_bonus < 0 else design.T().text)
        ca_box = ft.Container(
            content=ft.Column(
                [
                    ft.Text(ca_label, size=9, color=design.T().text_3,
                            weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text(str(ca_total), size=22, color=ca_color,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                            font_family=design.Font.MONO),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(vertical=10, horizontal=8),
            border=ft.Border.all(2 if ca_bonus != 0 else 1,
                                 ca_color if ca_bonus != 0 else design.T().border),
            border_radius=design.Radius.MD,
            expand=True,
            on_click=self._on_ca_bonus_click,
            ink=True,
            tooltip="Clicca per aggiungere/rimuovere bonus CA temporaneo",
        )

        # `card(density="dense")` invece del `ft.Container` a mano — stessa
        # resa (bordo/ombra/raggio livello 1, padding Space.MD=12 già usato
        # qui) ma passando dal token condiviso, coerente col trattamento
        # "dense" delle altre sezioni dati-intensive di questa tab
        # (statistiche/tiri salvezza/abilità).
        return design.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ca_box,
                            _stat_box(speed_label,
                                     ("0m" if self._cond_effects.get("speed_zero")
                                      else f"{effective_speed:g}m"),
                                     design.T().magic if speed_bonus_active else design.T().text),
                            _stat_box(
                                "INIZIAT.", init_str, design.T().magic,
                                on_click=lambda e: show_roll(
                                    self._page, cs.initiative_roll(self.character)),
                                tooltip=f"Tira l'iniziativa ({init_spec.note})",
                                rollable=True,
                            ),
                            ispir_box,
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            ft.TextButton(
                                "✎ Modifica CA / Velocità",
                                on_click=self._on_edit_stats_click,
                                style=ft.ButtonStyle(color=design.T().text_3),
                            )
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=6,
            ),
            accent=design.T().primary,
            density="dense",
        )

    def _toggle_inspiration(self, e):
        self.character.inspiration = not self.character.inspiration
        if not character_repo.update(self.character):
            self.character.inspiration = not self.character.inspiration  # rollback in memoria
            show_error_dialog(self._page)
            return
        self._refresh_stats_only()

    def _on_edit_stats_click(self, e):
        page = self._page
        if not page:
            return
        c = self.character
        f_ac    = ft.TextField(label="Classe Armatura (CA)", value=str(c.ac),
                               keyboard_type=ft.KeyboardType.NUMBER,
                               **design.field_style())
        f_speed = ft.TextField(label="Velocità (m)", value=str(c.speed),
                               keyboard_type=ft.KeyboardType.NUMBER,
                               **design.field_style())

        def save(ev):
            if page is None:
                return
            try:
                c.ac = max(0, int(f_ac.value or c.ac))
                # float, non int: alcune razze hanno velocità frazionaria
                # (Nano/Halfling 7,5 m, Elfo dei Boschi 10,5 m). Normalizza
                # anche la virgola italiana in punto, nel caso l'utente
                # digiti "7,5".
                speed_raw = (f_speed.value or str(c.speed)).strip().replace(",", ".")
                c.speed = max(0.0, float(speed_raw))
            except ValueError:
                return
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Modifica Statistiche"),
            content=ft.Column([f_ac, f_speed], spacing=10, width=280),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton("Salva", on_click=save,
                                  style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill)),
            ]),
        ))

    def _on_ca_bonus_click(self, e):
        """Dialog per aggiungere/modificare/rimuovere il bonus CA temporaneo."""
        page = self._page
        if not page:
            return
        c = self.character
        cur_bonus = c.ca_bonus

        f_bonus_style = design.field_style()
        f_bonus_style["text_style"] = ft.TextStyle(
            size=16, color=design.T().text, font_family=design.Font.MONO)
        f_bonus = ft.TextField(
            label="Bonus CA temporaneo (positivo o negativo)",
            value=str(cur_bonus),
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            **f_bonus_style)

        info_text = ft.Text(
            f"CA base (armatura): {c.ac}   |   CA totale con bonus: {c.ac + cur_bonus}",
            size=11, color=design.T().text_3,
        )

        def save(ev):
            if page is None:
                return
            try:
                new_bonus = int(f_bonus.value or 0)
            except ValueError:
                new_bonus = 0
            character_repo.update_ca_bonus(c.id, new_bonus)
            c.ca_bonus = new_bonus
            page.pop_dialog()
            self._refresh()

        def reset(ev):
            if page is None:
                return
            character_repo.update_ca_bonus(c.id, 0)
            c.ca_bonus = 0
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Bonus CA Temporaneo"),
            content=ft.Column([
                info_text,
                f_bonus,
                ft.Text(
                    "Usato per incantesimi (es. Scudo), reazioni o condizioni temporanee.\n"
                    "Resetta a 0 a fine round o quando l'effetto termina.",
                    size=11, color=design.T().text_3,
                ),
            ], spacing=8),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton("Reset a 0", on_click=reset,
                              style=ft.ButtonStyle(color=design.T().text_3)),
                ft.ElevatedButton("Applica", on_click=save,
                                  style=ft.ButtonStyle(
                                      bgcolor=design.T().magic, color=design.T().on_accent)),
            ]),
        ))

    # ------------------------------------------------------------------
    # Indebolimento (Exhaustion)
    # ------------------------------------------------------------------

    def _section_exhaustion(self, c: Character) -> ft.Container:
        """
        Livello di Indebolimento (Exhaustion), PHB IT — condizione cumulativa
        0 (nessuno) - 6 (morte). Nessun effetto meccanico viene applicato
        automaticamente (non dimezza velocità/HP max da sola): la sezione
        mostra gli effetti cumulativi attivi al livello corrente per
        consultazione rapida, il giocatore/master li applica a mano — stesso
        principio già usato per Abilità di Classe/Tratti di Razza (testo di
        riferimento, non enforcement automatico delle regole).
        """
        level = c.exhaustion_level

        if level >= 6:
            level_color = design.T().danger
        elif level >= 4:
            level_color = design.T().danger
        elif level >= 1:
            level_color = design.T().warning
        else:
            level_color = design.T().text_3

        level_text = ft.Text(
            f"Livello {level}" if level > 0 else "Nessuno",
            size=18, weight=ft.FontWeight.BOLD, color=level_color,
            font_family=design.Font.MONO,
        )

        counter_row = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    icon_size=22,
                    icon_color=design.T().primary_icon,
                    on_click=self._on_exhaustion_decrement,
                    disabled=level <= 0,
                    tooltip="Riduci di 1 livello",
                ),
                ft.Container(content=level_text, width=90, alignment=ft.Alignment.CENTER),
                ft.IconButton(
                    ft.Icons.ADD_CIRCLE_OUTLINE,
                    icon_size=22,
                    icon_color=level_color if level < 6 else design.T().text_3,
                    on_click=self._on_exhaustion_increment,
                    disabled=level >= 6,
                    tooltip="Aumenta di 1 livello",
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=4,
        )

        effect_rows: list[ft.Control] = []
        if level <= 0:
            effect_rows.append(
                ft.Text("Nessun effetto.", size=12, color=design.T().text_3)
            )
        else:
            for lvl in sorted(EXHAUSTION_LEVELS.keys()):
                if lvl > level:
                    break
                active_color = design.T().danger if lvl == 6 else design.T().text
                effect_rows.append(
                    ft.Row(
                        [
                            ft.Text(f"{lvl}.", size=12, color=level_color,
                                    weight=ft.FontWeight.BOLD, width=18),
                            ft.Text(EXHAUSTION_LEVELS[lvl], size=12, color=active_color,
                                    weight=ft.FontWeight.BOLD if lvl == 6 else ft.FontWeight.NORMAL,
                                    expand=True),
                        ],
                        spacing=4,
                    )
                )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("INDEBOLIMENTO", size=10, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD,
                                    style=ft.TextStyle(letter_spacing=0.8)),
                        ],
                    ),
                    counter_row,
                    ft.Divider(color=design.T().border, height=8),
                    ft.Column(effect_rows, spacing=4),
                ],
                spacing=8,
            ),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, level_color)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _on_exhaustion_increment(self, e: Any) -> None:
        c = self.character
        new_level = min(6, c.exhaustion_level + 1)
        if new_level == c.exhaustion_level:
            return
        character_repo.update_exhaustion_level(c.id, new_level)
        c.exhaustion_level = new_level
        self._refresh()

    def _on_exhaustion_decrement(self, e: Any) -> None:
        c = self.character
        new_level = max(0, c.exhaustion_level - 1)
        if new_level == c.exhaustion_level:
            return
        character_repo.update_exhaustion_level(c.id, new_level)
        c.exhaustion_level = new_level
        self._refresh()

    # ------------------------------------------------------------------
    # Azioni Turno
    # ------------------------------------------------------------------

    def _section_turn(self, c: Character) -> ft.Container:

        def _action_chip(label: str, used: bool, on_click) -> ft.Container:
            """Chip colorato: rosso = disponibile, grigio = usato."""
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if not used else ft.Icons.CANCEL,
                            size=20,
                            color=design.T().on_primary if not used
                            else ft.Colors.with_opacity(0.38, design.T().on_primary),
                        ),
                        ft.Text(
                            label, size=10, text_align=ft.TextAlign.CENTER,
                            color=design.T().on_primary if not used
                            else ft.Colors.with_opacity(0.38, design.T().on_primary),
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=3,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=design.T().primary_fill if not used else design.T().text_3,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=8,
                on_click=on_click,
                ink=True,
                expand=True,
                tooltip="Segna come usato" if not used else "Libera",
            )

        def _save_turn():
            character_repo.update_turn_state(
                c.id, c.action_used, c.bonus_action_used,
                c.reaction_used, c.movement_used,
                c.previous_turn_state or "",
            )

        def toggle_action(e):
            c.action_used = not c.action_used
            _save_turn()
            self._refresh()

        def toggle_bonus(e):
            c.bonus_action_used = not c.bonus_action_used
            _save_turn()
            self._refresh()

        def toggle_reaction(e):
            c.reaction_used = not c.reaction_used
            _save_turn()
            self._refresh()

        # --- Tracker movimento ---
        # Include il bonus dinamico di classe non equipaggiato (Monaco/Barbaro)
        # nel movimento realmente disponibile in combattimento
        speed = character_repo.get_effective_speed(c)
        used_m = c.movement_used or 0
        remaining_m = max(0, speed - used_m)
        move_ratio = min(1.0, used_m / speed) if speed > 0 else 0.0

        def use_movement(delta: float):
            """Aggiunge delta metri al movimento usato (positivo = usa, negativo = recupera)."""
            c.movement_used = max(0.0, min(speed, used_m + delta))
            character_repo.update_turn_state(
                c.id, c.action_used, c.bonus_action_used,
                c.reaction_used, c.movement_used,
                c.previous_turn_state or "",
            )
            self._refresh()

        move_bar = ft.ProgressBar(
            value=move_ratio, color=design.T().warning,
            bgcolor=design.T().surface_alt, height=8, border_radius=4,
        )
        movement_section = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("MOVIMENTO", size=9, color=design.T().text_3,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.Text(
                            f"{remaining_m:g} / {speed:g} m rimanenti",
                            size=12, color=design.T().text,
                        ),
                    ],
                    spacing=4,
                ),
                move_bar,
                # wrap=True: su finestre strette/smartphone i 7 pulsanti vanno a capo su
                # più righe invece di uscire dal bordo destro. Niente più spacer
                # expand=True (non compatibile con una Row che va a capo) —
                # "↩ Reset" resta semplicemente in fondo alla fila.
                ft.Row(
                    [
                        ft.TextButton("−0,5m", on_click=lambda e: use_movement(0.5),
                                      style=ft.ButtonStyle(color=design.T().warning)),
                        ft.TextButton("−1m", on_click=lambda e: use_movement(1),
                                      style=ft.ButtonStyle(color=design.T().warning)),
                        ft.TextButton("−1,5m", on_click=lambda e: use_movement(1.5),
                                      style=ft.ButtonStyle(color=design.T().warning)),
                        ft.TextButton("−2m", on_click=lambda e: use_movement(2),
                                      style=ft.ButtonStyle(color=design.T().warning)),
                        ft.TextButton("−3m", on_click=lambda e: use_movement(3),
                                      style=ft.ButtonStyle(color=design.T().warning)),
                        ft.TextButton("−6m", on_click=lambda e: use_movement(6),
                                      style=ft.ButtonStyle(color=design.T().warning)),
                        ft.TextButton("↩ Reset", on_click=lambda e: use_movement(-used_m),
                                      style=ft.ButtonStyle(color=design.T().text_3)),
                    ],
                    spacing=0,
                    wrap=True,
                ),
            ],
            spacing=4,
        )

        # --- Nuovo Turno / Annulla ---
        def nuovo_turno(e):
            snap = json.dumps({
                "action_used": c.action_used,
                "bonus_action_used": c.bonus_action_used,
                "reaction_used": c.reaction_used,
                "movement_used": c.movement_used,
            })
            character_repo.update_turn_state(c.id, False, False, False, 0, snap)
            self._refresh()

        def annulla_turno(e):
            prev = c.previous_turn_state
            if not prev:
                return
            try:
                snap = json.loads(prev)
                character_repo.update_turn_state(
                    c.id,
                    snap.get("action_used", False),
                    snap.get("bonus_action_used", False),
                    snap.get("reaction_used", False),
                    snap.get("movement_used", 0),
                    "",
                )
                self._refresh()
            except (json.JSONDecodeError, KeyError) as ex:
                logger.warning(f"Errore ripristino turno: {ex}")

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            _action_chip("AZIONE", c.action_used, toggle_action),
                            ft.Container(width=6),
                            _action_chip("BONUS", c.bonus_action_used, toggle_bonus),
                            ft.Container(width=6),
                            _action_chip("REAZIONE", c.reaction_used, toggle_reaction),
                        ],
                        spacing=0,
                    ),
                    ft.Container(height=8),
                    movement_section,
                    ft.Container(height=4),
                    ft.Divider(color=design.T().border),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "↺ Nuovo Turno", on_click=nuovo_turno,
                                expand=True,
                                style=ft.ButtonStyle(
                                    bgcolor=design.T().magic, color=design.T().on_accent,
                                ),
                            ),
                            ft.Container(width=8),
                            ft.OutlinedButton(
                                "↩ Annulla", on_click=annulla_turno,
                                disabled=not bool(c.previous_turn_state),
                                style=ft.ButtonStyle(
                                    color=design.T().text_2,
                                    side=ft.BorderSide(1, design.T().border),
                                ),
                            ),
                        ],
                        spacing=0,
                    ),
                ],
                spacing=4,
            ),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Tiri Salvezza & Abilità — riferimento rapido
    # ------------------------------------------------------------------

    def _section_saves_skills(self, c: Character) -> ft.Container:
        """
        Griglia compatta: 6 tiri salvezza + 18 abilità con modificatori.
        ✦ = competente, ★ = maestria (doppio bonus competenza).
        """
        pb = char_prof_bonus(c)
        scores = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        # Indici competenze dal DB
        save_profs: set[str] = {
            p.name for p in self._profs if p.proficiency_type == "save"
        }
        skill_profs: dict[str, bool] = {
            p.name: p.is_expert
            for p in self._profs if p.proficiency_type == "skill"
        }

        def _mod_str(val: int) -> str:
            return f"+{val}" if val >= 0 else str(val)

        def _save_row(stat_name: str, key: str) -> ft.Row:
            base = get_modifier(scores[key])
            prof = stat_name in save_profs
            total = base + (pb if prof else 0)
            marker = " ✦" if prof else ""
            color = design.T().text if prof else design.T().text_3
            return ft.Row([
                ft.Text(f"{_mod_str(total)}{marker}", size=12,
                        color=color, weight=ft.FontWeight.W_600,
                        font_family=design.Font.MONO, width=48),
                ft.Text(stat_name, size=12, color=color),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        def _skill_row(skill_name: str, stat_key: str) -> ft.Row:
            base = get_modifier(scores[stat_key])
            expert = skill_profs.get(skill_name, None)
            if expert is True:
                total = base + pb * 2
                marker, color = " ★", design.T().magic
            elif expert is False:
                total = base + pb
                marker, color = " ✦", design.T().text
            else:
                total, marker, color = base, "", design.T().text_3
            return ft.Row([
                ft.Text(f"{_mod_str(total)}{marker}", size=12,
                        color=color, weight=ft.FontWeight.W_600,
                        font_family=design.Font.MONO, width=48),
                ft.Text(skill_name, size=12, color=color),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # --- Tiri Salvezza ---
        save_pairs = list(zip(ABILITY_SCORES, ABILITY_KEYS))
        save_controls: list[ft.Control] = [
            ft.Text("TIRI SALVEZZA", size=9, color=design.T().text_3,
                    weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
        ]
        save_controls.extend(_save_row(name, key) for name, key in save_pairs)
        saves_col = ft.Column(controls=save_controls, spacing=3)

        # --- Abilità — due colonne da 9 ---
        skill_items = list(SKILLS.items())
        half = len(skill_items) // 2
        col_a = ft.Column(
            [_skill_row(n, k) for n, k in skill_items[:half]], spacing=3
        )
        col_b = ft.Column(
            [_skill_row(n, k) for n, k in skill_items[half:]], spacing=3
        )

        # `card(density="dense")` — griglia dati-intensa (6 tiri salvezza +
        # 18 abilità), stesso trattamento "dense" delle statistiche di
        # combattimento qui sopra.
        return design.card(
            ft.Column([
                saves_col,
                ft.Divider(color=design.T().border),
                ft.Text("ABILITÀ", size=9, color=design.T().text_3,
                        weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8)),
                ft.Row([col_a, ft.Container(width=20), col_b], spacing=0),
                ft.Text("✦ competente  ★ maestria", size=10, color=design.T().text_3,
                        italic=True),
            ], spacing=8),
            accent=design.T().primary,
            density="dense",
        )

    # ------------------------------------------------------------------
    # Armi Equipaggiate
    # ------------------------------------------------------------------

    def _section_weapons(self) -> ft.Container:
        """Armi is_equipped=True con bonus attacco, danno, proprietà.

        Calcolo automatico del tiro per colpire/danno: il totale mostrato è
        mod. caratteristica (Forza/Destrezza, automatico o scelto dal
        giocatore) + bonus competenza (solo se competente con quest'arma,
        dedotto da Weapon.weapon_category/proficiency_override contro le
        competenze arma del personaggio) + bonus magico dell'arma
        (attack_bonus, può essere negativo) — sovrascrivibile con un totale
        manuale (attack_total_override). Vedi core/weapon_calculator.py.
        """
        weapon_prof_names = {
            p.name.strip().lower()
            for p in self._profs
            if p.proficiency_type == "weapon" and p.name
        }
        c = self.character

        def _ctx(w: Weapon) -> AttackContext:
            return AttackContext(
                properties=w.properties or "",
                range_normal=w.range_normal or 0,
                weapon_category=w.weapon_category or "",
                proficiency_override=w.proficiency_override,
                finesse_ability=w.finesse_ability or "",
                attack_bonus=w.attack_bonus or 0,
                damage_bonus=w.damage_bonus or 0,
                attack_total_override=w.attack_total_override,
                attack_override_value=w.attack_override_value or 0,
            )

        def _atk_str(w: Weapon) -> tuple[str, str]:
            """Ritorna (totale mostrato, tooltip con il breakdown)."""
            ctx = _ctx(w)
            total, proficient, ability_key, breakdown = compute_attack_total(
                ctx, w.name, c.str_score, c.dex_score,
                char_prof_bonus(c), weapon_prof_names,
            )
            s = f"+{total}" if total >= 0 else str(total)
            ability_label = "Forza" if ability_key == "str" else "Destrezza"
            if w.attack_total_override:
                tooltip = f"Totale manuale: {s} (override del giocatore)"
            else:
                prof_txt = (f"+{breakdown['prof_bonus']} comp." if proficient
                            else "non competente")
                magic = breakdown["magic_bonus"]
                magic_txt = f" {'+' if magic >= 0 else ''}{magic} magico" if magic else ""
                tooltip = (
                    f"{ability_label} {'+' if breakdown['ability_mod'] >= 0 else ''}"
                    f"{breakdown['ability_mod']} {prof_txt}{magic_txt} = {s}"
                )
            return s, tooltip

        def _dmg_str(w: Weapon) -> str:
            ctx = _ctx(w)
            is_versatile = "versatile" in (w.properties or "").lower()
            dice = w.damage_dice or ""
            if is_versatile and w.grip_two_handed and w.versatile_damage_dice:
                dice = w.versatile_damage_dice
            if not dice:
                return "—"
            return compute_damage_formula(dice, w.damage_type or "", ctx, c.str_score, c.dex_score)

        def _range_str(w: Weapon) -> str:
            if w.range_normal and w.range_normal > 0:
                if w.range_max:
                    return f"{w.range_normal}/{w.range_max} m"
                return f"{w.range_normal} m"
            return "mischia"

        def _weapon_card(w: Weapon) -> ft.Container:
            props = w.properties.strip() if w.properties else ""

            # Descrizione magica (testo libero)
            magic_row = (
                ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=12, color=design.T().warning),
                    ft.Text(w.magic_description, size=11, color=design.T().warning,
                            expand=True),
                ], spacing=4)
                if w.is_magical and w.magic_description else None
            )

            # Danni magici aggiuntivi (JSON array: [{dice, type, note}])
            extra_damage_rows: list[ft.Control] = []
            try:
                magic_dmgs = json.loads(w.magic_damages or "[]")
                for md in magic_dmgs:
                    dice = md.get("dice", "")
                    typ  = md.get("type", "")
                    note = md.get("note", "")
                    if not dice:
                        continue
                    label = f"+ {dice}  {typ}"
                    if note:
                        label += f"  ({note})"
                    extra_damage_rows.append(
                        ft.Row([
                            ft.Icon(ft.Icons.WHATSHOT, size=11, color=design.T().warning),
                            ft.Text(label, size=11, color=design.T().warning,
                                    font_family=design.Font.MONO),
                        ], spacing=4)
                    )
            except (json.JSONDecodeError, AttributeError):
                pass

            atk_display, atk_tooltip = _atk_str(w)
            rows: list[ft.Control] = [
                ft.Row([
                    ft.Text(w.name, size=14, weight=ft.FontWeight.BOLD,
                            color=design.T().text, expand=True),
                    ft.Container(
                        content=ft.Text(_range_str(w), size=10, color=design.T().text_3),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                        border=ft.Border.all(1, design.T().border),
                        border_radius=design.Radius.SM,
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("ATT", size=9, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER),
                            ft.Text(atk_display, size=16, color=design.T().primary,
                                    weight=ft.FontWeight.BOLD, font_family=design.Font.MONO,
                                    text_align=ft.TextAlign.CENTER),
                        ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor=design.T().surface_alt,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=design.Radius.MD,
                        width=58,
                        tooltip=f"{atk_tooltip} — clicca per tirare",
                        ink=True,
                        on_click=(lambda e, wid=w.id: self._roll_weapon(wid, "attack")),
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("DANNO", size=9, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER),
                            ft.Text(_dmg_str(w), size=13, color=design.T().text,
                                    weight=ft.FontWeight.BOLD, font_family=design.Font.MONO,
                                    text_align=ft.TextAlign.CENTER),
                        ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor=design.T().surface_alt,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=design.Radius.MD,
                        expand=True,
                        tooltip="Clicca per tirare i danni",
                        ink=True,
                        on_click=(lambda e, wid=w.id: self._roll_weapon(wid, "damage")),
                    ),
                    ft.Icon(ft.Icons.CASINO_OUTLINED, size=14, color=design.T().primary_icon),
                ], spacing=8),
            ]
            if props:
                rows.append(ft.Text(props, size=11, color=design.T().text_3, italic=True))
            if magic_row:
                rows.append(magic_row)
            rows.extend(extra_damage_rows)

            return ft.Container(
                content=ft.Column(rows, spacing=6),
                bgcolor=design.T().surface_alt,
                padding=10,
                border_radius=design.Radius.MD,
                shadow=design.elevation(1),
            )

        if not self._weapons:
            body = ft.Column([
                ft.Text("Nessuna arma equipaggiata.", size=12, color=design.T().text_3),
                ft.Text("Aggiungi armi dalla scheda Inventario.",
                        size=11, color=design.T().text_3),
            ], spacing=4)
        else:
            body = ft.Column(
                [_weapon_card(w) for w in self._weapons], spacing=8
            )

        return ft.Container(
            content=body,
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Armatura e Scudo Equipaggiati
    # ------------------------------------------------------------------

    _ARMOR_TYPE_LABELS = {
        "leggera": "Armatura leggera",
        "media": "Armatura media",
        "pesante": "Armatura pesante",
        "scudo": "Scudo",
        "": "Indumento (nessun bonus CA)",
    }

    def _section_armor(self) -> ft.Container:
        """Armatura corporea + scudo equipaggiati, con CA ed effetti magici
        mostrati per intero (non solo un badge che ne segnala la
        presenza)."""

        def _armor_card(it: InventoryItem) -> ft.Container:
            type_label = self._ARMOR_TYPE_LABELS.get(it.armor_type, it.armor_type or "—")
            rows: list[ft.Control] = [
                ft.Row([
                    ft.Text(it.name, size=14, weight=ft.FontWeight.BOLD,
                            color=design.T().text, expand=True),
                    ft.Container(
                        content=ft.Text(type_label, size=10, color=design.T().text_3),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                        border=ft.Border.all(1, design.T().border),
                        border_radius=design.Radius.SM,
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ]
            if it.ca_value:
                rows.append(ft.Container(
                    content=ft.Column([
                        ft.Text("CA", size=9, color=design.T().text_3,
                                weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                        ft.Text(str(it.ca_value), size=16, color=design.T().magic,
                                weight=ft.FontWeight.BOLD, font_family=design.Font.MONO,
                                text_align=ft.TextAlign.CENTER),
                    ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=design.T().surface_alt,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border_radius=design.Radius.MD,
                    width=58,
                ))
            if it.effects and it.effects.strip():
                rows.append(ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=12, color=design.T().warning),
                    ft.Text(it.effects.strip(), size=12, color=design.T().warning,
                            expand=True),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START))
            if it.description and it.description.strip():
                rows.append(muted_text(it.description.strip(), 11))
            return ft.Container(
                content=ft.Column(rows, spacing=6),
                bgcolor=design.T().surface_alt,
                padding=10,
                border_radius=design.Radius.MD,
                shadow=design.elevation(1),
            )

        if not self._armor_items:
            body: ft.Control = ft.Column([
                ft.Text("Nessuna armatura o scudo equipaggiato.", size=12,
                        color=design.T().text_3),
                ft.Text("Aggiungi/equipaggia un'armatura dalla scheda Inventario.",
                        size=11, color=design.T().text_3),
            ], spacing=4)
        else:
            body = ft.Column(
                [_armor_card(it) for it in self._armor_items], spacing=8
            )

        return ft.Container(
            content=body,
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Slot Incantesimo BG3-style
    # ------------------------------------------------------------------

    def _section_spell_slots(self, c: Character) -> ft.Container:
        """
        Sezione Magia completa:
          - header: caratteristica, CD tiro salvezza, bonus attacco incantesimo
          - slot BG3-style cliccabili
          - incantesimi preparati raggruppati per livello
        """
        # --- Mapping chiave → nome italiano ---
        _KEY_TO_NAME = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
        _KEY_TO_ABBR = dict(zip(ABILITY_KEYS, ABILITY_ABBR))
        _KEY_TO_SCORE = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        pb = char_prof_bonus(c)
        sp_key = c.spellcasting_ability or ""
        is_caster = bool(sp_key and sp_key in _KEY_TO_SCORE)

        sections: list[ft.Control] = []

        # --- Header statistiche magia ---
        if is_caster:
            sp_mod  = get_modifier(_KEY_TO_SCORE[sp_key])
            # Formula PHB "8 + competenza + mod" — riusa core/character_stats.py
            # invece di ricalcolarla qui (stessa formula usata anche in
            # spells_view.py).
            # Il blocco `if is_caster:` sopra garantisce che
            # `spell_save_dc()` non ritorni mai `None` qui.
            save_dc = cs.spell_save_dc(c)
            atk_bon = pb + sp_mod
            atk_str = f"+{atk_bon}" if atk_bon >= 0 else str(atk_bon)
            sp_name = _KEY_TO_NAME[sp_key]
            sp_abbr = _KEY_TO_ABBR[sp_key]

            def _magic_stat(label: str, value: str) -> ft.Container:
                return ft.Container(
                    content=ft.Column([
                        ft.Text(label, size=9, color=design.T().text_3,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                        ft.Text(value, size=18, color=design.T().magic,
                                weight=ft.FontWeight.BOLD, font_family=design.Font.MONO,
                                text_align=ft.TextAlign.CENTER),
                    ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=design.T().surface_alt,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    border_radius=design.Radius.MD,
                    expand=True,
                )

            sections += [
                ft.Row([
                    _magic_stat(f"CARATTERISTICA\n({sp_abbr})", sp_name),
                    _magic_stat("CD TIRO SALVEZZA", str(save_dc)),
                    _magic_stat("BONUS ATTACCO", atk_str),
                ], spacing=8),
                ft.Divider(color=design.T().border),
            ]
        else:
            sections.append(
                ft.Text("Nessuna caratteristica da incantatore.",
                        size=12, color=design.T().text_3)
            )

        # --- Slot BG3-style ---
        active_slots = [s for s in self._slots if s.total > 0]
        configure_btn = ft.TextButton(
            "✎ Configura slot",
            on_click=self._on_configure_slots_click,
            style=ft.ButtonStyle(color=design.T().text_3),
        )

        if not active_slots:
            sections += [
                ft.Text("Nessuno slot configurato.", size=12, color=design.T().text_3),
                ft.Row([configure_btn], alignment=ft.MainAxisAlignment.END),
            ]
        else:
            slot_rows = []
            for slot in sorted(active_slots, key=lambda s: s.slot_level):
                avail = slot.total - slot.used
                circles = []
                for i in range(slot.total):
                    is_avail = i < avail
                    circles.append(design.dot_button(
                        is_avail, tone="magic", size=20,
                        on_click=lambda e, lv=slot.slot_level, use=is_avail:
                            self._toggle_slot(lv, use=use),
                        tooltip="Usa slot" if is_avail else "Recupera slot",
                    ))
                slot_rows.append(ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                _SLOT_NAMES[slot.slot_level - 1],
                                size=12, color=design.T().text_2,
                                weight=ft.FontWeight.W_600,
                            ),
                            width=28,
                        ),
                        ft.Row(circles, spacing=2),
                        ft.Container(expand=True),
                        ft.Text(f"{avail}/{slot.total}", size=11, color=design.T().text_3),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ))
            sections += slot_rows + [
                ft.Row([configure_btn], alignment=ft.MainAxisAlignment.END),
            ]

        # --- Incantesimi preparati ---
        if self._prepared:
            sections.append(ft.Divider(color=design.T().border))
            sections.append(
                ft.Text("INCANTESIMI PREPARATI", size=9, color=design.T().text_3,
                        weight=ft.FontWeight.BOLD, style=ft.TextStyle(letter_spacing=0.8))
            )
            sections.append(
                ft.Text("Clicca un incantesimo per la descrizione completa.",
                        size=10, color=design.T().text_3, italic=True)
            )
            # Raggruppa per livello
            by_level: dict[int, list[KnownSpell]] = {}
            for sp in self._prepared:
                by_level.setdefault(sp.spell_level, []).append(sp)

            def _make_spell_btn(sp: KnownSpell) -> ft.TextButton:
                return ft.TextButton(
                    sp.name,
                    on_click=lambda e, s=sp: self._open_spell_dialog(s.name, s.spell_level),
                    style=ft.ButtonStyle(
                        color=design.T().text,
                        padding=ft.Padding.symmetric(horizontal=2, vertical=0),
                        overlay_color=ft.Colors.with_opacity(0.08, design.T().magic),
                    ),
                )

            for lv in sorted(by_level.keys()):
                level_label = "Trucchetti" if lv == 0 else f"{_SLOT_NAMES[lv - 1]} livello"
                spell_controls: list[ft.Control] = []
                for i, sp in enumerate(by_level[lv]):
                    spell_controls.append(_make_spell_btn(sp))
                    if i < len(by_level[lv]) - 1:
                        spell_controls.append(
                            ft.Text("·", size=12, color=design.T().text_3)
                        )
                sections.append(ft.Row([
                    ft.Container(
                        content=ft.Text(level_label, size=10, color=design.T().magic,
                                        weight=ft.FontWeight.BOLD),
                        width=80,
                    ),
                    ft.Row(spell_controls, spacing=0, wrap=True, expand=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START))

        return ft.Container(
            content=ft.Column(sections, spacing=8),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _open_spell_dialog(self, spell_name: str, spell_level: int) -> None:
        """Apre un AlertDialog con la descrizione completa dell'incantesimo."""
        page = self._page
        if not page:
            return

        spell = _loader.get_spell_by_name(spell_name, self.character.class_name)

        if not spell:
            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title(spell_name),
                content=ft.Text(
                    "Trucchetto" if spell_level == 0 else f"{spell_level}° livello",
                    size=12, color=design.T().text_3,
                ),
                actions=[
                    ft.TextButton("Chiudi",
                                  on_click=lambda ev: page.pop_dialog() if page else None),
                ],
            ))
            return

        level_str = "Trucchetto" if spell_level == 0 else f"{spell_level}° livello"
        school    = spell.get("school", "")
        header    = f"{level_str}  ·  {school}" if school else level_str

        def _info_row(label: str, value: str) -> ft.Row:
            return ft.Row([
                ft.Text(label, size=11, color=design.T().text_3,
                        weight=ft.FontWeight.W_600, width=110),
                ft.Text(value, size=11, color=design.T().text, expand=True),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START)

        info_rows: list[ft.Control] = []
        for label, key in [
            ("Tempo di lancio", "casting_time"),
            ("Gittata",         "range"),
            ("Componenti",      "components"),
            ("Durata",          "duration"),
        ]:
            val = spell.get(key, "")
            if val:
                info_rows.append(_info_row(label, str(val)))

        tags: list[ft.Control] = []
        if spell.get("ritual"):
            tags.append(ft.Container(
                content=ft.Text("Rituale", size=10, color=design.T().magic),
                border=ft.Border.all(1, design.T().magic),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            ))
        if spell.get("concentration"):
            tags.append(ft.Container(
                content=ft.Text("Concentrazione", size=10, color=design.T().warning),
                border=ft.Border.all(1, design.T().warning),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            ))

        desc   = spell.get("description", "")
        higher = spell.get("higher_levels", "")

        content_items: list[ft.Control] = [
            ft.Text(header, size=11, color=design.T().text_3, italic=True),
            ft.Container(height=4),
        ]
        if info_rows:
            content_items.extend(info_rows)
            content_items.append(ft.Container(height=4))
        if tags:
            content_items.append(ft.Row(tags, spacing=6, wrap=True))
            content_items.append(ft.Container(height=4))
        if desc:
            content_items.append(ft.Divider(color=design.T().border))
            content_items.append(
                ft.Text(desc, size=13, color=design.T().text, selectable=True)
            )
        if higher:
            content_items.append(ft.Container(height=6))
            content_items.append(
                ft.Text("A livelli superiori:", size=11,
                        color=design.T().text_3, weight=ft.FontWeight.BOLD)
            )
            content_items.append(
                ft.Text(higher, size=12, color=design.T().text_2, italic=True)
            )

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(spell_name),
            content=ft.Column(
                content_items,
                spacing=6,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Chiudi",
                              on_click=lambda ev: page.pop_dialog() if page else None),
            ],
        ))

    def _toggle_slot(self, slot_level: int, use: bool):
        for slot in self._slots:
            if slot.slot_level == slot_level:
                if use:
                    slot.used = min(slot.total, slot.used + 1)
                else:
                    slot.used = max(0, slot.used - 1)
                character_repo.update_spell_slot(self.character.id, slot_level, slot.used)
                self._refresh_slots_only()
                return

    def _on_configure_slots_click(self, e):
        page = self._page
        if page is None:
            return
        slot_map = {s.slot_level: s for s in self._slots}
        fields: dict[int, ft.TextField] = {}

        for lv in range(1, 10):
            s = slot_map.get(lv)
            fields[lv] = ft.TextField(
                label=f"{_SLOT_NAMES[lv - 1]} livello",
                value=str(s.total if s else 0),
                keyboard_type=ft.KeyboardType.NUMBER,
                **design.field_style())

        # Layout 3×3
        grid = ft.Row(
            [
                ft.Column([fields[1], fields[4], fields[7]], spacing=8, expand=True),
                ft.Column([fields[2], fields[5], fields[8]], spacing=8, expand=True),
                ft.Column([fields[3], fields[6], fields[9]], spacing=8, expand=True),
            ],
            spacing=12,
        )

        def save(ev):
            if page is None:
                return
            for lv, field in fields.items():
                try:
                    total = max(0, min(9, int(field.value or 0)))
                except ValueError:
                    total = 0
                character_repo.update_spell_slot_total(self.character.id, lv, total)
            self._slots = character_repo.get_spell_slots(self.character.id)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Configura Slot Incantesimo"),
            content=ft.Column(
                [
                    ft.Text(
                        "Numero massimo di slot per livello (0 = non disponibile).",
                        size=12, color=design.T().text_2,
                    ),
                    ft.Container(height=6),
                    grid,
                ],
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Salva", on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().magic, color=design.T().on_accent,
                    ),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Risorse di Classe
    # ------------------------------------------------------------------

    def _section_class_resources(self) -> ft.Container:
        """
        Sezione risorse di classe (Furia, Ki, Incanalare Divinità, ecc.).
        - display_type "circles": cerchietti ● cliccabili (click = usa/recupera).
        - display_type "counter": etichetta numerica con bottoni − e +.
        """
        rows: list[ft.Control] = []
        for res in self._resources:
            if res.max_value < 0 or res.display_type == "unlimited":
                rows.append(self._resource_unlimited_row(res))
            elif res.display_type == "circles":
                rows.append(self._resource_circles_row(res))
            else:
                rows.append(self._resource_counter_row(res))

        # Incantesimi Flessibili (solo Stregone, dal momento in cui ha Punti Stregoneria)
        sp_res = next((r for r in self._resources if r.name == "Punti Stregoneria"), None)
        if (self.character.class_name or "").strip().lower() == "stregone" and sp_res:
            rows.append(ft.Divider(color=design.T().border, height=16))
            rows.append(self._section_flexible_casting(sp_res))

        # Frenesia (Barbaro, Cammino del Berserker). "berserker" in
        # sottoclasse è lo stesso pattern già usato altrove nel progetto
        # (es. Totem/Terreno) per riconoscere una sottoclasse via substring
        # case-insensitive.
        if (self.character.class_name or "").strip().lower() == "barbaro" \
                and "berserker" in (self.character.subclass or "").lower():
            rows.append(ft.Divider(color=design.T().border, height=16))
            rows.append(self._section_frenzy())

        return ft.Container(
            content=ft.Column(rows, spacing=10),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_flexible_casting(self, sp_res: ClassResource) -> ft.Column:
        """
        Incantesimi Flessibili (Stregone, PHB): converte Punti Stregoneria in slot
        incantesimo aggiuntivi (spariscono al riposo lungo) o viceversa.
        Costo di creazione letto da stregone.json ("spell_slot_creation_cost"),
        fonte unica condivisa con la scheda di classe.
        """
        class_data = _loader.get_class("Stregone") or {}
        cost_table: dict[int, int] = {
            row["slot_level"]: row["sorcery_points"]
            for row in class_data.get("spell_slot_creation_cost", [])
        } or {1: 2, 2: 3, 3: 5, 4: 6, 5: 7}  # fallback se il JSON non è disponibile

        create_dd = ft.Dropdown(
            label="Crea slot di livello",
            options=[
                ft.DropdownOption(key=str(lv), text=f"{lv}° — costo {cost} pt")
                for lv, cost in sorted(cost_table.items())
            ],
            value=str(min(cost_table.keys())) if cost_table else None,
            width=190,
            dense=True,
            text_size=12,
            **design.field_style())

        available_slots = [s for s in self._slots if s.total > 0 and s.used < s.total]
        convert_dd = ft.Dropdown(
            label="Converti slot di livello",
            options=(
                [
                    ft.DropdownOption(key=str(s.slot_level),
                                       text=f"{s.slot_level}° — {s.total - s.used} liber{'o' if s.total - s.used == 1 else 'i'}")
                    for s in available_slots
                ] or [ft.DropdownOption(key="", text="Nessuno slot disponibile")]
            ),
            value=str(available_slots[0].slot_level) if available_slots else "",
            disabled=not available_slots,
            width=190,
            dense=True,
            text_size=12,
            **design.field_style())

        def on_create(e: Any) -> None:
            if not create_dd.value:
                return
            lv = int(create_dd.value)
            cost = cost_table.get(lv, 0)
            if sp_res.current_value < cost:
                self._show_flex_cast_error(
                    f"Punti stregoneria insufficienti: servono {cost}, "
                    f"disponibili {sp_res.current_value}."
                )
                return
            sp_res.current_value -= cost
            character_repo.update_class_resource(sp_res.id, sp_res.current_value)
            slot = next((s for s in self._slots if s.slot_level == lv), None)
            new_total = (slot.total if slot else 0) + 1
            character_repo.update_spell_slot_total(self.character.id, lv, new_total)
            self._refresh_resources_only()
            self._refresh_slots_only()

        def on_convert(e: Any) -> None:
            if not convert_dd.value:
                return
            lv = int(convert_dd.value)
            slot = next((s for s in self._slots if s.slot_level == lv), None)
            if not slot or slot.used >= slot.total:
                self._show_flex_cast_error("Nessuno slot disponibile a quel livello.")
                return
            character_repo.update_spell_slot(self.character.id, lv, slot.used + 1)
            sp_res.current_value = min(sp_res.max_value, sp_res.current_value + lv)
            character_repo.update_class_resource(sp_res.id, sp_res.current_value)
            self._refresh_resources_only()
            self._refresh_slots_only()

        return ft.Column(
            [
                ft.Text("Incantesimi Flessibili", size=12, weight=ft.FontWeight.BOLD,
                        color=design.T().primary),
                muted_text(
                    "Azione bonus: crea uno slot spendendo punti stregoneria (svanisce "
                    "al riposo lungo), oppure sacrifica uno slot per ottenere punti "
                    "pari al suo livello.",
                    size=11,
                ),
                ft.Row([create_dd, ft.ElevatedButton("Crea", on_click=on_create, height=36)],
                       spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([convert_dd, ft.ElevatedButton("Converti", on_click=on_convert, height=36,
                                                        disabled=not available_slots)],
                       spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            spacing=8,
        )

    def _show_flex_cast_error(self, message: str) -> None:
        page = self._page
        if page is None:
            return
        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Operazione non valida"),
            content=ft.Text(message, size=13, color=design.T().text),
            actions=[ft.TextButton("OK", on_click=lambda ev: page.pop_dialog() if page else None)],
        ))

    def _section_frenzy(self) -> ft.Column:
        """
        Frenesia (Barbaro, Cammino del Berserker), PHB IT: "Il barbaro può
        entrare in frenesia quando entra in ira. Se lo fa... Quando la sua
        ira termina, il barbaro subisce un livello di indebolimento."

        L'Indebolimento NON è automatico ad ogni uso di Furia — solo se la
        Frenesia è stata dichiarata per l'ira in corso. Due passaggi
        distinti, entrambi in un solo click ciascuno:
          1. "Dichiara Frenesia" all'inizio dell'ira in frenesia — nessun
             effetto immediato, segna solo lo stato (persistito, per
             sopravvivere a un cambio tab/riavvio dell'app).
          2. "Termina Ira (Frenesia)" quando quell'ira finisce — applica
             automaticamente +1 Indebolimento (character_repo.end_frenzy_rage,
             scrittura atomica) senza dover aprire la sezione Indebolimento e
             incrementarla a mano.
        Un "Annulla dichiarazione" permette di correggere un click
        accidentale sul passo 1 senza subire l'Indebolimento.
        """
        c = self.character

        if not c.frenzy_active:
            chip = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.BOLT_OUTLINED, size=16, color=design.T().text_3),
                        ft.Text("Frenesia: dichiara per questa Ira", size=12,
                                color=design.T().text_3, weight=ft.FontWeight.W_600,
                                expand=True),
                    ],
                    spacing=6,
                ),
                bgcolor=design.T().surface_alt,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                shadow=design.elevation(1),
                border_radius=design.Radius.MD,
                on_click=self._on_declare_frenzy,
                ink=True,
                tooltip="PHB: il barbaro può entrare in frenesia quando entra in ira",
            )
            return ft.Column([chip], spacing=4)

        chip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.BOLT, size=16, color=design.T().primary_icon),
                    ft.Text("Frenesia attiva — Termina Ira (+1 Indebolimento)", size=12,
                            color=design.T().primary, weight=ft.FontWeight.BOLD,
                            expand=True),
                ],
                spacing=6,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border=ft.Border.all(2, design.T().primary),
            border_radius=design.Radius.MD,
            on_click=self._on_end_frenzy,
            ink=True,
            tooltip="Quando l'ira in frenesia termina: applica automaticamente 1 livello di Indebolimento",
        )
        cancel_btn = ft.TextButton(
            "Annulla dichiarazione (senza Indebolimento)",
            on_click=self._on_cancel_frenzy,
            style=ft.ButtonStyle(color=design.T().text_3),
        )
        return ft.Column(
            [chip, ft.Row([cancel_btn], alignment=ft.MainAxisAlignment.END)],
            spacing=0,
        )

    def _on_declare_frenzy(self, e: Any) -> None:
        c = self.character
        if not character_repo.update_frenzy_state(c.id, True):
            show_error_dialog(self._page, "Impossibile dichiarare la Frenesia.")
            return
        c.frenzy_active = True
        self._refresh_resources_only()

    def _on_cancel_frenzy(self, e: Any) -> None:
        c = self.character
        if not character_repo.update_frenzy_state(c.id, False):
            show_error_dialog(self._page, "Impossibile annullare la dichiarazione di Frenesia.")
            return
        c.frenzy_active = False
        self._refresh_resources_only()

    def _on_end_frenzy(self, e: Any) -> None:
        c = self.character
        new_level = character_repo.end_frenzy_rage(c.id, c.exhaustion_level)
        if new_level is None:
            show_error_dialog(self._page, "Impossibile terminare la Frenesia.")
            return
        c.frenzy_active = False
        c.exhaustion_level = new_level
        self._refresh()

    def _resource_unlimited_row(self, res: ClassResource) -> ft.Row:
        """Riga per risorse senza limite di utilizzi (es. Furia del Barbaro al 20° livello)."""
        reset_icon  = "☽" if res.reset_on == "short_rest" else "☀"
        reset_label = "Ripristino: riposo breve" if res.reset_on == "short_rest" else "Ripristino: riposo lungo"
        return ft.Row(
            [
                ft.Text(res.name, size=12, color=design.T().text,
                        weight=ft.FontWeight.W_600, expand=True),
                ft.Text(reset_icon, size=14, color=design.T().text_3, tooltip=reset_label),
                ft.Container(width=6),
                ft.Container(
                    content=ft.Text("∞ Illimitata", size=12, color=design.T().primary,
                                     weight=ft.FontWeight.BOLD),
                    bgcolor=design.T().surface_alt,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    border_radius=design.Radius.MD,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        )

    def _resource_circles_row(self, res: ClassResource) -> ft.Row:
        """Riga con cerchietti BG3-style per risorse a pool piccolo (≤ 6)."""
        reset_icon  = "☽" if res.reset_on == "short_rest" else "☀"
        reset_label = "Ripristino: riposo breve" if res.reset_on == "short_rest" else "Ripristino: riposo lungo"

        # Ispirazione Bardica: il dado (d6→d8→d10→d12) è calcolato a runtime dal
        # livello del personaggio, MAI salvato nel nome della risorsa — vedi
        # nota in config/settings.py get_class_resource_defaults() sul perché
        # (init_class_resources() fa il merge per nome esatto, un nome che
        # cambia ad ogni soglia di livello resetterebbe gli utilizzi già spesi).
        display_name = res.name
        if res.name == "Ispirazione Bardica":
            die = _loader.get_bardic_inspiration_die(self.character.level)
            display_name = f"{res.name} ({die})"

        circles: list[ft.Control] = []
        for i in range(res.max_value):
            is_avail = i < res.current_value
            circles.append(design.dot_button(
                is_avail, tone="primary", size=20,
                on_click=lambda e, r=res, use=is_avail: self._toggle_resource(r, use),
                tooltip="Usa" if is_avail else "Recupera",
            ))

        return ft.Row(
            [
                ft.Text(display_name, size=12, color=design.T().text,
                        weight=ft.FontWeight.W_600, expand=True),
                ft.Text(reset_icon, size=14, color=design.T().text_3,
                        tooltip=reset_label),
                ft.Container(width=6),
                ft.Row(circles, spacing=2),
                ft.Container(width=4),
                ft.Text(f"{res.current_value}/{res.max_value}", size=11,
                        color=design.T().text_3, font_family=design.Font.MONO),
                ft.IconButton(
                    ft.Icons.EDIT,
                    icon_size=14,
                    icon_color=design.T().magic if res.max_value_bonus else design.T().text_3,
                    tooltip="Modifica bonus massimo",
                    on_click=lambda e, r=res: self._on_edit_resource_bonus(r),
                    padding=ft.Padding.all(2),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        )

    def _resource_counter_row(self, res: ClassResource) -> ft.Column:
        """Riga con counter −/+ per risorse a pool grande (Ki, Stregoneria, ecc.)."""
        reset_icon  = "☽" if res.reset_on == "short_rest" else "☀"
        reset_label = "Ripristino: riposo breve" if res.reset_on == "short_rest" else "Ripristino: riposo lungo"

        ratio = (res.current_value / res.max_value) if res.max_value > 0 else 0.0
        bar_color = design.T().primary_fill if ratio > 0.4 else design.T().warning

        return ft.Column([
            ft.Row(
                [
                    ft.Text(res.name, size=12, color=design.T().text,
                            weight=ft.FontWeight.W_600, expand=True),
                    ft.Text(reset_icon, size=14, color=design.T().text_3,
                            tooltip=reset_label),
                    ft.Container(width=8),
                    ft.IconButton(
                        ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        icon_size=18,
                        icon_color=design.T().primary_icon,
                        on_click=lambda e, r=res: self._decrement_resource(r),
                        disabled=res.current_value <= 0,
                        tooltip="Usa 1",
                    ),
                    ft.Text(
                        f"{res.current_value}/{res.max_value}",
                        size=15, color=design.T().text,
                        weight=ft.FontWeight.BOLD, font_family=design.Font.MONO,
                        width=70, text_align=ft.TextAlign.CENTER,
                    ),
                    ft.IconButton(
                        ft.Icons.ADD_CIRCLE_OUTLINE,
                        icon_size=18,
                        icon_color=design.T().success,
                        on_click=lambda e, r=res: self._increment_resource(r),
                        disabled=res.current_value >= res.max_value,
                        tooltip="Recupera 1",
                    ),
                    ft.IconButton(
                        ft.Icons.EDIT,
                        icon_size=14,
                        icon_color=design.T().magic if res.max_value_bonus else design.T().text_3,
                        tooltip="Modifica bonus massimo",
                        on_click=lambda e, r=res: self._on_edit_resource_bonus(r),
                        padding=ft.Padding.all(2),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            ft.Row([ft.ProgressBar(
                value=ratio, color=bar_color,
                bgcolor=design.T().surface_alt, height=6,
                border_radius=3, expand=True,
            )]),
        ], spacing=4)

    def _on_edit_resource_bonus(self, res: ClassResource) -> None:
        """
        Dialog per impostare un bonus permanente additivo al massimo di una
        risorsa di classe — es. un talento/oggetto magico che concede +1
        uso. Il bonus si somma al valore PHB calcolato e sopravvive al
        ri-sync di init_class_resources() (chiamato ad ogni apertura
        tab/level-up), a differenza di un override assoluto che verrebbe
        sovrascritto.
        """
        page = self._page
        if page is None:
            return
        base_max = res.max_value - (res.max_value_bonus or 0)

        tf = ft.TextField(
            label="Bonus permanente al massimo",
            value=str(res.max_value_bonus or 0),
            hint_text="es. +1 (può essere anche negativo)",
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
            **design.field_style())

        def _save(e):
            raw = (tf.value or "").strip()
            try:
                bonus = int(raw) if raw else 0
            except ValueError:
                cast(Any, tf).error_text = "Inserisci un numero intero"
                tf.update()
                return
            if not character_repo.update_class_resource_bonus(res.id, bonus):
                show_error_dialog(page, "Errore nel salvataggio del bonus risorsa.")
                return
            # Il bonus da solo non basta: serve un ri-sync per applicarlo al
            # max_value effettivo del pool (stesso passaggio già eseguito ad
            # ogni level-up/apertura tab).
            character_repo.init_class_resources(
                self.character.id, self.character.class_name, self.character.level,
                character=self.character,
            )
            page.pop_dialog()
            self._refresh()

        def _reset(e):
            if not character_repo.update_class_resource_bonus(res.id, 0):
                show_error_dialog(page, "Errore nel salvataggio del bonus risorsa.")
                return
            character_repo.init_class_resources(
                self.character.id, self.character.class_name, self.character.level,
                character=self.character,
            )
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=design.dialog_title(f"Bonus — {res.name}"),
            content=ft.Column(
                [
                    muted_text(f"Massimo calcolato dal PHB: {base_max}", 12),
                    tf,
                ],
                spacing=12,
                tight=True,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Rimuovi bonus", on_click=_reset),
                ft.TextButton("Annulla", on_click=_cancel),
                ft.ElevatedButton("Applica", on_click=_save),
            ]),
        )
        page.show_dialog(dlg)

    def _toggle_resource(self, res: ClassResource, use: bool):
        """Click su cerchietto: usa (●→○) o recupera (○→●)."""
        if use:
            res.current_value = max(0, res.current_value - 1)
        else:
            res.current_value = min(res.max_value, res.current_value + 1)
        character_repo.update_class_resource(res.id, res.current_value)
        self._refresh_resources_only()

    def _decrement_resource(self, res: ClassResource):
        res.current_value = max(0, res.current_value - 1)
        character_repo.update_class_resource(res.id, res.current_value)
        self._refresh_resources_only()

    def _increment_resource(self, res: ClassResource):
        res.current_value = min(res.max_value, res.current_value + 1)
        character_repo.update_class_resource(res.id, res.current_value)
        self._refresh_resources_only()

    # ------------------------------------------------------------------
    # Tratti di Razza
    # ------------------------------------------------------------------

    def _section_racial_traits(self) -> ft.Container:
        """
        Sezione di riferimento rapido: resistenze e vantaggi ai TS razziali.
        Puramente informativa, nessuna interazione.
        """
        rt = self._race_traits
        rows: list[ft.Control] = []

        def _chip(label: str, icon: str, color: str) -> ft.Container:
            return ft.Container(
                content=ft.Row([
                    ft.Text(icon, size=14),
                    ft.Text(label, size=12, color=color,
                            weight=ft.FontWeight.W_600),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=f"{color}18",
                border=ft.Border.all(1, f"{color}60"),
                border_radius=16,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            )

        if rt["resistances"]:
            rows.append(ft.Text(
                "RESISTENZE", size=9, color=design.T().text_3,
                weight=ft.FontWeight.BOLD,
                style=ft.TextStyle(letter_spacing=0.8),
            ))
            rows.append(ft.Row(
                [_chip(r, "🛡", design.T().magic) for r in rt["resistances"]],
                spacing=6, wrap=True,
            ))

        if rt["advantage_saves"] and rows:
            rows.append(ft.Container(height=4))

        if rt["advantage_saves"]:
            rows.append(ft.Text(
                "VANTAGGIO AI TIRI SALVEZZA", size=9, color=design.T().text_3,
                weight=ft.FontWeight.BOLD,
                style=ft.TextStyle(letter_spacing=0.8),
            ))
            rows.append(ft.Row(
                [_chip(s, "↑", design.T().warning) for s in rt["advantage_saves"]],
                spacing=6, wrap=True,
            ))

        race_label = self.character.race or ""
        if self.character.subrace:
            race_label += f" · {self.character.subrace}"

        rows.append(ft.Container(height=2))
        rows.append(ft.Text(
            race_label, size=10, color=design.T().text_3, italic=True,
        ))

        return ft.Container(
            content=ft.Column(rows, spacing=6),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Stile di Combattimento / Suppliche Occulte — sola consultazione.
    # La scelta resta unicamente in Profilo (dove viene
    # assegnata al level-up: character.fighting_style, e le righe
    # character_proficiencies proficiency_type="invocation") — qui si legge
    # lo stesso dato per mostrarlo dove ha effetto in combattimento, senza
    # introdurre una seconda fonte di verità. Stesso pattern click-per-
    # descrizione già usato in _section_class_features().
    # ------------------------------------------------------------------

    def _section_fighting_style(self) -> ft.Container:
        style_name = (self.character.fighting_style or "").strip()
        style_data = next(
            (s for s in _loader.get_fighting_style_data(self.character.class_name or "")
             if s.get("name", "").strip().lower() == style_name.lower()),
            None,
        )
        description = (style_data or {}).get("description", "")

        def _open_dialog(e=None):
            if not self._page:
                return
            page = self._page
            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title(style_name),
                content=ft.Column([
                    ft.Text(
                        description or "Nessuna descrizione disponibile.",
                        size=13, color=design.T().text, selectable=True,
                    ),
                ], spacing=10, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Chiudi",
                                  on_click=lambda ev: page.pop_dialog() if page else None),
                ],
            ))

        row = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.SPORTS_MARTIAL_ARTS, size=18, color=design.T().primary_icon),
                ft.Container(width=8),
                ft.Text(style_name, size=13, color=design.T().text,
                        weight=ft.FontWeight.W_600, expand=True),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=design.T().text_3),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            on_click=_open_dialog,
            ink=True,
            border_radius=design.Radius.SM,
            padding=ft.Padding.symmetric(vertical=6, horizontal=4),
        )

        return ft.Container(
            content=row,
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _section_invocations(self) -> ft.Container:
        names = sorted({
            p.name for p in self._profs
            if p.proficiency_type == "invocation" and p.name
        })

        def _open_dialog(inv: dict, e=None):
            if not self._page:
                return
            page = self._page
            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title(inv.get("name", "")),
                content=ft.Column([
                    ft.Text(
                        inv.get("description", "") or "Nessuna descrizione disponibile.",
                        size=13, color=design.T().text, selectable=True,
                    ),
                ], spacing=10, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Chiudi",
                                  on_click=lambda ev: page.pop_dialog() if page else None),
                ],
            ))

        rows: list[ft.Control] = []
        for name in names:
            inv = _loader.get_invocation(name) or {"name": name, "description": ""}
            rows.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.AUTO_FIX_HIGH, size=16, color=design.T().magic),
                    ft.Container(width=8),
                    ft.Text(inv.get("name") or name, size=13, color=design.T().text,
                            weight=ft.FontWeight.W_600, expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=design.T().text_3),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                on_click=lambda e, i=inv: _open_dialog(i),
                ink=True,
                border_radius=design.Radius.SM,
                padding=ft.Padding.symmetric(vertical=6, horizontal=4),
            ))

        if not rows:
            rows.append(muted_text("Nessuna Supplica Occulta ancora appresa.", 12))

        return ft.Container(
            content=ft.Column(rows, spacing=2),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Abilità Speciali custom — voci additive, es. concesse dal master; non
    # modificano mai il testo ufficiale delle feature di classe/razza
    # mostrate sopra.
    # ------------------------------------------------------------------

    def _section_custom_abilities_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=3, height=14, bgcolor=design.T().primary_fill, border_radius=1),
                    ft.Container(width=8),
                    ft.Text(
                        "ABILITÀ SPECIALI",
                        size=10, color=design.T().text_2, weight=ft.FontWeight.BOLD,
                        style=ft.TextStyle(letter_spacing=2),
                    ),
                    ft.Container(width=8),
                    ft.Container(expand=True, height=1, bgcolor=design.T().border),
                    ft.Container(width=8),
                    ft.TextButton(
                        "+ Aggiungi",
                        on_click=lambda e: self._on_add_custom_ability(),
                        style=ft.ButtonStyle(color=design.T().primary),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            margin=ft.Margin.only(bottom=0, top=4),
        )

    def _section_custom_abilities(self) -> ft.Container:
        if not self._custom_abilities:
            content: ft.Control = muted_text(
                "Nessuna abilità speciale di combattimento registrata — usa "
                "«+ Aggiungi» per annotare capacità custom concesse dal master.",
                12,
            )
        else:
            rows: list[ft.Control] = []
            for ab in self._custom_abilities:
                rows.append(self._custom_ability_row(ab))
            content = ft.Column(rows, spacing=8)

        return ft.Container(
            content=content,
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _custom_ability_row(self, ab: CustomAbility) -> ft.Container:
        # Descrizione mostrata per intero, andando a capo liberamente (non
        # troncata: testi lunghi come "Punizione Glaciale" restano leggibili).
        full_desc = ab.description.strip()
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(ab.name, size=13, color=design.T().text,
                                    weight=ft.FontWeight.W_600),
                            muted_text(full_desc, 11) if full_desc else ft.Container(height=0),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.EDIT, icon_size=16, icon_color=design.T().text_3,
                        tooltip="Modifica",
                        on_click=lambda e, a=ab: self._on_edit_custom_ability(a),
                        padding=ft.Padding.all(2),
                    ),
                    ft.IconButton(
                        # `danger_icon`, non `primary_icon` — azione
                        # distruttiva (elimina), la palette separa i due
                        # registri (vedi Palette in design.py).
                        ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=design.T().danger_icon,
                        tooltip="Elimina",
                        on_click=lambda e, a=ab: self._on_delete_custom_ability(a),
                        padding=ft.Padding.all(2),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=4,
            ),
            border=ft.Border(bottom=ft.BorderSide(1, design.T().border)),
            padding=ft.Padding.only(bottom=8),
        )

    def _on_add_custom_ability(self) -> None:
        self._open_custom_ability_dialog(None)

    def _on_edit_custom_ability(self, ab: CustomAbility) -> None:
        self._open_custom_ability_dialog(ab)

    def _open_custom_ability_dialog(self, ab: CustomAbility | None) -> None:
        page = self._page
        if page is None:
            return

        tf_name = ft.TextField(
            label="Nome", value=(ab.name if ab else ""), autofocus=True,
            **design.field_style())
        tf_desc = ft.TextField(
            label="Descrizione", value=(ab.description if ab else ""),
            multiline=True, min_lines=3, max_lines=8,
            **design.field_style())

        def _save(e):
            name = (tf_name.value or "").strip()
            if not name:
                cast(Any, tf_name).error_text = "Inserisci il nome dell'abilità"
                tf_name.update()
                return
            desc = tf_desc.value or ""
            if ab is None:
                new_id = character_repo.create_custom_ability(
                    self.character.id, "combattimento", name, desc
                )
                if not new_id:
                    show_error_dialog(page, "Errore nel salvataggio dell'abilità.")
                    return
                self._push_custom_ability_to_world(
                    "create", {"category": "combattimento", "name": name, "description": desc},
                )
            else:
                if not character_repo.update_custom_ability(ab.id, name, desc):
                    show_error_dialog(page, "Errore nel salvataggio dell'abilità.")
                    return
                self._push_custom_ability_to_world(
                    "update",
                    {"ability_id": ab.id, "category": "combattimento", "name": name,
                     "description": desc},
                )
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Modifica Abilità Speciale" if ab else "Nuova Abilità Speciale"),
            content=ft.Column([tf_name, tf_desc], spacing=12, tight=True, width=340),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=_cancel),
                ft.ElevatedButton("Salva", on_click=_save),
            ]),
        )
        page.show_dialog(dlg)

    def _on_delete_custom_ability(self, ab: CustomAbility) -> None:
        page = self._page
        if page is None:
            return

        def _confirm(e):
            if not character_repo.delete_custom_ability(ab.id):
                show_error_dialog(page, "Errore nell'eliminazione dell'abilità.")
                return
            page.pop_dialog()
            self._refresh()

        def _cancel(e):
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Elimina Abilità Speciale"),
            content=ft.Text(f'Eliminare "{ab.name}" dalla scheda?'),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=_cancel),
                ft.ElevatedButton(
                    # `danger_fill`, non `primary_fill` — conferma di
                    # un'eliminazione.
                    "Elimina", on_click=_confirm,
                    style=ft.ButtonStyle(bgcolor=design.T().danger_fill, color=design.T().on_primary_fill),
                ),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Abilità di Classe
    # ------------------------------------------------------------------

    def _load_class_features(self, c: Character) -> list[dict]:
        """
        Carica le feature base + sottoclasse dalla classe JSON, filtrate per
        livello ≤ livello DI QUELLA CLASSE (mai il livello totale del
        personaggio: per un multiclasse i due divergono, PHB IT p.163).
        Ordina per livello poi per nome.

        Itera TUTTE le classi possedute (character_classes), non solo la
        primaria — un personaggio a classe singola ha una sola riga, il cui
        livello coincide sempre con c.level, quindi l'output resta identico
        per ogni personaggio a classe singola. Filtrare invece
        c.class_name/c.subclass contro c.level (il TOTALE) farebbe
        mostrare, per un multiclasse, feature della classe primaria mai
        realmente raggiunte (es. Chierico 12/Guerriero 1, c.level=13,
        mostrerebbe feature Chierico fino al 13° livello).
        """
        classes = character_repo.get_character_classes(c.id)
        if not classes:
            # Personaggio non ancora migrato (non dovrebbe succedere dopo
            # init_db(), ma niente crash): fallback al comportamento di
            # sempre, class_name/level/subclass di characters.
            if not c.class_name:
                return []
            classes = [CharacterClass(
                class_name=c.class_name, subclass=c.subclass or "", level=c.level,
            )]

        features: list[dict] = []
        for cc in classes:
            cls_data = _loader.get_class(cc.class_name)
            if not cls_data:
                continue

            for feat in cls_data.get("features", []):
                if feat.get("level", 1) <= cc.level:
                    features.append({
                        "level": feat["level"],
                        "name": feat["name"],
                        "description": feat.get("description", ""),
                        "source": cc.class_name,
                    })

            subclass_name = (cc.subclass or "").strip()
            if subclass_name:
                for sc in cls_data.get("subclasses", []):
                    if sc.get("name", "").lower() == subclass_name.lower():
                        for feat in sc.get("features", []):
                            if feat.get("level", 1) <= cc.level:
                                features.append({
                                    "level": feat["level"],
                                    "name": feat["name"],
                                    "description": feat.get("description", ""),
                                    "source": subclass_name,
                                })
                        break

        features.sort(key=lambda f: (f["level"], f["name"]))
        return features

    def _section_class_features(self) -> ft.Container:
        """
        Lista compatta delle abilità di classe disponibili al livello attuale.
        Ogni riga: badge livello + nome + fonte (sottoclasse se diversa).
        Click → dialog con descrizione completa.
        """
        def _open_feature_dialog(feat: dict, e=None):
            # Usa self._page direttamente: la closure viene invocata DOPO did_mount()
            if not self._page:
                return
            page = self._page
            source_label = (
                f"  ·  {feat['source']}"
                if feat["source"].lower() != (self.character.class_name or "").lower()
                else ""
            )
            page.show_dialog(ft.AlertDialog(
                title=ft.Row([
                    ft.Container(
                        content=ft.Text(
                            f"Lv {feat['level']}",
                            size=10, color=design.T().on_primary,
                            weight=ft.FontWeight.BOLD,
                        ),
                        bgcolor=design.T().primary_fill,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                        border_radius=design.Radius.SM,
                    ),
                    ft.Container(width=8),
                    ft.Text(feat["name"], size=14, weight=ft.FontWeight.BOLD,
                            color=design.T().text, expand=True),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                content=ft.Column([
                    ft.Text(
                        feat["description"] or "Nessuna descrizione disponibile.",
                        size=13, color=design.T().text,
                        selectable=True,
                    ),
                    ft.Text(
                        f"{self.character.class_name}{source_label}",
                        size=11, color=design.T().text_3, italic=True,
                    ) if source_label else ft.Container(height=0),
                ], spacing=10, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Chiudi",
                                  on_click=lambda ev: page.pop_dialog() if page else None),
                ],
            ))

        rows: list[ft.Control] = []
        current_level = -1
        for feat in self._features:
            # Separatore di livello
            if feat["level"] != current_level:
                current_level = feat["level"]
                if rows:
                    rows.append(ft.Divider(color=design.T().border, height=1))

            is_subclass = feat["source"].lower() != (self.character.class_name or "").lower()
            badge_color = design.T().magic if is_subclass else design.T().primary_fill

            # Attacco Furtivo (Ladro): il dado scala col livello — mostrato
            # in coda al nome, mai persistito (calcolato a runtime, stesso
            # pattern già usato per il dado di Ispirazione Bardica).
            display_name = feat["name"]
            if (
                feat["name"] == "Attacco Furtivo"
                and (self.character.class_name or "").lower() == "ladro"
            ):
                die = _loader.get_sneak_attack_dice(self.character.level)
                display_name = f"{feat['name']} ({die})"

            row = ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(
                            f"Lv{feat['level']}",
                            size=9, color=design.T().on_primary,
                            weight=ft.FontWeight.BOLD,
                        ),
                        bgcolor=badge_color,
                        padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                        border_radius=3,
                        width=32,
                    ),
                    ft.Container(width=8),
                    ft.Text(
                        display_name,
                        size=13, color=design.T().text,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=design.T().text_3),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                on_click=lambda e, f=feat: _open_feature_dialog(f),
                ink=True,
                border_radius=design.Radius.SM,
                padding=ft.Padding.symmetric(vertical=6, horizontal=4),
            )
            rows.append(row)

        legend = ft.Row([
            ft.Container(width=10, height=10, bgcolor=design.T().primary_fill,
                         border_radius=2),
            ft.Text(" classe base  ", size=10, color=design.T().text_3),
            ft.Container(width=10, height=10, bgcolor=design.T().magic,
                         border_radius=2),
            ft.Text(" sottoclasse", size=10, color=design.T().text_3),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        return ft.Container(
            content=ft.Column([*rows, ft.Divider(color=design.T().border), legend], spacing=2),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Dadi Vita
    # ------------------------------------------------------------------

    def _section_hit_dice(self, c: Character) -> ft.Container:
        die        = c.hit_dice_type or 8
        total      = c.hit_dice_total or c.level
        remaining  = c.hit_dice_remaining if c.hit_dice_remaining is not None else total
        con_mod    = get_modifier(c.con_score)
        con_str    = f"+{con_mod}" if con_mod >= 0 else str(con_mod)

        # Cerchietti ◆ disponibili / ◇ usati
        dice_circles: list[ft.Control] = []
        for i in range(total):
            avail = i < remaining
            dice_circles.append(ft.Container(
                content=ft.Text(
                    "◆" if avail else "◇", size=18,
                    color=design.T().primary if avail else design.T().text_3,
                ),
                tooltip=f"d{die} disponibile" if avail else "usato",
                padding=ft.Padding.all(1),
            ))

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"d{die}", size=28, weight=ft.FontWeight.BOLD,
                                    color=design.T().primary, font_family=design.Font.MONO),
                            ft.Container(width=10),
                            ft.Column(
                                [
                                    ft.Text(f"{remaining} / {total} rimanenti",
                                            size=13, color=design.T().text),
                                    ft.Text(f"Cura per dado: 1–{die} {con_str} CON",
                                            size=11, color=design.T().text_3),
                                ],
                                spacing=1,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=ft.Row(dice_circles, spacing=4, wrap=True),
                        padding=ft.Padding.symmetric(vertical=4),
                    ),
                    ft.ElevatedButton(
                        "Riposo Breve",
                        icon=ft.Icons.COFFEE,
                        on_click=self._on_short_rest_click,
                        disabled=(remaining == 0),
                        expand=True,
                        style=ft.ButtonStyle(
                            bgcolor=design.T().warning, color=design.T().on_primary,
                        ),
                    ),
                ],
                spacing=8,
            ),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().warning)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _on_short_rest_click(self, e):
        page = self._page
        if page is None:
            return
        c = self.character
        die       = c.hit_dice_type or 8
        total     = c.hit_dice_total or c.level
        remaining = c.hit_dice_remaining if c.hit_dice_remaining is not None else total
        con_mod   = get_modifier(c.con_score)

        hit_dice_style = design.field_style()
        hit_dice_style["focused_border_color"] = design.T().warning
        f_dice = ft.TextField(
            label=f"Dadi da spendere (max {remaining})", value="1",
            keyboard_type=ft.KeyboardType.NUMBER,
            **hit_dice_style)
        f_roll = ft.TextField(
            label="Totale dadi tirati (escluso CON)",
            hint_text=f"es. {die // 2} per un dado",
            keyboard_type=ft.KeyboardType.NUMBER,
            **hit_dice_style)

        def apply(ev):
            if page is None:
                return
            try:
                n = max(1, min(remaining, int(f_dice.value or 1)))
                roll = max(n, int(f_roll.value or n))
            except ValueError:
                return
            # PHB p.186: "Il personaggio recupera un numero di punti ferita pari
            # al totale (fino a un minimo di 0)" — il minimo è ZERO sul totale,
            # non 1 (rilevante con modificatore di Costituzione negativo).
            recovered = max(0, roll + con_mod * n)
            c.hp_current = min(c.hp_max, c.hp_current + recovered)
            c.hit_dice_remaining = max(0, remaining - n)
            character_repo.update_hp(c.id, c.hp_current)
            character_repo.update_hit_dice(c.id, c.hit_dice_remaining)
            # Riposto breve: risorse short_rest + slot Warlock (PHB p.107)
            character_repo.reset_class_resources(c.id, "short_rest")
            if c.class_name.strip().lower() == "warlock":
                character_repo.reset_all_spell_slots(c.id)
            self._schedule_hp_world_sync()
            page.pop_dialog()
            self._refresh()

        def roll_hit_dice(ev):
            """
            Tira i dadi vita indicati e compila il campo del totale.

            Il modificatore di Costituzione resta fuori dal campo (lo
            aggiunge `apply`, una volta per dado, come vuole il PHB) — per
            questo si tira la sola parte in dadi.
            """
            try:
                n = max(1, min(remaining, int(f_dice.value or 1)))
            except ValueError:
                n = 1
            spec = cs.hit_die_roll(c)
            # Il modificatore di CON è escluso deliberatamente: qui serve solo
            # il totale grezzo dei dadi.
            result = show_roll(self._page, RollSpec(
                kind="hit_die",
                label=f"Dadi vita ×{n} (d{die})",
                formula=f"{n}d{die}",
                note=f"{spec.note} per dado, aggiunto al momento di applicare il riposo",
            ))
            if result is not None:
                f_roll.value = str(result.total)
                try:
                    f_roll.update()
                except (RuntimeError, AssertionError):
                    pass

        roll_hd_btn = ft.OutlinedButton(
            "Tira i dadi vita", icon=ft.Icons.CASINO_OUTLINED, on_click=roll_hit_dice,
        )

        # Note classe-specifiche per il riposo breve
        class_key = c.class_name.strip().lower()
        extra_notes: list[ft.Control] = []
        if class_key == "warlock":
            extra_notes.append(ft.Text(
                "✦ Warlock: tutti gli slot del Patto della Magia vengono ripristinati.",
                size=11, color=design.T().magic, italic=True,
            ))
        if class_key == "mago" and c.level >= 1:
            max_rec = (c.level + 1) // 2  # metà livello arrotondata per eccesso
            extra_notes.append(ft.Text(
                f"✦ Mago: puoi usare Recupero Arcano (1/riposo lungo) per recuperare "
                f"slot incantesimo per un totale di {max_rec} livelli (max Lv5 ciascuno). "
                f"Aggiorna manualmente gli slot nella scheda degli incantesimi.",
                size=11, color=design.T().magic, italic=True,
            ))

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Riposo Breve"),
            content=ft.Column(
                [
                    ft.Text(
                        f"Lancia i dadi vita (d{die}) e aggiungi {con_mod:+d} CON per dado.",
                        size=12, color=design.T().text_2,
                    ),
                    ft.Container(height=4),
                    f_dice,
                    f_roll,
                    ft.Row([roll_hd_btn], wrap=True),
                    *extra_notes,
                ],
                spacing=8,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Applica Riposo", on_click=apply,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().warning, color=design.T().on_primary,
                    ),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Riposo Lungo
    # ------------------------------------------------------------------

    def _section_riposo_lungo(self, c: Character) -> ft.Container:

        # PHB p.291 (Appendice A): "Completando un riposo lungo, una creatura
        # riduce di 1 il suo livello di indebolimento, purché abbia anche avuto
        # modo di mangiare e bere qualcosa." La clausola su cibo e bevande è una
        # condizione reale del manuale, quindi è una scelta del giocatore, non
        # un automatismo dell'app.
        food_cb = ft.Checkbox(
            label="Ha mangiato e bevuto (riduce l'Indebolimento di 1)",
            value=True,
            label_style=ft.TextStyle(size=12, color=design.T().text_2),
            active_color=design.T().magic,
        )

        def do_rest(ev):
            page = self._page
            if page is None:
                return
            # HP e HP temp
            c.hp_current = c.hp_max
            c.hp_temp = 0
            # Recupera metà dei dadi vita (minimo 1) — PHB p.186
            total = c.hit_dice_total or c.level
            recovered_dice = max(1, total // 2)
            c.hit_dice_remaining = min(
                total,
                (c.hit_dice_remaining or 0) + recovered_dice,
            )
            # Azzera stato turno e death saves
            c.action_used = False
            c.bonus_action_used = False
            c.reaction_used = False
            c.movement_used = 0
            c.previous_turn_state = ""
            c.death_saves_success = 0
            c.death_saves_failure = 0
            # Indebolimento: -1 se il personaggio ha mangiato e bevuto (PHB p.291)
            exh_before = c.exhaustion_level or 0
            if food_cb.value and exh_before > 0:
                c.exhaustion_level = exh_before - 1
            # Un bonus CA temporaneo (incantesimo/reazione) non sopravvive alla
            # notte, e un'ira — quindi la Frenesia dichiarata per quell'ira —
            # non può attraversare un riposo lungo.
            c.ca_bonus = 0
            c.frenzy_active = False
            # Concentrazione: durante un riposo lungo si dorme almeno 6 ore, e
            # una creatura addormentata è priva di sensi — quindi incapacitata,
            # che è la causa di perdita indicata dal PHB p.204. Il riposo BREVE
            # non la interrompe: è "un'ora di attività leggera", non sonno.
            c.concentrating_spell = ""
            c.concentrating_since = ""
            # Le condizioni imposte durante l'avventura non attraversano una
            # notte di riposo: si azzerano insieme al resto. Restano comunque
            # riaggiungibili con un click se il DM le fa persistere.
            character_repo.clear_conditions(c.id)
            # Ripristina tutti gli slot incantesimo (usato=0)
            character_repo.reset_all_spell_slots(c.id)
            # Ricalcola i totali PHB — rimuove eventuali slot temporanei creati
            # con Incantesimi Flessibili (Stregone), che svaniscono al riposo lungo
            character_repo.auto_init_spell_slots(c.id, c.class_name or "", c.level)
            # Ripristina tutte le risorse di classe (short_rest e long_rest)
            character_repo.reset_class_resources(c.id, "short_rest")
            character_repo.reset_class_resources(c.id, "long_rest")
            # Forme selvatiche ed evocazioni attive terminano: nessuna dura 8 ore
            # (unico caso limite teorico: Forma Selvatica di un druido di 20°
            # livello, che durerebbe 10 ore — resta riattivabile con un click).
            character_repo.deactivate_all_creatures(c.id)
            # Salva tutto
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            character_repo.update_hp(c.id, c.hp_max, 0)
            self._schedule_hp_world_sync()
            page.pop_dialog()
            self._refresh()
            if food_cb.value and exh_before > 0:
                self._show_rule_notice(
                    "Indebolimento",
                    f"Livello di Indebolimento ridotto da {exh_before} a "
                    f"{exh_before - 1}.\nPHB p.291 — riposo lungo con cibo e bevande.",
                )

        def confirm(e):
            page = self._page
            if page is None:
                return

            # PHB p.186: "deve possedere almeno 1 punto ferita all'inizio del
            # riposo per ottenerne i benefici".
            if c.hp_current <= 0:
                page.show_dialog(ft.AlertDialog(
                    title=design.dialog_title("Riposo Lungo non possibile"),
                    content=ft.Text(
                        "Il personaggio è a 0 punti ferita.\n\n"
                        "PHB p.186: un personaggio «deve possedere almeno 1 punto "
                        "ferita all'inizio del riposo per ottenerne i benefici».\n\n"
                        "Va prima stabilizzato o curato.",
                        size=13, color=design.T().text,
                    ),
                    actions=[ft.TextButton("OK", on_click=lambda ev: page.pop_dialog())],
                ))
                return

            total = c.hit_dice_total or c.level
            recovered = max(1, total // 2)
            exh = c.exhaustion_level or 0
            rows: list[ft.Control] = [
                ft.Text(
                    f"Effettuare un riposo lungo?\n\n"
                    f"  ❤  HP ripristinati ({c.hp_current} → {c.hp_max})\n"
                    f"  ◆  Dadi vita recuperati (+{recovered})\n"
                    f"  ●  Slot incantesimo ripristinati\n"
                    f"  ⚡  Risorse di classe ripristinate\n"
                    f"  ↺  Azioni turno azzerate\n"
                    f"  ☠  Tiri salvezza morte azzerati\n"
                    f"  ⛨  Bonus CA temporaneo azzerato\n"
                    f"  ✦  Forme/evocazioni attive terminate",
                    size=13, color=design.T().text,
                ),
            ]
            if exh > 0:
                rows.append(ft.Container(height=4))
                rows.append(food_cb)
            page.show_dialog(ft.AlertDialog(
                title=design.dialog_title("Riposo Lungo"),
                content=ft.Column(rows, spacing=2, tight=True),
                actions=wrap_dialog_actions([
                    ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                    ft.ElevatedButton(
                        "Riposa",
                        on_click=do_rest,
                        style=ft.ButtonStyle(
                            bgcolor=design.T().magic, color=design.T().on_accent,
                        ),
                    ),
                ]),
            ))

        return ft.Container(
            content=ft.ElevatedButton(
                "Riposo Lungo",
                icon=ft.Icons.BEDTIME,
                on_click=confirm,
                expand=True,
                style=ft.ButtonStyle(
                    bgcolor=design.T().magic, color=design.T().on_accent,
                    padding=ft.Padding.symmetric(vertical=14, horizontal=20),
                ),
            ),
            padding=ft.Padding.only(bottom=24),
        )

    # ------------------------------------------------------------------
    # Sezione Forme Selvatiche (solo Druido)
    # ------------------------------------------------------------------

    def _section_forme(self) -> ft.Container:
        """
        Bestiary personale delle forme selvatiche del Druido.
        - Banner "In forma" se una forma è attiva (hp tracker + Esci).
        - Lista forme conosciute con tasto Trasformati.
        - Tasto "+ Aggiungi Forma" (ricerca nel bestiary Bestia).
        - Spillover HP: quando la forma scende a 0 hp chiede il danno totale
          e lo trasferisce al Druido.
        """
        rows: list[ft.Control] = []

        # ── Forma attiva ────────────────────────────────────────────────
        active = next((f for f in self._forme if f.is_active), None)
        if active:
            rows.append(self._active_forma_banner(active))
            rows.append(ft.Divider(height=8, color="transparent"))

        # ── Forme conosciute ────────────────────────────────────────────
        if not self._forme:
            rows.append(ft.Text(
                "Nessuna forma conosciuta.\nAggiungi le bestie in cui puoi trasformarti.",
                size=12, color=design.T().text_3, text_align=ft.TextAlign.CENTER,
            ))
        else:
            for forma in self._forme:
                rows.append(self._forma_row(forma, active))

        rows.append(ft.Container(height=6))
        rows.append(ft.TextButton(
            "+ Aggiungi Forma",
            icon=ft.Icons.ADD,
            on_click=lambda _: self._open_creature_search("forma"),
        ))

        return ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _active_forma_banner(self, forma: CreatureEntry) -> ft.Container:
        """Banner grande per la forma selvatica attiva con tracker HP."""
        ratio = (forma.hp_current / forma.hp_max) if forma.hp_max > 0 else 0.0
        ratio = max(0.0, min(1.0, ratio))
        hp_color = design.T().success if ratio > 0.5 else (design.T().warning if ratio > 0.25 else design.T().danger)

        def apply_damage(_e: ft.ControlEvent) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Danno", keyboard_type=ft.KeyboardType.NUMBER, width=120, **design.field_style())

            def confirm(_ev: Any) -> None:
                try:
                    dmg = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = forma.hp_current - dmg
                if new_hp <= 0:
                    # Spillover: danno eccede i PF della forma
                    spillover = abs(new_hp)
                    character_repo.update_creature_hp(forma.id, 0)
                    character_repo.set_creature_active(forma.id, False)
                    page.pop_dialog()
                    self._spillover_dialog(spillover)
                else:
                    character_repo.update_creature_hp(forma.id, new_hp)
                    page.pop_dialog()
                    self._refresh()

            dlg = ft.AlertDialog(
                title=design.dialog_title(f"Danno a {forma.name}"),
                content=tf,
                actions=cast(list[ft.Control], wrap_dialog_actions([
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ])),
            )
            page.show_dialog(dlg)

        def apply_heal(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Cura", keyboard_type=ft.KeyboardType.NUMBER, width=120, **design.field_style())

            def confirm(_ev: Any) -> None:
                try:
                    heal = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = min(forma.hp_max, forma.hp_current + heal)
                character_repo.update_creature_hp(forma.id, new_hp)
                page.pop_dialog()
                self._refresh()

            dlg = ft.AlertDialog(
                title=design.dialog_title(f"Cura {forma.name}"),
                content=tf,
                actions=cast(list[ft.Control], wrap_dialog_actions([
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ])),
            )
            page.show_dialog(dlg)

        def exit_form(_e: Any) -> None:
            character_repo.set_creature_active(forma.id, False, reset_hp=True)
            self._refresh()

        def _on_apply_damage(_e: Any) -> None: apply_damage(_e)  # type: ignore[arg-type]
        def _on_apply_heal(_e: Any) -> None: apply_heal(_e)  # type: ignore[arg-type]

        return ft.Container(
            content=ft.Column(cast(list[ft.Control], [
                ft.Row(cast(list[ft.Control], [
                    ft.Text("🐺 IN FORMA:", size=10, color=design.T().text_3,
                            weight=ft.FontWeight.W_600),
                    ft.Text(forma.name.title(), size=14, color=design.T().text,
                            weight=ft.FontWeight.BOLD, expand=True),
                    ft.TextButton("Esci dalla Forma", on_click=exit_form,
                                  style=ft.ButtonStyle(color=design.T().primary)),
                ]), vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row(cast(list[ft.Control], [
                    ft.Text(str(forma.hp_current), size=30, weight=ft.FontWeight.BOLD,
                            color=hp_color, font_family=design.Font.MONO),
                    ft.Text(f" / {forma.hp_max} PF", size=14, color=design.T().text_3,
                            font_family=design.Font.MONO),
                    ft.Container(expand=True),
                    # `danger_icon`, non `primary_icon` — applica danno è
                    # l'azione distruttiva gemella di "Cura" qui sotto (che
                    # resta `success`).
                    ft.IconButton(ft.Icons.REMOVE, on_click=_on_apply_damage,
                                  icon_color=design.T().danger_icon,
                                  tooltip="Applica danno"),
                    ft.IconButton(ft.Icons.ADD, on_click=_on_apply_heal,
                                  icon_color=design.T().success,
                                  tooltip="Cura"),
                ]), vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.ProgressBar(
                        value=ratio, height=6,
                        color=hp_color, bgcolor=design.T().surface_alt,
                        expand=True,
                    )
                ]),
                ft.Text(f"CA {forma.ac}{' (' + forma.ac_note + ')' if forma.ac_note else ''} · {forma.speed}",
                        size=11, color=design.T().text_3),
            ]), spacing=4),
            bgcolor=design.T().surface_alt,
            padding=12,
            border_radius=8,
            border=ft.Border.all(1, design.T().primary),
        )

    def _forma_row(self, forma: CreatureEntry, active: "CreatureEntry | None") -> ft.Container:
        """Riga compatta per una forma selvatica nel bestiary."""
        is_active = forma.is_active

        def trasformati(_e: Any) -> None:
            # Disattiva eventuale forma precedente (non si può stare in due forme)
            for f in self._forme:
                if f.is_active:
                    character_repo.set_creature_active(f.id, False, reset_hp=True)
            character_repo.set_creature_active(forma.id, True)
            self._refresh()

        def show_sheet(_e: Any) -> None:
            self._show_creature_sheet(forma)

        def remove(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            def confirm(_ev: Any) -> None:
                character_repo.delete_creature_entry(forma.id)
                page.pop_dialog()
                self._refresh()
            dlg = ft.AlertDialog(
                title=design.dialog_title("Rimuovi forma?"),
                content=ft.Text(f"Rimuovere {forma.name.title()} dal bestiary?"),
                actions=cast(list[ft.Control], wrap_dialog_actions([
                    # `danger`, non `primary` — conferma di rimozione
                    # permanente.
                    ft.TextButton("Rimuovi", on_click=confirm,
                                  style=ft.ButtonStyle(color=design.T().danger)),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ])),
            )
            page.show_dialog(dlg)

        cr_text = f"GS {forma.cr}" if forma.cr else "GS —"
        hp_text = f"{forma.hp_max} PF ({forma.hp_formula})" if forma.hp_formula else f"{forma.hp_max} PF"

        return ft.Container(
            content=ft.Row([
                ft.GestureDetector(
                    content=ft.Column([
                        ft.Text(forma.name.title(), size=13, weight=ft.FontWeight.W_600,
                                color=design.T().text),
                        ft.Text(f"{cr_text} · {hp_text} · CA {forma.ac}",
                                size=11, color=design.T().text_3),
                    ], spacing=2),
                    on_tap=show_sheet,
                    expand=True,
                ),
                ft.Container(width=8),
                ft.ElevatedButton(
                    "Trasformati",
                    on_click=trasformati,
                    disabled=is_active or (active is not None and not is_active),
                    style=ft.ButtonStyle(
                        bgcolor=design.T().primary_fill if not (active and not is_active) else design.T().surface_alt,
                        color=design.T().on_primary_fill if not (active and not is_active) else design.T().text_3,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    ),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_color=design.T().text_3,
                    on_click=remove,
                    tooltip="Rimuovi dal bestiary",
                    icon_size=18,
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=6, horizontal=2),
            border=ft.Border(
                bottom=ft.BorderSide(1, design.T().border),
            ),
        )

    def _spillover_dialog(self, spillover: int) -> None:
        """Dialog che informa del danno spillover al personaggio dopo la forma a 0 HP."""
        if not self._page:
            return
        page = self._page
        c = self.character
        new_hp = max(0, c.hp_current - spillover)

        def apply(_e: Any) -> None:
            character_repo.update_hp(c.id, new_hp)
            self._schedule_hp_world_sync()
            page.pop_dialog()
            self._refresh()

        def dismiss(_e: Any) -> None:
            page.pop_dialog()
            self._refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("⚠️ Forma a 0 PF!"),
            content=ft.Column([
                ft.Text("La forma selvatica ha esaurito i suoi Punti Ferita.", size=13),
                ft.Container(height=4),
                ft.Text(f"Danno spillover: {spillover} PF", size=13,
                        weight=ft.FontWeight.BOLD, color=design.T().primary),
                ft.Text(f"PF {c.name}: {c.hp_current} → {new_hp}", size=13),
                ft.Container(height=4),
                ft.Text("Se il danno spillover supera i tuoi PF massimi, cadi immediatamente privo di sensi.",
                        size=11, color=design.T().text_3),
            ], spacing=2, tight=True),
            actions=cast(list[ft.Control], wrap_dialog_actions([
                ft.TextButton("Applica danno al personaggio", on_click=apply,
                              style=ft.ButtonStyle(color=design.T().primary)),
                ft.TextButton("Ignora (gestione manuale)", on_click=dismiss),
            ])),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Sezione Evocazioni (tutti i personaggi)
    # ------------------------------------------------------------------

    def _section_evocazioni(self) -> ft.Container:
        """
        Bestiary delle evocazioni del personaggio.
        - Evocazioni attive: HP tracker + tasto Elimina (rimuove dall'attivo).
        - Bestiary: lista con tasto Evoca + tasto rimuovi.
        - Tasto "+ Evoca" per aggiungere dal bestiary mostri.
        """
        rows: list[ft.Control] = []

        # ── Evocazioni attive ───────────────────────────────────────────
        active_evocs = [e for e in self._evocazioni if e.is_active]
        if active_evocs:
            rows.append(ft.Text("In campo", size=11, color=design.T().text_3,
                                weight=ft.FontWeight.W_600))
            for evoc in active_evocs:
                rows.append(self._active_evocazione_card(evoc))
            rows.append(ft.Divider(height=8, color=design.T().border))

        # ── Bestiary evocazioni ────────────────────────────────────────
        inactive = [e for e in self._evocazioni if not e.is_active]
        if not self._evocazioni:
            rows.append(ft.Text(
                "Nessuna evocazione salvata.\nEvoca creature tramite incantesimi e aggiungile qui.",
                size=12, color=design.T().text_3, text_align=ft.TextAlign.CENTER,
            ))
        elif inactive:
            rows.append(ft.Text("Bestiary evocazioni", size=11, color=design.T().text_3,
                                weight=ft.FontWeight.W_600))
            for evoc in inactive:
                rows.append(self._evocazione_row(evoc))

        rows.append(ft.Container(height=6))
        rows.append(ft.TextButton(
            "+ Evoca",
            icon=ft.Icons.ADD,
            on_click=lambda _: self._open_creature_search("evocazione"),
        ))

        return ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor=design.T().surface,
            padding=14,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().magic)),
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
        )

    def _active_evocazione_card(self, evoc: CreatureEntry) -> ft.Container:
        """Card con HP tracker per un'evocazione attiva in campo."""
        ratio = (evoc.hp_current / evoc.hp_max) if evoc.hp_max > 0 else 0.0
        ratio = max(0.0, min(1.0, ratio))
        hp_color = design.T().success if ratio > 0.5 else (design.T().warning if ratio > 0.25 else design.T().danger)

        def apply_damage(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Danno", keyboard_type=ft.KeyboardType.NUMBER, width=120, **design.field_style())

            def confirm(_ev: Any) -> None:
                try:
                    dmg = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = evoc.hp_current - dmg
                if new_hp <= 0:
                    # Evocazione a 0 HP: rimuove dall'attivo ma non dal bestiary
                    character_repo.update_creature_hp(evoc.id, 0)
                    character_repo.set_creature_active(evoc.id, False, reset_hp=False)
                    page.pop_dialog()
                    # Mostra avviso
                    page.show_dialog(ft.AlertDialog(
                        title=design.dialog_title("Evocazione eliminata"),
                        content=ft.Text(
                            f"{evoc.name.title()} ha raggiunto 0 PF ed è stata rimossa dal campo.\n"
                            "La voce rimane nel tuo bestiary per future evocazioni."
                        ),
                        actions=[ft.TextButton("OK", on_click=lambda _:
                            (page.pop_dialog(), self._refresh()) if self._page else None)],
                    ))
                else:
                    character_repo.update_creature_hp(evoc.id, new_hp)
                    page.pop_dialog()
                    self._refresh()

            dlg = ft.AlertDialog(
                title=design.dialog_title(f"Danno a {evoc.name.title()}"),
                content=tf,
                actions=cast(list[ft.Control], wrap_dialog_actions([
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ])),
            )
            page.show_dialog(dlg)

        def apply_heal(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            tf = ft.TextField(label="Cura", keyboard_type=ft.KeyboardType.NUMBER, width=120, **design.field_style())

            def confirm(_ev: Any) -> None:
                try:
                    heal = int(tf.value or "0")
                except ValueError:
                    return
                new_hp = min(evoc.hp_max, evoc.hp_current + heal)
                character_repo.update_creature_hp(evoc.id, new_hp)
                page.pop_dialog()
                self._refresh()

            dlg = ft.AlertDialog(
                title=design.dialog_title(f"Cura {evoc.name.title()}"),
                content=tf,
                actions=cast(list[ft.Control], wrap_dialog_actions([
                    ft.TextButton("Applica", on_click=confirm),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ])),
            )
            page.show_dialog(dlg)

        def dismiss_evocation(_e: Any) -> None:
            """Libera l'evocazione (torna al bestiary con HP resettati)."""
            character_repo.set_creature_active(evoc.id, False, reset_hp=True)
            self._refresh()

        def show_sheet(_e: Any) -> None:
            self._show_creature_sheet(evoc)

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.GestureDetector(
                        content=ft.Text(evoc.name.title(), size=13, weight=ft.FontWeight.W_600,
                                        color=design.T().text),
                        on_tap=show_sheet,
                    ),
                    ft.Text(f" — GS {evoc.cr}" if evoc.cr else "", size=11, color=design.T().text_3),
                    ft.Container(expand=True),
                    # `danger_icon`, non `primary_icon` — stesso principio
                    # delle forme selvatiche qui sopra.
                    ft.IconButton(ft.Icons.REMOVE, on_click=apply_damage,
                                  icon_color=design.T().danger_icon, icon_size=18,
                                  tooltip="Applica danno"),
                    ft.IconButton(ft.Icons.ADD, on_click=apply_heal,
                                  icon_color=design.T().success, icon_size=18,
                                  tooltip="Cura"),
                    ft.IconButton(ft.Icons.CLOSE, on_click=dismiss_evocation,
                                  icon_color=design.T().text_3, icon_size=18,
                                  tooltip="Libera (fine combattimento)"),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                ft.Row([
                    ft.Text(str(evoc.hp_current), size=22, weight=ft.FontWeight.BOLD,
                            color=hp_color, font_family=design.Font.MONO),
                    ft.Text(f" / {evoc.hp_max} PF", size=12, color=design.T().text_3,
                            font_family=design.Font.MONO),
                    ft.Container(expand=True),
                    ft.Text(f"CA {evoc.ac}", size=12, color=design.T().text_3),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.ProgressBar(value=ratio, height=5, color=hp_color,
                                   bgcolor=design.T().surface_alt, expand=True)
                ]),
            ], spacing=4),
            bgcolor=design.T().surface_alt,
            padding=10,
            border_radius=design.Radius.MD,
            border=ft.Border.all(1, design.T().magic),
        )

    def _evocazione_row(self, evoc: CreatureEntry) -> ft.Container:
        """Riga compatta per un'evocazione nel bestiary (non attiva)."""

        def evoca(_e: Any) -> None:
            character_repo.set_creature_active(evoc.id, True, reset_hp=True)
            self._refresh()

        def show_sheet(_e: Any) -> None:
            self._show_creature_sheet(evoc)

        def remove(_e: Any) -> None:
            if not self._page:
                return
            page = self._page
            def confirm(_ev: Any) -> None:
                character_repo.delete_creature_entry(evoc.id)
                page.pop_dialog()
                self._refresh()
            dlg = ft.AlertDialog(
                title=design.dialog_title("Rimuovi evocazione?"),
                content=ft.Text(f"Rimuovere {evoc.name.title()} dal bestiary?"),
                actions=cast(list[ft.Control], wrap_dialog_actions([
                    # `danger`, non `primary` — conferma di rimozione
                    # permanente.
                    ft.TextButton("Rimuovi", on_click=confirm,
                                  style=ft.ButtonStyle(color=design.T().danger)),
                    ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
                ])),
            )
            page.show_dialog(dlg)

        cr_text = f"GS {evoc.cr}" if evoc.cr else "GS —"
        hp_text = f"{evoc.hp_max} PF"

        return ft.Container(
            content=ft.Row([
                ft.GestureDetector(
                    content=ft.Column([
                        ft.Text(evoc.name.title(), size=13, weight=ft.FontWeight.W_600,
                                color=design.T().text),
                        ft.Text(f"{cr_text} · {hp_text} · CA {evoc.ac}",
                                size=11, color=design.T().text_3),
                    ], spacing=2),
                    on_tap=show_sheet,
                    expand=True,
                ),
                ft.ElevatedButton(
                    "Evoca",
                    on_click=evoca,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().magic,
                        color=design.T().on_accent,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    ),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_color=design.T().text_3,
                    on_click=remove,
                    tooltip="Rimuovi dal bestiary",
                    icon_size=18,
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=6, horizontal=2),
            border=ft.Border(bottom=ft.BorderSide(1, design.T().border)),
        )

    # ------------------------------------------------------------------
    # Dialog ricerca creatura (condiviso tra Forme e Evocazioni)
    # ------------------------------------------------------------------

    def _open_creature_search(self, entry_type: str) -> None:
        """
        Dialog di ricerca nel bestiario con filtri tipo/GS e vista dettaglio
        inline. Delega interamente a `show_monster_picker`
        (ui/components/monster_picker.py, riusato anche dalla Sezione
        Master) — il salvataggio su `creature_entries` (specifico del
        personaggio) resta locale qui.
        entry_type = "forma"      → filtra solo Bestie
                   = "evocazione" → tutte le creature
        """
        if not self._page:
            return
        page = self._page

        all_monsters = load_monsters()
        pool = (
            [m for m in all_monsters if m.get("type") == "Bestia"]
            if entry_type == "forma" else all_monsters
        )

        title_label = "Aggiungi Forma Selvatica" if entry_type == "forma" else "Evoca Creatura"
        existing_names = {
            e.name.upper()
            for e in (self._forme if entry_type == "forma" else self._evocazioni)
        }
        select_label = "✔ Aggiungi al Bestiary" if entry_type == "forma" else "✔ Evoca"
        select_color = design.T().primary_fill if entry_type == "forma" else design.T().magic

        # ── Salva nel DB e chiude (specifico del personaggio, resta locale) ──
        def _save_creature(m: dict) -> None:
            entry = character_repo.create_creature_entry(
                character_id=self.character.id,
                entry_type=entry_type,
                name=m["name"],
                creature_type=m.get("type", ""),
                alignment=m.get("alignment", ""),
                cr=str(m.get("cr", "")),
                ac=int(m.get("ac", 10)),
                ac_note=m.get("ac_note", ""),
                hp_max=int(m.get("hp_max", 1)),
                hp_formula=m.get("hp_formula", ""),
                speed=m.get("speed", ""),
                str_score=int(m.get("str_score", 10)),
                dex_score=int(m.get("dex_score", 10)),
                con_score=int(m.get("con_score", 10)),
                int_score=int(m.get("int_score", 10)),
                wis_score=int(m.get("wis_score", 10)),
                cha_score=int(m.get("cha_score", 10)),
                saving_throws=json.dumps(m.get("saving_throws", {})),
                skills=json.dumps(m.get("skills", {})),
                damage_vulnerabilities=m.get("damage_vulnerabilities", ""),
                damage_resistances=m.get("damage_resistances", ""),
                damage_immunities=m.get("damage_immunities", ""),
                condition_immunities=m.get("condition_immunities", ""),
                senses=m.get("senses", ""),
                languages=m.get("languages", ""),
                traits=json.dumps(m.get("traits", [])),
                actions=json.dumps(m.get("actions", [])),
                reactions=json.dumps(m.get("reactions", [])),
                legendary_actions=json.dumps(m.get("legendary_actions", [])),
                lair_actions_intro=m.get("lair_actions_intro", ""),
                lair_actions=json.dumps(m.get("lair_actions", [])),
                regional_effects_label=m.get("regional_effects_label", ""),
                regional_effects_intro=m.get("regional_effects_intro", ""),
                regional_effects=json.dumps(m.get("regional_effects", [])),
                variant_rules=json.dumps(m.get("variant_rules", [])),
                source_page=int(m.get("source_page", 0)),
            )
            if entry:
                if entry_type == "evocazione":
                    character_repo.set_creature_active(entry.id, True)
                page.pop_dialog()
                self._refresh()

        show_monster_picker(
            page,
            title_label,
            pool,
            existing_names=existing_names,
            on_select=_save_creature,
            select_label=select_label,
            select_color=select_color,
            on_manual=lambda: self._open_manual_creature_dialog(entry_type),
        )

    def _open_manual_creature_dialog(self, entry_type: str) -> None:
        """Dialog per inserire manualmente una creatura non presente nel bestiary."""
        if not self._page:
            return
        page = self._page

        f_name = ft.TextField(label="Nome*", autofocus=True, **design.field_style())
        f_type = ft.TextField(label="Tipo (es. Bestia, Elementale)", **design.field_style())
        f_cr   = ft.TextField(label="Grado Sfida (es. 1/4, 5)", **design.field_style())
        f_ac   = ft.TextField(label="CA", value="10", keyboard_type=ft.KeyboardType.NUMBER, width=90, **design.field_style())
        f_hp   = ft.TextField(label="PF massimi*", keyboard_type=ft.KeyboardType.NUMBER, width=120, **design.field_style())
        f_speed= ft.TextField(label="Velocità (es. 9 m)", **design.field_style())

        def save(_e: Any) -> None:
            if not f_name.value or not f_hp.value:
                return
            try:
                hp_max = int(f_hp.value)
                ac = int(f_ac.value or "10")
            except ValueError:
                return
            entry = character_repo.create_creature_entry(
                character_id=self.character.id,
                entry_type=entry_type,
                name=f_name.value.upper(),
                creature_type=f_type.value or "",
                cr=f_cr.value or "",
                ac=ac,
                hp_max=hp_max,
                speed=f_speed.value or "",
            )
            if entry and entry_type == "evocazione":
                character_repo.set_creature_active(entry.id, True)
            if self._page:
                page.pop_dialog()
            self._refresh()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Inserimento manuale"),
            content=ft.Column([
                f_name,
                ft.Row([f_type, ft.Container(width=8), f_cr], spacing=0, run_spacing=8, wrap=True),
                ft.Row([f_ac, ft.Container(width=8), f_hp], spacing=0, run_spacing=8, wrap=True),
                f_speed,
            ], spacing=10, tight=True),
            actions=cast(list[ft.Control], wrap_dialog_actions([
                ft.TextButton("Salva", on_click=save),
                ft.TextButton("Annulla", on_click=lambda _: page.pop_dialog()),
            ])),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Dialog scheda creatura completa (condiviso)
    # ------------------------------------------------------------------

    def _show_creature_sheet(self, c: CreatureEntry) -> None:
        """
        AlertDialog con scheda completa della creatura: CA, HP, velocità,
        6 stat, TS, skill, resistenze, sensi, lingue, CR, tratti/azioni
        (scrollabile). Delega a `show_stat_block_dialog`/`creature_entry_dict`
        (ui/components/monster_picker.py) — stesso rendering condiviso con
        `_open_creature_search`, senza duplicarlo riga per riga.
        """
        if not self._page:
            return
        show_stat_block_dialog(self._page, c.name, creature_entry_dict(c))

    # ------------------------------------------------------------------
    # Refresh mirati (solo visivo: stessi dati di `_refresh()`, ma senza
    # ricostruire l'intera tab — vedi il piano "Fluidità transizioni e
    # animazioni")
    # ------------------------------------------------------------------

    def _refresh_hp_only(self) -> None:
        """
        Aggiorna solo la card HP (numero, barra, HP temp, TS morte) dopo
        Danno/Cura/HP temporanei/Modifica HP — questi flussi non toccano
        altre sezioni della tab TRANNE quando fanno scattare un cambiamento
        strutturale (es. la concentrazione si interrompe e la sezione
        "Concentrazione" compare/scompare in `_build()`): in quei casi il
        chiamante deve usare `_refresh()` pieno, non questo metodo.
        """
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        hp_container = self._hp_stats_row.controls[0]
        hp_container.content = self._section_hp(self.character)
        try:
            hp_container.update()
        except RuntimeError:
            pass
        if self._on_refresh:
            self._on_refresh()

    def _refresh_stats_only(self) -> None:
        """
        Aggiorna solo il riquadro Statistiche (CA, Velocità, Iniziativa,
        Ispirazione) dopo `_toggle_inspiration()` — cambio isolato, nessun
        effetto su altre sezioni.
        """
        stats_container = self._hp_stats_row.controls[1]
        stats_container.content = self._section_stats(self.character)
        try:
            stats_container.update()
        except RuntimeError:
            pass

    def _refresh_resources_only(self) -> None:
        """
        Aggiorna solo la sezione Risorse di Classe dopo un uso/recupero
        rapido (cerchietti, counter −/+, dichiarazione Frenesia, conversione
        Incantesimi Flessibili) — non tocca il resto della tab. Se la
        sezione non esiste (personaggio senza risorse di classe, non
        dovrebbe capitare dato che i chiamanti agiscono su una risorsa già
        presente) ricade su `_refresh()` pieno.
        """
        if self._class_resources_ref is None:
            self._refresh()
            return
        new_section = self._section_class_resources()
        self._class_resources_ref.content = new_section.content
        try:
            self._class_resources_ref.update()
        except RuntimeError:
            pass

    def _refresh_slots_only(self) -> None:
        """
        Aggiorna solo la sezione Magia (slot + incantesimi preparati) dopo
        un tap su un pallino slot — `_toggle_slot()` non tocca nient'altro
        nella tab.
        """
        new_section = self._section_spell_slots(self.character)
        self._spell_slots_ref.content = new_section.content
        try:
            self._spell_slots_ref.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        self._slots     = character_repo.get_spell_slots(self.character.id)
        self._profs     = character_repo.get_proficiencies(self.character.id)
        self._weapons   = character_repo.get_weapons(self.character.id)
        self._armor_items = [
            it for it in character_repo.get_inventory(self.character.id)
            if it.category == "armor" and it.is_equipped
        ]
        self._prepared  = character_repo.get_prepared_spells(self.character.id)
        self._resources = character_repo.get_class_resources(self.character.id)
        self._features     = self._load_class_features(self.character)
        self._race_traits  = get_race_display_traits(
            self.character.race or "", self.character.subrace or ""
        )
        self._forme = character_repo.get_creature_entries(self.character.id, entry_type="forma")
        self._evocazioni = character_repo.get_creature_entries(self.character.id, entry_type="evocazione")
        self._custom_abilities = character_repo.get_custom_abilities(self.character.id, "combattimento")
        self._conditions = character_repo.get_conditions(self.character.id)
        self._cond_effects = character_repo.condition_effects(self.character.id)
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        # Ripristina la posizione di scroll: il rebuild sopra ricrea tutti i
        # controlli, quindi senza questo la vista tornerebbe in cima ad ogni
        # singola azione.
        self.restore_scroll()
        if self._on_refresh:
            self._on_refresh()
