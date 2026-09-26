from __future__ import annotations

import sqlite3
from typing import Any

# `relationships.actor_a_id` is the source/observer; `actor_b_id` is the target.
# Structural ties (kinship, spouse, office, membership, teaching, contracts) live in their own owners.
DIRECTIONAL_FIELDS = (
    "stance", "familiarity", "trust", "affection", "respect", "fear",
    "loyalty", "resentment", "obligation", "professional_confidence",
)

def _clamp100(v: float) -> float:
    return max(-100.0, min(100.0, float(v)))

def _clamp_familiarity(v: float) -> float:
    return max(0.0, min(100.0, float(v)))

def relationship_view(conn: sqlite3.Connection, source_actor_id: int, target_actor_id: int) -> dict[str, float]:
    row = conn.execute(
        "SELECT * FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
        (int(source_actor_id), int(target_actor_id)),
    ).fetchone()
    if not row:
        return {k: 0.0 for k in DIRECTIONAL_FIELDS}
    return {k: float(row[k]) for k in DIRECTIONAL_FIELDS}

def ensure_relationship(
    conn: sqlite3.Connection, source_actor_id: int, target_actor_id: int, day: int, *,
    started_day: int | None = None, **values: float
) -> int:
    source_actor_id, target_actor_id = int(source_actor_id), int(target_actor_id)
    if source_actor_id == target_actor_id:
        raise ValueError("a directional relationship cannot target self")
    row = conn.execute(
        "SELECT id FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
        (source_actor_id, target_actor_id),
    ).fetchone()
    if row:
        return int(row[0])
    vals = {k: 0.0 for k in DIRECTIONAL_FIELDS}
    vals.update({k: float(v) for k, v in values.items() if k in vals})
    vals["familiarity"] = _clamp_familiarity(vals["familiarity"])
    for k in DIRECTIONAL_FIELDS:
        if k not in {"familiarity", "obligation"}:
            vals[k] = _clamp100(vals[k])
    cur = conn.execute(
        """INSERT INTO relationships(
               actor_a_id,actor_b_id,stance,familiarity,trust,affection,respect,fear,loyalty,resentment,obligation,professional_confidence,updated_day,started_day
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (source_actor_id,target_actor_id,vals['stance'],vals['familiarity'],vals['trust'],vals['affection'],
         vals['respect'],vals['fear'],vals['loyalty'],vals['resentment'],vals['obligation'],vals['professional_confidence'],int(day),
         int(day if started_day is None else started_day)),
    )
    return int(cur.lastrowid)

def ensure_reciprocal_relationship(
    conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int, day: int, **values: float
) -> tuple[int,int]:
    return (
        ensure_relationship(conn, actor_a_id, actor_b_id, day, **values),
        ensure_relationship(conn, actor_b_id, actor_a_id, day, **values),
    )

def adjust_relationship(
    conn: sqlite3.Connection, source_actor_id: int, target_actor_id: int, day: int,
    *, stance_delta: float=0.0, familiarity_delta: float=0.0, trust_delta: float=0.0,
    affection_delta: float=0.0, respect_delta: float=0.0, fear_delta: float=0.0,
    loyalty_delta: float=0.0, resentment_delta: float=0.0, obligation_delta: float=0.0,
    professional_confidence_delta: float=0.0,
) -> None:
    rid = ensure_relationship(conn, source_actor_id, target_actor_id, day)
    row = conn.execute("SELECT * FROM relationships WHERE id=?", (rid,)).fetchone()
    deltas = {
        'stance': stance_delta, 'familiarity': familiarity_delta, 'trust': trust_delta,
        'affection': affection_delta, 'respect': respect_delta, 'fear': fear_delta,
        'loyalty': loyalty_delta, 'resentment': resentment_delta, 'obligation': obligation_delta,
        'professional_confidence': professional_confidence_delta,
    }
    vals: dict[str, float] = {}
    for k, delta in deltas.items():
        v = float(row[k]) + float(delta)
        if k == 'familiarity':
            v = _clamp_familiarity(v)
        elif k != 'obligation':
            v = _clamp100(v)
        vals[k] = v
    conn.execute(
        """UPDATE relationships SET stance=?,familiarity=?,trust=?,affection=?,respect=?,fear=?,loyalty=?,resentment=?,obligation=?,professional_confidence=?,updated_day=? WHERE id=?""",
        (vals['stance'],vals['familiarity'],vals['trust'],vals['affection'],vals['respect'],vals['fear'],vals['loyalty'],vals['resentment'],vals['obligation'],vals['professional_confidence'],int(day),rid),
    )

def adjust_relationship_pair(
    conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int, day: int,
    *, a_to_b: dict[str,float] | None=None, b_to_a: dict[str,float] | None=None,
    symmetric: dict[str,float] | None=None,
) -> None:
    if symmetric is not None:
        if a_to_b is not None or b_to_a is not None:
            raise ValueError("use symmetric or directional delta maps, not both")
        a_to_b = dict(symmetric); b_to_a = dict(symmetric)
    a_to_b = a_to_b or {}; b_to_a = b_to_a or {}
    adjust_relationship(conn, actor_a_id, actor_b_id, day, **a_to_b)
    adjust_relationship(conn, actor_b_id, actor_a_id, day, **b_to_a)

def relationship_exists(conn: sqlite3.Connection, source_actor_id: int, target_actor_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
        (int(source_actor_id), int(target_actor_id)),
    ).fetchone() is not None


def record_relationship_effect(
    conn: sqlite3.Connection, source_actor_id: int, target_actor_id: int, day: int, *,
    source_kind: str, source_id: int | None = None, summary: str, metadata: dict[str, Any] | None = None,
    stance_delta: float=0.0, familiarity_delta: float=0.0, trust_delta: float=0.0,
    affection_delta: float=0.0, respect_delta: float=0.0, fear_delta: float=0.0,
    loyalty_delta: float=0.0, resentment_delta: float=0.0, obligation_delta: float=0.0,
    professional_confidence_delta: float=0.0,
) -> int:
    """Apply a directional social consequence and preserve why it changed.

    Structural relationships remain owned by their domain tables; this ledger records evaluative
    social memory so later decisions can distinguish trust, fear, resentment, respect, etc.
    """
    effect = {
        'stance_delta': stance_delta, 'familiarity_delta': familiarity_delta, 'trust_delta': trust_delta,
        'affection_delta': affection_delta, 'respect_delta': respect_delta, 'fear_delta': fear_delta,
        'loyalty_delta': loyalty_delta, 'resentment_delta': resentment_delta, 'obligation_delta': obligation_delta,
        'professional_confidence_delta': professional_confidence_delta,
    }
    adjust_relationship(conn, source_actor_id, target_actor_id, day, **effect)
    import json
    cur = conn.execute(
        """INSERT INTO relationship_history(day,source_actor_id,target_actor_id,source_kind,source_id,effect_json,summary,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (int(day), int(source_actor_id), int(target_actor_id), str(source_kind), source_id,
         json.dumps(effect, sort_keys=True), str(summary), json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)

def record_relationship_pair_effect(
    conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int, day: int, *, source_kind: str, source_id: int | None,
    a_to_b: dict[str,float], b_to_a: dict[str,float], summary_a: str, summary_b: str, metadata: dict[str,Any] | None=None
) -> tuple[int,int]:
    return (
        record_relationship_effect(conn, actor_a_id, actor_b_id, day, source_kind=source_kind, source_id=source_id, summary=summary_a, metadata=metadata, **a_to_b),
        record_relationship_effect(conn, actor_b_id, actor_a_id, day, source_kind=source_kind, source_id=source_id, summary=summary_b, metadata=metadata, **b_to_a),
    )
