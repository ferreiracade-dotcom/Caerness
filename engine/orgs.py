"""Organisation seats: who holds which role in which organisation, under whom, and at what simulation level.

Sphere-free: roles, labels, the head role and the unit-leader role all come from the package's orgs.json (`kind_rules`).
A person may hold seats in several organisations; his simulation level is the highest of his active seats.
"""
from __future__ import annotations

import json
import random
import sqlite3

from .design import run_seed
from .world_package import org_rules, package_for

_DEAD = ("dead", "deceased", "historical")


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def db_key(conn: sqlite3.Connection):
    """Which database this connection is on (a cache key that survives a freed connection's address being reused).
    Kept on the connection object when it can hold an attribute (the engine's own can), so the hot paths do not ask
    SQLite each time; a plain sqlite3 connection asks every time."""
    k = getattr(conn, "_org_db_key", None)
    if k is None:
        k = (id(conn), conn.execute("PRAGMA database_list").fetchone()[2])
        try:
            conn._org_db_key = k
        except AttributeError:
            pass
    return k


_KINDS: dict = {"key": None, "by": {}}


def kind_rules(conn: sqlite3.Connection, org_actor_id: int) -> dict:
    """The orgs.json entry for this organisation's kind, plus its own additions (`rules` are appended); {} when it has none.
    Kept per database once found (the package's data does not change in a run and an organisation's kind does not either)."""
    key = db_key(conn)
    if _KINDS["key"] != key:
        _KINDS.update(key=key, by={})
    hit = _KINDS["by"].get(org_actor_id)
    if hit is not None:
        return hit
    row = conn.execute("SELECT org_kind,package_key FROM org_profiles WHERE org_actor_id=?", (int(org_actor_id),)).fetchone()
    if row is None:
        return {}
    rules = org_rules(package_for(conn))
    kind = (rules.get("kinds") or {}).get(row[0])
    if not kind:
        return {}
    out = dict(kind)
    extra = (rules.get("orgs") or {}).get(row[1]) or {}
    out["rules"] = list(kind.get("rules") or []) + list(extra.get("rules") or [])
    _KINDS["by"][int(org_actor_id)] = out
    return out


def is_living(conn: sqlite3.Connection, actor_id: int) -> bool:
    r = conn.execute(
        """SELECT COALESCE(lp.life_status,'living') AS life_status, lower(COALESCE(a.status,'active')) AS actor_status
           FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""", (int(actor_id),)).fetchone()
    return r is not None and r[0] == "living" and r[1] not in _DEAD


