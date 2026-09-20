from __future__ import annotations

import json
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(v: Any) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def create_role(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    role_key: str,
    title: str,
    domain_key: str,
    *,
    role_kind: str = "technical_role",
    capacity_slots: int = 1,
    durable: bool = True,
    source_kind: str | None = None,
    source_id: int | None = None,
    remit: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    minimum_filled_slots: int = 0,
    autonomous_refill: bool = False,
    minimum_candidate_quality: float = 0,
    staffing_priority: float = 50,
    day: int | None = None,
) -> int:
    day = _day(conn) if day is None else int(day)
    existing = conn.execute(
        "SELECT id FROM institutional_roles WHERE institution_actor_id=? AND role_key=? LIMIT 1",
        (institution_actor_id, role_key),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO institutional_roles(
               institution_actor_id,role_key,title,domain_key,role_kind,capacity_slots,durable,status,
               created_day,source_kind,source_id,remit_json,metadata_json,minimum_filled_slots,autonomous_refill,
               minimum_candidate_quality,staffing_priority
           ) VALUES (?,?,?,?,?,?,?,'active',?,?,?,?,?,?,?,?,?)""",
        (
            institution_actor_id, role_key, title, domain_key, role_kind, max(1, int(capacity_slots)),
            1 if durable else 0, day, source_kind, source_id, _j(remit or {}), _j(metadata or {}),
            max(0, min(max(1, int(capacity_slots)), int(minimum_filled_slots))), 1 if autonomous_refill else 0,
            max(0.0, min(100.0, float(minimum_candidate_quality))), max(0.0, min(100.0, float(staffing_priority))),
        ),
    )
    return int(cur.lastrowid)


def role_open_slots(conn: sqlite3.Connection, role_id: int) -> int:
    role = conn.execute("SELECT capacity_slots,status FROM institutional_roles WHERE id=?", (role_id,)).fetchone()
    if not role or str(role["status"]) != "active":
        return 0
    filled = int(conn.execute(
        "SELECT COUNT(*) FROM institutional_appointments WHERE role_id=? AND status='active'",
        (role_id,),
    ).fetchone()[0])
    return max(0, int(role["capacity_slots"]) - filled)


def find_reusable_role(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    domain_key: str,
    role_key: str | None,
    compatible_role_keys: list[str] | None = None,
) -> sqlite3.Row | None:
    keys: list[str] = []
    if role_key:
        keys.append(str(role_key))
    for k in compatible_role_keys or []:
        if k and str(k) not in keys:
            keys.append(str(k))
    for key in keys:
        row = conn.execute(
            """SELECT * FROM institutional_roles
               WHERE institution_actor_id=? AND role_key=? AND status='active' LIMIT 1""",
            (institution_actor_id, key),
        ).fetchone()
        if row and role_open_slots(conn, int(row["id"])) > 0:
            return row
    return None


def ensure_program(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    config: dict[str, Any],
    *, source_kind: str, source_id: int | None, day: int,
) -> tuple[int | None, str | None]:
    key = config.get("program_key")
    if not key:
        return None, None
    row = conn.execute(
        "SELECT * FROM institutional_programs WHERE institution_actor_id=? AND program_key=? LIMIT 1",
        (institution_actor_id, str(key)),
    ).fetchone()
    priority = max(0.0, min(100.0, float(config.get("program_priority", 65))))
    if row:
        conn.execute(
            """UPDATE institutional_programs
               SET priority=MAX(priority,?),status=CASE WHEN status='planning' THEN 'active' ELSE status END,
                   metadata_json=? WHERE id=?""",
            (priority, _j({"adapt01_last_source_kind": source_kind, "adapt01_last_source_id": source_id}), int(row["id"])),
        )
        return int(row["id"]), "reshape_program"
    cur = conn.execute(
        """INSERT INTO institutional_programs(
               institution_actor_id,program_key,title,domain_key,program_kind,horizon,priority,status,started_day,
               source_kind,source_id,objective_json,metadata_json
           ) VALUES (?,?,?,?,?,?,?,'active',?,?,?,?,?)""",
        (
            institution_actor_id, str(key), str(config.get("program_title") or key.replace("_", " ").title()),
            str(config.get("domain_key") or "general"), str(config.get("program_kind") or "initiative"),
            str(config.get("horizon") or "durable"), priority, day, source_kind, source_id,
            _j(config.get("objective") or {}), _j({"adapt01": True}),
        ),
    )
    return int(cur.lastrowid), "create_program"


def _record_adaptation(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    adaptation_kind: str,
    *, program_id: int | None, role_id: int | None, source_kind: str, source_id: int | None,
    candidate_kind: str | None, candidate_id: int | None, day: int, rationale: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO institutional_plan_adaptations(
               institution_actor_id,program_id,role_id,adaptation_kind,source_kind,source_id,candidate_kind,candidate_id,
               created_day,rationale,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (institution_actor_id, program_id, role_id, adaptation_kind, source_kind, source_id,
         candidate_kind, candidate_id, day, rationale, _j(metadata or {})),
    )
    return int(cur.lastrowid)


def _propose_actor_service(
    conn: sqlite3.Connection,
    search: sqlite3.Row,
    candidate_actor_id: int,
    *, title: str, service_kind: str, duration_days: int | None, standing: bool,
    scope: dict[str, Any] | None = None, exclusivity: float = 0,
) -> tuple[int, int]:
    from .opportunity import create_proposal, add_term, present_proposal
    proposal_kind = "retainership" if standing else "temporary_service"
    pid = create_proposal(
        conn, int(search["seeker_actor_id"]), proposal_kind, str(search["domain_key"]), title,
        proposer_institution_actor_id=int(search["seeker_institution_actor_id"]) if search["seeker_institution_actor_id"] is not None else None,
        target_actor_id=candidate_actor_id, source_kind="adaptive_plan", source_id=int(search["id"]),
        metadata={"search_id": int(search["id"]), "adapt01": True, "standing": bool(standing)},
    )
    add_term(
        conn, pid, "service_commitment", subject_kind="actor", subject_id=candidate_actor_id, execution_order=20,
        value={"service_kind": service_kind, "duration_days": duration_days, "scope": scope or {}, "exclusivity": float(exclusivity)},
    )
    iid = present_proposal(conn, pid, rationale="The institution adapted its plan around a discovered person without inventing a new office where a contract or retainer suffices.")
    conn.execute("UPDATE opportunity_searches SET status='approaching' WHERE id=?", (int(search["id"]),))
    return pid, iid


def adapt_and_propose_talent(
    conn: sqlite3.Connection,
    search_id: int,
    candidate_actor_id: int,
    need: dict[str, Any],
    *, day: int | None = None,
) -> dict[str, Any]:
    """Resolve how an institution should relate to discovered talent.

    Reuse-before-creation is authoritative here. A new institutional role is created only when:
    - no compatible existing role has an open slot;
    - the need is durable/recurring;
    - internal authority is genuinely required;
    - the source domain explicitly allows structural role creation; and
    - structural need is high enough.
    """
    from .opportunity import propose_talent_recruitment

    day = _day(conn) if day is None else int(day)
    s = conn.execute("SELECT * FROM opportunity_searches WHERE id=? AND status='searching'", (search_id,)).fetchone()
    if not s or s["seeker_institution_actor_id"] is None:
        raise ValueError("adaptive talent planning requires an active institutional search")
    result = conn.execute(
        "SELECT * FROM opportunity_search_results WHERE search_id=? AND candidate_kind='actor' AND candidate_id=?",
        (search_id, candidate_actor_id),
    ).fetchone()
    if not result:
        raise ValueError("candidate was not discovered by this search")
    iid = int(s["seeker_institution_actor_id"])
    cfg = need.get("adaptive_plan") if isinstance(need.get("adaptive_plan"), dict) else {}
    cfg = dict(cfg)
    cfg.setdefault("domain_key", str(s["domain_key"]))
    program_id, program_change = ensure_program(conn, iid, cfg, source_kind="opportunity_search", source_id=search_id, day=day)

    role_key = str(cfg.get("role_key") or s["role_key"] or "") or None
    existing_role = find_reusable_role(conn, iid, str(s["domain_key"]), role_key, cfg.get("compatible_role_keys") or [])
    title = str(cfg.get("title") or cfg.get("role_title") or role_key or "Institutional specialist")
    relationship_preference = str(cfg.get("relationship_preference") or "auto")
    horizon = str(cfg.get("horizon") or "durable")
    duration_days = cfg.get("duration_days")
    internal_authority = bool(cfg.get("internal_authority_required", False))
    allow_role_creation = bool(cfg.get("allow_role_creation", False))
    structural_need = float(cfg.get("structural_need", 0))
    create_threshold = float(cfg.get("role_creation_threshold", 80))
    role_id: int | None = None

    if existing_role is not None and relationship_preference not in {"temporary_service", "standing_service"}:
        role_id = int(existing_role["id"])
        pid, interaction = propose_talent_recruitment(
            conn, search_id, candidate_actor_id, proposal_kind="appointment", title=str(existing_role["title"]),
            appointment_key=str(existing_role["role_key"]), appointment_kind=str(existing_role["role_kind"]),
            obligations=cfg.get("obligations") or {}, privileges=cfg.get("privileges") or {},
            stipend=float(cfg.get("stipend") or 0), exclusivity=float(cfg.get("exclusivity") or 0), role_id=role_id,
        )
        kind = "reuse_role"
        rationale = "A compatible existing institutional role had an open slot, so the institution reused it rather than creating a new office."
    elif relationship_preference == "temporary_service" or horizon in {"one_off", "temporary"} or duration_days is not None:
        pid, interaction = _propose_actor_service(
            conn, s, candidate_actor_id, title=title, service_kind=str(cfg.get("service_kind") or role_key or s["domain_key"]),
            duration_days=int(duration_days) if duration_days is not None else 120, standing=False,
            scope=cfg.get("scope") or {}, exclusivity=float(cfg.get("exclusivity") or 0),
        )
        kind = "temporary_contract"
        rationale = "The need is bounded or temporary, so the institution used a service contract rather than creating a role."
    elif not internal_authority or relationship_preference in {"standing_service", "retainership"}:
        pid, interaction = _propose_actor_service(
            conn, s, candidate_actor_id, title=title, service_kind=str(cfg.get("service_kind") or role_key or s["domain_key"]),
            duration_days=None, standing=True, scope=cfg.get("scope") or {}, exclusivity=float(cfg.get("exclusivity") or 0),
        )
        kind = "standing_service"
        rationale = "The institution wants durable access but does not require an internal office, so it proposed a standing service/retainer relationship."
    elif allow_role_creation and structural_need >= create_threshold and horizon in {"recurring", "durable"}:
        if not role_key:
            raise ValueError("structural role creation requires a role_key")
        role_id = create_role(
            conn, iid, role_key, str(cfg.get("role_title") or title), str(s["domain_key"]),
            role_kind=str(cfg.get("role_kind") or "technical_role"), capacity_slots=int(cfg.get("capacity_slots") or 1),
            durable=True, source_kind="opportunity_search", source_id=search_id, remit=cfg.get("remit") or {},
            metadata={"created_because_no_existing_fit": True, "structural_need": structural_need},
            minimum_filled_slots=1, autonomous_refill=True, minimum_candidate_quality=float(s["min_quality"] or 0),
            staffing_priority=max(50.0, min(100.0, structural_need)), day=day,
        )
        pid, interaction = propose_talent_recruitment(
            conn, search_id, candidate_actor_id, proposal_kind="appointment", title=str(cfg.get("role_title") or title),
            appointment_key=role_key, appointment_kind=str(cfg.get("role_kind") or "technical_role"),
            obligations=cfg.get("obligations") or {}, privileges=cfg.get("privileges") or {},
            stipend=float(cfg.get("stipend") or 0), exclusivity=float(cfg.get("exclusivity") or 0), role_id=role_id,
        )
        kind = "create_role"
        rationale = "No compatible role existed and the need was explicitly durable, internal and structurally important enough to justify a new role."
    else:
        pid, interaction = _propose_actor_service(
            conn, s, candidate_actor_id, title=title, service_kind=str(cfg.get("service_kind") or role_key or s["domain_key"]),
            duration_days=None, standing=True, scope=cfg.get("scope") or {}, exclusivity=float(cfg.get("exclusivity") or 0),
        )
        kind = "standing_service"
        rationale = "No existing role fit, but the structural threshold for creating a new role was not met; a standing service relationship was used instead."

    adaptation_id = _record_adaptation(
        conn, iid, kind, program_id=program_id, role_id=role_id, source_kind="opportunity_search", source_id=search_id,
        candidate_kind="actor", candidate_id=candidate_actor_id, day=day, rationale=rationale,
        metadata={"program_change": program_change, "relationship_preference": relationship_preference, "horizon": horizon},
    )
    return {
        "proposal_id": pid, "interaction_id": interaction, "adaptation_id": adaptation_id,
        "adaptation_kind": kind, "program_id": program_id, "program_change": program_change, "role_id": role_id,
        "summary": rationale,
    }
