from __future__ import annotations

import json
import random
import sqlite3
from typing import Any, Callable


_VALID_INTENTS = {"controlled", "hostile", "lethal", "accidental"}
_VALID_OUTCOMES = {"transient", "persistent", "fatal"}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _seed(conn: sqlite3.Connection, actor_id: int, source_kind: str, source_ref_id: int, intent_class: str) -> int:
    base = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    # source_kind is salted in so duel #12 and war_battle #12 draw independent rolls.
    salt = sum((i + 1) * ord(ch) for i, ch in enumerate(f"{source_kind}:{intent_class}"))
    return (base * 1000003 + int(actor_id) * 9176 + int(source_ref_id) * 131071 + salt * 271) & 0x7FFFFFFF


def _living(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute(
        """SELECT a.status,lp.life_status FROM actors a
           LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""",
        (actor_id,),
    ).fetchone()
    return bool(row and str(row["status"]) != "deceased" and (row["life_status"] is None or str(row["life_status"]) == "living"))


def _intent_multiplier(intent_class: str) -> float:
    return {"controlled": 0.62, "accidental": 0.82, "hostile": 1.0, "lethal": 1.18}[intent_class]


def _persistent_probability(intent_class: str, severity: float) -> float:
    if intent_class == "controlled":
        return max(0.0, min(0.18, (severity - 18.0) / 180.0))
    if intent_class == "accidental":
        return max(0.01, min(0.45, (severity - 12.0) / 105.0))
    if intent_class == "hostile":
        return max(0.03, min(0.70, (severity - 10.0) / 85.0))
    return max(0.18, min(0.95, (severity - 6.0) / 70.0))


def _fatal_probability(intent_class: str, severity: float) -> float:
    if intent_class == "controlled":
        return 0.0
    if intent_class == "accidental":
        return max(0.0, min(0.12, (severity - 86.0) / 110.0))
    if intent_class == "hostile":
        return max(0.0, min(0.22, (severity - 82.0) / 80.0))
    return max(0.0, min(0.82, (severity - 62.0) / 46.0))


def record_harm(
    conn: sqlite3.Connection,
    actor_id: int,
    *,
    source_kind: str,
    source_ref_id: int,
    severity: float,
    intent_class: str = "hostile",
    harm_kind: str = "physical",
    exposure: float = 50.0,
    body_system: str | None = None,
    location_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    outcome_override: str | None = None,
    event_logger: Callable[..., int] | None = None,
) -> dict[str, Any]:
    """Project a concrete hazard into persistent health/life state once.

    HARM-01 is deliberately provenance-first.  The source event decides exposure and intent;
    this resolver decides whether the tracked actor escapes with transient harm, receives a real
    health condition, or dies.  Replaying the same source against the same actor is idempotent.

    ``outcome_override`` is not a narrative shortcut.  It exists for upstream owners that already
    know the authoritative casualty class (for example WAR-01 aggregate casualty assignment).
    """
    if intent_class not in _VALID_INTENTS:
        raise ValueError(f"Unknown harm intent: {intent_class}")
    if outcome_override is not None and outcome_override not in _VALID_OUTCOMES:
        raise ValueError(f"Unknown harm outcome override: {outcome_override}")
    if not _living(conn, actor_id):
        existing = conn.execute(
            "SELECT * FROM harm_incidents WHERE actor_id=? AND source_kind=? AND source_ref_id=? AND harm_kind=?",
            (actor_id, source_kind, int(source_ref_id), harm_kind),
        ).fetchone()
        if existing:
            return dict(existing)
        raise ValueError("Harm target must be a living actor")

    existing = conn.execute(
        "SELECT * FROM harm_incidents WHERE actor_id=? AND source_kind=? AND source_ref_id=? AND harm_kind=?",
        (actor_id, source_kind, int(source_ref_id), harm_kind),
    ).fetchone()
    if existing:
        return dict(existing)

    from .health import ensure_health_profile
    ensure_health_profile(conn, actor_id)
    hp = conn.execute("SELECT injury_resilience FROM actor_health_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    resilience = float(hp[0]) if hp else 70.0
    raw = max(0.0, min(100.0, float(severity)))
    exposure = max(0.0, min(100.0, float(exposure)))
    # Prime healthy bodies are more resilient, but never immune.  Exposure is a modest multiplier,
    # not a second severity score; this keeps controlled sport distinct from lethal intent.
    vulnerability = max(0.55, min(1.15, 1.08 - resilience / 230.0))
    exposure_factor = 0.78 + exposure / 220.0
    resolved = max(0.0, min(100.0, raw * _intent_multiplier(intent_class) * vulnerability * exposure_factor))

    rng = random.Random(_seed(conn, actor_id, source_kind, int(source_ref_id), intent_class))
    fatal_roll = rng.random()
    persistent_roll = rng.random()
    if outcome_override is not None:
        outcome = outcome_override
    elif intent_class == "lethal" and resolved >= 99.0:
        outcome = "fatal"
    elif fatal_roll < _fatal_probability(intent_class, resolved):
        outcome = "fatal"
    elif persistent_roll < _persistent_probability(intent_class, resolved):
        outcome = "persistent"
    else:
        outcome = "transient"

    day = _day(conn)
    meta = dict(metadata or {})
    meta.update({
        "authority": "ENGINE_DERIVED_HARM01",
        "raw_severity": round(raw, 3),
        "injury_resilience": round(resilience, 3),
        "exposure": round(exposure, 3),
    })
    cur = conn.execute(
        """INSERT INTO harm_incidents(day,actor_id,source_kind,source_ref_id,harm_kind,intent_class,location_id,
                    exposure,raw_severity,resolved_severity,outcome,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (day, actor_id, source_kind, int(source_ref_id), harm_kind, intent_class, location_id,
         exposure, raw, resolved, outcome, json.dumps(meta, sort_keys=True)),
    )
    incident_id = int(cur.lastrowid)
    condition_id = None

    if outcome == "fatal":
        from .household_life import mark_actor_deceased
        mark_actor_deceased(conn, actor_id, reason=f"Fatal {harm_kind} harm from {source_kind} #{source_ref_id}.",
                            event_logger=event_logger)
        conn.execute("UPDATE harm_incidents SET fatal=1 WHERE id=?", (incident_id,))
    elif outcome == "persistent":
        from .health import add_condition
        condition_severity = max(12.0, resolved)
        condition_id = add_condition(
            conn,
            actor_id,
            "injury",
            f"{harm_kind.replace('_',' ').title()} injury from {source_kind} #{source_ref_id}",
            severity=condition_severity,
            body_system=body_system,
            capacity_impact=min(75.0, condition_severity * 0.62),
            pain_impact=min(85.0, condition_severity * 0.76),
            recovery_rate_per_30=11.0 if condition_severity < 55 else 7.0,
            progression_rate_per_30=0.0,
            fatality_pressure=(max(0.0, condition_severity - 72.0) * 0.55 if intent_class != "controlled" else 0.0),
            specialist_requirement="physician" if condition_severity >= 60 else "none",
            next_review_days=7 if condition_severity >= 60 else 14,
            metadata={
                "source_harm_incident_id": incident_id,
                "source_kind": source_kind,
                "source_ref_id": int(source_ref_id),
                "can_leave_disability": condition_severity >= 65,
                "mobility_related": True,
                **meta,
            },
        )
        conn.execute("UPDATE harm_incidents SET condition_id=? WHERE id=?", (condition_id, incident_id))

    row = conn.execute("SELECT * FROM harm_incidents WHERE id=?", (incident_id,)).fetchone()
    return dict(row)


def project_duel_harm(conn: sqlite3.Connection, engagement_id: int, *,
                      event_logger: Callable[..., int] | None = None) -> list[dict[str, Any]]:
    """Create final anatomical consequences for a resolved duel exactly once per combatant."""
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=? AND engagement_kind='duel'", (engagement_id,)).fetchone()
    if not eng or str(eng["status"]) != "resolved":
        return []
    meta = json.loads(eng["metadata_json"] or "{}")
    outcome = json.loads(eng["outcome_json"] or "{}")
    winner = outcome.get("winner_actor_id")
    nonlethal = meta.get("nonlethal")
    if nonlethal is True:
        intent = "controlled"
    elif nonlethal is False and int(eng["stakes"]) >= 4:
        intent = "lethal"
    else:
        intent = "hostile"

    rows = conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()
    projected: list[dict[str, Any]] = []
    for row in rows:
        aid = int(row["actor_id"])
        is_loser = winner is not None and aid != int(winner)
        readiness_depletion = max(0.0, 100.0 - float(row["readiness"]))
        stamina_depletion = max(0.0, 100.0 - float(row["stamina"]))
        if intent == "controlled":
            raw = 3.0 + int(eng["stakes"]) * 2.2 + readiness_depletion * 0.28 + stamina_depletion * 0.08 + (5.0 if is_loser else 1.5)
        elif intent == "lethal":
            raw = 18.0 + int(eng["stakes"]) * 7.0 + readiness_depletion * 0.48 + stamina_depletion * 0.12 + (24.0 if is_loser else 8.0)
        else:
            raw = 8.0 + int(eng["stakes"]) * 4.0 + readiness_depletion * 0.38 + stamina_depletion * 0.10 + (12.0 if is_loser else 4.0)
        projected.append(record_harm(
            conn,
            aid,
            source_kind="duel",
            source_ref_id=int(engagement_id),
            severity=min(100.0, raw),
            intent_class=intent,
            harm_kind="combat",
            exposure=min(100.0, 35.0 + readiness_depletion * 0.55 + stamina_depletion * 0.20),
            location_id=eng["location_id"],
            metadata={
                "winner_actor_id": winner,
                "combatant_status": str(row["status"]),
                "stakes": int(eng["stakes"]),
                "nonlethal": nonlethal,
            },
            event_logger=event_logger,
        ))
    return projected
