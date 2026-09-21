from __future__ import annotations

"""TEACHECO / NONMERCHANT teaching ecology.

Teachers are ordinary people first. Existing teachers publish only spare capacity. If real demand
cannot find one, a teacher may be resolved from a pre-existing POPBACK identity. Three students
can make a persistent informal circle; a school exists only after a later explicit formalization
decision, never automatically from demand or profitability.
"""

import json
import sqlite3
from typing import Any

from .education import _set_competence_floor, create_program
from .person_ecology import resolve_background_person
from .seeking import register_offering


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, sort_keys=True, ensure_ascii=False)


def _competence(conn: sqlite3.Connection, actor_id: int, domain: str = "martial_instruction") -> float:
    r = conn.execute(
        """SELECT ac.score FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=? AND ac.specialty_key='' ORDER BY ac.id LIMIT 1""",
        (actor_id, domain),
    ).fetchone()
    return float(r[0]) if r else 0.0


def _capacity_for(competence: float, occupied: int) -> int:
    # Deliberately modest personal capacity. 60 teaching competence -> 3 places, preserving the
    # recovered Halric Sten calibration (two existing students, one spare place).
    base = max(1, min(6, 1 + int(max(0.0, competence) // 30.0)))
    return max(base, occupied)


def _independent_program(conn: sqlite3.Connection, teacher_actor_id: int, capacity: int) -> int:
    key = f"independent-martial-instruction:{teacher_actor_id}"
    row = conn.execute(
        "SELECT id FROM education_programs WHERE institution_actor_id IS NULL AND program_key=? AND status='active' ORDER BY id LIMIT 1",
        (key,),
    ).fetchone()
    if row:
        pid = int(row[0])
        conn.execute("UPDATE education_programs SET capacity=? WHERE id=?", (max(1,capacity),pid))
        return pid
    name = conn.execute("SELECT name FROM actors WHERE id=?", (teacher_actor_id,)).fetchone()
    return create_program(
        conn, key, f"Personal instruction — {name[0] if name else teacher_actor_id}",
        "martial_instruction", "advanced_instruction", duration_days=365, capacity=max(1,capacity),
        min_entry_score=0, min_teacher_score=1, completion_gain=3, max_score_from_program=70,
        review_cadence_days=30,
        metadata={"teacheco":True,"independent_teacher":True,"no_institution_implied":True},
    )


def refresh_teacher_market(conn: sqlite3.Connection) -> dict[str, int]:
    day = _day(conn)
    teacher_ids = {int(r[0]) for r in conn.execute("SELECT DISTINCT teacher_actor_id FROM teaching_relationships WHERE status='active'")}
    # Established teaching competence can identify a provider even before a named student happens
    # to be present, but does not imply the teacher is accepting students.
    teacher_ids |= {int(r[0]) for r in conn.execute(
        """SELECT ac.actor_id FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           JOIN actors a ON a.id=ac.actor_id WHERE d.domain_key='martial_instruction' AND ac.score>=45 AND a.actor_type='character' AND a.status='active'"""
    )}
    profiles = offerings = circles = 0
    for aid in sorted(teacher_ids):
        alive = conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'", (aid,)).fetchone()
        if not alive:
            continue
        occupied = int(conn.execute("SELECT COUNT(*) FROM teaching_relationships WHERE teacher_actor_id=? AND domain_key='martial_instruction' AND status='active'", (aid,)).fetchone()[0])
        comp = _competence(conn, aid)
        if comp <= 0:
            comp = _set_competence_floor(conn, aid, "martial_instruction", 60, source_kind="campaign")
        capacity = _capacity_for(comp, occupied)
        spare = max(0, capacity - occupied)
        discoverability = max(20.0, min(95.0, 30.0 + comp * .55))
        conn.execute(
            """INSERT INTO teaching_capacity_profiles(teacher_actor_id,domain_key,personal_capacity,occupied_places,spare_places,discoverability,last_review_day,metadata_json)
               VALUES (?,'martial_instruction',?,?,?,?,?,?) ON CONFLICT(teacher_actor_id) DO UPDATE SET
               personal_capacity=excluded.personal_capacity,occupied_places=excluded.occupied_places,spare_places=excluded.spare_places,
               discoverability=excluded.discoverability,last_review_day=excluded.last_review_day,metadata_json=excluded.metadata_json""",
            (aid,capacity,occupied,spare,discoverability,day,_j({"teacheco":True,"capacity_from_existing_person":True})),
        )
        profiles += 1
        pid = _independent_program(conn, aid, capacity)
        loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (aid,)).fetchone()[0]
        oid = register_offering(
            conn, aid, "instruction", "martial_instruction", "martial_instruction", location_id=int(loc) if loc is not None else None,
            quality=max(1.0,comp), capacity_per_30=float(capacity), availability=(100.0*spare/capacity if capacity else 0.0),
            public_reputation=max(25.0,min(95.0,comp)), visibility=discoverability, scarcity=max(20.0,70.0-spare*10.0),
            access_mode="appointment", metadata={"program_id":pid,"teacheco":True,"spare_places":spare},
        )
        offerings += 1
        if occupied >= 3:
            circle = conn.execute("SELECT id FROM informal_teaching_circles WHERE teacher_actor_id=? AND domain_key='martial_instruction' AND status='active' ORDER BY id LIMIT 1", (aid,)).fetchone()
            if circle:
                conn.execute("UPDATE informal_teaching_circles SET active_students=? WHERE id=?", (occupied,int(circle[0])))
            else:
                conn.execute(
                    """INSERT INTO informal_teaching_circles(teacher_actor_id,domain_key,started_day,active_students,status,metadata_json)
                       VALUES (?,'martial_instruction',?,?,'active',?)""",
                    (aid,day,occupied,_j({"formed_from_existing_teacher_student_relations":True,"not_a_school":True,"people_created":0})),
                )
                circles += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('teacheco_activation_version','1')")
    return {"teacher_capacity_profiles":profiles,"teacher_offerings":offerings,"informal_teaching_circles_created":circles}


def ensure_provider_for_seek_intent(conn: sqlite3.Connection, intent_id: int) -> int | None:
    """Resolve a provider only when an actual instruction seeker has no discoverable provider."""
    intent = conn.execute("SELECT * FROM actor_seek_intents WHERE id=?", (intent_id,)).fetchone()
    if not intent or str(intent["need_kind"]) != "instruction" or str(intent["domain_key"]) != "martial_instruction":
        return None
    seeker = int(intent["seeker_actor_id"])
    locrow = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (seeker,)).fetchone()
    loc = int(locrow[0]) if locrow and locrow[0] is not None else None
    if loc is None:
        return None
    aid = resolve_background_person(
        conn, reason=f"real instruction demand from actor {seeker} revealed a pre-existing local teacher",
        location_id=loc, occupation_domains=("teacher","soldier","artisan","labor"), min_age=24, max_age=75,
        require_open_core=True, required_stage="First", teaching_weight=1.0, command_weight=.15,
        subtype="Independent martial teacher",
    )
    if aid is None:
        return None
    score = _set_competence_floor(conn, aid, "martial_instruction", 55, source_kind="crystallization")
    # This competence floor represents the profession for which the pre-profiled person was selected;
    # it does not alter Stage/core or population identity.
    refresh_teacher_market(conn)
    row = conn.execute(
        "SELECT id FROM seekable_offerings WHERE provider_actor_id=? AND offer_kind='instruction' AND domain_key='martial_instruction' AND status='active' ORDER BY id LIMIT 1",
        (aid,),
    ).fetchone()
    return int(row[0]) if row else None


def formalize_teaching_circle(conn: sqlite3.Connection, circle_id: int, deciding_actor_id: int, *, proposed_name: str | None = None) -> int:
    """Explicit voluntary decision boundary between an informal circle and a school candidate."""
    day = _day(conn)
    circle = conn.execute("SELECT * FROM informal_teaching_circles WHERE id=? AND status='active'", (circle_id,)).fetchone()
    if not circle:
        raise ValueError("teaching circle is not active")
    if int(circle["teacher_actor_id"]) != int(deciding_actor_id):
        raise ValueError("only the teacher can formalize this personal circle")
    students = [int(r[0]) for r in conn.execute("SELECT student_actor_id FROM teaching_relationships WHERE teacher_actor_id=? AND domain_key=? AND status='active' ORDER BY student_actor_id", (deciding_actor_id,str(circle["domain_key"]))).fetchall()]
    active_students = len(students)
    conn.execute("UPDATE informal_teaching_circles SET active_students=? WHERE id=?", (active_students,circle_id))
    if day - int(circle["started_day"]) < 365:
        raise ValueError("circle has not persisted for a year")
    if active_students < 3:
        raise ValueError("circle does not have three active students")
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (deciding_actor_id,)).fetchone()[0]
    from .resolution_controller import create_institution_candidate, update_institution_candidate
    evidence = [{"kind":"voluntary_formalization_decision","teacher_actor_id":deciding_actor_id,"circle_id":circle_id,"persistence_days":day-int(circle["started_day"]),"active_students":active_students}]
    resources = {"preexisting_organization":False,"business_age_days":day-int(circle["started_day"]),"active_staff":active_students,"branch_count":0,"completed_trade_contracts":0,"distinct_trade_locations":0,"institutional_form":"martial_school"}
    cid = create_institution_candidate(
        conn, "martial school", location_id=int(loc) if loc is not None else None, founder_actor_id=deciding_actor_id,
        proposed_name=proposed_name, significance_score=38.0, resources=resources,
        participants=[deciding_actor_id,*students], evidence=evidence, day=day,
    )
    # Generic candidate threshold is sufficient for a genuine three-student year-old school circle.
    update_institution_candidate(conn,cid,significance_score=38.0,resources=resources,day=day)
    meta=json.loads(circle["metadata_json"] or "{}"); meta.update({"formalization_decision_day":day,"candidate_id":cid,"people_created":0})
    conn.execute("UPDATE informal_teaching_circles SET status='formalized',metadata_json=? WHERE id=?", (_j(meta),circle_id))
    return cid
