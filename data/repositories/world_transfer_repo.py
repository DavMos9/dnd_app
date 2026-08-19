"""
Trasferimento del personaggio su un ALTRO dispositivo — codice monouso e
transazione di riassegnazione.

Design completo in `dnd_app/docs/multiplayer_design.md` §11.9. In breve:
l'identità di un giocatore è il `device_id` (UUID per installazione,
`ui/device_identity.py`), e le sue istanze di personaggio sono legate a quello
via `characters.owner_device_id`. Cambiare dispositivo — o reinstallare l'app,
che azzera `app_settings` e con esso il `device_id` — significa presentarsi
all'host come uno sconosciuto senza personaggi. Questo modulo copre le due metà
della soluzione:

  1. **il codice** (`issue_transfer` e compagnia): 8 caratteri, monouso, a
     scadenza, emesso dal membro stesso oppure da un master/owner quando il
     vecchio dispositivo è perso o rotto;
  2. **la riassegnazione** (`rebind_device`): una sola transazione che sposta
     appartenenza, istanze di personaggio, visibilità delle note e richieste di
     rientro dal vecchio `device_id` al nuovo.

Vive SOLO sul dispositivo che ospita il mondo: `world_device_transfers` è stato
dell'host come il PIN e i token, non viaggia in un `.dndworld` e non viene
replicato ai client.

⚠️ Ogni funzione che apre `get_connection()` la chiude in un `finally`:
`test_connessioni_db.py` è una guardia AST che fa fallire l'intera batteria
altrimenti (vedi il suo docstring per il bug "database is locked" da cui nasce).
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid as _uuid
from datetime import datetime, timedelta

from data.database import get_connection
from data.models import WorldDeviceTransfer
from data.repositories.world_repo import JOIN_CODE_ALPHABET

logger = logging.getLogger(__name__)

#: Lunghezza del codice di trasferimento. Più lungo del `join_code` (6) perché
#: ha un potere diverso: il join_code identifica un mondo ed è pensato per
#: essere detto a voce al tavolo, questo autorizza a subentrare nell'identità di
#: un membro. 31**8 ≈ 8,5·10¹¹ combinazioni, ed è comunque monouso, a scadenza,
#: legato a un solo membro e soggetto al rate limit di `/join`.
TRANSFER_CODE_LENGTH = 8

#: Validità del codice: una settimana. Copre "ci vediamo alla prossima serata"
#: senza diventare una chiave permanente scritta su un foglietto. Il master può
#: sempre revocarlo prima (`revoke_transfer`) o emetterne uno nuovo, cosa che
#: invalida automaticamente il precedente.
TRANSFER_CODE_TTL_S = 7 * 24 * 3600

STATUS_PENDING = "pending"
STATUS_REDEEMED = "redeemed"
STATUS_REVOKED = "revoked"
STATUS_EXPIRED = "expired"


def _now() -> str:
    return datetime.now().isoformat()


def _row_to_transfer(row) -> WorldDeviceTransfer:
    d = dict(row)
    return WorldDeviceTransfer(
        id=d["id"],
        world_id=d.get("world_id", ""),
        code=d.get("code", ""),
        member_device_id=d.get("member_device_id", ""),
        member_display_name=d.get("member_display_name", ""),
        issued_by_device_id=d.get("issued_by_device_id", ""),
        status=d.get("status", STATUS_PENDING),
        new_device_id=d.get("new_device_id", ""),
        expires_at=d.get("expires_at", ""),
        created_at=d.get("created_at", ""),
        resolved_at=d.get("resolved_at", ""),
    )


def generate_transfer_code() -> str:
    """
    Codice a 8 caratteri dallo stesso alfabeto del codice d'ingresso
    (`world_repo.JOIN_CODE_ALPHABET`: nessuno fra 0/O e 1/I/L, che si
    confondono quando qualcuno li detta o li ricopia da un altro schermo).

    L'alfabeto è importato, non riscritto: due copie divergerebbero appena una
    delle due venisse ritoccata.
    """
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(TRANSFER_CODE_LENGTH))


def _is_expired(transfer: WorldDeviceTransfer, now: datetime | None = None) -> bool:
    """
    True se il codice è scaduto. Un `expires_at` vuoto o illeggibile è
    considerato SCADUTO (fail-closed): un codice senza scadenza valida non deve
    diventare per sbaglio un codice eterno.
    """
    if not transfer.expires_at:
        return True
    try:
        deadline = datetime.fromisoformat(transfer.expires_at)
    except ValueError:
        logger.warning(
            "world_transfer_repo: expires_at illeggibile (%r) sul codice %s — "
            "trattato come scaduto", transfer.expires_at, transfer.id,
        )
        return True
    return (now or datetime.now()) >= deadline


# ---------------------------------------------------------------------------
# Emissione, revoca, scadenza
# ---------------------------------------------------------------------------

def issue_transfer(world_id: str, member_device_id: str, member_display_name: str,
                    issued_by_device_id: str) -> WorldDeviceTransfer | None:
    """
    Emette un codice per sostituire il dispositivo di un membro.

    Revoca nella STESSA transazione ogni codice `pending` preesistente per lo
    stesso `(world_id, member_device_id)`: un membro ha sempre al massimo un
    codice valido, così un codice vecchio letto ad alta voce o rimasto in una
    chat non vale più nulla appena se ne genera un altro.

    Nessun controllo di permessi qui (è un repository): li applica
    `core/world_backend.py::_handle_device_transfer_issue`.
    """
    world_id = (world_id or "").strip()
    member_device_id = (member_device_id or "").strip()
    if not world_id or not member_device_id:
        logger.error("issue_transfer: world_id o member_device_id mancante")
        return None

    now = datetime.now()
    transfer = WorldDeviceTransfer(
        id=str(_uuid.uuid4()),
        world_id=world_id,
        code=generate_transfer_code(),
        member_device_id=member_device_id,
        member_display_name=(member_display_name or "").strip(),
        issued_by_device_id=(issued_by_device_id or "").strip(),
        status=STATUS_PENDING,
        expires_at=(now + timedelta(seconds=TRANSFER_CODE_TTL_S)).isoformat(),
        created_at=now.isoformat(),
    )

    conn = None
    try:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE world_device_transfers SET status=?, resolved_at=? "
                "WHERE world_id=? AND member_device_id=? AND status=?",
                (STATUS_REVOKED, transfer.created_at, world_id,
                 member_device_id, STATUS_PENDING),
            )
            conn.execute(
                """
                INSERT INTO world_device_transfers (
                    id, world_id, code, member_device_id, member_display_name,
                    issued_by_device_id, status, new_device_id, expires_at,
                    created_at, resolved_at
                ) VALUES (?,?,?,?,?,?,?,'',?,?,'')
                """,
                (transfer.id, transfer.world_id, transfer.code,
                 transfer.member_device_id, transfer.member_display_name,
                 transfer.issued_by_device_id, transfer.status,
                 transfer.expires_at, transfer.created_at),
            )
            conn.commit()
            return transfer
        except Exception:
            conn.rollback()
            raise
    except Exception as e:
        logger.error(f"Errore issue_transfer: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_transfer(transfer_id: str) -> WorldDeviceTransfer | None:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_device_transfers WHERE id=?", (transfer_id,)
        ).fetchone()
        return _row_to_transfer(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_transfer: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_pending_transfer_by_code(world_id: str, code: str) -> WorldDeviceTransfer | None:
    """
    Il codice `pending` e NON scaduto di questo mondo, se esiste.

    Restituisce `None` indistintamente per "non esiste", "già usato",
    "revocato" e "scaduto": chi chiama (`handle_join`) mostra un unico messaggio
    generico, per non dire a chi prova codici a caso quale dei quattro casi ha
    incontrato — lo stesso principio già applicato al PIN.
    """
    code = (code or "").strip().upper()
    if not code:
        return None
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_device_transfers WHERE world_id=? AND code=? AND status=?",
            (world_id, code, STATUS_PENDING),
        ).fetchone()
        if row is None:
            return None
        transfer = _row_to_transfer(row)
        return None if _is_expired(transfer) else transfer
    except Exception as e:
        logger.error(f"Errore get_pending_transfer_by_code: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_pending_transfer_for_member(world_id: str,
                                     member_device_id: str) -> WorldDeviceTransfer | None:
    """Il codice valido attualmente in circolazione per un membro (per mostrarlo
    di nuovo al master senza generarne un altro)."""
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_device_transfers "
            "WHERE world_id=? AND member_device_id=? AND status=? "
            "ORDER BY created_at DESC LIMIT 1",
            (world_id, member_device_id, STATUS_PENDING),
        ).fetchone()
        if row is None:
            return None
        transfer = _row_to_transfer(row)
        return None if _is_expired(transfer) else transfer
    except Exception as e:
        logger.error(f"Errore get_pending_transfer_for_member: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def revoke_transfer(transfer_id: str) -> bool:
    """Annulla un codice non ancora usato. Idempotente: revocare un codice già
    risolto non fa nulla e non è un errore."""
    conn = None
    try:
        conn = get_connection()
        cur = conn.execute(
            "UPDATE world_device_transfers SET status=?, resolved_at=? "
            "WHERE id=? AND status=?",
            (STATUS_REVOKED, _now(), transfer_id, STATUS_PENDING),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Errore revoke_transfer: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def expire_stale_transfers(world_id: str) -> int:
    """
    Marca `expired` i codici `pending` la cui scadenza è passata, e restituisce
    quanti ne ha marcati.

    È solo igiene dei dati: `get_pending_transfer_by_code` scarta comunque i
    codici scaduti da sé (non si fa affidamento su questa chiamata per la
    sicurezza), ma senza di essa la lista dei codici in circolazione mostrata al
    master resterebbe piena di voci morte.
    """
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM world_device_transfers WHERE world_id=? AND status=?",
            (world_id, STATUS_PENDING),
        ).fetchall()
        stale = [r["id"] for r in rows if _is_expired(_row_to_transfer(r))]
        if not stale:
            return 0
        now = _now()
        conn.executemany(
            "UPDATE world_device_transfers SET status=?, resolved_at=? WHERE id=?",
            [(STATUS_EXPIRED, now, tid) for tid in stale],
        )
        conn.commit()
        return len(stale)
    except Exception as e:
        logger.error(f"Errore expire_stale_transfers: {e}")
        return 0
    finally:
        if conn is not None:
            conn.close()


def was_transferred_away(world_id: str, device_id: str) -> WorldDeviceTransfer | None:
    """
    Il codice `redeemed` con cui QUESTO dispositivo è stato sostituito, se c'è.

    Serve a `WorldHostServer.handle_join` per spiegare al vecchio dispositivo
    perché non è più membro. Senza questa riga il vecchio dispositivo cade nel
    percorso "non è membro" → PIN richiesto → `resolve_backend_for_world` ritenta
    in silenzio con PIN vuoto → **"PIN errato."**, un messaggio che manda a
    cercare il problema nel posto sbagliato. È il motivo per cui le righe
    `redeemed` non vengono mai cancellate.
    """
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM world_device_transfers "
            "WHERE world_id=? AND member_device_id=? AND status=? "
            "ORDER BY resolved_at DESC LIMIT 1",
            (world_id, device_id, STATUS_REDEEMED),
        ).fetchone()
        return _row_to_transfer(row) if row else None
    except Exception as e:
        logger.error(f"Errore was_transferred_away: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# La riassegnazione
# ---------------------------------------------------------------------------
#
# Tutte le colonne del progetto che contengono un device_id, enumerate con un
# grep su data/database.py e data/models.py — e per ognuna la decisione, incluse
# quelle che si lasciano DELIBERATAMENTE ferme:
#
#   world_members.device_id                     → SPOSTATA
#   characters.owner_device_id                  → SPOSTATA (anche archiviate)
#   master_campaign_notes.visible_to_device_ids → RIMAPPATA (lista JSON)
#   world_rejoin_requests.requested_by          → SPOSTATA (solo le pending)
#   world_device_transfers                      → marcato redeemed
#
#   worlds.owner_device_id            → MAI. Per l'owner la via è l'export/import
#                                       `.dndworld` (§6.3/§11.4), che rende già
#                                       owner chi importa; `_handle_device_
#                                       transfer_issue` rifiuta i codici per
#                                       l'owner proprio per questo.
#   world_events.actor_device_id      → MAI. Il giornale è un registro storico
#                                       (§5): la storia non si riscrive, si
#                                       aggiunge un evento nuovo.
#   loot_stash_entries.added_by_device_id → MAI. Verificato: scritta da
#                                       loot_repo.py, mai letta per autorizzare
#                                       o mostrare qualcosa. È pura provenienza
#                                       ("chi ha messo questo qui"), e riscriverla
#                                       falsificherebbe un dato storico esatto.
#   world_change_requests.requested_by → MAI. È il device_id del MASTER che
#                                       propone (data/models.py), non del
#                                       giocatore che risponde.
#   app_settings (device_id, display_name) → MAI. Per installazione, per
#                                       progetto (§14.2).
#
# game_maps / master_encounters / master_encounter_members non hanno colonne
# device: la visibilità lì è un booleano.


def _remap_note_visibility(conn, world_id: str, old_device_id: str,
                            new_device_id: str) -> int:
    """
    Sostituisce il vecchio device_id col nuovo nelle liste JSON
    `master_campaign_notes.visible_to_device_ids`, e restituisce quante note ha
    toccato.

    La colonna è una lista JSON, quindi non aggiornabile con un UPDATE mirato:
    si legge, si modifica in Python e si riscrive — la stessa gestione già usata
    da `master_repo.get_notes_visible_to` per leggerla. Senza questo passaggio il
    giocatore perderebbe in SILENZIO l'accesso a ogni nota condivisa
    specificamente con lui: nessun errore, la nota semplicemente non compare più.

    Ristretto a `visibility='selected'` e al mondo in questione: le note di altri
    mondi che nominano lo stesso device_id non vanno toccate (quel dispositivo
    resta membro là).
    """
    rows = conn.execute(
        "SELECT id, visible_to_device_ids FROM master_campaign_notes "
        "WHERE world_id=? AND visibility='selected'",
        (world_id,),
    ).fetchall()

    updates: list[tuple[str, str]] = []
    for row in rows:
        raw = row["visible_to_device_ids"] or "[]"
        try:
            ids = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Stessa tolleranza di get_notes_visible_to: un valore illeggibile
            # equivale a "nessuno", e non è questa la sede per ripararlo.
            continue
        if not isinstance(ids, list) or old_device_id not in ids:
            continue
        # Sostituzione in posizione, preservando l'ordine e senza duplicare il
        # nuovo id nel caso (improbabile) in cui fosse già presente.
        remapped: list = []
        for entry in ids:
            candidate = new_device_id if entry == old_device_id else entry
            if candidate not in remapped:
                remapped.append(candidate)
        updates.append((json.dumps(remapped), row["id"]))

    if updates:
        conn.executemany(
            "UPDATE master_campaign_notes SET visible_to_device_ids=? WHERE id=?",
            updates,
        )
    return len(updates)


def rebind_device(world_id: str, old_device_id: str,
                   new_device_id: str) -> dict | None:
    """
    Sposta l'appartenenza e tutto ciò che le appartiene dal vecchio dispositivo
    al nuovo, in UNA transazione.

    Restituisce un riepilogo (`{"characters": n, "notes_remapped": n,
    "rejoin_requests": n, "display_name": str, "role": str, "member_id": str}`)
    da usare nel payload dell'evento di giornale, oppure `None` se qualcosa è
    andato storto — e in quel caso **nulla** è stato scritto.

    La riga `world_members` mantiene lo STESSO `id`: `world_repo.save_replica_member`
    fa `INSERT OR REPLACE` per `id`, quindi le repliche aggiornano il membro in
    posizione invece di crearne un secondo, e non si scontrano con
    `UNIQUE (world_id, device_id)`. Ruolo e nome visualizzato sono preservati:
    cambiare dispositivo non è una promozione né un rinomino.

    `is_connected` va a 0: il nuovo dispositivo lo alzerà quando si collega
    davvero, e nel frattempo il vecchio non è più collegato per definizione.

    NON appende l'evento di giornale: lo fa il chiamante
    (`WorldHostServer._approve_transfer`), che conosce anche il nome dell'attore
    e deve emetterlo con `world_repo.append_event` come qualunque altro evento.
    """
    old_device_id = (old_device_id or "").strip()
    new_device_id = (new_device_id or "").strip()
    if not world_id or not old_device_id or not new_device_id:
        logger.error("rebind_device: parametri mancanti")
        return None
    if old_device_id == new_device_id:
        logger.error("rebind_device: vecchio e nuovo dispositivo coincidono")
        return None

    conn = None
    try:
        conn = get_connection()
        try:
            member = conn.execute(
                "SELECT * FROM world_members WHERE world_id=? AND device_id=?",
                (world_id, old_device_id),
            ).fetchone()
            if member is None:
                logger.error(
                    "rebind_device: nessun membro %s nel mondo %s",
                    old_device_id, world_id,
                )
                conn.rollback()
                return None

            # Controllato anche da handle_join prima di accodare la richiesta,
            # ripetuto qui perché fra l'approvazione e questa transazione può
            # essere passato tempo (e perché UNIQUE farebbe fallire l'UPDATE con
            # un errore molto meno chiaro di questo log).
            clash = conn.execute(
                "SELECT 1 FROM world_members WHERE world_id=? AND device_id=?",
                (world_id, new_device_id),
            ).fetchone()
            if clash is not None:
                logger.error(
                    "rebind_device: il dispositivo %s è già membro del mondo %s",
                    new_device_id, world_id,
                )
                conn.rollback()
                return None

            now = _now()

            conn.execute(
                "UPDATE world_members SET device_id=?, is_connected=0, updated_at=? "
                "WHERE id=?",
                (new_device_id, now, member["id"]),
            )

            # Nessun filtro su `world_instance_archived`: anche le istanze
            # archiviate devono seguire il proprietario, altrimenti il nuovo
            # dispositivo non potrebbe mai chiedere il loro rientro (§6, flusso
            # `character.rejoin.request`) e resterebbero orfane sull'host.
            cur = conn.execute(
                "UPDATE characters SET owner_device_id=?, updated_at=? "
                "WHERE world_id=? AND owner_device_id=?",
                (new_device_id, now, world_id, old_device_id),
            )
            n_characters = cur.rowcount

            n_notes = _remap_note_visibility(conn, world_id, old_device_id, new_device_id)

            # Le richieste di rientro pendenti: `handle_snapshot` le filtra per
            # `requested_by == device_id`, quindi una richiesta lasciata sul
            # vecchio id diventerebbe invisibile per sempre — il master la
            # vedrebbe ancora, il giocatore no. Solo le `pending`: quelle già
            # risolte sono storia, come il giornale.
            cur = conn.execute(
                "UPDATE world_rejoin_requests SET requested_by=? "
                "WHERE world_id=? AND requested_by=? AND status='pending'",
                (new_device_id, world_id, old_device_id),
            )
            n_rejoin = cur.rowcount

            conn.commit()
            return {
                "member_id": member["id"],
                "display_name": member["display_name"] or "",
                "role": member["role"] or "player",
                "characters": n_characters,
                "notes_remapped": n_notes,
                "rejoin_requests": n_rejoin,
            }
        except Exception:
            conn.rollback()
            raise
    except Exception as e:
        logger.error(f"Errore rebind_device: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def mark_redeemed(transfer_id: str, new_device_id: str) -> bool:
    """
    Chiude il codice come usato. Il `WHERE status='pending'` rende l'operazione
    monouso a livello di DB, non solo di controlli applicativi: due riscatti
    dello stesso codice non possono entrambi riuscire.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.execute(
            "UPDATE world_device_transfers SET status=?, new_device_id=?, resolved_at=? "
            "WHERE id=? AND status=?",
            (STATUS_REDEEMED, new_device_id, _now(), transfer_id, STATUS_PENDING),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Errore mark_redeemed: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()
