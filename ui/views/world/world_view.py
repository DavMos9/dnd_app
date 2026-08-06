"""
Sezione «Mondi» — passo 2 di `dnd_app/docs/multiplayer_design.md` ("Modello
mondo, senza rete"). UI minimale per creare/gestire un mondo condiviso e
verificare la pipeline comando → validazione → evento senza dover aspettare
le istanze di personaggio (passo 3) o la rete LAN (passo 4).

Indipendente da ogni personaggio, stesso principio di `master_view.py`:
raggiungibile dalla Home con una pillola sempre visibile (mai un'azione
nascosta in un menu, convenzione già stabilita nel progetto).
"""

from __future__ import annotations

import logging

import flet as ft

from core import world_permissions as perm
from core import world_sync
from core.world_backend import LocalBackend
from data.game_data.game_data_loader import GameDataLoader
from data.models import Character, World, WorldEvent, WorldMember
from data.repositories import character_repo, world_repo
from network.host_server import PendingJoinRequest, WorldHostServer, local_ip_hint
from network.qr_join import build_join_text, generate_qr_png_base64
from ui import design as d
from ui.device_identity import resolve_device_id
from ui.widgets import wrap_dialog_actions

logger = logging.getLogger(__name__)


class WorldsView(ft.Column):
    """
    Callbacks:
        on_back_to_home()              → torna alla Home
        on_toggle_theme(e)/theme_preference → stessa pillola tema delle altre sezioni
    """

    def __init__(self, on_back_to_home, on_toggle_theme=None, theme_preference: str = "system"):
        super().__init__(expand=True, spacing=0)
        self.on_back_to_home = on_back_to_home
        self.on_toggle_theme = on_toggle_theme
        self.theme_preference = theme_preference

        self.backend = LocalBackend()
        self.device_id: str | None = None
        self._current_world: World | None = None  # None = elenco, valorizzato = dettaglio

        #: Passo 4 (LAN): al più un hosting attivo per volta in questa
        #: view — coerente con §11.5 ("due dispositivi non possono
        #: ospitare lo stesso mondo"), qui applicato più semplicemente
        #: come "un solo hosting alla volta da questa sessione dell'app".
        self._host_server: WorldHostServer | None = None

        self._body = ft.Column(spacing=d.Space.MD, scroll=ft.ScrollMode.AUTO, expand=True)
        self._build_shell()
        self._render_loading()

    def did_mount(self):
        page = self.page
        if page is not None:
            page.run_task(self._init_identity)

    def will_unmount(self):
        # Il server si accende solo quando il master apre l'hosting e si
        # spegne alla chiusura (§9.4) — uscire dalla sezione Mondi senza
        # fermarlo esplicitamente non deve lasciare una porta aperta.
        if self._host_server is not None:
            self._host_server.stop()
            self._host_server = None

    async def _init_identity(self):
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
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
                    d.muted("Campagne condivise — passo 2, senza rete: funziona oggi "
                            "solo tra sessioni che condividono lo stesso database "
                            "(web mode multi-scheda)."),
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
                d.pill(ft.Icons.ADD, "Crea un mondo", filled=True, color=p.primary,
                       on_click=lambda e: self._open_create_dialog()),
                d.pill(ft.Icons.MEETING_ROOM, "Unisciti con un codice", color=p.magic,
                       on_click=lambda e: self._open_join_dialog()),
                d.pill(ft.Icons.WIFI, "Unisciti in LAN", color=p.magic,
                       on_click=lambda e: self._open_lan_join_dialog()),
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
        return d.card(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(world.name, size=d.Size.SUBTITLE, weight=ft.FontWeight.BOLD,
                                    color=p.text, font_family=d.Font.DISPLAY),
                            ft.Row(
                                [d.chip(role, role_tone),
                                 d.muted(f"{len(members)} membri")],
                                spacing=d.Space.SM,
                            ),
                        ],
                        spacing=d.Space.XS, expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=p.text_3),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e, w=world: self._open_detail(w),
        )

    def _open_detail(self, world: World):
        self._current_world = world
        self._render()
        try:
            self.page.update()
        except RuntimeError:
            pass

    def _back_to_list(self):
        self._current_world = None
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

        sections: list[ft.Control] = [
            d.pill(ft.Icons.ARROW_BACK, "Tutti i mondi", color=p.text_2,
                   on_click=lambda e: self._back_to_list()),
            ft.Container(height=d.Space.SM),
            ft.Text(world.name, size=d.Size.TITLE, weight=ft.FontWeight.BOLD,
                    color=p.text, font_family=d.Font.DISPLAY),
        ]

        if is_owner:
            sections.append(self._rename_section(world))

        sections.append(self._join_code_section(world, is_owner))
        if is_owner and world.is_local_host:
            sections.append(self._hosting_section(world))
        if perm.can_perform(my_role, perm.CMD_XP_GRANT):
            sections.append(self._remote_actions_section(world))
        sections.append(self._members_section(world, my_role))
        sections.append(self._events_section(world))

        if is_owner:
            sections.append(self._danger_zone_section(world))

        self._body.controls = sections

    def _rename_section(self, world: World) -> ft.Control:
        field = ft.TextField(value=world.name, dense=True, expand=True, **d.field_style())

        def _save(e):
            result = self.backend.send_command(
                world.id, self.device_id, perm.CMD_WORLD_RENAME,
                {"name": field.value},
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
        result = self.backend.send_command(
            world.id, self.device_id, perm.CMD_WORLD_JOIN_CODE_REGENERATE, {},
        )
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

    def _members_section(self, world: World, my_role: str) -> ft.Control:
        members = world_repo.get_members(world.id)
        rows = [self._member_row(world, m, my_role) for m in members]
        return d.section("Membri", ft.Column(rows, spacing=d.Space.SM, tight=True))

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
                icon_color=p.danger,
                on_click=lambda e, m=member: self._confirm_kick(world, m),
            ))

        return ft.Row(
            [
                ft.Icon(ft.Icons.PERSON, color=p.text_3, size=18),
                ft.Text(member.display_name + (" (tu)" if is_me else ""),
                        color=p.text, expand=True),
                d.chip(member.role, role_tone),
                *actions,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _member_command(self, world: World, kind: str, member: WorldMember):
        result = self.backend.send_command(
            world.id, self.device_id, kind, {"device_id": member.device_id},
        )
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

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
                    style=ft.ButtonStyle(bgcolor=p.danger, color=p.text),
                ),
            ]),
        )
        self.page.show_dialog(dlg)

    def _do_kick(self, world: World, member: WorldMember):
        self.page.pop_dialog()
        self._member_command(world, perm.CMD_MEMBER_KICK, member)

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
        )

    def _remote_character_row(self, world: World, character: Character) -> ft.Control:
        p = d.T()
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
                            tooltip="Rimuovi condizione",
                            on_click=lambda e, w=world, c=character, cid=cond.id:
                                self._send_remote_command(
                                    w, c, perm.CMD_CONDITION_REMOVE, {"condition_id": cid}),
                        ),
                    ],
                    spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=p.danger, border_radius=d.Radius.SM,
                padding=ft.Padding.only(left=8, right=2),
            ))

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
                        d.pill(ft.Icons.STARS, "PE", color=p.success,
                               on_click=lambda e, w=world, c=character: self._open_xp_dialog(w, c)),
                        d.pill(ft.Icons.FAVORITE_BORDER, "Danno", color=p.danger,
                               on_click=lambda e, w=world, c=character: self._open_damage_dialog(w, c)),
                        d.pill(ft.Icons.HEALING, "Cura", color=p.primary,
                               on_click=lambda e, w=world, c=character: self._open_heal_dialog(w, c)),
                        d.pill(ft.Icons.SICK, "Condizione", color=p.magic,
                               on_click=lambda e, w=world, c=character: self._open_condition_dialog(w, c)),
                    ],
                    spacing=d.Space.XS, wrap=True,
                ),
            ],
            spacing=d.Space.XS, tight=True,
        )

    def _send_remote_command(self, world: World, character: Character, kind: str,
                              payload: dict) -> None:
        result = self.backend.send_command(
            world.id, self.device_id, kind, payload,
            target_type="character", target_id=character.id,
        )
        if result.success:
            self._refresh_detail()
        else:
            self._show_error(result.error)

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
        p = d.T()
        amount_field = ft.TextField(
            label="Danno", dense=True, value="0",
            keyboard_type=ft.KeyboardType.NUMBER, **d.field_style(),
        )
        critical_cb = ft.Checkbox(label="Colpo critico", value=False)

        def _confirm(e):
            try:
                amount = int((amount_field.value or "0").strip())
            except ValueError:
                self._show_error("Il valore deve essere un numero intero.")
                return
            if amount <= 0:
                self._show_error("Il danno deve essere positivo.")
                return
            self.page.pop_dialog()
            self._send_remote_command(world, character, perm.CMD_HP_DAMAGE,
                                       {"amount": amount, "is_critical": critical_cb.value})

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Applica danno — {character.name}", ft.Icons.FAVORITE_BORDER,
                                  tone="danger"),
            content=ft.Column([amount_field, critical_cb], tight=True),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Conferma", icon=ft.Icons.CHECK, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.danger, color=p.on_accent)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _open_heal_dialog(self, world: World, character: Character):
        p = d.T()
        amount_field = ft.TextField(
            label="Cura", dense=True, value="0",
            keyboard_type=ft.KeyboardType.NUMBER, **d.field_style(),
        )

        def _confirm(e):
            try:
                amount = int((amount_field.value or "0").strip())
            except ValueError:
                self._show_error("Il valore deve essere un numero intero.")
                return
            if amount <= 0:
                self._show_error("La cura deve essere positiva.")
                return
            self.page.pop_dialog()
            self._send_remote_command(world, character, perm.CMD_HP_HEAL, {"amount": amount})

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Applica cura — {character.name}", ft.Icons.HEALING),
            content=ft.Column([amount_field], tight=True),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Conferma", icon=ft.Icons.CHECK, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.primary, color=p.on_primary)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _open_condition_dialog(self, world: World, character: Character):
        p = d.T()
        conditions = GameDataLoader().get_conditions()
        options = [ft.DropdownOption(key=c["key"], text=c.get("name", c["key"]))
                   for c in conditions]
        condition_dd = ft.Dropdown(label="Condizione", options=options, dense=True,
                                    **d.field_style())
        note_field = ft.TextField(label="Nota (opzionale)", dense=True, **d.field_style())

        def _confirm(e):
            key = condition_dd.value
            if not key:
                self._show_error("Seleziona una condizione.")
                return
            self.page.pop_dialog()
            self._send_remote_command(
                world, character, perm.CMD_CONDITION_APPLY,
                {"condition_key": key, "note": (note_field.value or "").strip()},
            )

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title(f"Imponi condizione — {character.name}", ft.Icons.SICK,
                                  tone="magic"),
            content=ft.Column([condition_dd, note_field], tight=True, spacing=d.Space.SM),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Conferma", icon=ft.Icons.CHECK, on_click=_confirm,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_accent)),
            ]),
        )
        self.page.show_dialog(dlg)

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

        rows: list[ft.Control] = [
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
        ]

        rows.append(ft.Container(height=d.Space.SM))
        rows.append(self._hosting_qr_image(world, host, ip))

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
        dover leggere/digitare a mano quei 4 dati (richiesta di Davide,
        2026-08-06). Contenuto e generazione in `network/qr_join.py`; la
        scansione lato giocatore resta manuale (nessuno scanner in-app,
        vedi il docstring di quel modulo).

        Errore mostrato IN UI, non solo loggato (2026-08-06, corretto dopo
        che Davide non riusciva a vedere il QR e il log su stderr non era
        raggiungibile dall'app impacchettata che stava usando — un log da
        solo non è "diagnosticabile" se nessuno lo legge, il primo
        fallback era di fatto silenzioso quanto quello che voleva evitare).
        Il PIN testuale sopra resta comunque sufficiente da solo per
        entrare anche quando il QR fallisce.
        """
        p = d.T()
        try:
            text = build_join_text(world.name, ip, host.port, world.join_code, host.pin)
            b64 = generate_qr_png_base64(text)
        except Exception as e:
            logger.error("Errore nella generazione del QR d'ingresso: %s", e)
            return ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=16, color=p.danger),
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
        return ft.Row(
            [
                ft.Icon(ft.Icons.PERSON_ADD, size=16, color=p.text_3),
                ft.Text(req.display_name, color=p.text, expand=True),
                ft.IconButton(ft.Icons.CHECK, icon_color=p.primary, tooltip="Approva ingresso",
                              on_click=lambda e, r=req: self._approve_join(world, r.id)),
                ft.IconButton(ft.Icons.CLOSE, icon_color=p.danger, tooltip="Rifiuta ingresso",
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

    def _danger_zone_section(self, world: World) -> ft.Control:
        p = d.T()
        return d.section(
            "Zona pericolosa",
            d.pill(ft.Icons.DELETE_FOREVER, "Elimina mondo", color=p.danger,
                   on_click=lambda e: self._confirm_delete(world)),
            accent=p.danger,
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
                    style=ft.ButtonStyle(bgcolor=p.danger, color=p.text),
                ),
            ]),
        )
        self.page.show_dialog(dlg)

    def _do_delete(self, world: World):
        self.page.pop_dialog()
        result = self.backend.send_command(world.id, self.device_id, perm.CMD_WORLD_DELETE, {})
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
                                  style=ft.ButtonStyle(bgcolor=p.primary, color=p.on_primary)),
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
            if not code:
                self._show_error("Inserisci il codice d'ingresso.")
                return
            result = world_repo.join_world_by_code(
                code, self.device_id, display_field.value.strip() or "Giocatore",
            )
            self.page.pop_dialog()
            if result is None:
                self._show_error("Nessun mondo trovato con questo codice.")
                return
            world, _member = result
            self._open_detail(world)

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Unisciti a un mondo", ft.Icons.MEETING_ROOM),
            content=ft.Column([code_field, display_field], tight=True, spacing=d.Space.MD),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Unisciti", icon=ft.Icons.LOGIN, on_click=_join,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary)),
            ]),
        )
        self.page.show_dialog(dlg)

    def _open_lan_join_dialog(self):
        """
        Ingresso in un mondo ospitato da un altro dispositivo (passo 4,
        §9.3/§9.4) — a differenza di "Unisciti con un codice" (che scrive
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
        status_text = ft.Text("", color=p.danger, size=12)
        retry_btn = ft.TextButton("Controlla di nuovo", icon=ft.Icons.REFRESH,
                                   visible=False)
        pending_state: dict = {"backend": None, "request_id": "", "host_port": ""}

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
                    ft.Icon(ft.Icons.WIFI_TETHERING, size=16, color=p.magic),
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
                self.page.pop_dialog()
                assert result.world is not None
                self._open_detail(result.world)
                return
            if result.pending_request_id and keep_dialog_open_on_pending:
                pending_state["backend"] = result.backend
                pending_state["request_id"] = result.pending_request_id
                status_text.color = p.text_2
                status_text.value = result.error or "In attesa dell'approvazione del master…"
                retry_btn.visible = True
            else:
                status_text.color = p.danger
                status_text.value = result.error or "Ingresso fallito."
            try:
                self.page.update()
            except RuntimeError:
                pass

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
            pending_state["host_port"] = f"{host_addr}:{port}"
            result = world_sync.start_lan_join(
                host_addr, port, (code_field.value or "").strip(),
                (pin_field.value or "").strip(), self.device_id or "",
                (display_field.value or "").strip() or "Giocatore",
            )
            _report(result)

        def _retry(e):
            if pending_state["backend"] is None:
                return
            result = world_sync.finish_pending_join(
                pending_state["backend"], pending_state["request_id"],
                pending_state["host_port"],
            )
            _report(result)

        retry_btn.on_click = _retry

        dlg = ft.AlertDialog(
            modal=True,
            title=d.dialog_title("Unisciti in LAN", ft.Icons.WIFI),
            content=ft.Column(
                [
                    d.muted(
                        "Chiedi al master l'indirizzo IP, la porta (di norma 8765), il "
                        "codice a 6 caratteri del mondo e il PIN mostrato sul suo schermo.",
                    ),
                    d.pill(ft.Icons.WIFI_FIND, "Cerca reti nelle vicinanze", color=p.magic,
                           on_click=_search_nearby),
                    discovery_status,
                    discovery_results,
                    ft.Divider(height=1),
                    host_field, port_field, code_field, pin_field, display_field,
                    status_text, retry_btn,
                ],
                tight=True, spacing=d.Space.SM, scroll=ft.ScrollMode.AUTO,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: self.page.pop_dialog(),
                              style=ft.ButtonStyle(color=p.text_2)),
                ft.ElevatedButton("Entra", icon=ft.Icons.WIFI, on_click=_attempt,
                                  style=ft.ButtonStyle(bgcolor=p.magic, color=p.on_primary)),
            ]),
        )
        self.page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Errori
    # ------------------------------------------------------------------

    def _show_error(self, message: str):
        p = d.T()
        snack = ft.SnackBar(content=ft.Text(message, color=p.text), bgcolor=p.danger)
        self.page.show_dialog(snack)
