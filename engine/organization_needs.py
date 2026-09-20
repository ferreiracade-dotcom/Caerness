from __future__ import annotations

import json
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        value = json.loads(raw) if raw else default
        return value
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def set_role_staffing_requirement(
    conn: sqlite3.Connection,
    role_id: int,
    *,
    minimum_filled_slots: int = 1,
    autonomous_refill: bool = True,
    minimum_candidate_quality: float = 0,
    staffing_priority: float = 50,
) -> None:
    """Make an existing role explicitly required.

    An open role is not automatically a vacancy the institution cares about. This policy is
    opt-in so spare capacity, honorary offices and intentionally dormant posts do not create
    recruitment behaviour merely because a role row exists.
    """
    role = conn.execute("SELECT capacity_slots FROM institutional_roles WHERE id=?", (role_id,)).fetchone()
    if not role:
        raise ValueError("unknown institutional role")
    capacity = max(1, int(role["capacity_slots"]))
    minimum = max(0, min(capacity, int(minimum_filled_slots)))
    conn.execute(
        """UPDATE institutional_roles
           SET minimum_filled_slots=?, autonomous_refill=?, minimum_candidate_quality=?, staffing_priority=?
           WHERE id=?""",
        (minimum, 1 if autonomous_refill else 0, _clamp(minimum_candidate_quality), _clamp(staffing_priority), role_id),
    )


def create_capability_requirement(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    requirement_key: str,
    capability_key: str,
    domain_key: str,
    *,
    minimum_capacity: float = 0,
    minimum_readiness: float = 0,
    search_kind: str = "service_provider",
    role_key: str | None = None,
    min_quality: float = 0,
    intensity: float = 60,
    urgency: float = 50,
    source_kind: str | None = None,
    source_id: int | None = None,
    adaptive_plan: dict[str, Any] | None = None,
    proposal: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    day: int | None = None,
) -> int:
    """Persist a domain-owned capability requirement.

    This function does not infer that an institution *ought* to possess a capability. A domain
    calls it only when a real program, office, policy, asset, obligation or other persisted fact
    establishes that requirement. ORGNEED-01 then detects whether the requirement is actually met.
    """
    if search_kind not in {"talent", "service_provider"}:
        raise ValueError("autonomous capability requirements currently support talent or service_provider searches")
    day = _day(conn) if day is None else int(day)
    conn.execute(
        """INSERT INTO organization_capability_requirements(
               institution_actor_id,requirement_key,capability_key,domain_key,minimum_capacity,minimum_readiness,
               search_kind,role_key,min_quality,intensity,urgency,status,source_kind,source_id,adaptive_plan_json,
               proposal_json,created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?,?,?,?,?)
           ON CONFLICT(institution_actor_id,requirement_key) DO UPDATE SET
               capability_key=excluded.capability_key,domain_key=excluded.domain_key,
               minimum_capacity=excluded.minimum_capacity,minimum_readiness=excluded.minimum_readiness,
               search_kind=excluded.search_kind,role_key=excluded.role_key,min_quality=excluded.min_quality,
               intensity=excluded.intensity,urgency=excluded.urgency,status='active',source_kind=excluded.source_kind,
               source_id=excluded.source_id,adaptive_plan_json=excluded.adaptive_plan_json,
               proposal_json=excluded.proposal_json,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
        (
            institution_actor_id, str(requirement_key), str(capability_key), str(domain_key),
            _clamp(minimum_capacity), _clamp(minimum_readiness), str(search_kind), role_key,
            _clamp(min_quality), _clamp(intensity), _clamp(urgency), source_kind, source_id,
            _j(adaptive_plan or {}), _j(proposal or {}), day, day, _j(metadata or {}),
        ),
    )
    row = conn.execute(
        "SELECT id FROM organization_capability_requirements WHERE institution_actor_id=? AND requirement_key=?",
        (institution_actor_id, str(requirement_key)),
    ).fetchone()
    return int(row[0])


def _active_pressure_for_source(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    source_kind: str,
    source_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT * FROM organization_pressures
           WHERE institution_actor_id=? AND source_kind=? AND source_id=? AND status='active'
           ORDER BY id DESC LIMIT 1""",
        (institution_actor_id, source_kind, source_id),
    ).fetchone()


