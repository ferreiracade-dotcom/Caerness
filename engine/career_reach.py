from __future__ import annotations

import json
import random
import sqlite3
from typing import Any, Callable

from .continuity import create_career_track, add_career_stage, start_career, advance_career_stage

# v0.59 flexible-career correction:
# Career standing is only a coarse description of established place in a profession.
# It is NOT a mandatory ladder of jobs. Concrete responsibilities/appointments branch sideways,
# can overlap, and can become available before a standing change. Cultivation Stage, wealth,
# reputation, service and trust change eligibility/reach; none automatically promotes an actor.
CAREER_MODELS: dict[str, dict[str, Any]] = {
    "martial_institution": {
        "key": "structural_martial_institution_service",
        "name": "Martial Institution Service",
        "domain": "martial execution",
        "stages": [
            ("junior", "Junior Disciple", 10),
            ("established", "Established Disciple", 20),
            ("senior", "Senior Disciple", 30),
        ],
    },
    "longroad": {
        "key": "structural_long_road_escort",
        "name": "Long Road Escort Work",
        "domain": "martial execution",
        "stages": [
            ("escort_hand", "Working Escort Hand", 10),
            ("proven_escort", "Proven Escort", 20),
            ("renowned_escort", "Renowned Escort", 30),
        ],
    },
    "retainer": {
        "key": "structural_retainer_service",
        "name": "Household Retainer Service",
        "domain": "martial execution",
        "stages": [
            ("retainer", "Retainer", 10),
            ("senior_retainer", "Senior Retainer", 20),
        ],
    },
    "merchant": {
        "key": "structural_independent_merchant",
        "name": "Independent Merchant Career",
        "domain": "commerce",
        "stages": [
            ("small_operator", "Local-Scale Operator", 10),
            ("regional_operator", "Regional-Scale Operator", 20),
            ("major_operator", "Major-Scale Operator", 30),
        ],
    },
    "witness": {
        "key": "structural_witness_lay_service",
        "name": "Witness Lay Service",
        "domain": "administration",
        "stages": [
            ("parish_worker", "Parish Worker", 10),
            ("trusted_worker", "Trusted Parish Worker", 20),
            ("established_worker", "Established Lay Worker", 30),
        ],
    },
    # Independent criminal organizations are not career ladders. Their bosses, crews and internal offices
    # are modeled by underworld organization structure, not by promotion through a universal hierarchy.
    "martial": {
        "key": "structural_independent_martial_professional",
        "name": "Independent Martial Professional",
        "domain": "martial execution",
        "stages": [
            ("practitioner", "Working Practitioner", 10),
            ("veteran", "Veteran Practitioner", 20),
        ],
    },
}

# Branching responsibilities/appointments. These are NOT career stages. A junior or established
# institutional disciple can, for example, be trusted with patrol leadership or assistant teaching
# without first climbing every standing band. Likewise a merchant can coordinate factors while still
# formally a local-scale proprietor, and a retainer can become the estate's horse specialist without
# becoming captain.
RESPONSIBILITY_MODELS: dict[str, dict[str, str]] = {
    "martial_institution": {
        "patrol_lead": "Patrol Lead",
        "assistant_instructor": "Assistant Instructor",
        "disciple_examiner": "Disciple Examiner",
        "external_representative": "External Representative",
        "full_instructor": "Instructor",
    },
    "longroad": {
        "contract_lead": "Escort Contract Lead",
        "high_value_guard": "High-Value Client Guard",
        "road_mentor": "Road Mentor",
        "master_grade_guard": "Master-Grade Protection Specialist",
    },
    "retainer": {
        "mounted_detail_lead": "Mounted Detail Lead",
        "horsemaster": "Remount / Horse Readiness Specialist",
        "household_instructor": "Household Martial Instructor",
        "security_planner": "Household Security Planner",
        "retainer_captain": "Retainer Captain",
    },
    "merchant": {
        "factor_coordinator": "Factor / Carrier Coordinator",
        "regional_contractor": "Regional Contracting Lead",
        "warehouse_operator": "Warehouse / Stock Principal",
        "multi_market_principal": "Multi-Market Principal",
    },
    "witness": {
        "relief_supervisor": "Relief Supervisor",
        "records_supervisor": "Records Supervisor",
        "volunteer_coordinator": "Volunteer Coordinator",
        "parish_service_coordinator": "Parish Service Coordinator",
    },
    "martial": {
        "contract_lead": "Martial Contract Lead",
        "mentor": "Working Mentor",
        "independent_teacher": "Independent Teacher",
    },
}

