"""Outfit membership: who holds which rank, under whom, and at what simulation level (Saint Jude mob minimum)."""
from __future__ import annotations

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
