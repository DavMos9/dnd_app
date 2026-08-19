"""
Repository per i Mondi condivisi / LAN party — passo 2 di
`dnd_app/docs/multiplayer_design.md` ("Modello mondo, senza rete").

Copre le quattro tabelle introdotte in data/database.py: `worlds`,
`world_members`, `world_events`, `world_change_requests`. Nessuna logica di
permessi qui (vive in `core/world_permissions.py`, che non tocca Flet né il
DB) e nessuna scrittura diretta sullo stato di un personaggio: quella passa
da `core/world_backend.py`, che opera sulle istanze via `character_repo.py`.
Questo modulo è deliberatamente "dumb": CRUD + giornale, stesso principio
già seguito da `loot_repo.py`/`character_repo.py` ("Repository: mai logica
UI, mai trasformazioni di business").

Il giornale (`world_events`) è sia la sincronizzazione sia il registro degli
interventi (§5 del design doc): un'unica scrittura serve entrambi gli
scopi, non due meccanismi paralleli.
"""

from __future__ import annotations

import logging
import secrets
import uuid as _uuid
from datetime import datetime

from data.database import get_connection
from data.models import World, WorldChangeRequest, WorldEvent, WorldMember, WorldRejoinRequest

logger = logging.getLogger(__name__)

#: Alfabeto del codice d'ingresso a 6 caratteri (§9.3): esclude 0/O, 1/I/L —
#: caratteri facilmente confondibili quando qualcuno lo detta o lo digita a
#: mano da uno schermo di un altro dispositivo.
#:
#: Pubblico perché lo riusa anche `world_transfer_repo.
#: generate_transfer_code()` (§11.9), che ha bisogno dello stesso alfabeto con
#: una lunghezza diversa. Importato invece di ricopiato — due copie
#: divergerebbero appena una delle due venisse ritoccata.
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_JOIN_CODE_LENGTH = 6

#: Ruoli ammessi, in scala di privilegio (§4). Il primo è quello dell'owner:
#: unico per mondo, assegnato automaticamente a chi lo crea.
ROLES: tuple[str, ...] = ("owner", "master", "player")


def _s(value) -> str:
    """Converte None in stringa vuota per i campi TEXT NOT NULL."""
    return value if value is not None else ""


def _now() -> str:
    return datetime.now().isoformat()


def generate_join_code() -> str:
    """Codice a 6 caratteri leggibile a voce/mano — §9.3 del design doc."""
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(_JOIN_CODE_LENGTH))


# ---------------------------------------------------------------------------
# Conversione riga -> dataclass
# ---------------------------------------------------------------------------