MAX_ACTIVE_RESPONSIBILITIES = {
    "martial_institution": 3,
    "longroad": 3,
    "retainer": 3,
    "merchant": 3,
    "witness": 3,
    "martial": 2,
}

STAGE_ORDER = {None: 0, "First": 1, "Temper": 2, "Third": 3, "Breach": 4, "Fifth": 5, "Sixth": 6}


def _loads(value: Any, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rng(conn: sqlite3.Connection, actor_id: int, day: int, salt: int) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 1000003 + actor_id * 9176 + day * 131 + salt)


def _resource(conn: sqlite3.Connection, actor_id: int, key: str) -> float:
    r = conn.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type=? ORDER BY id LIMIT 1", (actor_id, key)).fetchone()
    return float(r[0]) if r else 0.0


def _cultivation_stage(conn: sqlite3.Connection, actor_id: int) -> str | None:
    r = conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=? AND active=1 AND status='active'", (actor_id,)).fetchone()
    return str(r[0]) if r and r[0] else None


def _enterprise(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained') ORDER BY id LIMIT 1", (actor_id,)).fetchone()


def _drive(conn: sqlite3.Connection, actor_id: int, key: str, default: float = .5) -> float:
    r = conn.execute(f"SELECT {key} FROM actor_drives WHERE actor_id=?", (actor_id,)).fetchone()
    return float(r[0]) if r and r[0] is not None else default


def _role_events(conn: sqlite3.Connection, actor_id: int) -> int:
    r = conn.execute("""SELECT COUNT(*) FROM events WHERE source_actor_id=? AND
        (event_type LIKE 'role_%' OR event_type IN ('career_advancement','career_responsibility'))""", (actor_id,)).fetchone()
    return int(r[0] or 0)


def _ensure_track(conn: sqlite3.Connection, kind: str) -> tuple[int, dict[str, int]] | None:
    model = CAREER_MODELS.get(kind)
    if not model:
        return None
    tid = create_career_track(
        conn, model["key"], model["name"], model["domain"],
        description="STRUCTURAL v0.59 flexible career standing. Standing is coarse; appointments/responsibilities branch independently.",
        stage_model={
            "authority": "ENGINE_STRUCTURAL",
            "principle": "standing_is_not_job_ladder",
            "responsibilities_branch_independently": True,
            "eligibility_changes_opportunity_not_destiny": True,
        },
        is_canon=False,
    )
    stages: dict[str, int] = {}
    valid_keys = {x[0] for x in model["stages"]}
    for key, name, seq in model["stages"]:
        sid = add_career_stage(
            conn, tid, key, name, seq,
            description="Coarse professional standing band; not a mandatory sequence of concrete jobs or appointments.",
            entry_requirements={"resolved_by": "career_reach_v059_flexible"},
            responsibilities={"role_kind": kind, "appointments_independent": True},
        )
        stages[key] = sid
    # Fresh v0.59 branches have no obsolete structural rows. On a developer DB that already contains
    # the first ladder-shaped draft, leave historical stage rows in place but never select them again.
    # Existing actors on an obsolete row are normalized by ensure_role_career below.
    return tid, stages


def _initial_stage_key(conn: sqlite3.Connection, actor_id: int, kind: str, context: Any = None) -> str:
    model = CAREER_MODELS[kind]
    first = model["stages"][0][0]
    a = conn.execute("SELECT COALESCE(subtype,'') FROM actors WHERE id=?", (actor_id,)).fetchone()
    text = (str(a[0]) if a else "").lower()
    if context is not None:
        try:
            text += " " + str(context["role_text"] or "").lower()
        except Exception:
            pass
    if kind == "martial_institution":
        if "senior disciple" in text or "instructor" in text or "teacher" in text:
            return "senior"
        if "experienced working" in text or "solid working" in text or "established" in text:
            return "established"
        return first
    if kind == "retainer":
        if "senior retainer" in text or "captain" in text or "commander" in text:
            return "senior_retainer"
    if kind == "merchant":
        if "major" in text and ("merchant" in text or "principal" in text or "operator" in text):
            return "major_operator"
        if "regional principal" in text or "regional merchant" in text or "regional operator" in text:
            return "regional_operator"
    if kind == "witness":
        if "senior" in text or "coordinator" in text or "supervisor" in text:
            return "established_worker"
        if "trusted" in text:
            return "trusted_worker"
    if kind == "longroad":
        if "renowned" in text or "master guard" in text:
            return "renowned_escort"
        if "veteran escort" in text or "proven escort" in text or "contract lead" in text or "escort captain" in text:
            return "proven_escort"
    if kind == "martial":
        if "veteran" in text or "experienced" in text or "teacher" in text or "instructor" in text:
            return "veteran"
    return first


def _normalize_existing_stage(conn: sqlite3.Connection, row: sqlite3.Row, kind: str, stages: dict[str, int]) -> sqlite3.Row:
    current_key = str(row["stage_key"] or "")
    if current_key in stages:
        return row
    # Normalize the first ladder-shaped v0.59 developer draft without inventing advancement.
    fallback = _initial_stage_key(conn, int(row["actor_id"]), kind)
    if kind == "martial_institution" and current_key == "instructor":
        fallback = "senior"
    elif kind == "longroad" and current_key in {"contract_lead", "master_guard"}:
        fallback = "renowned_escort" if current_key == "master_guard" else "proven_escort"
    elif kind == "retainer" and current_key == "retainer_captain":
        fallback = "senior_retainer"
    elif kind == "merchant" and current_key == "regional_principal":
        fallback = "regional_operator"
    elif kind == "merchant" and current_key == "major_principal":
        fallback = "major_operator"
    elif kind == "witness" and current_key == "senior_worker":
        fallback = "trusted_worker"
    elif kind == "witness" and current_key == "relief_coordinator":
        fallback = "established_worker"
    elif kind == "martial" and current_key == "teacher":
        fallback = "veteran"
    conn.execute("UPDATE actor_careers SET current_stage_id=? WHERE id=?", (stages[fallback], int(row["id"])))
    return conn.execute("SELECT ac.*,cs.stage_key,cs.stage_name,cs.sequence_index FROM actor_careers ac LEFT JOIN career_stages cs ON cs.id=ac.current_stage_id WHERE ac.id=?", (int(row["id"]),)).fetchone()


def ensure_role_career(conn: sqlite3.Connection, actor_id: int, kind: str, context: Any = None) -> sqlite3.Row | None:
    built = _ensure_track(conn, kind)
    if not built:
        return None
    tid, stages = built
    row = conn.execute("SELECT ac.*,cs.stage_key,cs.stage_name,cs.sequence_index FROM actor_careers ac LEFT JOIN career_stages cs ON cs.id=ac.current_stage_id WHERE ac.actor_id=? AND ac.track_id=? AND ac.status='active' ORDER BY ac.id LIMIT 1", (actor_id, tid)).fetchone()
    if row:
        return _normalize_existing_stage(conn, row, kind, stages)
    first_key = _initial_stage_key(conn, actor_id, kind, context)
    inst_id = None
    if kind == "martial_institution" and context is not None:
        try:
            inst_id = int(context["institution_actor_id"])
        except Exception:
            inst_id = None
    cid = start_career(conn, actor_id, tid, stage_id=stages[first_key], institution_actor_id=inst_id,
                       notes="Auto-attached by v0.59 from already-persisted role; does not invent a new occupation.")
    conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (_dumps({
        "role_events": 0,
        "opportunities": 0,
        "advancements": 0,
        "responsibilities": [],
        "responsibility_opportunities": 0,
        "authority": "V0_59_FLEXIBLE_ROLE_REACH",
    }), cid))
    return conn.execute("SELECT ac.*,cs.stage_key,cs.stage_name,cs.sequence_index FROM actor_careers ac LEFT JOIN career_stages cs ON cs.id=ac.current_stage_id WHERE ac.id=?", (cid,)).fetchone()