def seat_of(conn: sqlite3.Connection, actor_id: int, org_actor_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM org_seats WHERE actor_id=? AND org_actor_id=?", (int(actor_id), int(org_actor_id))).fetchone()


def seats_of(conn: sqlite3.Connection, actor_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM org_seats WHERE actor_id=? ORDER BY org_actor_id", (int(actor_id),)).fetchall()


def members(conn: sqlite3.Connection, org_actor_id: int, role_key: str | None = None, status: str = "active") -> list[sqlite3.Row]:
    """The organisation's seats in one role (all roles when None), in actor-id order."""
    sql = "SELECT * FROM org_seats WHERE org_actor_id=? AND status=?"
    args: list = [int(org_actor_id), status]
    if role_key is not None:
        sql += " AND role_key=?"
        args.append(role_key)
    return conn.execute(sql + " ORDER BY actor_id", args).fetchall()


def superior_of(conn: sqlite3.Connection, actor_id: int, org_actor_id: int) -> int | None:
    r = seat_of(conn, actor_id, org_actor_id)
    return int(r["superior_actor_id"]) if r is not None and r["superior_actor_id"] is not None else None


def head_of(conn: sqlite3.Connection, org_actor_id: int) -> int | None:
    """The first active holder of the kind's head role."""
    role = kind_rules(conn, org_actor_id).get("head")
    if not role:
        return None
    r = conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' ORDER BY actor_id LIMIT 1",
                     (int(org_actor_id), role)).fetchone()
    return int(r[0]) if r else None


def unit_leader_of(conn: sqlite3.Connection, actor_id: int, org_actor_id: int) -> int | None:
    """The unit leader over this person: himself when he holds the kind's unit-leader role, otherwise the first holder
    of it up his chain of superiors; None when the kind has no unit leaders or the chain never reaches one."""
    role = kind_rules(conn, org_actor_id).get("unit_leader")
    if not role:
        return None
    seen: set[int] = set()
    cur: int | None = int(actor_id)
    while cur is not None and cur not in seen:
        seen.add(cur)
        row = seat_of(conn, cur, org_actor_id)
        if row is None:
            return None
        if row["role_key"] == role:
            return cur
        cur = int(row["superior_actor_id"]) if row["superior_actor_id"] is not None else None
    return None


def stand_in_for(conn: sqlite3.Connection, actor_id: int, org_actor_id: int) -> int | None:
    """Who earns for this person when he cannot: his unit leader if alive, else the head if alive, else no one."""
    for cand in (unit_leader_of(conn, actor_id, org_actor_id), head_of(conn, org_actor_id)):
        if cand is None or cand == int(actor_id):
            continue
        s = seat_of(conn, cand, org_actor_id)
        if s is not None and s["status"] == "active" and is_living(conn, cand):
            return cand
    return None


def set_level(conn: sqlite3.Connection, actor_id: int, level: int, day: int, org_actor_id: int | None = None) -> None:
    """Level 4 people are ACTIVE and reviewed daily, level 3 STRATEGIC and reviewed weekly; both run a quiet routine.
    With `org_actor_id` the level is that seat's; the person's simulation level is the highest of his active seats."""
    if org_actor_id is not None:
        conn.execute("UPDATE org_seats SET level=? WHERE actor_id=? AND org_actor_id=?", (int(level), int(actor_id), int(org_actor_id)))
    best = conn.execute("SELECT MAX(level) FROM org_seats WHERE actor_id=? AND status='active'", (int(actor_id),)).fetchone()[0]
    effective = int(level) if best is None else max(int(best), int(level) if org_actor_id is None else 0)
    cadence_by_level = org_rules(package_for(conn)).get("cadence_days", {})
    cadence = int(cadence_by_level[str(effective)])
    tier = "ACTIVE" if effective == 4 else "STRATEGIC"
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,last_review_day,next_review_day,quiet_routine)
           VALUES (?,?,?,?,?,1)
           ON CONFLICT(actor_id) DO UPDATE SET tier=excluded.tier,cadence_days=excluded.cadence_days,
             last_review_day=excluded.last_review_day,next_review_day=excluded.next_review_day,quiet_routine=1""",
        (int(actor_id), tier, cadence, int(day), int(day) + cadence),
    )


def give_personality(conn: sqlite3.Connection, actor_id: int, stream: str) -> tuple[float, float]:
    """Drives for a member (ambition, loyalty, aggression, risk_tolerance) plus greed and reliability, each
    clamp(gauss(0.5, 0.18)) from the run seed; returns (greed, reliability). Patience and pragmatism keep their values."""
    rng = random.Random(f"{run_seed(conn)}:personality:{stream}:{int(actor_id)}")
    g = lambda: clamp01(rng.gauss(0.5, 0.18))  # noqa: E731
    ambition, loyalty, aggression, caution = g(), g(), g(), g()
    conn.execute(
        """INSERT INTO actor_drives(actor_id,ambition,loyalty,aggression,risk_tolerance) VALUES (?,?,?,?,?)
           ON CONFLICT(actor_id) DO UPDATE SET ambition=excluded.ambition,loyalty=excluded.loyalty,
             aggression=excluded.aggression,risk_tolerance=excluded.risk_tolerance""",
        (int(actor_id), ambition, loyalty, aggression, 1.0 - caution),
    )
    return g(), g()


def seat(
    conn: sqlite3.Connection, actor_id: int, org_actor_id: int, role_key: str, *, unit_id: int | None,
    superior_actor_id: int | None, level: int, day: int, inducted_day: int | None = None, standing: float = 0.0,
    provenance: str = "opening",
) -> int:
    """Put a person in an organisation at a role: the seat row, membership row, personality and simulation level.
    Returns the seat id. A person who already holds a seat elsewhere keeps his personality."""
    other = conn.execute("SELECT greed,reliability FROM org_seats WHERE actor_id=? AND org_actor_id<>? ORDER BY id LIMIT 1",
                         (int(actor_id), int(org_actor_id))).fetchone()
    if other is not None:
        greed, reliability = float(other[0]), float(other[1])
    else:
        greed, reliability = give_personality(conn, actor_id, "outfit")
    seat_id = int(conn.execute(
        """INSERT INTO org_seats(actor_id,org_actor_id,role_key,unit_id,superior_actor_id,level,joined_day,inducted_day,standing,greed,reliability)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (int(actor_id), int(org_actor_id), role_key, unit_id, superior_actor_id, int(level), int(day), inducted_day,
         float(standing), greed, reliability),
    ).lastrowid)
    name = conn.execute("SELECT name FROM actors WHERE id=?", (int(org_actor_id),)).fetchone()[0]
    label = (kind_rules(conn, org_actor_id).get("labels") or {}).get(role_key, role_key)
    role = f"{label} in the {name}"
    existing = conn.execute("SELECT id FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND membership_kind='member'",
                            (int(org_actor_id), int(actor_id))).fetchone()
    if existing is None:
        conn.execute(
            """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json)
               VALUES (?,?,'member',?,'active',?,?)""",
            (int(org_actor_id), int(actor_id), role, int(day), json.dumps([provenance])),
        )
    elif conn.execute("SELECT joined_day FROM institution_memberships WHERE id=?", (existing[0],)).fetchone()[0] is None:
        conn.execute("UPDATE institution_memberships SET joined_day=? WHERE id=?", (int(day), existing[0]))
    set_level(conn, actor_id, level, day, org_actor_id)
    return seat_id