def _row_to_world(row) -> World:
    d = dict(row)
    return World(
        id=d["id"],
        name=d.get("name", ""),
        description=d.get("description", ""),
        owner_device_id=d.get("owner_device_id", ""),
        join_code=d.get("join_code", ""),
        is_local_host=bool(d.get("is_local_host", 0)),
        last_seen_host=d.get("last_seen_host", ""),
        session_token=d.get("session_token", ""),
        last_synced_seq=d.get("last_synced_seq", 0),
        last_export_seq=d.get("last_export_seq", 0),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def _row_to_member(row) -> WorldMember:
    d = dict(row)
    return WorldMember(
        id=d["id"],
        world_id=d.get("world_id", ""),
        device_id=d.get("device_id", ""),
        display_name=d.get("display_name", ""),
        role=d.get("role", "player"),
        is_connected=bool(d.get("is_connected", 0)),
        last_seen_at=d.get("last_seen_at", ""),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def _row_to_event(row) -> WorldEvent:
    d = dict(row)
    return WorldEvent(
        seq=d.get("seq", 0),
        id=d["id"],
        world_id=d.get("world_id", ""),
        actor_device_id=d.get("actor_device_id", ""),
        actor_name=d.get("actor_name", ""),
        kind=d.get("kind", ""),
        target_type=d.get("target_type", ""),
        target_id=d.get("target_id", ""),
        summary=d.get("summary", ""),
        payload=d.get("payload", "{}"),
        before_state=d.get("before_state", "{}"),
        created_at=d.get("created_at", ""),
    )


def _row_to_change_request(row) -> WorldChangeRequest:
    d = dict(row)
    return WorldChangeRequest(
        id=d["id"],
        world_id=d.get("world_id", ""),
        character_id=d.get("character_id", ""),
        requested_by=d.get("requested_by", ""),
        payload=d.get("payload", "{}"),
        reason=d.get("reason", ""),
        status=d.get("status", "pending"),
        created_at=d.get("created_at", ""),
        resolved_at=d.get("resolved_at", ""),
    )


def _row_to_rejoin_request(row) -> WorldRejoinRequest:
    d = dict(row)
    return WorldRejoinRequest(
        id=d["id"],
        world_id=d.get("world_id", ""),
        character_id=d.get("character_id", ""),
        requested_by=d.get("requested_by", ""),
        requester_name=d.get("requester_name", ""),
        mode=d.get("mode", "frozen"),
        payload=d.get("payload", "{}"),
        reason=d.get("reason", ""),
        status=d.get("status", "pending"),
        created_at=d.get("created_at", ""),
        resolved_at=d.get("resolved_at", ""),
    )


# ---------------------------------------------------------------------------
# Mondi
# ---------------------------------------------------------------------------

def create_world(name: str, owner_device_id: str, owner_display_name: str,
                  description: str = "") -> World | None:
    """
    Crea un mondo ospitato su QUESTO dispositivo (`is_local_host=True`) e
    registra automaticamente il creatore come `owner` tra i membri —
    un mondo senza il suo owner tra i membri non è uno stato valido.

    Scrive anche il primo evento del giornale ("world.created"), così il
    registro è completo fin dalla nascita del mondo, non solo dalle
    modifiche successive.

    Ritorna il mondo creato, o None in caso di errore (loggato). Operazione
    atomica: mondo + membro + evento in un'unica transazione.
    """
    name = _s(name).strip()
    if not name:
        logger.error("create_world: nome mondo vuoto")
        return None
    owner_device_id = _s(owner_device_id).strip()
    if not owner_device_id:
        logger.error("create_world: owner_device_id mancante")
        return None

    world_id = str(_uuid.uuid4())
    join_code = generate_join_code()
    now = _now()
    try:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO worlds (
                    id, name, description, owner_device_id, join_code,
                    is_local_host, last_seen_host, last_synced_seq,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,1,'',0,?,?)
                """,
                (world_id, name, _s(description), owner_device_id, join_code, now, now),
            )
            member_id = str(_uuid.uuid4())
            conn.execute(
                """
                INSERT INTO world_members (
                    id, world_id, device_id, display_name, role,
                    is_connected, last_seen_at, created_at, updated_at
                ) VALUES (?,?,?,?,'owner',0,'',?,?)
                """,
                (member_id, world_id, owner_device_id,
                 _s(owner_display_name) or "Master", now, now),
            )
            _insert_event(
                conn, world_id=world_id, actor_device_id=owner_device_id,
                actor_name=_s(owner_display_name) or "Master",
                kind="world.created", target_type="world", target_id=world_id,
                summary=f"Mondo «{name}» creato.",
            )
            conn.commit()
            row = conn.execute("SELECT * FROM worlds WHERE id=?", (world_id,)).fetchone()
            return _row_to_world(row) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore create_world: {e}")
        return None


def get_world(world_id: str) -> World | None:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute("SELECT * FROM worlds WHERE id=?", (world_id,)).fetchone()
        return _row_to_world(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_world: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_world_by_join_code(join_code: str) -> World | None:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM worlds WHERE join_code=?", (_s(join_code).strip().upper(),)
        ).fetchone()
        return _row_to_world(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_world_by_join_code: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_worlds_for_device(device_id: str, roles: tuple[str, ...] | None = None) -> list[World]:
    """Tutti i mondi in cui questo dispositivo è owner o membro, i più
    recenti per ultimo aggiornamento per primi.

    `roles`: se passato, limita ai
    mondi in cui il ruolo di questo dispositivo è tra quelli elencati — es.
    `(ROLE_OWNER, ROLE_MASTER)` per popolare il selettore "mondo da
    masterare" in `MasterView` (un semplice `player` non deve poter
    "masterare" un mondo in cui è solo un giocatore). Filtro qui e non in
    Python lato chiamante: stessa query, un `IN (...)` in più, evita N
    round-trip su `get_member()` per ogni mondo del dispositivo."""
    conn = None
    try:
        conn = get_connection()
        query = """
            SELECT DISTINCT w.* FROM worlds w
            JOIN world_members m ON m.world_id = w.id
            WHERE m.device_id = ?
        """
        params: list = [_s(device_id)]
        if roles:
            placeholders = ",".join("?" for _ in roles)
            query += f" AND m.role IN ({placeholders})"
            params.extend(roles)
        query += " ORDER BY w.updated_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_world(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_worlds_for_device: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()


def rename_world(world_id: str, new_name: str) -> bool:
    """Aggiornamento diretto (senza passare dal giornale) — usato solo
    internamente da `core.world_backend`, che scrive l'evento a parte dopo
    aver validato i permessi. Non chiamare direttamente dalla UI."""
    new_name = _s(new_name).strip()
    if not new_name:
        return False
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET name=?, updated_at=? WHERE id=?",
            (new_name, _now(), world_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore rename_world: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def regenerate_join_code(world_id: str) -> str | None:
    """Genera un nuovo codice d'ingresso (es. il vecchio è trapelato)."""
    new_code = generate_join_code()
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET join_code=?, updated_at=? WHERE id=?",
            (new_code, _now(), world_id),
        )
        conn.commit()
        return new_code
    except Exception as e:
        logger.error(f"Errore regenerate_join_code: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def mark_world_exported(world_id: str, seq: int) -> bool:
    """Registra `world_events.seq` al momento di un export `.dndworld`
    riuscito — alimenta il promemoria di backup periodico in
    `ui/views/world/world_view.py::_backup_section`. Chiamata SOLO dopo
    che il file è stato scritto con successo su disco/scaricato — un
    export fallito non deve mai spegnere il promemoria."""
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET last_export_seq=?, updated_at=? WHERE id=?",
            (int(seq), _now(), world_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore mark_world_exported: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def count_events_since(world_id: str, since_seq: int) -> int:
    """
    Numero di eventi DI QUESTO mondo con `seq > since_seq` (passo 9E,
    promemoria di backup) — MAI `get_latest_event_seq(world_id) - since_seq`:
    `seq` è l'autoincrement GLOBALE di `world_events` (condiviso da TUTTI i
    mondi, non riparte da 1 per ciascuno), quindi una sottrazione tra "il
    seq più recente di questo mondo" e "il seq registrato all'ultimo export"
    darebbe un numero enorme e sbagliato per un mondo appena creato dopo che
    altri mondi hanno già generato molti eventi (bug reale trovato scrivendo
    il test di questa stessa feature: un mondo mai esportato, `last_export_
    seq=0`, risultava già "oltre soglia" solo perché il contatore globale
    era già avanti). Un `COUNT(*)` filtrato per `world_id` E `seq`
    corrisponde sempre al numero VERO di eventi di QUESTO mondo, qualunque
    sia la posizione del contatore globale."""
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM world_events WHERE world_id=? AND seq>?",
            (world_id, int(since_seq)),
        ).fetchone()
        return int(row["c"]) if row else 0
    except Exception as e:
        logger.error(f"Errore count_events_since: {e}")
        return 0
    finally:
        if conn is not None:
            conn.close()


def get_latest_event_seq(world_id: str) -> int:
    """`seq` dell'evento più recente del giornale di un mondo (0 se non ne
    ha ancora nessuno) — usato per calcolare "quanto è cambiato dall'ultimo
    export" (passo 9E) senza dover scaricare l'intero giornale solo per
    contarne la lunghezza."""
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT MAX(seq) AS m FROM world_events WHERE world_id=?", (world_id,)
        ).fetchone()
        return int(row["m"]) if row and row["m"] is not None else 0
    except Exception as e:
        logger.error(f"Errore get_latest_event_seq: {e}")
        return 0
    finally:
        if conn is not None:
            conn.close()