def _active_responsibility_entries(exp: dict[str, Any]) -> list[dict[str, Any]]:
    raw = exp.get("responsibilities", [])
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict) and str(r.get("status", "active")) == "active" and r.get("key")]


def career_responsibilities(conn: sqlite3.Connection, actor_id: int, kind: str, context: Any = None) -> set[str]:
    row = ensure_role_career(conn, actor_id, kind, context)
    if not row:
        return set()
    exp = _loads(row["experience_json"], {})
    return {str(r["key"]) for r in _active_responsibility_entries(exp)}


def has_responsibility(conn: sqlite3.Connection, actor_id: int, kind: str, key: str, context: Any = None) -> bool:
    return key in career_responsibilities(conn, actor_id, kind, context)


def career_state(conn: sqlite3.Connection, actor_id: int, kind: str, context: Any = None) -> dict[str, Any]:
    row = ensure_role_career(conn, actor_id, kind, context)
    if not row:
        return {"kind": kind, "stage_key": None, "stage_name": None, "sequence_index": 0, "responsibilities": []}
    exp = _loads(row["experience_json"], {})
    return {
        "career_id": int(row["id"]),
        "kind": kind,
        "stage_key": row["stage_key"],
        "stage_name": row["stage_name"],
        "sequence_index": int(row["sequence_index"] or 0),
        "experience": exp,
        "responsibilities": _active_responsibility_entries(exp),
    }


