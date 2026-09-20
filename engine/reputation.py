from __future__ import annotations

import json
import sqlite3
from typing import Iterable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def value(conn: sqlite3.Connection, subject_kind: str, subject_id: int, domains: Iterable[str], *, default: float = 35.0) -> float:
    domains = list(dict.fromkeys(str(d) for d in domains if d))
    if not domains:
        return float(default)
    marks = ','.join('?' for _ in domains)
    rows = conn.execute(
        f"SELECT domain,value FROM social_reputation WHERE subject_kind=? AND subject_id=? AND domain IN ({marks})",
        (subject_kind, int(subject_id), *domains),
    ).fetchall()
    if not rows:
        return float(default)
    # Domain-specific reputation is strongest; adjacent public domains support discoverability but
    # do not turn unrelated fame into expertise.
    weights = {domains[0]: 1.0}
    for i, d in enumerate(domains[1:], start=1):
        weights[d] = max(0.35, 0.70 - i * 0.08)
    total = sum(float(r['value']) * weights.get(str(r['domain']), .45) for r in rows)
    denom = sum(weights.get(str(r['domain']), .45) for r in rows)
    return max(0.0, min(100.0, total / max(.001, denom)))


def adjust(conn: sqlite3.Connection, subject_kind: str, subject_id: int, domain: str, delta: float, *, day: int | None = None, metadata: dict | None = None) -> float:
    day = _day(conn) if day is None else int(day)
    row = conn.execute(
        "SELECT value,metadata_json FROM social_reputation WHERE subject_kind=? AND subject_id=? AND domain=?",
        (subject_kind, int(subject_id), str(domain)),
    ).fetchone()
    before = float(row['value']) if row else 50.0
    new = max(0.0, min(100.0, before + float(delta)))
    old_meta = {}
    if row and row['metadata_json']:
        try: old_meta = json.loads(row['metadata_json'])
        except Exception: old_meta = {}
    old_meta.update(metadata or {})
    conn.execute(
        """INSERT INTO social_reputation(subject_kind,subject_id,domain,value,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(subject_kind,subject_id,domain) DO UPDATE SET
             value=excluded.value,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
        (subject_kind, int(subject_id), str(domain), new, day, json.dumps(old_meta, sort_keys=True)),
    )
    return new


def martial_instruction_public(conn: sqlite3.Connection, actor_id: int) -> float:
    return value(
        conn, 'actor', int(actor_id),
        ['martial_instruction', 'martial_public', 'tournament', 'martial_spectacle'],
        default=32.0,
    )