# ---- rhythm: agenda, speed-up and the reasons that end a quiet routine ----
_REASON_CHECKS: list = []


def register_reason_check(fn) -> None:
    """Register a plain function (conn, actor_id, day) -> bool that says a man has reason to choose today.
    Registration is idempotent by function identity, so a module reload does not double up."""
    for i, existing in enumerate(_REASON_CHECKS):
        if existing is fn or (getattr(existing, "__module__", None), getattr(existing, "__qualname__", None)) == (
                getattr(fn, "__module__", None), getattr(fn, "__qualname__", None)):
            _REASON_CHECKS[i] = fn
            return
    _REASON_CHECKS.append(fn)


def has_reason_to_choose(conn: sqlite3.Connection, actor_id: int, day: int) -> bool:
    for check in _REASON_CHECKS:
        if check(conn, int(actor_id), int(day)):
            return True
    return False


def _open_agenda_due(conn: sqlite3.Connection, actor_id: int, day: int) -> bool:
    # a `history` item is a note for the GM, not something he has to act on
    return conn.execute("SELECT 1 FROM org_agenda WHERE actor_id=? AND status='open' AND due_day<=? AND kind<>'history' LIMIT 1",
                        (int(actor_id), int(day))).fetchone() is not None


register_reason_check(_open_agenda_due)


def _today(conn: sqlite3.Connection) -> int:
    r = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
    return int(r[0]) if r else 0


def speed_up(conn: sqlite3.Connection, actor_id: int, until_day: int) -> None:
    """Make a man ACTIVE (reviewed daily) until `until_day`: something is coming for him."""
    today = _today(conn)
    conn.execute(
        """UPDATE simulation_profiles SET forced_tier='ACTIVE',
             forced_until_day=MAX(COALESCE(forced_until_day,0), ?), next_review_day=MIN(next_review_day, ?)
           WHERE actor_id=?""",
        (int(until_day), today + 1, int(actor_id)),
    )


def add_agenda(conn: sqlite3.Connection, actor_id: int, kind: str, due_day: int, *, subject_kind: str | None = None,
               subject_id: int | None = None, metadata: dict | None = None) -> int:
    """An item on a man's list that falls due on `due_day`; he is reviewed daily from now until a week after."""
    cur = conn.execute(
        """INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,metadata_json)
           VALUES (?,?,?,?,?,?,?)""",
        (int(actor_id), kind, int(due_day), subject_kind, subject_id, _today(conn), json.dumps(metadata or {}, sort_keys=True)),
    )
    speed_up(conn, actor_id, int(due_day) + 7)
    return int(cur.lastrowid)


def resolve_agenda(conn: sqlite3.Connection, agenda_id: int, day: int) -> None:
    conn.execute("UPDATE org_agenda SET status='resolved', resolved_day=? WHERE id=?", (int(day), int(agenda_id)))