def note_role_event(conn: sqlite3.Connection, actor_id: int, kind: str, context: Any = None) -> None:
    row = ensure_role_career(conn, actor_id, kind, context)
    if not row:
        return
    exp = _loads(row["experience_json"], {})
    exp["role_events"] = int(exp.get("role_events", 0)) + 1
    exp["last_role_event_day"] = _day(conn)
    conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (_dumps(exp), int(row["id"])))


def _eligibility(conn: sqlite3.Connection, actor_id: int, kind: str, current_key: str, next_key: str, role_events: int) -> tuple[bool, list[str], float]:
    """Standing eligibility only. Standing is coarse status, not a chain of concrete appointments."""
    reasons: list[str] = []
    readiness = 0.0
    stage = _cultivation_stage(conn, actor_id)
    s = STAGE_ORDER.get(stage, 0)
    ent = _enterprise(conn, actor_id)
    if kind == "martial_institution":
        if next_key == "established":
            ok = role_events >= 4
            if ok:
                reasons.append("repeated institutional service")
            readiness = min(1.0, role_events / 8.0)
            return ok, reasons, readiness
        if next_key == "senior":
            # Third is the normal route, but unusually long reliable service can also create senior standing.
            ok = role_events >= 9 and (s >= 3 or role_events >= 14)
            if role_events >= 9:
                reasons.append("sustained institutional service")
            if s >= 3:
                reasons.append(f"{stage}-stage professional standing")
            elif role_events >= 14:
                reasons.append("exceptionally long professional service despite lower Stage")
            readiness = min(1.0, .55 * min(1, role_events / 14) + .45 * min(1, max(s, 1) / 3))
            return ok, reasons, readiness
    elif kind == "longroad":
        rep = _resource(conn, actor_id, "road_reputation")
        thresholds = {"proven_escort": (20, 4), "renowned_escort": (34, 8)}
        rr, ev = thresholds[next_key]
        ok = rep >= rr and role_events >= ev
        if rep >= rr:
            reasons.append(f"Road reputation {rep:.1f}")
        if role_events >= ev:
            reasons.append("proven contract history")
        readiness = min(1, (rep / rr + role_events / ev) / 2)
        return ok, reasons, readiness
    elif kind == "retainer":
        loyalty = _drive(conn, actor_id, "loyalty")
        ok = next_key == "senior_retainer" and role_events >= 8 and loyalty >= .55
        if role_events >= 8:
            reasons.append("sustained estate service")
        if loyalty >= .55:
            reasons.append("demonstrated household loyalty")
        readiness = min(1, (role_events / 10 + loyalty) / 2)
        return ok, reasons, readiness
    elif kind == "merchant":
        if not ent:
            return False, [], 0.0
        net = max(0.0, float(ent["capital"]) + float(ent["cash"]) - float(ent["debt"]))
        rep = float(ent["reputation"])
        thresholds = {"regional_operator": (90, 52, 5), "major_operator": (200, 60, 9)}
        wealth, rmin, ev = thresholds[next_key]
        ok = net >= wealth and rep >= rmin and role_events >= ev
        if net >= wealth:
            reasons.append(f"net business resources {net:.1f}")
        if rep >= rmin:
            reasons.append(f"enterprise reputation {rep:.1f}")
        if role_events >= ev:
            reasons.append("completed commercial history")
        readiness = min(1, (net / wealth + rep / rmin + role_events / ev) / 3)
        return ok, reasons, readiness
    elif kind == "witness":
        trust = _resource(conn, actor_id, "local_trust")
        thresholds = {"trusted_worker": (24, 4), "established_worker": (34, 8)}
        tr, ev = thresholds[next_key]
        ok = trust >= tr and role_events >= ev
        if trust >= tr:
            reasons.append(f"local trust {trust:.1f}")
        if role_events >= ev:
            reasons.append("sustained parish service")
        readiness = min(1, (trust / tr + role_events / ev) / 2)
        return ok, reasons, readiness
    elif kind == "underworld":
        if not ent:
            return False, [], 0.0
        rep = float(ent["reputation"])
        evidence = int(conn.execute("SELECT COUNT(*) FROM underworld_evidence WHERE subject_kind='enterprise' AND subject_id=?", (int(ent["id"]),)).fetchone()[0])
        crew = _resource(conn, actor_id, "crew_loyalty")
        thresholds = {"crew_leader": (45, 4, 8, 3), "ward_boss": (52, 7, 8, 7), "organization_head": (60, 10, 10, 11)}
        rmin, emin, cmin, ev = thresholds[next_key]
        ok = rep >= rmin and evidence >= emin and crew >= cmin and role_events >= ev
        if rep >= rmin:
            reasons.append(f"front/crew reputation {rep:.1f}")
        if evidence >= emin:
            reasons.append("durable underworld activity")
        if crew >= cmin:
            reasons.append("stable crew base")
        if role_events >= ev:
            reasons.append("sustained operational history")
        readiness = min(1, (rep / rmin + evidence / emin + crew / cmin + role_events / ev) / 4)
        return ok, reasons, readiness
    elif kind == "martial":
        ok = next_key == "veteran" and role_events >= 7 and s >= 2
        if role_events >= 7:
            reasons.append("sustained martial work")
        if s >= 2:
            reasons.append(f"{stage}-stage standing")
        readiness = min(1, (role_events / 9 + s / 3) / 2)
        return ok, reasons, readiness
    return False, [], 0.0