def delete_world(world_id: str) -> bool:
    """Elimina il mondo — CASCADE rimuove membri, eventi e richieste di
    modifica. NON tocca le istanze di personaggio (passo 3): quando
    esisteranno, la loro `world_id` punterà a un mondo inesistente e andranno
    gestite esplicitamente (non responsabilità di questo passo)."""
    conn = None
    try:
        conn = get_connection()
        conn.execute("DELETE FROM worlds WHERE id=?", (world_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore delete_world: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Membri
# ---------------------------------------------------------------------------

def get_members(world_id: str) -> list[WorldMember]:
    """Membri di un mondo, owner sempre per primo poi per ordine d'ingresso —
    è la gerarchia in cui la UI deve mostrarli (§4)."""
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM world_members WHERE world_id=?
            ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'master' THEN 1 ELSE 2 END,
                     created_at ASC
            """,
            (world_id,),
        ).fetchall()
        return [_row_to_member(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_members: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_member(world_id: str, device_id: str) -> WorldMember | None:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_members WHERE world_id=? AND device_id=?",
            (world_id, device_id),
        ).fetchone()
        return _row_to_member(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_member: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def join_world_by_code(join_code: str, device_id: str, display_name: str) -> tuple[World, WorldMember] | None:
    """
    Ingresso in un mondo tramite codice (§9.3 — nessuna rete qui, funziona
    solo se questo dispositivo condivide già il DB con l'host: web mode
    multi-sessione, oppure LAN via `network/host_server.py`, che chiama
    questa stessa funzione lato host).

    Se questo `device_id` è già membro del mondo, non crea una seconda riga:
    ritorna il membro esistente (comportamento "riprendi" coerente con §6
    per il personaggio — qui applicato all'appartenenza al mondo). Il
    display_name passato viene ignorato in quel caso: cambiarlo è
    un'azione a sé, non un effetto collaterale di un nuovo tentativo di
    ingresso.
    """
    world = get_world_by_join_code(join_code)
    if world is None:
        logger.warning("join_world_by_code: nessun mondo con codice %r", join_code)
        return None

    existing = get_member(world.id, device_id)
    if existing is not None:
        return world, existing

    display_name = _s(display_name).strip() or "Giocatore"
    member_id = str(_uuid.uuid4())
    now = _now()
    try:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO world_members (
                    id, world_id, device_id, display_name, role,
                    is_connected, last_seen_at, created_at, updated_at
                ) VALUES (?,?,?,?,'player',0,'',?,?)
                """,
                (member_id, world.id, device_id, display_name, now, now),
            )
            _insert_event(
                conn, world_id=world.id, actor_device_id=device_id,
                actor_name=display_name, kind="member.joined",
                target_type="member", target_id=member_id,
                summary=f"{display_name} è entrato nel mondo.",
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM world_members WHERE id=?", (member_id,)
            ).fetchone()
            return (world, _row_to_member(row)) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore join_world_by_code: {e}")
        return None


def update_member_role(world_id: str, device_id: str, new_role: str) -> bool:
    """Aggiornamento diretto del ruolo — usato solo da `core.world_backend`
    dopo la validazione dei permessi (solo l'owner può promuovere/degradare,
    §4). Non chiamare direttamente dalla UI."""
    if new_role not in ROLES:
        logger.error(f"update_member_role: ruolo non valido {new_role!r}")
        return False
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE world_members SET role=?, updated_at=? WHERE world_id=? AND device_id=?",
            (new_role, _now(), world_id, device_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore update_member_role: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def remove_member(world_id: str, device_id: str) -> bool:
    """Espulsione (o uscita volontaria) — usato solo da `core.world_backend`
    dopo la validazione dei permessi."""
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "DELETE FROM world_members WHERE world_id=? AND device_id=?",
            (world_id, device_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore remove_member: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def set_member_connected(world_id: str, device_id: str, connected: bool) -> bool:
    """Aggiorna solo lo stato di connessione — usato dal livello di rete
    (`network/host_server.py`) per riflettere chi è online in un mondo LAN."""
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE world_members SET is_connected=?, last_seen_at=?, updated_at=? "
            "WHERE world_id=? AND device_id=?",
            (1 if connected else 0, _now(), _now(), world_id, device_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore set_member_connected: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Giornale eventi
# ---------------------------------------------------------------------------

def _insert_event(conn, *, world_id: str, actor_device_id: str, actor_name: str,
                   kind: str, target_type: str = "", target_id: str = "",
                   summary: str = "", payload: str = "{}",
                   before_state: str = "{}") -> str:
    """Scrive un evento sulla connessione/transazione già aperta dal
    chiamante (usato da create_world/join_world_by_code per restare
    atomici). Ritorna l'id UUID dell'evento creato."""
    event_id = str(_uuid.uuid4())
    conn.execute(
        """
        INSERT INTO world_events (
            id, world_id, actor_device_id, actor_name, kind,
            target_type, target_id, summary, payload, before_state, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (event_id, world_id, _s(actor_device_id), _s(actor_name), _s(kind),
         _s(target_type), _s(target_id), _s(summary), _s(payload),
         _s(before_state), _now()),
    )
    conn.execute("UPDATE worlds SET updated_at=? WHERE id=?", (_now(), world_id))
    return event_id


def append_event(world_id: str, actor_device_id: str, actor_name: str, kind: str,
                  target_type: str = "", target_id: str = "", summary: str = "",
                  payload: str = "{}", before_state: str = "{}") -> WorldEvent | None:
    """
    Scrive un evento nel giornale con la propria connessione/transazione —
    punto d'ingresso pubblico usato da `core.world_backend.LocalBackend`
    dopo aver applicato un comando validato. Ritorna l'evento scritto (con
    `seq` assegnato dall'AUTOINCREMENT) o None in caso di errore.
    """
    try:
        conn = get_connection()
        try:
            event_id = _insert_event(
                conn, world_id=world_id, actor_device_id=actor_device_id,
                actor_name=actor_name, kind=kind, target_type=target_type,
                target_id=target_id, summary=summary, payload=payload,
                before_state=before_state,
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM world_events WHERE id=?", (event_id,)
            ).fetchone()
            return _row_to_event(row) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore append_event: {e}")
        return None


def get_events_since(world_id: str, since_seq: int = 0, limit: int | None = 200) -> list[WorldEvent]:
    """
    Eventi di un mondo con `seq > since_seq`, in ordine crescente — è la
    query di sincronizzazione incrementale (§5: "un client chiede 'cosa è
    successo dopo il #481'"). `limit` protegge da un giornale enorme dopo
    una lunga assenza; il chiamante (`network/host_server.py`) decide se
    questo numero implica "troppo indietro, serve uno snapshot" (§11.2).

    `limit=None` rimuove il limite — usato da `handle_snapshot()` (passo 9),
    che deve portare l'INTERO giornale a un nuovo arrivato: con un limite
    implicito di 200 uno snapshot di un mondo più vecchio risulterebbe
    silenziosamente troncato.
    """
    conn = None
    try:
        conn = get_connection()
        if limit is None:
            rows = conn.execute(
                """
                SELECT * FROM world_events
                WHERE world_id=? AND seq > ?
                ORDER BY seq ASC
                """,
                (world_id, since_seq),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM world_events
                WHERE world_id=? AND seq > ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (world_id, since_seq, max(1, limit)),
            ).fetchall()
        return [_row_to_event(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_events_since: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_latest_seq(world_id: str) -> int:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT MAX(seq) AS s FROM world_events WHERE world_id=?", (world_id,)
        ).fetchone()
        return int(row["s"]) if row and row["s"] is not None else 0
    except Exception as e:
        logger.error(f"Errore get_latest_seq: {e}")
        return 0
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Lato replica (passo 4, LAN) — un dispositivo che si unisce a un mondo
# ospitato altrove tiene una copia locale di `worlds`/`world_members`/
# `world_events` (§4: "sul dispositivo del giocatore sono repliche,
# aggiornate dagli eventi"). Queste funzioni scrivono lo stato COSÌ COM'È
# ricevuto dall'host (via `core.world_sync`) — a differenza delle funzioni
# sopra non generano un nuovo id, non scrivono un evento proprio, non
# validano permessi: quella validazione è già avvenuta sull'host, qui si
# registra solo il risultato. Mai chiamate dalla UI direttamente.
# ---------------------------------------------------------------------------

def save_replica_world(world: World) -> bool:
    """Inserisce o aggiorna la replica locale di un mondo ospitato da un
    altro dispositivo (`is_local_host` sempre `False` qui — un mondo che
    QUESTO dispositivo ospita passa da `create_world()`, mai da qui, così
    §11.5 ("due dispositivi non possono ospitare lo stesso mondo") resta
    garantito per costruzione: nessuna funzione imposta `is_local_host=1`
    tranne `create_world()`). Preserva `created_at` se il mondo esiste già
    localmente (un ri-sincronizzazione non deve invecchiare la riga)."""
    conn = None
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT created_at FROM worlds WHERE id=?", (world.id,)
        ).fetchone()
        created_at = existing["created_at"] if existing else (world.created_at or _now())
        conn.execute(
            """
            INSERT OR REPLACE INTO worlds (
                id, name, description, owner_device_id, join_code,
                is_local_host, last_seen_host, session_token, last_synced_seq,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,0,?,?,?,?,?)
            """,
            (world.id, _s(world.name), _s(world.description), _s(world.owner_device_id),
             _s(world.join_code), _s(world.last_seen_host), _s(world.session_token),
             int(world.last_synced_seq), created_at, _now()),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore save_replica_world: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def save_replica_member(member: WorldMember) -> bool:
    """Inserisce o aggiorna la replica locale di un membro — usata sia per
    seminare l'elenco completo ricevuto da uno snapshot, sia per applicare
    un singolo evento `member.joined`/`member.promote`/`member.demote`."""
    conn = None
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT created_at FROM world_members WHERE id=?", (member.id,)
        ).fetchone()
        created_at = existing["created_at"] if existing else (member.created_at or _now())
        conn.execute(
            """
            INSERT OR REPLACE INTO world_members (
                id, world_id, device_id, display_name, role,
                is_connected, last_seen_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (member.id, member.world_id, member.device_id, _s(member.display_name),
             member.role, int(member.is_connected), _s(member.last_seen_at),
             created_at, _now()),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore save_replica_member: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def remove_replica_member(world_id: str, device_id: str) -> bool:
    """Alias esplicito di `remove_member` per il lato replica: stessa
    operazione SQL, nome distinto per chiarire nel codice del passo 4 che
    qui si sta rispecchiando un evento già avvenuto sull'host
    (`member.kick`, o un membro non più presente nello snapshot), non
    applicando un comando validato localmente."""
    return remove_member(world_id, device_id)


def save_replica_event(event: WorldEvent) -> bool:
    """
    Salva la copia locale di un evento ricevuto dall'host (passo 4) — a
    differenza di `append_event()` NON assegna un nuovo `seq`
    (`AUTOINCREMENT`): riusa `seq`/`id` esattamente come arrivano
    dall'host, così il giornale locale resta identico a quello
    autoritativo invece di avere una propria numerazione indipendente.
    `INSERT OR REPLACE` lo rende idempotente: ririchiedere lo stesso evento
    dopo una riconnessione non lo duplica.
    """
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO world_events (
                seq, id, world_id, actor_device_id, actor_name, kind,
                target_type, target_id, summary, payload, before_state, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (event.seq, event.id, event.world_id, _s(event.actor_device_id),
             _s(event.actor_name), _s(event.kind), _s(event.target_type),
             _s(event.target_id), _s(event.summary), _s(event.payload),
             _s(event.before_state), event.created_at or _now()),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore save_replica_event: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def update_last_synced_seq(world_id: str, seq: int) -> bool:
    """Aggiorna `worlds.last_synced_seq` — il punto da cui ripartire alla
    prossima sincronizzazione (§5: "un client chiede 'cosa è successo dopo
    il #481'"). Significativo solo su una replica (`is_local_host=False`);
    innocuo ma senza effetto pratico se chiamato sull'host."""
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET last_synced_seq=?, updated_at=? WHERE id=?",
            (int(seq), _now(), world_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore update_last_synced_seq: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def update_last_seen_host(world_id: str, host_port: str) -> bool:
    """Aggiorna `worlds.last_seen_host` (§11.7: cambio di rete/IP) — usata
    dopo ogni ingresso o riconnessione riuscita, così il prossimo avvio
    dell'app puo' ritentare lo stesso indirizzo prima di ricorrere alla
    scoperta automatica (passo 5) o a chiederlo di nuovo all'utente."""
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET last_seen_host=?, updated_at=? WHERE id=?",
            (_s(host_port), _now(), world_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore update_last_seen_host: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def clear_session_token(world_id: str) -> bool:
    """
    Azzera `worlds.session_token` su una replica (§11.9).

    Serve quando questo dispositivo scopre di essere stato SOSTITUITO da un
    altro (trasferimento del personaggio): senza azzerare il token,
    `core.world_sync.resolve_backend_for_world` proverebbe a riconnettersi, si
    vedrebbe rifiutare il token, e ritenterebbe da sé un ingresso completo con
    PIN vuoto — arrivando a mostrare "PIN errato" invece della verità. Con il
    token azzerato il backend remoto non viene nemmeno costruito e la replica
    resta una copia locale in sola lettura.
    """
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET session_token='', updated_at=? WHERE id=?",
            (_now(), world_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore clear_session_token: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Richieste di modifica (§7.1) — proposte dal master (CMD_CHANGE_REQUEST_PROPOSE
# in core/world_backend.py) e approvate/rifiutate dal giocatore.
# ---------------------------------------------------------------------------

def create_change_request(world_id: str, character_id: str, requested_by: str,
                           payload: str, reason: str = "") -> WorldChangeRequest | None:
    request_id = str(_uuid.uuid4())
    now = _now()
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO world_change_requests (
                id, world_id, character_id, requested_by, payload, reason,
                status, created_at, resolved_at
            ) VALUES (?,?,?,?,?,?,'pending',?,'')
            """,
            (request_id, world_id, character_id, _s(requested_by), _s(payload),
             _s(reason), now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM world_change_requests WHERE id=?", (request_id,)
        ).fetchone()
        return _row_to_change_request(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_change_request: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_change_request(request_id: str) -> WorldChangeRequest | None:
    """Una singola richiesta per id — usata dall'handler di
    `change_request.respond` (Multiplayer passo 6) per verificare che
    esista, sia ancora `pending` e riguardi davvero il personaggio di chi
    sta rispondendo, prima di risolverla."""
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_change_requests WHERE id=?", (request_id,)
        ).fetchone()
        return _row_to_change_request(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_change_request: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_pending_change_requests(world_id: str) -> list[WorldChangeRequest]:
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM world_change_requests WHERE world_id=? AND status='pending' "
            "ORDER BY created_at ASC",
            (world_id,),
        ).fetchall()
        return [_row_to_change_request(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_pending_change_requests: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()


def save_replica_change_request(request: WorldChangeRequest) -> bool:
    """
    Replica locale di una richiesta di modifica (§7.1, Multiplayer passo 6)
    — stesso principio delle altre `save_replica_*`: scrive lo stato COSÌ
    COM'È ricevuto dall'host (via `core.world_sync`), riusando l'id
    originale invece di generarne uno nuovo, `INSERT OR REPLACE` per
    restare idempotente a una riconnessione. La creazione/risoluzione
    VALIDATA resta sempre `create_change_request()`/`resolve_change_request()`
    sull'host — qui si specchia solo il risultato.
    """
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO world_change_requests (
                id, world_id, character_id, requested_by, payload, reason,
                status, created_at, resolved_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (request.id, request.world_id, request.character_id,
             _s(request.requested_by), _s(request.payload), _s(request.reason),
             request.status, request.created_at or _now(), _s(request.resolved_at)),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore save_replica_change_request: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def resolve_change_request(request_id: str, status: str) -> bool:
    if status not in ("accepted", "rejected", "expired"):
        logger.error(f"resolve_change_request: stato non valido {status!r}")
        return False
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE world_change_requests SET status=?, resolved_at=? WHERE id=?",
            (status, _now(), request_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore resolve_change_request: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Richieste di rientro — un personaggio archiviato (espulso, o rimosso dal
# master via `CMD_CHARACTER_INSTANCE_REMOVE`) che il giocatore vuole far
# tornare attivo nel mondo. Verso opposto delle richieste di modifica sopra:
# qui propone il giocatore, risponde il master (`core/world_backend.py::
# _handle_character_rejoin_request`/`_handle_character_rejoin_respond`).
# ---------------------------------------------------------------------------

def create_rejoin_request(world_id: str, character_id: str, requested_by: str,
                           requester_name: str, mode: str, payload: str,
                           reason: str = "") -> WorldRejoinRequest | None:
    request_id = str(_uuid.uuid4())
    now = _now()
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO world_rejoin_requests (
                id, world_id, character_id, requested_by, requester_name,
                mode, payload, reason, status, created_at, resolved_at
            ) VALUES (?,?,?,?,?,?,?,?,'pending',?,'')
            """,
            (request_id, world_id, character_id, _s(requested_by),
             _s(requester_name), _s(mode) or "frozen", _s(payload) or "{}",
             _s(reason), now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM world_rejoin_requests WHERE id=?", (request_id,)
        ).fetchone()
        return _row_to_rejoin_request(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_rejoin_request: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_rejoin_request(request_id: str) -> WorldRejoinRequest | None:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_rejoin_requests WHERE id=?", (request_id,)
        ).fetchone()
        return _row_to_rejoin_request(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_rejoin_request: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_pending_rejoin_requests(world_id: str) -> list[WorldRejoinRequest]:
    """Non filtrata per proprietario — a differenza di
    `get_pending_change_requests` (dove chi risponde è sempre il
    proprietario del personaggio), qui chi risponde è il master: deve
    vedere le richieste su QUALSIASI personaggio del mondo."""
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM world_rejoin_requests WHERE world_id=? AND status='pending' "
            "ORDER BY created_at ASC",
            (world_id,),
        ).fetchall()
        return [_row_to_rejoin_request(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_pending_rejoin_requests: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_pending_rejoin_request_for_character(character_id: str) -> WorldRejoinRequest | None:
    """Guardia anti-duplicati: al più una richiesta `pending` per personaggio
    alla volta — usata sia dall'handler (`_handle_character_rejoin_request`)
    sia dalla UI (per mostrare "richiesta già inviata" invece di riaprire
    il dialogo)."""
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_rejoin_requests WHERE character_id=? AND status='pending' "
            "ORDER BY created_at DESC LIMIT 1",
            (character_id,),
        ).fetchone()
        return _row_to_rejoin_request(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_pending_rejoin_request_for_character: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def save_replica_rejoin_request(request: WorldRejoinRequest) -> bool:
    """Replica locale di una richiesta di rientro — stesso principio di
    `save_replica_change_request`: scrive lo stato così com'è ricevuto
    dall'host, `INSERT OR REPLACE` per restare idempotente a una
    riconnessione."""
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO world_rejoin_requests (
                id, world_id, character_id, requested_by, requester_name,
                mode, payload, reason, status, created_at, resolved_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (request.id, request.world_id, request.character_id,
             _s(request.requested_by), _s(request.requester_name),
             _s(request.mode) or "frozen", _s(request.payload) or "{}",
             _s(request.reason), request.status, request.created_at or _now(),
             _s(request.resolved_at)),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore save_replica_rejoin_request: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def resolve_rejoin_request(request_id: str, status: str) -> bool:
    if status not in ("accepted", "rejected", "expired"):
        logger.error(f"resolve_rejoin_request: stato non valido {status!r}")
        return False
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE world_rejoin_requests SET status=?, resolved_at=? WHERE id=?",
            (status, _now(), request_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore resolve_rejoin_request: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()
