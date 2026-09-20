from __future__ import annotations

import json
import sqlite3
from typing import Any

from .interactions import create_interaction


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _government_actor(conn: sqlite3.Connection, polity_id: int) -> int | None:
    row = conn.execute("SELECT decision_actor_id FROM polity_government_actors WHERE polity_id=?", (polity_id,)).fetchone()
    return int(row[0]) if row else None


def _local_polity(conn: sqlite3.Connection, location_id: int | None) -> sqlite3.Row | None:
    if location_id is None:
        return None
    return conn.execute(
        """SELECT p.*,a.name institution_name FROM locations l
           JOIN actors a ON a.name=l.political_owner
           JOIN political_polities p ON p.institution_actor_id=a.id
           WHERE l.id=? AND p.status!='dissolved' LIMIT 1""",
        (int(location_id),),
    ).fetchone()


def create_attention_case(
    conn: sqlite3.Connection,
    observer_actor_id: int,
    target_actor_id: int,
    domain_key: str,
    interest_kind: str,
    *,
    observer_institution_actor_id: int | None = None,
    salience: float = 50,
    source_kind: str | None = None,
    source_id: int | None = None,
    expires_in_days: int | None = 365,
    metadata: dict[str, Any] | None = None,
) -> int:
    day = _day(conn)
    existing = conn.execute(
        """SELECT id FROM strategic_attention_cases
           WHERE observer_actor_id=? AND target_actor_id=? AND domain_key=? AND interest_kind=?
             AND status IN ('observing','planning','approaching')
           ORDER BY id LIMIT 1""",
        (observer_actor_id, target_actor_id, domain_key, interest_kind),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO strategic_attention_cases(
               observer_actor_id,observer_institution_actor_id,target_actor_id,domain_key,interest_kind,salience,status,
               source_kind,source_id,created_day,last_review_day,next_review_day,expires_day,metadata_json
           ) VALUES (?,?,?,?,?,?,'observing',?,?,?,?,?,?,?)""",
        (
            observer_actor_id, observer_institution_actor_id, target_actor_id, domain_key, interest_kind,
            max(0.0, min(100.0, float(salience))), source_kind, source_id, day, day, day + 7,
            None if expires_in_days is None else day + int(expires_in_days), _j(metadata or {}),
        ),
    )
    return int(cur.lastrowid)


def ensure_horse_breeder_attention(conn: sqlite3.Connection, day: int | None = None) -> int:
    """Let governments notice strategically important horse breeders, not merely buy from them.

    This is one domain provider for ATTENTION-01.  The shared layer owns relevance/approach state;
    the domain provider decides what horse-breeding excellence can mean to a polity.  It does not
    imply that every successful breeder receives office, and it does not require the breeder to
    publish a SEEK offering first.
    """
    day = _day(conn) if day is None else int(day)
    rows = conn.execute(
        """SELECT e.id enterprise_id,e.owner_actor_id,e.institution_actor_id,e.location_id,e.reputation,
                  bp.quality,bp.service_reliability,
                  COALESCE((SELECT SUM(ps.inventory) FROM production_sites ps
                            JOIN market_goods mg ON mg.id=ps.good_id
                            WHERE ps.enterprise_id=e.id AND ps.active=1 AND mg.good_key='horses_remounts'),0) horse_stock
           FROM civilian_enterprises e
           JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id
           JOIN business_archetypes ba ON ba.id=bp.archetype_id
           WHERE e.status IN ('active','strained') AND ba.archetype_key='horse_breeder'
             AND e.owner_actor_id IS NOT NULL
           ORDER BY e.id"""
    ).fetchall()
    created = 0
    for r in rows:
        owner = int(r["owner_actor_id"])
        polity = _local_polity(conn, int(r["location_id"]) if r["location_id"] is not None else None)
        if not polity:
            continue
        government = _government_actor(conn, int(polity["id"]))
        if government is None or government == owner:
            continue
        rep = float(r["reputation"] or 0.0)
        quality = float(r["quality"] or 0.0)
        reliability = float(r["service_reliability"] or 0.0)
        stock = float(r["horse_stock"] or 0.0)
        military = float(polity["military_capacity"] or 0.0)
        admin = float(polity["administrative_capacity"] or 0.0)
        # Appointment relevance requires more than being a viable supplier.  The breeder must have
        # durable public standing and quality; stock/reliability make the claim credible, while the
        # state's own military/administrative capacity determines whether it can use such an office.
        salience = (
            rep * 0.31 + quality * 0.30 + reliability * 0.13 + min(100.0, stock * 5.0) * 0.10
            + military * 0.10 + admin * 0.06
        )
        if rep < 62 or quality < 62 or reliability < 50 or salience < 64:
            continue
        if conn.execute(
            """SELECT 1 FROM institutional_appointments
               WHERE appointing_institution_actor_id=? AND holder_actor_id=?
                 AND appointment_key='state_remount_master' AND status='active' LIMIT 1""",
            (int(polity["institution_actor_id"]), owner),
        ).fetchone():
            continue
        if conn.execute(
            """SELECT 1 FROM strategic_attention_cases
               WHERE observer_actor_id=? AND target_actor_id=? AND domain_key='horse_breeding'
                 AND interest_kind='appoint' AND status IN ('observing','planning','approaching','accepted','fulfilled') LIMIT 1""",
            (government, owner),
        ).fetchone():
            continue
        title = f"Remount Master to {polity['institution_name']}"
        create_attention_case(
            conn, government, owner, "horse_breeding", "appoint",
            observer_institution_actor_id=int(polity["institution_actor_id"]), salience=salience,
            source_kind="recognized_enterprise_excellence", source_id=int(r["enterprise_id"]), expires_in_days=300,
            metadata={
                "provider": "horse_breeder_state_appointment",
                "enterprise_id": int(r["enterprise_id"]),
                "polity_id": int(polity["id"]),
                "appointment_key": "state_remount_master",
                "appointment_title": title,
                "proposal_kind": "incorporation",
                "appointment_kind": "technical_office",
                "stipend": round(8.0 + salience * 0.08, 2),
                "exclusivity": 0.85,
                "transfer_enterprise_to_institution": True,
                "retain_breeder_as_operator": True,
                "obligations": {
                    "direct_royal_stud_operations": True,
                    "advise_remount_procurement": True,
                    "inspect_state_breeding_stock": True,
                },
                "privileges": {
                    "court_or_government_access": True,
                    "authority_over_royal_stud_operations": True,
                },
                "evidence": {
                    "enterprise_reputation": rep,
                    "quality": quality,
                    "reliability": reliability,
                    "horse_stock": stock,
                    "salience": round(salience, 3),
                },
            },
        )
        created += 1
    return created


def _pending_case_interaction(conn: sqlite3.Connection, case_id: int) -> sqlite3.Row | None:
    rows = conn.execute("SELECT * FROM interactions WHERE status='pending' ORDER BY id DESC LIMIT 200").fetchall()
    for row in rows:
        terms = _loads(row["terms_json"], {})
        if int(terms.get("attention_case_id") or 0) == int(case_id):
            return row
    return None


def _last_case_interaction(conn: sqlite3.Connection, case_id: int) -> sqlite3.Row | None:
    rows = conn.execute("SELECT * FROM interactions ORDER BY id DESC LIMIT 250").fetchall()
    for row in rows:
        terms = _loads(row["terms_json"], {})
        if int(terms.get("attention_case_id") or 0) == int(case_id):
            return row
    return None


def process_attention_case(conn: sqlite3.Connection, case_id: int, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    case = conn.execute("SELECT * FROM strategic_attention_cases WHERE id=?", (case_id,)).fetchone()
    if not case or str(case["status"]) not in {"observing", "planning", "approaching"}:
        return {"case_id": case_id, "action": "none"}
    if case["expires_day"] is not None and day > int(case["expires_day"]):
        conn.execute("UPDATE strategic_attention_cases SET status='expired',last_review_day=?,next_review_day=? WHERE id=?", (day, day, case_id))
        return {"case_id": case_id, "action": "expired"}
    pending = _pending_case_interaction(conn, case_id)
    if pending:
        conn.execute("UPDATE strategic_attention_cases SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 7, case_id))
        return {"case_id": case_id, "action": "pending_interaction", "interaction_id": int(pending["id"])}
    last = _last_case_interaction(conn, case_id)
    if last and str(last["status"]) in {"rejected", "cancelled", "expired"}:
        conn.execute("UPDATE strategic_attention_cases SET status='rejected',last_review_day=?,next_review_day=? WHERE id=?", (day, day, case_id))
        return {"case_id": case_id, "action": "rejected"}

    meta = _loads(case["metadata_json"], {})
    interest = str(case["interest_kind"])
    observer = int(case["observer_actor_id"])
    target = int(case["target_actor_id"])
    if interest == "patronize":
        from .patronage import propose_patronage
        existing = conn.execute(
            "SELECT id FROM opportunity_proposals WHERE source_attention_case_id=? AND status IN ('draft','pending','countered','accepted') ORDER BY id LIMIT 1",
            (case_id,),
        ).fetchone()
        if existing:
            pid = int(existing[0])
            interaction = None
            prow = conn.execute("SELECT status FROM opportunity_proposals WHERE id=?", (pid,)).fetchone()
            if prow and str(prow[0]) == 'pending':
                from .opportunity import _proposal_interaction
                ir = _proposal_interaction(conn, pid, pending_only=True)
                interaction = int(ir['id']) if ir else None
        else:
            pid, interaction = propose_patronage(
                conn, observer, target, str(case['domain_key']),
                title=str(meta.get('title') or f"Patronage in {case['domain_key']}"),
                amount_per_cycle=float(meta.get('amount_per_cycle') or 0),
                recurrence_days=int(meta.get('recurrence_days') or 30),
                duration_days=meta.get('duration_days'), patronage_kind=meta.get('patronage_kind'),
                funding_source_kind=meta.get('funding_source_kind'), funding_source_id=meta.get('funding_source_id'),
                exclusivity=float(meta.get('exclusivity') or 0), support=meta.get('support') or {}, expectations=meta.get('expectations') or {},
                source_attention_case_id=case_id,
            )
        conn.execute("UPDATE strategic_attention_cases SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 7, case_id))
        return {"case_id":case_id,"action":"opportunity_offer","proposal_id":pid,"interaction_id":interaction,"target_actor_id":target}

    if interest == "appoint":
        institution_id = int(case["observer_institution_actor_id"]) if case["observer_institution_actor_id"] is not None else None
        if institution_id is None:
            conn.execute("UPDATE strategic_attention_cases SET status='blocked',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 30, case_id))
            return {"case_id": case_id, "action": "blocked_no_institution"}
        # ATTENTION identifies strategic relevance. OPPORTUNITY owns what relationship is actually being offered.
        from .opportunity import create_proposal, add_term, present_proposal
        existing = conn.execute(
            "SELECT id FROM opportunity_proposals WHERE source_attention_case_id=? AND status IN ('draft','pending','countered','accepted','fulfilled') ORDER BY id LIMIT 1",
            (case_id,),
        ).fetchone()
        if existing:
            pid = int(existing[0])
        else:
            pid = create_proposal(
                conn, observer, str(meta.get("proposal_kind") or "appointment"), str(case["domain_key"]),
                str(meta.get("appointment_title") or "Institutional appointment"),
                proposer_institution_actor_id=institution_id, target_actor_id=target,
                source_attention_case_id=case_id, source_kind=str(case["source_kind"] or "strategic_attention"),
                source_id=case["source_id"], metadata={"attention_case_id": case_id, "provider": meta.get("provider")},
            )
            enterprise_id = meta.get("enterprise_id")
            if meta.get("transfer_enterprise_to_institution") and enterprise_id is not None:
                add_term(conn, pid, "enterprise_legal_ownership", subject_kind="enterprise", subject_id=int(enterprise_id), execution_order=20,
                         value={"holder_kind":"institution","holder_id":institution_id,"share":1.0,"replace":True})
                add_term(conn, pid, "enterprise_beneficial_control", subject_kind="enterprise", subject_id=int(enterprise_id), execution_order=30,
                         value={"holder_kind":"institution","holder_id":institution_id,"share":1.0,"replace":True})
                if meta.get("retain_breeder_as_operator"):
                    add_term(conn, pid, "enterprise_operation", subject_kind="enterprise", subject_id=int(enterprise_id), execution_order=40,
                             value={"holder_kind":"actor","holder_id":target,"share":1.0,"replace":True})
            add_term(conn, pid, "appointment", subject_kind="actor", subject_id=target, execution_order=50, value={
                "institution_actor_id": institution_id, "holder_actor_id": target,
                "appointment_key": meta.get("appointment_key"), "title": meta.get("appointment_title"),
                "appointment_kind": meta.get("appointment_kind", "technical_office"),
                "obligations": meta.get("obligations", {}), "privileges": meta.get("privileges", {}),
                "stipend": meta.get("stipend", 0), "exclusivity": meta.get("exclusivity", 0),
            })
        iid = present_proposal(
            conn, pid, day=day,
            rationale="The institution wants a defined relationship with this strategically relevant person. The explicit proposal terms determine whether property, control or independence changes.",
        )
        conn.execute("UPDATE strategic_attention_cases SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 7, case_id))
        return {"case_id": case_id, "action": "opportunity_offer", "proposal_id": pid, "interaction_id": iid, "target_actor_id": target}

    conn.execute("UPDATE strategic_attention_cases SET status='planning',last_review_day=?,next_review_day=? WHERE id=?", (day, day + 30, case_id))
    return {"case_id": case_id, "action": "unsupported_interest_pending_domain_provider", "interest_kind": interest}


def accept_institutional_appointment(
    conn: sqlite3.Connection,
    attention_case_id: int,
    holder_actor_id: int,
    interaction_id: int,
    day: int | None = None,
) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    case = conn.execute("SELECT * FROM strategic_attention_cases WHERE id=?", (attention_case_id,)).fetchone()
    if not case or str(case["interest_kind"]) != "appoint":
        raise ValueError("attention case is not an appointment")
    if int(case["target_actor_id"]) != int(holder_actor_id):
        raise ValueError("appointment holder does not match attention target")
    institution = int(case["observer_institution_actor_id"]) if case["observer_institution_actor_id"] is not None else None
    if institution is None:
        raise ValueError("appointment has no appointing institution")
    meta = _loads(case["metadata_json"], {})
    key = str(meta.get("appointment_key") or f"appointment_{attention_case_id}")
    title = str(meta.get("appointment_title") or "Institutional Specialist")
    existing = conn.execute(
        """SELECT id FROM institutional_appointments WHERE appointing_institution_actor_id=? AND holder_actor_id=?
           AND appointment_key=? AND status='active' ORDER BY id LIMIT 1""",
        (institution, holder_actor_id, key),
    ).fetchone()
    if existing:
        appointment_id = int(existing[0])
    else:
        cur = conn.execute(
            """INSERT INTO institutional_appointments(
                   appointing_institution_actor_id,holder_actor_id,appointment_key,title,domain_key,appointment_kind,
                   source_attention_case_id,source_interaction_id,started_day,stipend,exclusivity,status,
                   obligations_json,privileges_json,metadata_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
            (
                institution, holder_actor_id, key, title, str(case["domain_key"]),
                str(meta.get("appointment_kind") or "technical_office"), attention_case_id, interaction_id, day,
                max(0.0, float(meta.get("stipend") or 0.0)), max(0.0, min(1.0, float(meta.get("exclusivity") or 0.0))),
                _j(meta.get("obligations", {})), _j(meta.get("privileges", {})),
                _j({"authority": "ENGINE_DERIVED", "attention01": True, "source_kind": case["source_kind"], "source_id": case["source_id"]}),
            ),
        )
        appointment_id = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json)
           VALUES (?,?,'appointed_office',?,'active',?,?,?)
           ON CONFLICT(institution_actor_id,member_actor_id,membership_kind) DO UPDATE SET
             role_text=excluded.role_text,status='active',left_day=NULL,metadata_json=excluded.metadata_json""",
        (institution, holder_actor_id, title, day, _j(["ATTENTION-01 accepted institutional appointment"]), _j({"institutional_appointment_id": appointment_id})),
    )
    conn.execute("UPDATE strategic_attention_cases SET status='fulfilled',last_review_day=?,next_review_day=? WHERE id=?", (day, day, attention_case_id))
    return {"appointment_id": appointment_id, "institution_actor_id": institution, "holder_actor_id": holder_actor_id, "title": title}


def next_attention_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals: list[int] = []
    r = conn.execute(
        """SELECT MIN(next_review_day) FROM strategic_attention_cases
           WHERE status IN ('observing','planning','approaching') AND next_review_day>? AND next_review_day<=?""",
        (after_day, end_day),
    ).fetchone()
    if r and r[0] is not None:
        vals.append(int(r[0]))
    cycle = ((int(after_day) // 90) + 1) * 90
    if cycle <= int(end_day):
        vals.append(cycle)
    return min(vals) if vals else None


def process_due_attention(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str, int]:
    from .patronage import ensure_patronage_attention, ensure_patronage_seeking, refresh_patronage_competitions
    created = ensure_horse_breeder_attention(conn, day) + ensure_patronage_attention(conn, day)
    patronage_requests = ensure_patronage_seeking(conn, day)
    rows = conn.execute(
        """SELECT id FROM strategic_attention_cases
           WHERE status IN ('observing','planning','approaching') AND next_review_day<=?
           ORDER BY next_review_day,id""",
        (day,),
    ).fetchall()
    counts = {"attention_cases_created": created, "attention_cases_reviewed": 0, "attention_approaches": 0,
              "patronage_requests_created": patronage_requests}
    for row in rows:
        result = process_attention_case(conn, int(row[0]), day)
        counts["attention_cases_reviewed"] += 1
        if str(result.get("action", "")).endswith("offer"):
            counts["attention_approaches"] += 1
    counts["patronage_competitions_created"] = refresh_patronage_competitions(conn, day)
    return counts


def summary(conn: sqlite3.Connection) -> dict[str, int]:
    q = lambda sql: int(conn.execute(sql).fetchone()[0])
    return {
        "active_attention_cases": q("SELECT COUNT(*) FROM strategic_attention_cases WHERE status IN ('observing','planning','approaching')"),
        "fulfilled_attention_cases": q("SELECT COUNT(*) FROM strategic_attention_cases WHERE status='fulfilled'"),
        "active_appointments": q("SELECT COUNT(*) FROM institutional_appointments WHERE status='active'"),
    }