def _responsibility_eligibility(conn: sqlite3.Connection, actor_id: int, kind: str, key: str, role_events: int, current_stage_key: str) -> tuple[bool, list[str], float]:
    """Eligibility for a branching responsibility. No responsibility requires a prior responsibility."""
    reasons: list[str] = []
    stage = _cultivation_stage(conn, actor_id)
    s = STAGE_ORDER.get(stage, 0)
    ent = _enterprise(conn, actor_id)
    rep_road = _resource(conn, actor_id, "road_reputation")
    trust = _resource(conn, actor_id, "local_trust")
    horse = _resource(conn, actor_id, "horse_access")

    if kind == "martial_institution":
        rules = {
            "patrol_lead": (4, 2),
            "assistant_instructor": (5, 3),
            "disciple_examiner": (7, 3),
            "external_representative": (6, 3),
            "full_instructor": (10, 3),
        }
        ev, st = rules[key]
        ok = role_events >= ev and s >= st
        if role_events >= ev:
            reasons.append("reliable institutional service")
        if s >= st:
            reasons.append(f"{stage}-stage capability")
        # Full instructor is not locked behind Senior Disciple or Assistant Instructor; those make it likelier.
        bonus = .0
        if key == "full_instructor" and current_stage_key == "senior":
            bonus += .15
            reasons.append("senior institutional standing")
        readiness = min(1, (role_events / max(ev, 1) + s / max(st, 1)) / 2 + bonus)
        return ok, reasons, readiness

    if kind == "longroad":
        rules = {
            "contract_lead": (22, 5, 2),
            "high_value_guard": (24, 5, 3),
            "road_mentor": (28, 8, 3),
            "master_grade_guard": (28, 7, 4),
        }
        rr, ev, st = rules[key]
        ok = rep_road >= rr and role_events >= ev and s >= st
        if rep_road >= rr:
            reasons.append(f"Road reputation {rep_road:.1f}")
        if role_events >= ev:
            reasons.append("proven Road work")
        if s >= st:
            reasons.append(f"{stage}-stage capability")
        readiness = min(1, (rep_road / rr + role_events / ev + s / st) / 3)
        return ok, reasons, readiness

    if kind == "retainer":
        rules = {
            "mounted_detail_lead": (5, 2),
            "horsemaster": (4, 1),
            "household_instructor": (7, 3),
            "security_planner": (8, 3),
            "retainer_captain": (10, 3),
        }
        ev, st = rules[key]
        ok = role_events >= ev and s >= st
        if key == "horsemaster":
            ok = role_events >= ev and horse >= 10
            if horse >= 10:
                reasons.append(f"substantial horse/remount access {horse:.1f}")
        elif s >= st:
            reasons.append(f"{stage}-stage martial capability")
        if role_events >= ev:
            reasons.append("sustained estate service")
        readiness = min(1, (role_events / ev + (horse / 14 if key == "horsemaster" else s / max(st, 1))) / 2)
        return ok, reasons, readiness

    if kind == "merchant":
        if not ent:
            return False, [], 0.0
        net = max(0.0, float(ent["capital"]) + float(ent["cash"]) - float(ent["debt"]))
        rep = float(ent["reputation"])
        rules = {
            "factor_coordinator": (75, 50, 4),
            "regional_contractor": (90, 52, 5),
            "warehouse_operator": (110, 54, 6),
            "multi_market_principal": (190, 58, 8),
        }
        wealth, rmin, ev = rules[key]
        ok = net >= wealth and rep >= rmin and role_events >= ev
        if net >= wealth:
            reasons.append(f"business resources {net:.1f}")
        if rep >= rmin:
            reasons.append(f"commercial reputation {rep:.1f}")
        if role_events >= ev:
            reasons.append("completed commercial history")
        readiness = min(1, (net / wealth + rep / rmin + role_events / ev) / 3)
        return ok, reasons, readiness

    if kind == "witness":
        rules = {
            "relief_supervisor": (24, 4),
            "records_supervisor": (22, 4),
            "volunteer_coordinator": (28, 5),
            "parish_service_coordinator": (34, 8),
        }
        tr, ev = rules[key]
        ok = trust >= tr and role_events >= ev
        if trust >= tr:
            reasons.append(f"local trust {trust:.1f}")
        if role_events >= ev:
            reasons.append("sustained lay service")
        readiness = min(1, (trust / tr + role_events / ev) / 2)
        return ok, reasons, readiness

    if kind == "underworld":
        if not ent:
            return False, [], 0.0
        rep = float(ent["reputation"])
        evidence = int(conn.execute("SELECT COUNT(*) FROM underworld_evidence WHERE subject_kind='enterprise' AND subject_id=?", (int(ent["id"]),)).fetchone()[0])
        crew = _resource(conn, actor_id, "crew_loyalty")
        rules = {
            "enforcement_lead": (43, 3, 7, 3),
            "front_manager": (42, 2, 6, 3),
            "collector_coordinator": (48, 4, 8, 4),
            "fixer": (50, 5, 7, 5),
        }
        rmin, emin, cmin, ev = rules[key]
        ok = rep >= rmin and evidence >= emin and crew >= cmin and role_events >= ev
        if rep >= rmin:
            reasons.append(f"local underworld reputation {rep:.1f}")
        if evidence >= emin:
            reasons.append("durable criminal activity")
        if crew >= cmin:
            reasons.append("stable crew relationships")
        if role_events >= ev:
            reasons.append("operational history")
        readiness = min(1, (rep / rmin + evidence / emin + crew / cmin + role_events / ev) / 4)
        return ok, reasons, readiness

    if kind == "martial":
        rules = {"contract_lead": (5, 2), "mentor": (7, 2), "independent_teacher": (9, 3)}
        ev, st = rules[key]
        ok = role_events >= ev and s >= st
        if role_events >= ev:
            reasons.append("sustained professional martial work")
        if s >= st:
            reasons.append(f"{stage}-stage capability")
        readiness = min(1, (role_events / ev + s / st) / 2)
        return ok, reasons, readiness

    return False, [], 0.0


