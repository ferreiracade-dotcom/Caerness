from __future__ import annotations

import math
import random
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class WorldProcessResult:
    process_id: int
    day: int
    emitted_events: int
    metric_delta: float


def _rng(conn: sqlite3.Connection, process_id: int, day: int) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 97_531 + process_id * 8_191 + day * 31_337)


def next_world_process_due_day(conn: sqlite3.Connection, after_day: int, through_day: int) -> int | None:
    row = conn.execute(
        """SELECT MIN(next_review_day) FROM world_processes
           WHERE active=1 AND next_review_day>? AND next_review_day<=?""",
        (after_day, through_day),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _clamp(value: float, lower: float | None, upper: float | None) -> float:
    if lower is not None:
        value = max(value, lower)
    if upper is not None:
        value = min(value, upper)
    return value


def _record_location_metric(
    conn: sqlite3.Connection,
    location_id: int,
    key: str,
    delta: float,
    day: int,
) -> None:
    row = conn.execute(
        "SELECT id,value,min_value,max_value FROM location_metrics WHERE location_id=? AND key=?",
        (location_id, key),
    ).fetchone()
    if row:
        value = _clamp(
            float(row["value"]) + delta,
            float(row["min_value"]) if row["min_value"] is not None else None,
            float(row["max_value"]) if row["max_value"] is not None else None,
        )
        conn.execute(
            "UPDATE location_metrics SET value=?,updated_day=? WHERE id=?",
            (value, day, int(row["id"])),
        )
    else:
        conn.execute(
            "INSERT INTO location_metrics(location_id,key,value,updated_day) VALUES (?,?,?,?)",
            (location_id, key, delta, day),
        )


def resolve_world_process(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    day: int,
    *,
    event_logger,
) -> WorldProcessResult:
    """Advance one location/regional process without requiring any actor to be present.

    `event_logger` is injected to avoid importing simulation.py here and creating a cycle.
    It must accept a SimEvent-compatible object or keyword bundle through the local shim below.
    """
    elapsed = max(0, day - int(row["last_resolved_day"]))
    if elapsed <= 0:
        conn.execute(
            "UPDATE world_processes SET next_review_day=? WHERE id=?",
            (day + int(row["cadence_days"]), int(row["id"])),
        )
        return WorldProcessResult(int(row["id"]), day, 0, 0.0)

    process_id = int(row["id"])
    rng = _rng(conn, process_id, day)
    base_delta = float(row["rate_per_30_days"]) * elapsed / 30.0
    noise_scale = abs(base_delta) * float(row["volatility"])
    noise = rng.gauss(0.0, noise_scale) if noise_scale else 0.0
    delta = base_delta + noise
    accumulator = float(row["accumulator"]) + abs(delta)

    if row["location_id"] is not None and row["metric_key"]:
        _record_location_metric(conn, int(row["location_id"]), str(row["metric_key"]), delta, day)

    emitted = 0
    threshold = float(row["event_threshold"])
    while accumulator >= threshold:
        accumulator -= threshold
        emitted += 1
        loc_name = "the wider region"
        if row["location_id"] is not None:
            found = conn.execute("SELECT name FROM locations WHERE id=?", (int(row["location_id"]),)).fetchone()
            if found:
                loc_name = str(found[0])
        event_logger(
            day=day,
            event_type=f"world:{row['process_type']}",
            title=f"Regional change: {loc_name}",
            summary=(
                f"The off-screen regional process '{row['name']}' in {loc_name} accumulated enough change "
                "to become world-significant. This occurred independently of player presence."
            ),
            severity=int(row["event_severity"]),
            location_id=int(row["location_id"]) if row["location_id"] is not None else None,
        )

    conn.execute(
        """UPDATE world_processes
           SET accumulator=?,last_resolved_day=?,next_review_day=? WHERE id=?""",
        (accumulator, day, day + int(row["cadence_days"]), process_id),
    )
    return WorldProcessResult(process_id, day, emitted, delta)


def process_due_world_processes(conn: sqlite3.Connection, day: int, *, event_logger) -> list[WorldProcessResult]:
    rows = conn.execute(
        "SELECT * FROM world_processes WHERE active=1 AND next_review_day<=? ORDER BY next_review_day,id",
        (day,),
    ).fetchall()
    return [resolve_world_process(conn, row, day, event_logger=event_logger) for row in rows]


def catch_up_world_processes(conn: sqlite3.Connection, day: int, *, event_logger) -> list[WorldProcessResult]:
    rows = conn.execute(
        "SELECT * FROM world_processes WHERE active=1 AND last_resolved_day<? ORDER BY id",
        (day,),
    ).fetchall()
    return [resolve_world_process(conn, row, day, event_logger=event_logger) for row in rows]


def world_activity_summary(conn: sqlite3.Connection, since_day: int = 0) -> dict:
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id = int(player[0]) if player and player[0] is not None else None

    total_events = int(conn.execute("SELECT COUNT(*) FROM events WHERE day>=?", (since_day,)).fetchone()[0])
    world_events = int(conn.execute("SELECT COUNT(*) FROM events WHERE day>=? AND event_type LIKE 'world:%'", (since_day,)).fetchone()[0])
    background_events = int(conn.execute("SELECT COUNT(*) FROM events WHERE day>=? AND event_type LIKE 'background:%'", (since_day,)).fetchone()[0])
    npc_decisions = int(conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE day>=?" + (" AND actor_id<>?" if player_id is not None else ""),
        (since_day, player_id) if player_id is not None else (since_day,),
    ).fetchone()[0])
    npc_interactions = int(conn.execute(
        """SELECT COUNT(*) FROM interactions WHERE created_day>=?""" + (
            " AND proposer_actor_id<>? AND recipient_actor_id<>?" if player_id is not None else ""
        ),
        (since_day, player_id, player_id) if player_id is not None else (since_day,),
    ).fetchone()[0])
    player_events = 0
    if player_id is not None:
        player_events = int(conn.execute(
            """SELECT COUNT(DISTINCT e.id) FROM events e
               LEFT JOIN event_targets et ON et.event_id=e.id
               WHERE e.day>=? AND (e.source_actor_id=? OR et.actor_id=?)""",
            (since_day, player_id, player_id),
        ).fetchone()[0])

    return {
        "since_day": since_day,
        "total_events": total_events,
        "regional_world_events": world_events,
        "actor_background_events": background_events,
        "npc_decisions": npc_decisions,
        "npc_to_npc_interactions": npc_interactions,
        "events_directly_involving_player": player_events,
        "camera_principle": (
            "Player presence changes what is observed, not what exists. Off-screen actors and regional processes continue independently."
        ),
    }
