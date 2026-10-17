"""Commitments: things the protagonist (or someone he commands) has taken on that no engine system models in detail.

A commitment is an `obligations` row (source_kind 'player_commitment') with its costs, people and time kept as JSON in
`notes`, so the simulation's own reminders, overdue cues and time-skip interruptions already see it. Nothing is invented:
the money, the people and the days are debited where they come from, and the GM narrates within that.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

SOURCE = "player_commitment"


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def record(conn: sqlite3.Connection, actor_id: int, description: str, *, kind: str = "project",
           counterparty_actor_id: int | None = None, target_actor_id: int | None = None, target_location_id: int | None = None,
           due_day: int | None = None, importance: int = 2, details: dict[str, Any] | None = None) -> int:
    """Write a commitment. `details` carries: costs (money, people, days), people (actor ids), conditions, terms, outcome."""
    from .competence import add_obligation
    notes = json.dumps({"kind": kind, **(details or {})}, sort_keys=True, default=str)
    return add_obligation(conn, actor_id, description[:300], counterparty_actor_id=counterparty_actor_id, due_day=due_day,
                          target_actor_id=target_actor_id, target_location_id=target_location_id, importance=importance,
                          source_kind=SOURCE, notes=notes)


def details_of(row) -> dict[str, Any]:
    try:
        return json.loads(row["notes"] or "{}")
    except (TypeError, ValueError):
        return {}


def active(conn: sqlite3.Connection, actor_id: int, limit: int = 12, offset: int = 0) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM obligations WHERE actor_id=? AND source_kind=? AND status='active' ORDER BY COALESCE(due_day,999999),id LIMIT ? OFFSET ?",
                          (actor_id, SOURCE, limit, offset)):
        d = details_of(r)
        out.append({"id": int(r["id"]), "what": r["description"], "kind": d.get("kind"), "due_day": r["due_day"], "terms": d.get("terms"),
                    "people": d.get("people_names"), "costs": d.get("cost_words")})
    return out


def complete(conn: sqlite3.Connection, commitment_id: int, status: str = "fulfilled") -> None:
    conn.execute("UPDATE obligations SET status=?,updated_day=? WHERE id=? AND source_kind=?", (status, _day(conn), commitment_id, SOURCE))