def _update_membership_role(conn: sqlite3.Connection, actor_id: int, kind: str, stage_key: str) -> None:
    if kind != "martial_institution":
        return
    labels = {
        "junior": "ordinary junior spear disciple",
        "established": "established spear disciple",
        "senior": "senior spear disciple",
    }
    label = labels.get(stage_key)
    if label:
        conn.execute("UPDATE institution_memberships SET role_text=? WHERE member_actor_id=? AND status='active' AND (lower(COALESCE(role_text,'')) LIKE '%disciple%' OR lower(COALESCE(role_text,'')) LIKE '%instructor%' OR lower(COALESCE(role_text,'')) LIKE '%teacher%')", (label, actor_id))


def _record_responsibility(conn: sqlite3.Connection, row: sqlite3.Row, kind: str, key: str, reasons: list[str]) -> None:
    exp = _loads(row["experience_json"], {})
    current = _active_responsibility_entries(exp)
    if key in {str(x.get("key")) for x in current}:
        return
    name = RESPONSIBILITY_MODELS[kind][key]
    current.append({
        "key": key,
        "name": name,
        "acquired_day": _day(conn),
        "status": "active",
        "reasons": reasons,
        "kind": "branching_responsibility",
    })
    exp["responsibilities"] = current
    exp["responsibility_opportunities"] = int(exp.get("responsibility_opportunities", 0)) + 1
    exp["last_responsibility_day"] = _day(conn)
    conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (_dumps(exp), int(row["id"])))


