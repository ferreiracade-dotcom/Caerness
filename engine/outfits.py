"""Outfit membership: who holds which rank, under whom, and at what simulation level (Saint Jude mob minimum)."""
from __future__ import annotations

import json
import random
import sqlite3

from .design import run_seed
from .world_package import outfit_rules, package_for


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def members(conn: sqlite3.Connection, outfit_actor_id: int, rank_key: str | None = None, status: str = "active") -> list[sqlite3.Row]:
    """The outfit's members of one rank (all ranks when None), in actor-id order."""
    sql = "SELECT * FROM outfit_ranks WHERE outfit_actor_id=? AND status=?"
    args: list = [int(outfit_actor_id), status]
    if rank_key is not None:
        sql += " AND rank_key=?"
        args.append(rank_key)
    return conn.execute(sql + " ORDER BY actor_id", args).fetchall()


def superior_of(conn: sqlite3.Connection, actor_id: int) -> int | None:
    r = conn.execute("SELECT superior_actor_id FROM outfit_ranks WHERE actor_id=?", (int(actor_id),)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def capo_of(conn: sqlite3.Connection, actor_id: int) -> int | None:
    """The capo over this man: himself for a capo, otherwise the first capo up his chain of superiors."""
    seen: set[int] = set()
    cur: int | None = int(actor_id)
    while cur is not None and cur not in seen:
        seen.add(cur)
        row = conn.execute("SELECT rank_key,superior_actor_id FROM outfit_ranks WHERE actor_id=?", (cur,)).fetchone()
        if row is None:
            return None
        if row["rank_key"] == "capo":
            return cur
        cur = int(row["superior_actor_id"]) if row["superior_actor_id"] is not None else None
    return None


def boss_of(conn: sqlite3.Connection, outfit_actor_id: int) -> int | None:
    r = conn.execute("SELECT actor_id FROM outfit_ranks WHERE outfit_actor_id=? AND rank_key='boss' AND status='active' "
                     "ORDER BY actor_id LIMIT 1", (int(outfit_actor_id),)).fetchone()
    return int(r[0]) if r else None


def set_level(conn: sqlite3.Connection, actor_id: int, level: int, day: int) -> None:
    """Level 4 people are ACTIVE and reviewed daily, level 3 STRATEGIC and reviewed weekly; both run a quiet routine."""
    cadence_by_level = outfit_rules(package_for(conn)).get("cadence_days", {})
    cadence = int(cadence_by_level[str(int(level))])
    tier = "ACTIVE" if int(level) == 4 else "STRATEGIC"
    conn.execute("UPDATE outfit_ranks SET level=? WHERE actor_id=?", (int(level), int(actor_id)))
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


def add_member(
    conn: sqlite3.Connection, actor_id: int, outfit_actor_id: int, rank_key: str, *, crew_id: int | None,
    superior_actor_id: int | None, level: int, day: int, made_day: int | None = None, standing: float = 0.0,
) -> None:
    """Put a person in an outfit at a rank: the rank row, membership row, personality and simulation level."""
    greed, reliability = give_personality(conn, actor_id, "outfit")
    conn.execute(
        """INSERT INTO outfit_ranks(actor_id,outfit_actor_id,rank_key,crew_id,superior_actor_id,level,joined_day,made_day,standing,greed,reliability)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (int(actor_id), int(outfit_actor_id), rank_key, crew_id, superior_actor_id, int(level), int(day), made_day,
         float(standing), greed, reliability),
    )
    inst = conn.execute("SELECT name FROM actors WHERE id=?", (int(outfit_actor_id),)).fetchone()[0]
    role = f"{rank_key.capitalize()} in the {inst}"
    existing = conn.execute("SELECT id FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND membership_kind='member'",
                            (int(outfit_actor_id), int(actor_id))).fetchone()
    if existing is None:
        conn.execute(
            """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json)
               VALUES (?,?,'member',?,'active',?,?)""",
            (int(outfit_actor_id), int(actor_id), role, int(day), '["outfit opening"]'),
        )
    elif conn.execute("SELECT joined_day FROM institution_memberships WHERE id=?", (existing[0],)).fetchone()[0] is None:
        conn.execute("UPDATE institution_memberships SET joined_day=? WHERE id=?", (int(day), existing[0]))
    set_level(conn, actor_id, level, day)


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
    return any(check(conn, int(actor_id), int(day)) for check in _REASON_CHECKS)


def _open_agenda_due(conn: sqlite3.Connection, actor_id: int, day: int) -> bool:
    return conn.execute("SELECT 1 FROM outfit_agenda WHERE actor_id=? AND status='open' AND due_day<=? LIMIT 1",
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
        """INSERT INTO outfit_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,metadata_json)
           VALUES (?,?,?,?,?,?,?)""",
        (int(actor_id), kind, int(due_day), subject_kind, subject_id, _today(conn), json.dumps(metadata or {}, sort_keys=True)),
    )
    speed_up(conn, actor_id, int(due_day) + 7)
    return int(cur.lastrowid)


def resolve_agenda(conn: sqlite3.Connection, agenda_id: int, day: int) -> None:
    conn.execute("UPDATE outfit_agenda SET status='resolved', resolved_day=? WHERE id=?", (int(day), int(agenda_id)))