def _upsert_pressure(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    pressure_key: str,
    domain: str,
    *,
    intensity: float,
    urgency: float,
    source_kind: str,
    source_id: int,
    metadata: dict[str, Any],
    day: int,
) -> tuple[int, bool]:
    existing = _active_pressure_for_source(conn, institution_actor_id, source_kind, source_id)
    if existing:
        conn.execute(
            """UPDATE organization_pressures
               SET pressure_key=?,domain=?,intensity=?,urgency=?,updated_day=?,metadata_json=?
               WHERE id=?""",
            (pressure_key, domain, _clamp(intensity), _clamp(urgency), day, _j(metadata), int(existing["id"])),
        )
        return int(existing["id"]), False
    cur = conn.execute(
        """INSERT INTO organization_pressures(
               institution_actor_id,pressure_key,domain,intensity,urgency,source_kind,source_id,status,
               created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,'active',?,?,?)""",
        (
            institution_actor_id, pressure_key, domain, _clamp(intensity), _clamp(urgency),
            source_kind, source_id, day, day, _j(metadata),
        ),
    )
    return int(cur.lastrowid), True


def _resolve_source_pressure(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    source_kind: str,
    source_id: int,
    *,
    day: int,
    reason: str,
) -> int:
    rows = conn.execute(
        """SELECT id FROM organization_pressures
           WHERE institution_actor_id=? AND source_kind=? AND source_id=? AND status='active'""",
        (institution_actor_id, source_kind, source_id),
    ).fetchall()
    for row in rows:
        pressure_id = int(row["id"])
        conn.execute(
            "UPDATE organization_pressures SET status='resolved',updated_day=?,metadata_json=json_patch(metadata_json,?) WHERE id=?",
            (day, _j({"resolved_reason": reason, "resolved_day": day}), pressure_id),
        )
        # A need that ceased to exist should not keep generating approaches. This closes only the
        # search. Already-presented voluntary proposals remain real social facts and are not revoked.
        conn.execute(
            """UPDATE opportunity_searches SET status='fulfilled'
               WHERE seeker_institution_actor_id=? AND json_extract(metadata_json,'$.source_pressure_id')=?
                 AND status IN ('searching','approaching')""",
            (institution_actor_id, pressure_id),
        )
    return len(rows)


def _role_need(conn: sqlite3.Connection, role: sqlite3.Row, *, day: int) -> tuple[bool, int]:
    role_id = int(role["id"])
    iid = int(role["institution_actor_id"])
    minimum = max(0, min(int(role["capacity_slots"]), int(role["minimum_filled_slots"])))
    filled = int(conn.execute(
        "SELECT COUNT(*) FROM institutional_appointments WHERE role_id=? AND status='active'", (role_id,)
    ).fetchone()[0])
    deficit = max(0, minimum - filled)
    if str(role["status"]) != "active" or not bool(role["autonomous_refill"]) or minimum <= 0 or deficit <= 0:
        return False, _resolve_source_pressure(
            conn, iid, "institutional_role_staffing", role_id, day=day,
            reason="required staffing level is currently satisfied or no longer active",
        )

    priority = _clamp(float(role["staffing_priority"]))
    deficit_ratio = deficit / max(1, minimum)
    intensity = _clamp(35.0 + priority * 0.45 + deficit_ratio * 20.0)
    urgency = _clamp(25.0 + priority * 0.55 + deficit_ratio * 20.0)
    need = {
        "search_kind": "talent",
        "domain_key": str(role["domain_key"]),
        "role_key": str(role["role_key"]),
        "min_quality": float(role["minimum_candidate_quality"]),
        "expires_in_days": 180,
        "adaptive_plan": {
            "domain_key": str(role["domain_key"]),
            "role_key": str(role["role_key"]),
            "role_title": str(role["title"]),
            "horizon": "durable" if bool(role["durable"]) else "temporary",
            "relationship_preference": "appointment",
            "internal_authority_required": True,
            "allow_role_creation": False,
            "structural_need": priority,
        },
    }
    pressure_id, created = _upsert_pressure(
        conn, iid, f"role_staffing:{role_id}", str(role["domain_key"]), intensity=intensity, urgency=urgency,
        source_kind="institutional_role_staffing", source_id=role_id, day=day,
        metadata={
            "orgneed01": True, "evidence_kind": "required_role_vacancy", "role_id": role_id,
            "minimum_filled_slots": minimum, "filled_slots": filled, "deficit": deficit,
            "opportunity_need": need,
        },
    )
    return created, 0