def _responsibility_fit(conn: sqlite3.Connection, actor_id: int, kind: str, key: str) -> float:
    ambition = _drive(conn, actor_id, "ambition")
    loyalty = _drive(conn, actor_id, "loyalty")
    patience = _drive(conn, actor_id, "patience")
    pragmatism = _drive(conn, actor_id, "pragmatism")
    risk = _drive(conn, actor_id, "risk_tolerance")
    aggression = _drive(conn, actor_id, "aggression")
    fit = .30 + .18 * ambition + .12 * pragmatism
    if any(x in key for x in ("instructor", "mentor", "examiner", "supervisor")):
        fit += .18 * patience + .10 * loyalty
    if any(x in key for x in ("lead", "captain", "planner", "coordinator", "representative")):
        fit += .12 * ambition + .12 * loyalty
    if kind == "merchant":
        fit += .16 * pragmatism
    if kind == "witness":
        fit += .16 * loyalty + .10 * patience
    if kind == "underworld":
        fit += .10 * risk + .08 * aggression
    if kind == "longroad":
        fit += .08 * risk + .08 * pragmatism
    return max(.15, min(.90, fit))


def _review_responsibility_opportunity(conn: sqlite3.Connection, actor_id: int, kind: str, row: sqlite3.Row,
                                       current_key: str, role_events: int, elapsed_days: int,
                                       *, event_logger: Callable[..., int]) -> dict[str, Any] | None:
    definitions = RESPONSIBILITY_MODELS.get(kind, {})
    if not definitions:
        return None
    exp = _loads(row["experience_json"], {})
    active = _active_responsibility_entries(exp)
    active_keys = {str(r["key"]) for r in active}
    if len(active_keys) >= int(MAX_ACTIVE_RESPONSIBILITIES.get(kind, 3)):
        return None
    candidates: list[tuple[str, list[str], float]] = []
    for key in definitions:
        if key in active_keys:
            continue
        ok, reasons, readiness = _responsibility_eligibility(conn, actor_id, kind, key, role_events, current_key)
        if ok:
            candidates.append((key, reasons, readiness))
    if not candidates:
        return None
    day = _day(conn)
    # Responsibilities are easier to encounter than formal standing changes, but still sparse.
    annual = {
        "martial_institution": .48, "longroad": .46, "retainer": .44,
        "merchant": .50, "witness": .42, "underworld": .48, "martial": .38,
    }[kind]
    best_readiness = max(x[2] for x in candidates)
    chance = min(.24, annual * max(1, int(elapsed_days)) / 365.0 * (.55 + .45 * best_readiness))
    rng = _rng(conn, actor_id, day, 5917 + len(active_keys) * 31)
    if rng.random() >= chance:
        return None
    # Weighted but not deterministic: a person can branch into any eligible responsibility.
    weights = [max(.15, x[2]) for x in candidates]
    total = sum(weights)
    pick = rng.random() * total
    chosen = candidates[-1]
    for cand, w in zip(candidates, weights):
        pick -= w
        if pick <= 0:
            chosen = cand
            break
    key, reasons, readiness = chosen
    exp["responsibility_opportunities"] = int(exp.get("responsibility_opportunities", 0)) + 1
    exp["last_responsibility_opportunity_day"] = day
    conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (_dumps(exp), int(row["id"])))
    accepted = rng.random() < _responsibility_fit(conn, actor_id, kind, key)
    actor_name = str(conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()[0])
    name = definitions[key]
    if accepted:
        # Reload because opportunity counter was persisted above.
        row2 = conn.execute("SELECT ac.*,cs.stage_key,cs.stage_name,cs.sequence_index FROM actor_careers ac LEFT JOIN career_stages cs ON cs.id=ac.current_stage_id WHERE ac.id=?", (int(row["id"]),)).fetchone()
        _record_responsibility(conn, row2, kind, key, reasons)
        event_logger(day=day, event_type="career_responsibility", title=f"{actor_name}: {name}",
                     summary=f"A real responsibility opened because of {', '.join(reasons)}. {actor_name} accepted/was entrusted with {name}. This is a branching appointment or working role, not a required rung in a promotion ladder.",
                     severity=2, source_actor_id=actor_id, target_actor_ids=(actor_id,),
                     location_id=conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()[0],
                     visibility="limited", rumorability=.10, reliability=.95)
        return {"type": "responsibility", "offered": True, "accepted": True, "key": key, "name": name, "reasons": reasons}
    event_logger(day=day, event_type="career_responsibility_opportunity", title=f"{actor_name}: {name} opportunity passed",
                 summary=f"{name} became genuinely possible because of {', '.join(reasons)}, but the appointment/working responsibility did not result. No other career path is blocked by this.",
                 severity=1, source_actor_id=actor_id, target_actor_ids=(actor_id,),
                 location_id=conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()[0],
                 visibility="limited", rumorability=.04, reliability=.95)
    return {"type": "responsibility", "offered": True, "accepted": False, "key": key, "name": name, "reasons": reasons}