def _capability_need(conn: sqlite3.Connection, req: sqlite3.Row, *, day: int) -> tuple[bool, int]:
    rid = int(req["id"])
    iid = int(req["institution_actor_id"])
    if str(req["status"]) != "active":
        return False, _resolve_source_pressure(
            conn, iid, "organization_capability_requirement", rid, day=day,
            reason="capability requirement is no longer active",
        )
    cap = conn.execute(
        "SELECT capacity,readiness FROM organization_capabilities WHERE institution_actor_id=? AND capability_key=?",
        (iid, str(req["capability_key"])),
    ).fetchone()
    capacity = float(cap["capacity"]) if cap else 0.0
    readiness = float(cap["readiness"]) if cap else 0.0
    target_capacity = float(req["minimum_capacity"])
    target_readiness = float(req["minimum_readiness"])
    cap_gap = max(0.0, target_capacity - capacity)
    ready_gap = max(0.0, target_readiness - readiness)
    unmet = cap_gap > 1e-9 or ready_gap > 1e-9
    if not unmet:
        return False, _resolve_source_pressure(
            conn, iid, "organization_capability_requirement", rid, day=day,
            reason="persisted capability now meets the explicit requirement",
        )

    gap_fraction = max(
        cap_gap / max(1.0, target_capacity) if target_capacity > 0 else 0.0,
        ready_gap / max(1.0, target_readiness) if target_readiness > 0 else 0.0,
    )
    intensity = _clamp(float(req["intensity"]) + gap_fraction * 15.0)
    urgency = _clamp(float(req["urgency"]) + gap_fraction * 10.0)
    need: dict[str, Any] = {
        "search_kind": str(req["search_kind"]),
        "domain_key": str(req["domain_key"]),
        "role_key": str(req["role_key"] or req["capability_key"]),
        "min_quality": float(req["min_quality"]),
        "expires_in_days": 180,
    }
    adaptive_plan = _loads(req["adaptive_plan_json"], {})
    proposal = _loads(req["proposal_json"], {})
    if adaptive_plan:
        need["adaptive_plan"] = adaptive_plan
    if proposal:
        need["proposal"] = proposal
    _, created = _upsert_pressure(
        conn, iid, f"capability_requirement:{rid}", str(req["domain_key"]), intensity=intensity, urgency=urgency,
        source_kind="organization_capability_requirement", source_id=rid, day=day,
        metadata={
            "orgneed01": True, "evidence_kind": "explicit_capability_gap", "requirement_id": rid,
            "capability_key": str(req["capability_key"]), "capacity": capacity, "readiness": readiness,
            "minimum_capacity": target_capacity, "minimum_readiness": target_readiness,
            "capacity_gap": cap_gap, "readiness_gap": ready_gap, "opportunity_need": need,
        },
    )
    return created, 0


def refresh_organization_needs(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    *,
    day: int | None = None,
) -> dict[str, int]:
    """Project only explicit structural requirements into actionable organization pressures.

    The function intentionally does not inspect generic lifecycle labels such as declining/crisis,
    wealth, prestige or organization type and infer a profession from them. Those facts may cause a
    domain to persist a requirement, but they are not themselves a license to manufacture one.
    """
    day = _day(conn) if day is None else int(day)
    created = 0
    resolved = 0
    active = 0

    roles = conn.execute(
        """SELECT * FROM institutional_roles
           WHERE institution_actor_id=? AND (autonomous_refill=1 OR minimum_filled_slots>0)
           ORDER BY id""",
        (institution_actor_id,),
    ).fetchall()
    for role in roles:
        was_created, was_resolved = _role_need(conn, role, day=day)
        created += 1 if was_created else 0
        resolved += int(was_resolved)

    requirements = conn.execute(
        "SELECT * FROM organization_capability_requirements WHERE institution_actor_id=? ORDER BY id",
        (institution_actor_id,),
    ).fetchall()
    for req in requirements:
        was_created, was_resolved = _capability_need(conn, req, day=day)
        created += 1 if was_created else 0
        resolved += int(was_resolved)

    active = int(conn.execute(
        """SELECT COUNT(*) FROM organization_pressures
           WHERE institution_actor_id=? AND status='active'
             AND source_kind IN ('institutional_role_staffing','organization_capability_requirement')""",
        (institution_actor_id,),
    ).fetchone()[0])
    return {"needs_created": created, "needs_resolved": resolved, "active_autonomous_needs": active}


def refresh_all_organization_needs(conn: sqlite3.Connection, *, day: int | None = None) -> dict[str, int]:
    day = _day(conn) if day is None else int(day)
    ids = {int(r[0]) for r in conn.execute(
        "SELECT DISTINCT institution_actor_id FROM institutional_roles WHERE autonomous_refill=1 OR minimum_filled_slots>0"
    ).fetchall()}
    ids.update(int(r[0]) for r in conn.execute(
        "SELECT DISTINCT institution_actor_id FROM organization_capability_requirements WHERE status='active'"
    ).fetchall())
    created = resolved = active = 0
    for iid in sorted(ids):
        state = refresh_organization_needs(conn, iid, day=day)
        created += state["needs_created"]
        resolved += state["needs_resolved"]
        active += state["active_autonomous_needs"]
    return {"institutions_reviewed": len(ids), "needs_created": created, "needs_resolved": resolved, "active_autonomous_needs": active}