def review_career_reach(conn: sqlite3.Connection, actor_id: int, kind: str, context: Any, elapsed_days: int,
                        *, event_logger: Callable[..., int]) -> dict[str, Any] | None:
    """Review branching responsibilities and coarse professional standing.

    Important: responsibilities are checked independently of standing. A Third-stage established disciple can
    become an instructor without first being promoted to Senior Disciple; a retainer can become horsemaster
    without becoming captain; a merchant can coordinate factors while still a local-scale proprietor.
    """
    row = ensure_role_career(conn, actor_id, kind, context)
    if not row:
        return None
    model = CAREER_MODELS[kind]
    stages = model["stages"]
    current_key = str(row["stage_key"])
    idx = next((i for i, st in enumerate(stages) if st[0] == current_key), None)
    exp = _loads(row["experience_json"], {})
    role_events = max(int(exp.get("role_events", 0)), _role_events(conn, actor_id))

    # Branching responsibility first. It can happen whether or not formal standing changes this review.
    responsibility_result = _review_responsibility_opportunity(
        conn, actor_id, kind, row, current_key, role_events, elapsed_days, event_logger=event_logger
    )

    if idx is None or idx >= len(stages) - 1:
        return responsibility_result
    next_key, next_name, _ = stages[idx + 1]
    eligible, reasons, readiness = _eligibility(conn, actor_id, kind, current_key, next_key, role_events)
    if not eligible:
        return responsibility_result

    day = _day(conn)
    # Coarse standing changes are deliberately rarer than new duties. They summarize durable social position;
    # they are not the engine's mechanism for giving someone interesting work.
    annual = .32
    if kind in {"longroad", "merchant"}:
        annual = .40
    if kind == "witness":
        annual = .28
    chance = min(.18, annual * max(1, int(elapsed_days)) / 365.0 * (.58 + .42 * readiness))
    rng = _rng(conn, actor_id, day, 5901 + idx * 17)
    if rng.random() >= chance:
        return responsibility_result

    # For merchant/Long Road this is recognition of durable scale/standing, not a vacancy-based office.
    actor_name = str(conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()[0])
    if kind in {"merchant", "longroad"}:
        accepted = True
    else:
        ambition = _drive(conn, actor_id, "ambition")
        loyalty = _drive(conn, actor_id, "loyalty")
        patience = _drive(conn, actor_id, "patience")
        pragmatism = _drive(conn, actor_id, "pragmatism")
        fit = .30 + .24 * ambition + .12 * patience + .12 * pragmatism
        if kind in {"martial_institution", "retainer", "witness"}:
            fit += .14 * loyalty
        accepted = rng.random() < max(.18, min(.86, fit))

    exp = _loads(row["experience_json"], {})
    exp["opportunities"] = int(exp.get("opportunities", 0)) + 1
    exp["last_opportunity_day"] = day
    if accepted:
        sid = int(conn.execute("SELECT id FROM career_stages WHERE track_id=? AND stage_key=?", (int(row["track_id"]), next_key)).fetchone()[0])
        advance_career_stage(conn, int(row["id"]), sid, day=day)
        exp["advancements"] = int(exp.get("advancements", 0)) + 1
        exp["last_advancement_day"] = day
        conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (_dumps(exp), int(row["id"])))
        _update_membership_role(conn, actor_id, kind, next_key)
        event_logger(day=day, event_type="career_advancement", title=f"{actor_name}: {next_name}",
                     summary=f"{actor_name}'s durable professional standing changed to {next_name} because of {', '.join(reasons)}. This standing change does not determine which appointments or specializations they hold.",
                     severity=2, source_actor_id=actor_id, target_actor_ids=(actor_id,),
                     location_id=conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()[0],
                     visibility="limited", rumorability=.10, reliability=.95)
        return {"type": "standing", "offered": True, "accepted": True, "from": current_key, "to": next_key, "reasons": reasons, "responsibility_result": responsibility_result}

    exp["declined_or_missed"] = int(exp.get("declined_or_missed", 0)) + 1
    conn.execute("UPDATE actor_careers SET experience_json=? WHERE id=?", (_dumps(exp), int(row["id"])))
    event_logger(day=day, event_type="career_opportunity", title=f"{actor_name}: {next_name} standing opportunity passed",
                 summary=f"A durable standing change became possible because of {', '.join(reasons)}, but it did not occur. Branching responsibilities remain independently available.",
                 severity=1, source_actor_id=actor_id, target_actor_ids=(actor_id,),
                 location_id=conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()[0],
                 visibility="limited", rumorability=.04, reliability=.95)
    return {"type": "standing", "offered": True, "accepted": False, "from": current_key, "to": next_key, "reasons": reasons, "responsibility_result": responsibility_result}
