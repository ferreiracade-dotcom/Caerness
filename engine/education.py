from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _actor(conn: sqlite3.Connection, actor_id: int, *, institution: bool | None = None, living: bool = False) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not r:
        raise ValueError("Unknown actor")
    if institution is True and str(r["actor_type"]) != "institution":
        raise ValueError("Actor must be an institution")
    if institution is False and str(r["actor_type"]) != "character":
        raise ValueError("Actor must be a character")
    if living and str(r["status"]).lower() in ("dead", "deceased"):
        raise ValueError("Actor is deceased")
    return r


def _domain_id(conn: sqlite3.Connection, domain_key: str, *, create: bool = True) -> int | None:
    r = conn.execute("SELECT id FROM competence_domains WHERE domain_key=?", (domain_key,)).fetchone()
    if r:
        return int(r[0])
    if not create:
        return None
    conn.execute("INSERT INTO competence_domains(domain_key,name,description) VALUES (?,?,?)", (domain_key, domain_key.replace('_',' ').title(), "Campaign-defined competence domain."))
    return int(conn.execute("SELECT id FROM competence_domains WHERE domain_key=?", (domain_key,)).fetchone()[0])


def competence_score(conn: sqlite3.Connection, actor_id: int, domain_key: str) -> float:
    did = _domain_id(conn, domain_key, create=False)
    if did is None:
        return 0.0
    r = conn.execute("SELECT MAX(score) FROM actor_competence WHERE actor_id=? AND domain_id=?", (actor_id, did)).fetchone()
    return float(r[0] or 0.0)


def _set_competence_floor(conn: sqlite3.Connection, actor_id: int, domain_key: str, score: float, *, source_kind: str = "career") -> float:
    did = _domain_id(conn, domain_key, create=True)
    row = conn.execute("SELECT id,score FROM actor_competence WHERE actor_id=? AND domain_id=? AND specialty_key=''", (actor_id, did)).fetchone()
    day = _day(conn)
    score = max(0.0, min(100.0, float(score)))
    if row:
        new = max(float(row["score"]), score)
        conn.execute("UPDATE actor_competence SET score=?,source_kind=?,updated_day=? WHERE id=?", (new, source_kind, day, row["id"]))
        return new
    conn.execute("INSERT INTO actor_competence(actor_id,domain_id,score,source_kind,updated_day) VALUES (?,?,?,?,?)", (actor_id, did, score, source_kind, day))
    return score


def _history(conn: sqlite3.Connection, event_kind: str, summary: str, **ids: Any) -> int:
    day = _day(conn)
    cols = {"actor_id": None, "teacher_actor_id": None, "institution_actor_id": None, "program_id": None, "line_id": None, "asset_id": None}
    cols.update({k:v for k,v in ids.items() if k in cols})
    cur = conn.execute("""INSERT INTO education_history(day,event_kind,actor_id,teacher_actor_id,institution_actor_id,program_id,line_id,asset_id,summary,detail_json)
                          VALUES (?,?,?,?,?,?,?,?,?,?)""",
                       (day,event_kind,cols["actor_id"],cols["teacher_actor_id"],cols["institution_actor_id"],cols["program_id"],cols["line_id"],cols["asset_id"],summary,json.dumps(ids.get("detail",{}),sort_keys=True)))
    return int(cur.lastrowid)


def create_program(conn: sqlite3.Connection, program_key: str, name: str, domain_key: str, program_kind: str, *,
                   institution_actor_id: int | None = None, duration_days: int = 365, capacity: int = 10,
                   min_entry_score: float = 0, min_teacher_score: float = 0, completion_gain: float = 5,
                   max_score_from_program: float = 70, certificate_key: str | None = None,
                   lineage_key: str | None = None, review_cadence_days: int = 30,
                   metadata: dict[str,Any] | None = None) -> int:
    if institution_actor_id is not None:
        _actor(conn, institution_actor_id, institution=True)
    _domain_id(conn, domain_key, create=True)
    if duration_days < 1 or capacity < 1:
        raise ValueError("Duration and capacity must be positive")
    day = _day(conn)
    cur = conn.execute("""INSERT INTO education_programs(institution_actor_id,program_key,name,domain_key,program_kind,duration_days,capacity,
                         min_entry_score,min_teacher_score,completion_gain,max_score_from_program,certificate_key,lineage_key,status,created_day,review_cadence_days,metadata_json)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
                       (institution_actor_id,program_key,name,domain_key,program_kind,duration_days,capacity,min_entry_score,min_teacher_score,
                        completion_gain,max_score_from_program,certificate_key,lineage_key,day,review_cadence_days,json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def create_teaching_relationship(conn: sqlite3.Connection, teacher_actor_id: int, student_actor_id: int, relation_kind: str, domain_key: str, *,
                                 institution_actor_id: int | None = None, responsibility: float = 50, notes: str | None = None) -> int:
    _actor(conn, teacher_actor_id, institution=False, living=True); _actor(conn, student_actor_id, institution=False, living=True)
    if teacher_actor_id == student_actor_id:
        raise ValueError("An actor cannot teach themself")
    if institution_actor_id is not None:
        _actor(conn, institution_actor_id, institution=True)
    if competence_score(conn, teacher_actor_id, domain_key) <= 0:
        raise ValueError("Teacher has no established competence in this domain")
    day = _day(conn)
    cur = conn.execute("""INSERT INTO teaching_relationships(teacher_actor_id,student_actor_id,relation_kind,domain_key,institution_actor_id,responsibility,start_day,status,notes)
                          VALUES (?,?,?,?,?,?,?,'active',?)""", (teacher_actor_id,student_actor_id,relation_kind,domain_key,institution_actor_id,responsibility,day,notes))
    _history(conn,"teaching_relationship_started",f"Teaching relationship began in {domain_key}.",actor_id=student_actor_id,teacher_actor_id=teacher_actor_id,institution_actor_id=institution_actor_id)
    return int(cur.lastrowid)


def end_teaching_relationship(conn: sqlite3.Connection, relationship_id: int, *, status: str = "ended", notes: str | None = None) -> None:
    if status not in ("ended","interrupted","repudiated"):
        raise ValueError("Invalid terminal teaching status")
    r=conn.execute("SELECT * FROM teaching_relationships WHERE id=?",(relationship_id,)).fetchone()
    if not r or r["status"]!='active':
        raise ValueError("Teaching relationship is not active")
    day=_day(conn)
    conn.execute("UPDATE teaching_relationships SET status=?,end_day=?,notes=COALESCE(?,notes) WHERE id=?",(status,day,notes,relationship_id))
    _history(conn,"teaching_relationship_ended",f"Teaching relationship ended ({status}).",actor_id=r["student_actor_id"],teacher_actor_id=r["teacher_actor_id"],institution_actor_id=r["institution_actor_id"])


def create_knowledge_asset(conn: sqlite3.Connection, title: str, asset_kind: str, domain_key: str, *, institution_actor_id: int | None = None,
                           lineage_key: str | None = None, access_tier: str = "limited", completeness: float = 1,
                           teachability: float = 0.5, preservation_mode: str = "documented", loss_threshold_days: int | None = None,
                           metadata: dict[str,Any] | None = None) -> int:
    if institution_actor_id is not None: _actor(conn,institution_actor_id,institution=True)
    _domain_id(conn,domain_key,create=True)
    day=_day(conn)
    cur=conn.execute("""INSERT INTO knowledge_assets(title,asset_kind,domain_key,institution_actor_id,lineage_key,access_tier,completeness,teachability,preservation_mode,loss_threshold_days,status,created_day,last_review_day,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,'extant',?,?,?)""",
                     (title,asset_kind,domain_key,institution_actor_id,lineage_key,access_tier,completeness,teachability,preservation_mode,loss_threshold_days,day,day,json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def add_knowledge_custody(conn: sqlite3.Connection, asset_id: int, custody_kind: str, *, actor_id: int | None = None,
                          institution_actor_id: int | None = None, notes: str | None = None) -> int:
    if not conn.execute("SELECT 1 FROM knowledge_assets WHERE id=?",(asset_id,)).fetchone(): raise ValueError("Unknown knowledge asset")
    if actor_id is not None: _actor(conn,actor_id,living=True)
    if institution_actor_id is not None: _actor(conn,institution_actor_id,institution=True)
    if actor_id is None and institution_actor_id is None: raise ValueError("Custody requires an actor or institution")
    cur=conn.execute("INSERT INTO knowledge_custody(asset_id,actor_id,institution_actor_id,custody_kind,start_day,status,notes) VALUES (?,?,?,?,?,'active',?)",
                     (asset_id,actor_id,institution_actor_id,custody_kind,_day(conn),notes))
    return int(cur.lastrowid)


def grant_knowledge_access(conn: sqlite3.Connection, asset_id: int, actor_id: int, access_level: str = "study", *, granted_by_actor_id: int | None = None, notes: str | None = None) -> None:
    asset=conn.execute("SELECT * FROM knowledge_assets WHERE id=?",(asset_id,)).fetchone()
    if not asset or asset["status"] not in ("extant","endangered"): raise ValueError("Knowledge asset is not available")
    _actor(conn,actor_id,living=True)
    if granted_by_actor_id is not None: _actor(conn,granted_by_actor_id,living=True)
    conn.execute("UPDATE knowledge_access SET status='revoked',revoked_day=? WHERE asset_id=? AND actor_id=? AND status='active'",(_day(conn),asset_id,actor_id))
    conn.execute("INSERT INTO knowledge_access(asset_id,actor_id,access_level,granted_by_actor_id,granted_day,status,notes) VALUES (?,?,?,?,?,'active',?)",
                 (asset_id,actor_id,access_level,granted_by_actor_id,_day(conn),notes))


def revoke_knowledge_access(conn: sqlite3.Connection, asset_id: int, actor_id: int) -> None:
    cur=conn.execute("UPDATE knowledge_access SET status='revoked',revoked_day=? WHERE asset_id=? AND actor_id=? AND status='active'",(_day(conn),asset_id,actor_id))
    if cur.rowcount==0: raise ValueError("No active access to revoke")


def link_program_knowledge(conn: sqlite3.Connection, program_id: int, asset_id: int, requirement_kind: str = "supporting") -> None:
    p=conn.execute("SELECT domain_key FROM education_programs WHERE id=?",(program_id,)).fetchone(); a=conn.execute("SELECT domain_key FROM knowledge_assets WHERE id=?",(asset_id,)).fetchone()
    if not p or not a: raise ValueError("Unknown program or asset")
    if str(p[0])!=str(a[0]): raise ValueError("Program and knowledge asset domains must match")
    conn.execute("INSERT OR REPLACE INTO program_knowledge_assets(program_id,asset_id,requirement_kind) VALUES (?,?,?)",(program_id,asset_id,requirement_kind))


def create_transmission_line(conn: sqlite3.Connection, lineage_key: str, name: str, domain_key: str, *, institution_actor_id: int | None = None,
                             parent_line_id: int | None = None, founding_teacher_actor_id: int | None = None,
                             interpretation_summary: str | None = None, vitality: float = 70, fragility_per_year: float = 8) -> int:
    if institution_actor_id is not None: _actor(conn,institution_actor_id,institution=True)
    if founding_teacher_actor_id is not None: _actor(conn,founding_teacher_actor_id,institution=False,living=True)
    if parent_line_id is not None and not conn.execute("SELECT 1 FROM transmission_lines WHERE id=?",(parent_line_id,)).fetchone(): raise ValueError("Unknown parent line")
    day=_day(conn)
    cur=conn.execute("""INSERT INTO transmission_lines(institution_actor_id,lineage_key,name,domain_key,parent_line_id,founding_teacher_actor_id,interpretation_summary,vitality,fragility_per_year,status,created_day,last_review_day)
                        VALUES (?,?,?,?,?,?,?,?,?,'active',?,?)""",(institution_actor_id,lineage_key,name,domain_key,parent_line_id,founding_teacher_actor_id,interpretation_summary,vitality,fragility_per_year,day,day))
    lid=int(cur.lastrowid)
    if founding_teacher_actor_id is not None:
        conn.execute("INSERT INTO actor_transmissions(line_id,actor_id,relation_kind,depth,joined_day,status) VALUES (?,?, 'teacher',100,?,'active')",(lid,founding_teacher_actor_id,day))
    return lid


def set_actor_transmission(conn: sqlite3.Connection, line_id: int, actor_id: int, relation_kind: str, *, depth: float = 0) -> None:
    line=conn.execute("SELECT * FROM transmission_lines WHERE id=?",(line_id,)).fetchone()
    if not line or line["status"]=='lost': raise ValueError("Transmission line unavailable")
    _actor(conn,actor_id,institution=False,living=True)
    day=_day(conn)
    conn.execute("""INSERT INTO actor_transmissions(line_id,actor_id,relation_kind,depth,joined_day,status) VALUES (?,?,?,?,?,'active')
                    ON CONFLICT(line_id,actor_id) DO UPDATE SET relation_kind=excluded.relation_kind,depth=excluded.depth,left_day=NULL,status='active'""",
                 (line_id,actor_id,relation_kind,depth,day))


def enroll(conn: sqlite3.Connection, actor_id: int, program_id: int, *, primary_teacher_actor_id: int | None = None, practice_quality: float = 1.0,
           metadata: dict[str,Any] | None = None) -> int:
    _actor(conn,actor_id,institution=False,living=True)
    p=conn.execute("SELECT * FROM education_programs WHERE id=?",(program_id,)).fetchone()
    if not p or p["status"]!='active': raise ValueError("Program is not active")
    active=int(conn.execute("SELECT COUNT(*) FROM education_enrollments WHERE program_id=? AND status='active'",(program_id,)).fetchone()[0])
    if active>=int(p["capacity"]): raise ValueError("Program is at capacity")
    if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND program_id=? AND status='completed' LIMIT 1",(actor_id,program_id)).fetchone():
        raise ValueError("Actor has already completed this program")
    if competence_score(conn,actor_id,str(p["domain_key"])) < float(p["min_entry_score"]): raise ValueError("Actor does not meet program entry competence")
    if primary_teacher_actor_id is not None:
        _actor(conn,primary_teacher_actor_id,institution=False,living=True)
        if competence_score(conn,primary_teacher_actor_id,str(p["domain_key"])) < float(p["min_teacher_score"]): raise ValueError("Teacher does not meet program teaching competence")
    elif float(p["min_teacher_score"])>0:
        raise ValueError("This program requires a qualified primary teacher")
    # Required student access must already exist; a manual never teaches itself merely because it exists.
    for req in conn.execute("SELECT pka.*,ka.status FROM program_knowledge_assets pka JOIN knowledge_assets ka ON ka.id=pka.asset_id WHERE pka.program_id=?",(program_id,)).fetchall():
        if req["requirement_kind"]=='required_access':
            if not conn.execute("SELECT 1 FROM knowledge_access WHERE asset_id=? AND actor_id=? AND status='active'",(req["asset_id"],actor_id)).fetchone():
                raise ValueError("Required knowledge access is missing")
        if req["requirement_kind"]=='required_teacher_access':
            if primary_teacher_actor_id is None or not conn.execute("SELECT 1 FROM knowledge_access WHERE asset_id=? AND actor_id=? AND status='active' AND access_level IN ('teach','keeper')",(req["asset_id"],primary_teacher_actor_id)).fetchone():
                raise ValueError("Teacher lacks required authority/access for this inheritance")
    day=_day(conn); cadence=int(p["review_cadence_days"])
    cur=conn.execute("""INSERT INTO education_enrollments(actor_id,program_id,primary_teacher_actor_id,started_day,progress_days,practice_quality,status,last_review_day,next_review_day,metadata_json)
                        VALUES (?,?,?,?,0,?,'active',?,?,?)""",(actor_id,program_id,primary_teacher_actor_id,day,practice_quality,day,day+cadence,json.dumps(metadata or {},sort_keys=True)))
    _history(conn,"enrolled",f"Enrolled in {p['name']}.",actor_id=actor_id,teacher_actor_id=primary_teacher_actor_id,institution_actor_id=p["institution_actor_id"],program_id=program_id)
    return int(cur.lastrowid)


def pause_enrollment(conn: sqlite3.Connection, enrollment_id: int, reason: str) -> None:
    r=conn.execute("SELECT * FROM education_enrollments WHERE id=?",(enrollment_id,)).fetchone()
    if not r or r["status"]!='active': raise ValueError("Enrollment is not active")
    conn.execute("UPDATE education_enrollments SET status='paused',interruption_reason=?,next_review_day=? WHERE id=?",(reason,_day(conn)+30,enrollment_id))


def resume_enrollment(conn: sqlite3.Connection, enrollment_id: int, *, teacher_actor_id: int | None = None) -> None:
    r=conn.execute("SELECT e.*,p.domain_key,p.min_teacher_score,p.review_cadence_days,p.status AS program_status FROM education_enrollments e JOIN education_programs p ON p.id=e.program_id WHERE e.id=?",(enrollment_id,)).fetchone()
    if not r or r["status"]!='paused' or r["program_status"]!='active': raise ValueError("Enrollment cannot be resumed")
    teacher=teacher_actor_id if teacher_actor_id is not None else r["primary_teacher_actor_id"]
    if float(r["min_teacher_score"])>0:
        if teacher is None: raise ValueError("A qualified teacher is required")
        _actor(conn,int(teacher),institution=False,living=True)
        if competence_score(conn,int(teacher),str(r["domain_key"])) < float(r["min_teacher_score"]): raise ValueError("Teacher is not qualified")
    day=_day(conn)
    conn.execute("UPDATE education_enrollments SET status='active',primary_teacher_actor_id=?,interruption_reason=NULL,last_review_day=?,next_review_day=? WHERE id=?",(teacher,day,day+int(r["review_cadence_days"]),enrollment_id))


def withdraw_enrollment(conn: sqlite3.Connection, enrollment_id: int, reason: str | None = None) -> None:
    r=conn.execute("SELECT * FROM education_enrollments WHERE id=?",(enrollment_id,)).fetchone()
    if not r or r["status"] not in ('active','paused'): raise ValueError("Enrollment is not current")
    conn.execute("UPDATE education_enrollments SET status='withdrawn',interruption_reason=?,next_review_day=? WHERE id=?",(reason,_day(conn),enrollment_id))


def configure_reproduction(conn: sqlite3.Connection, institution_actor_id: int, *, recruitment_capacity: float = 50, training_capacity: float = 50,
                           instructor_depth: float = 50, archival_resilience: float = 50, review_cadence_days: int = 90,
                           metadata: dict[str,Any] | None = None) -> None:
    _actor(conn,institution_actor_id,institution=True)
    day=_day(conn)
    conn.execute("""INSERT INTO institution_reproduction_profiles(institution_actor_id,recruitment_capacity,training_capacity,instructor_depth,archival_resilience,pipeline_health,continuity_pressure,last_review_day,next_review_day,review_cadence_days,metadata_json)
                    VALUES (?,?,?,?,?,50,0,?,?,?,?) ON CONFLICT(institution_actor_id) DO UPDATE SET recruitment_capacity=excluded.recruitment_capacity,
                    training_capacity=excluded.training_capacity,instructor_depth=excluded.instructor_depth,archival_resilience=excluded.archival_resilience,
                    next_review_day=excluded.next_review_day,review_cadence_days=excluded.review_cadence_days,metadata_json=excluded.metadata_json""",
                 (institution_actor_id,recruitment_capacity,training_capacity,instructor_depth,archival_resilience,day,day+review_cadence_days,review_cadence_days,json.dumps(metadata or {},sort_keys=True)))


def set_successor_candidate(conn: sqlite3.Connection, institution_actor_id: int, actor_id: int, role_key: str, *, readiness: float = 0,
                            legitimacy: float = 50, transmission_depth: float = 0) -> int:
    _actor(conn,institution_actor_id,institution=True); _actor(conn,actor_id,institution=False,living=True)
    day=_day(conn)
    conn.execute("""INSERT INTO institutional_successor_candidates(institution_actor_id,actor_id,role_key,readiness,legitimacy,transmission_depth,status,created_day,updated_day)
                    VALUES (?,?,?,?,?,?,'candidate',?,?) ON CONFLICT(institution_actor_id,actor_id,role_key) DO UPDATE SET readiness=excluded.readiness,
                    legitimacy=excluded.legitimacy,transmission_depth=excluded.transmission_depth,status=CASE WHEN institutional_successor_candidates.status='chosen' THEN 'chosen' ELSE 'candidate' END,updated_day=excluded.updated_day""",
                 (institution_actor_id,actor_id,role_key,readiness,legitimacy,transmission_depth,day,day))
    return int(conn.execute("SELECT id FROM institutional_successor_candidates WHERE institution_actor_id=? AND actor_id=? AND role_key=?",(institution_actor_id,actor_id,role_key)).fetchone()[0])


def choose_successor_candidate(conn: sqlite3.Connection, candidate_id: int) -> None:
    r=conn.execute("SELECT * FROM institutional_successor_candidates WHERE id=?",(candidate_id,)).fetchone()
    if not r or r["status"] not in ('candidate','eligible'): raise ValueError("Candidate is not available")
    _actor(conn,int(r["actor_id"]),living=True)
    # This records the choice only; no office, career, or political ruler field is silently changed.
    conn.execute("UPDATE institutional_successor_candidates SET status='chosen',updated_day=? WHERE id=?",(_day(conn),candidate_id))
    _history(conn,"successor_designated",f"Successor candidate chosen for role {r['role_key']}.",actor_id=r["actor_id"],institution_actor_id=r["institution_actor_id"])


def _teacher_ok(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    needed=float(row["min_teacher_score"])
    if needed<=0: return True
    tid=row["primary_teacher_actor_id"]
    if tid is None: return False
    a=conn.execute("SELECT status FROM actors WHERE id=?",(tid,)).fetchone()
    if not a or str(a[0]).lower() in ('dead','deceased'): return False
    return competence_score(conn,int(tid),str(row["domain_key"]))>=needed


def _requirements_still_met(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    for req in conn.execute("SELECT * FROM program_knowledge_assets WHERE program_id=?",(row["program_id"],)).fetchall():
        asset=conn.execute("SELECT status FROM knowledge_assets WHERE id=?",(req["asset_id"],)).fetchone()
        if not asset or asset[0] not in ('extant','endangered'): return False
        if req["requirement_kind"]=='required_access' and not conn.execute("SELECT 1 FROM knowledge_access WHERE asset_id=? AND actor_id=? AND status='active'",(req["asset_id"],row["actor_id"])).fetchone(): return False
        if req["requirement_kind"]=='required_teacher_access':
            tid=row["primary_teacher_actor_id"]
            if tid is None or not conn.execute("SELECT 1 FROM knowledge_access WHERE asset_id=? AND actor_id=? AND status='active' AND access_level IN ('teach','keeper')",(req["asset_id"],tid)).fetchone(): return False
    return True


def _complete_enrollment(conn: sqlite3.Connection, row: sqlite3.Row, day: int, event_logger: Callable[...,int] | None) -> None:
    before=competence_score(conn,int(row["actor_id"]),str(row["domain_key"]))
    target=min(float(row["max_score_from_program"]),before+float(row["completion_gain"]))
    if row["primary_teacher_actor_id"] is not None:
        # A teacher can transmit what they actually know; one course cannot manufacture competence beyond its living teacher.
        target=min(target,competence_score(conn,int(row["primary_teacher_actor_id"]),str(row["domain_key"])))
    after=_set_competence_floor(conn,int(row["actor_id"]),str(row["domain_key"]),target,source_kind='career')
    conn.execute("UPDATE education_enrollments SET status='completed',completed_day=?,progress_days=?,last_review_day=?,next_review_day=? WHERE id=?",(day,max(float(row["progress_days"]),float(row["duration_days"])),day,day,row["id"]))
    if row["certificate_key"]:
        existing=conn.execute("SELECT id FROM professional_certifications WHERE actor_id=? AND certificate_key=? AND status='active'",(row["actor_id"],row["certificate_key"])).fetchone()
        if existing:
            conn.execute("UPDATE professional_certifications SET level=?,institution_actor_id=?,granted_day=? WHERE id=?",(after,row["institution_actor_id"],day,existing[0]))
        else:
            conn.execute("""INSERT INTO professional_certifications(actor_id,domain_key,certificate_key,institution_actor_id,level,granted_day,status)
                            VALUES (?,?,?,?,?,?,'active')""",(row["actor_id"],row["domain_key"],row["certificate_key"],row["institution_actor_id"],after,day))
    if row["lineage_key"]:
        line=conn.execute("SELECT id FROM transmission_lines WHERE lineage_key=? AND (institution_actor_id IS ? OR institution_actor_id=?) ORDER BY id LIMIT 1",(row["lineage_key"],row["institution_actor_id"],row["institution_actor_id"])).fetchone()
        if line:
            set_actor_transmission(conn,int(line[0]),int(row["actor_id"]),'student',depth=min(100,max(10,after)))
    _history(conn,"program_completed",f"Completed {row['name']}; competence changed from {before:.1f} to {after:.1f}.",actor_id=row["actor_id"],teacher_actor_id=row["primary_teacher_actor_id"],institution_actor_id=row["institution_actor_id"],program_id=row["program_id"])
    if row["primary_teacher_actor_id"] is not None:
        prog_meta = conn.execute("SELECT metadata_json FROM education_programs WHERE id=?", (row["program_id"],)).fetchone()
        try:
            parsed_meta = json.loads(prog_meta[0]) if prog_meta and prog_meta[0] else {}
        except Exception:
            parsed_meta = {}
        if parsed_meta.get("seek01") and parsed_meta.get("personal_teacher_actor_id") == int(row["primary_teacher_actor_id"]):
            # Successful students create reputation; competence alone never does.  The increment is
            # bounded so one pupil cannot make an unknown hermit continent-famous overnight.
            from .reputation import adjust as adjust_social_reputation
            gain = max(0.0, float(after) - float(before))
            adjust_social_reputation(
                conn, 'actor', int(row["primary_teacher_actor_id"]), 'martial_instruction',
                min(3.0, .45 + gain * .16), day=day,
                metadata={"source": "personal_student_completion", "last_student_actor_id": int(row["actor_id"]), "program_id": int(row["program_id"])},
            )
    if event_logger:
        event_logger(day=day,event_type='education:completion',title='Training completed',summary=f"{row['name']} was completed.",severity=1,source_actor_id=row["actor_id"])


def _resolve_enrollments(conn: sqlite3.Connection, day: int, event_logger: Callable[...,int] | None = None) -> int:
    rows=conn.execute("""SELECT e.*,p.name,p.domain_key,p.duration_days,p.min_teacher_score,p.completion_gain,p.max_score_from_program,p.certificate_key,p.lineage_key,p.institution_actor_id,p.review_cadence_days,p.status AS program_status
                         FROM education_enrollments e JOIN education_programs p ON p.id=e.program_id
                         WHERE e.status='active' AND e.next_review_day<=? ORDER BY e.next_review_day,e.id""",(day,)).fetchall()
    count=0
    for r in rows:
        a=conn.execute("SELECT status FROM actors WHERE id=?",(r["actor_id"],)).fetchone()
        if not a or str(a[0]).lower() in ('dead','deceased'):
            conn.execute("UPDATE education_enrollments SET status='deceased',interruption_reason='student_deceased',last_review_day=?,next_review_day=? WHERE id=?",(day,day,r["id"])); count+=1; continue
        if r["program_status"]!='active':
            conn.execute("UPDATE education_enrollments SET status='paused',interruption_reason='program_unavailable',last_review_day=?,next_review_day=? WHERE id=?",(day,day+int(r["review_cadence_days"]),r["id"])); count+=1; continue
        if not _teacher_ok(conn,r):
            conn.execute("UPDATE education_enrollments SET status='paused',interruption_reason='teacher_unavailable_or_unqualified',last_review_day=?,next_review_day=? WHERE id=?",(day,day+int(r["review_cadence_days"]),r["id"])); count+=1; continue
        if not _requirements_still_met(conn,r):
            conn.execute("UPDATE education_enrollments SET status='paused',interruption_reason='required_knowledge_unavailable',last_review_day=?,next_review_day=? WHERE id=?",(day,day+int(r["review_cadence_days"]),r["id"])); count+=1; continue
        elapsed=max(0,day-int(r["last_review_day"])); teacher_factor=1.0
        if r["primary_teacher_actor_id"] is not None:
            teacher_factor=max(0.65,min(1.25,0.65+competence_score(conn,int(r["primary_teacher_actor_id"]),str(r["domain_key"]))/170.0))
        progress=float(r["progress_days"])+elapsed*float(r["practice_quality"])*teacher_factor
        if progress+1e-9>=float(r["duration_days"]):
            rr=dict(r); rr["progress_days"]=progress
            # sqlite Row expected in complete; use lightweight mapping via namespace-compatible dict accesses.
            class M(dict):
                __getattr__=dict.__getitem__
            _complete_enrollment(conn,M(rr),day,event_logger)
        else:
            conn.execute("UPDATE education_enrollments SET progress_days=?,last_review_day=?,next_review_day=? WHERE id=?",(progress,day,day+int(r["review_cadence_days"]),r["id"]))
        count+=1
    return count


def _resolve_teaching_deaths(conn: sqlite3.Connection, day: int) -> int:
    rows=conn.execute("""SELECT tr.* FROM teaching_relationships tr JOIN actors a ON a.id=tr.teacher_actor_id
                         WHERE tr.status='active' AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows:
        conn.execute("UPDATE teaching_relationships SET status='interrupted',end_day=?,notes=COALESCE(notes,'Teacher died.') WHERE id=?",(day,r["id"]))
    return len(rows)


def _resolve_custody_deaths(conn: sqlite3.Connection, day: int) -> int:
    rows=conn.execute("""SELECT kc.* FROM knowledge_custody kc JOIN actors a ON a.id=kc.actor_id
                         WHERE kc.status='active' AND kc.actor_id IS NOT NULL AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows: conn.execute("UPDATE knowledge_custody SET status='ended',end_day=? WHERE id=?",(day,r["id"]))
    return len(rows)


def _resolve_assets(conn: sqlite3.Connection, day: int) -> int:
    count=0
    for a in conn.execute("SELECT * FROM knowledge_assets WHERE status IN ('extant','endangered','inaccessible') AND last_review_day<?",(day,)).fetchall():
        # Institutional/archive custody counts without a living character. Personal custody requires a living actor.
        custodians=conn.execute("""SELECT kc.actor_id,kc.institution_actor_id,ac.status AS actor_status,ai.status AS inst_status
                                   FROM knowledge_custody kc LEFT JOIN actors ac ON ac.id=kc.actor_id LEFT JOIN actors ai ON ai.id=kc.institution_actor_id
                                   WHERE kc.asset_id=? AND kc.status='active'""",(a["id"],)).fetchall()
        viable=False
        for c in custodians:
            if c["institution_actor_id"] is not None and str(c["inst_status"] or '').lower() not in ('dead','deceased','dissolved'): viable=True
            if c["actor_id"] is not None and str(c["actor_status"] or '').lower() not in ('dead','deceased'): viable=True
        mode=str(a["preservation_mode"])
        status=str(a["status"]); endangered=a["endangered_since_day"]
        if viable:
            status='extant'; endangered=None
        elif mode in ('oral','embodied','site_bound'):
            if endangered is None: endangered=day
            status='endangered'
            threshold=a["loss_threshold_days"]
            if threshold is not None and day-int(endangered)>=int(threshold): status='lost'
        else:
            status='inaccessible' if not viable else 'extant'
        conn.execute("UPDATE knowledge_assets SET status=?,endangered_since_day=?,last_review_day=? WHERE id=?",(status,endangered,day,a["id"]))
        if status=='lost' and a["status"]!='lost': _history(conn,"knowledge_lost",f"Knowledge asset '{a['title']}' became lost after its transmission/custody failed.",asset_id=a["id"],institution_actor_id=a["institution_actor_id"])
        count+=1
    return count


def _resolve_lines(conn: sqlite3.Connection, day: int) -> int:
    count=0
    for line in conn.execute("SELECT * FROM transmission_lines WHERE status IN ('active','fragile','dormant') AND last_review_day<?",(day,)).fetchall():
        elapsed=day-int(line["last_review_day"])
        living=conn.execute("""SELECT at.relation_kind,at.depth FROM actor_transmissions at JOIN actors a ON a.id=at.actor_id
                               WHERE at.line_id=? AND at.status='active' AND lower(a.status) NOT IN ('dead','deceased') AND at.relation_kind IN ('teacher','inheritor','keeper')""",(line["id"],)).fetchall()
        vitality=float(line["vitality"]); dormant_since=line["dormant_since_day"]
        if living:
            vitality=min(100.0,vitality+elapsed/365.0*3.0); dormant_since=None
        else:
            vitality=max(0.0,vitality-float(line["fragility_per_year"])*elapsed/365.0)
            if dormant_since is None: dormant_since=day
        status='active' if vitality>=40 and living else 'fragile' if vitality>0 and living else 'dormant'
        conn.execute("UPDATE transmission_lines SET vitality=?,status=?,dormant_since_day=?,last_review_day=? WHERE id=?",(vitality,status,dormant_since,day,line["id"]))
        count+=1
    return count


def _resolve_transmission_deaths(conn: sqlite3.Connection, day: int) -> int:
    rows=conn.execute("""SELECT at.* FROM actor_transmissions at JOIN actors a ON a.id=at.actor_id
                         WHERE at.status='active' AND lower(a.status) IN ('dead','deceased')""").fetchall()
    for r in rows: conn.execute("UPDATE actor_transmissions SET status='deceased',left_day=? WHERE line_id=? AND actor_id=?",(day,r["line_id"],r["actor_id"]))
    return len(rows)


def _resolve_certifications(conn: sqlite3.Connection, day: int) -> int:
    cur=conn.execute("UPDATE professional_certifications SET status='expired' WHERE status='active' AND expires_day IS NOT NULL AND expires_day<?",(day,))
    return int(cur.rowcount)



def _structural_cohort_size(program: sqlite3.Row, cohort_index: int) -> int:
    cap=max(1,int(program['capacity']))
    # A structural cohort is the unnamed majority beneath the tracked registry. Calibration varies
    # modestly by program/cohort and never claims to be a literal census.
    base=max(2,round(cap*0.55))
    jitter=((int(program['id'])*37 + int(cohort_index)*19) % 7)-3
    return max(1,min(cap,base+jitter))


def ensure_structural_training_cohorts(conn: sqlite3.Connection, day: int | None = None) -> int:
    day=_day(conn) if day is None else int(day)
    created=0
    for p in conn.execute("SELECT * FROM education_programs WHERE status='active' ORDER BY id").fetchall():
        active=conn.execute("SELECT id FROM structural_training_cohorts WHERE program_id=? AND status='active' ORDER BY id LIMIT 1",(int(p['id']),)).fetchone()
        if active: continue
        idx=int(conn.execute("SELECT COALESCE(MAX(cohort_index),0)+1 FROM structural_training_cohorts WHERE program_id=?",(int(p['id']),)).fetchone()[0])
        count=_structural_cohort_size(p,idx)
        conn.execute("""INSERT INTO structural_training_cohorts(program_id,cohort_index,estimated_count,started_day,expected_completion_day,status,metadata_json)
                      VALUES (?,?,?,?,?,'active','{\"authority\":\"STRUCTURAL_CAMPAIGN_CALIBRATION\",\"named_registry_is_not_census\":true}')""",
                     (int(p['id']),idx,count,day,day+int(p['duration_days'])))
        created+=1
    return created


def _resolve_structural_training_cohorts(conn: sqlite3.Connection, day: int) -> int:
    changed=0
    due=conn.execute("""SELECT stc.*,ep.duration_days,ep.capacity,ep.status program_status
                        FROM structural_training_cohorts stc JOIN education_programs ep ON ep.id=stc.program_id
                        WHERE stc.status='active' AND stc.expected_completion_day<=? ORDER BY stc.id""",(day,)).fetchall()
    for row in due:
        conn.execute("UPDATE structural_training_cohorts SET status='completed',completed_day=? WHERE id=?",(day,int(row['id'])))
        changed+=1
    changed+=ensure_structural_training_cohorts(conn,day)
    return changed

def _resolve_reproduction(conn: sqlite3.Connection, day: int) -> int:
    rows=conn.execute("SELECT * FROM institution_reproduction_profiles WHERE next_review_day<=? ORDER BY next_review_day,institution_actor_id",(day,)).fetchall(); count=0
    for p in rows:
        inst=int(p["institution_actor_id"])
        active_students=int(conn.execute("SELECT COUNT(*) FROM education_enrollments e JOIN education_programs ep ON ep.id=e.program_id WHERE ep.institution_actor_id=? AND e.status='active'",(inst,)).fetchone()[0])
        paused=int(conn.execute("SELECT COUNT(*) FROM education_enrollments e JOIN education_programs ep ON ep.id=e.program_id WHERE ep.institution_actor_id=? AND e.status='paused'",(inst,)).fetchone()[0])
        living_teachers=int(conn.execute("""SELECT COUNT(*) FROM (
                                               SELECT tr.teacher_actor_id AS actor_id FROM teaching_relationships tr JOIN actors a ON a.id=tr.teacher_actor_id
                                               WHERE tr.institution_actor_id=? AND tr.status='active' AND lower(a.status) NOT IN ('dead','deceased')
                                               UNION
                                               SELECT pm.actor_id FROM professional_memberships pm JOIN actors a ON a.id=pm.actor_id
                                               WHERE pm.institution_actor_id=? AND pm.profession_domain='martial_instruction'
                                                 AND pm.role='instructor' AND pm.status='active' AND lower(a.status) NOT IN ('dead','deceased')
                                           )""",(inst,inst)).fetchone()[0])
        active_lines=int(conn.execute("SELECT COUNT(*) FROM transmission_lines WHERE institution_actor_id=? AND status IN ('active','fragile')",(inst,)).fetchone()[0])
        endangered=int(conn.execute("SELECT COUNT(*) FROM knowledge_assets WHERE institution_actor_id=? AND status IN ('endangered','inaccessible','lost')",(inst,)).fetchone()[0])
        # Structural health only. It never manufactures recruits, teachers, or successors.
        capacity=(float(p["recruitment_capacity"])+float(p["training_capacity"])+float(p["instructor_depth"])+float(p["archival_resilience"]))/4
        strain=min(60.0,paused*4+endangered*8+max(0,active_students-max(1,living_teachers)*8)*1.5)
        continuity=min(100.0,max(0.0,50+active_lines*4+living_teachers*2-strain))
        pipeline=max(0.0,min(100.0,capacity*0.55+continuity*0.45))
        conn.execute("UPDATE institution_reproduction_profiles SET pipeline_health=?,continuity_pressure=?,last_review_day=?,next_review_day=? WHERE institution_actor_id=?",
                     (pipeline,100-pipeline,day,day+int(p["review_cadence_days"]),inst))
        # Readiness can become eligible but never chosen automatically.
        candidates=conn.execute("SELECT * FROM institutional_successor_candidates WHERE institution_actor_id=? AND status IN ('candidate','eligible')",(inst,)).fetchall()
        for c in candidates:
            a=conn.execute("SELECT status FROM actors WHERE id=?",(c["actor_id"],)).fetchone()
            if not a or str(a[0]).lower() in ('dead','deceased'):
                conn.execute("UPDATE institutional_successor_candidates SET status='deceased',updated_day=? WHERE id=?",(day,c["id"])); continue
            readiness=min(100.0,float(c["readiness"])+(day-int(c["updated_day"]))/365.0*2.0)
            status='eligible' if readiness>=70 and float(c["legitimacy"])>=50 and float(c["transmission_depth"])>=50 else 'candidate'
            conn.execute("UPDATE institutional_successor_candidates SET readiness=?,status=?,updated_day=? WHERE id=?",(readiness,status,day,c["id"]))
        count+=1
    return count


def next_education_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    q=[
        ("SELECT MIN(next_review_day) FROM education_enrollments WHERE status='active' AND next_review_day>? AND next_review_day<=?",),
        ("SELECT MIN(next_review_day) FROM institution_reproduction_profiles WHERE next_review_day>? AND next_review_day<=?",),
    ]
    for (sql,) in q:
        r=conn.execute(sql,(after_day,end_day)).fetchone()[0]
        if r is not None: vals.append(int(r))
    # knowledge/line preservation reviews are annual-ish but terminal processing still catches them; schedule next yearly boundary if relevant.
    if conn.execute("SELECT 1 FROM knowledge_assets WHERE status IN ('extant','endangered','inaccessible') LIMIT 1").fetchone() or conn.execute("SELECT 1 FROM transmission_lines WHERE status IN ('active','fragile','dormant') LIMIT 1").fetchone():
        candidate=min(end_day,after_day+365)
        if candidate>after_day: vals.append(candidate)
    return min(vals) if vals else None


def process_due_education(conn: sqlite3.Connection, day: int, *, event_logger: Callable[...,int] | None = None) -> dict[str,int]:
    return {
        'teaching_deaths': _resolve_teaching_deaths(conn,day),
        'custody_deaths': _resolve_custody_deaths(conn,day),
        'transmission_deaths': _resolve_transmission_deaths(conn,day),
        'enrollments': _resolve_enrollments(conn,day,event_logger),
        'structural_cohorts': _resolve_structural_training_cohorts(conn,day),
        'assets': _resolve_assets(conn,day),
        'lines': _resolve_lines(conn,day),
        'certifications': _resolve_certifications(conn,day),
        'institutions': _resolve_reproduction(conn,day),
    }


def education_summary(conn: sqlite3.Connection) -> dict[str,int]:
    return {
        'programs': int(conn.execute("SELECT COUNT(*) FROM education_programs").fetchone()[0]),
        'active_enrollments': int(conn.execute("SELECT COUNT(*) FROM education_enrollments WHERE status='active'").fetchone()[0]),
        'structural_active_trainees': int(conn.execute("SELECT COALESCE(SUM(estimated_count),0) FROM structural_training_cohorts WHERE status='active'").fetchone()[0]),
        'active_structural_cohorts': int(conn.execute("SELECT COUNT(*) FROM structural_training_cohorts WHERE status='active'").fetchone()[0]),
        'paused_enrollments': int(conn.execute("SELECT COUNT(*) FROM education_enrollments WHERE status='paused'").fetchone()[0]),
        'teaching_relationships': int(conn.execute("SELECT COUNT(*) FROM teaching_relationships WHERE status='active'").fetchone()[0]),
        'knowledge_assets': int(conn.execute("SELECT COUNT(*) FROM knowledge_assets").fetchone()[0]),
        'lost_assets': int(conn.execute("SELECT COUNT(*) FROM knowledge_assets WHERE status IN ('lost','destroyed')").fetchone()[0]),
        'transmission_lines': int(conn.execute("SELECT COUNT(*) FROM transmission_lines").fetchone()[0]),
        'active_certifications': int(conn.execute("SELECT COUNT(*) FROM professional_certifications WHERE status='active'").fetchone()[0]),
        'reproduction_profiles': int(conn.execute("SELECT COUNT(*) FROM institution_reproduction_profiles").fetchone()[0]),
        'history_entries': int(conn.execute("SELECT COUNT(*) FROM education_history").fetchone()[0]),
    }


def education_context(conn: sqlite3.Connection, actor_id: int) -> dict[str,Any]:
    enrollments=[dict(r) for r in conn.execute("""SELECT e.id,e.status,e.progress_days,e.interruption_reason,e.started_day,e.completed_day,
                                                         p.name,p.domain_key,p.program_kind,p.duration_days,p.institution_actor_id,
                                                         t.name teacher_name,i.name institution_name
                                                  FROM education_enrollments e JOIN education_programs p ON p.id=e.program_id
                                                  LEFT JOIN actors t ON t.id=e.primary_teacher_actor_id LEFT JOIN actors i ON i.id=p.institution_actor_id
                                                  WHERE e.actor_id=? ORDER BY e.started_day,e.id""",(actor_id,)).fetchall()]
    teachers=[dict(r) for r in conn.execute("""SELECT tr.relation_kind,tr.domain_key,tr.status,tr.start_day,tr.end_day,a.name teacher_name,i.name institution_name
                                               FROM teaching_relationships tr JOIN actors a ON a.id=tr.teacher_actor_id
                                               LEFT JOIN actors i ON i.id=tr.institution_actor_id WHERE tr.student_actor_id=?
                                               ORDER BY tr.start_day,tr.id""",(actor_id,)).fetchall()]
    certs=[dict(r) for r in conn.execute("SELECT domain_key,certificate_key,level,granted_day,expires_day,status FROM professional_certifications WHERE actor_id=? ORDER BY granted_day,id",(actor_id,)).fetchall()]
    transmissions=[dict(r) for r in conn.execute("""SELECT tl.name,tl.lineage_key,tl.domain_key,tl.status AS line_status,at.relation_kind,at.depth,at.status
                                                     FROM actor_transmissions at JOIN transmission_lines tl ON tl.id=at.line_id
                                                     WHERE at.actor_id=? ORDER BY tl.domain_key,tl.name""",(actor_id,)).fetchall()]
    access=[dict(r) for r in conn.execute("""SELECT ka.title,ka.asset_kind,ka.domain_key,ka.status AS asset_status,kac.access_level,kac.status
                                            FROM knowledge_access kac JOIN knowledge_assets ka ON ka.id=kac.asset_id
                                            WHERE kac.actor_id=? ORDER BY ka.domain_key,ka.title""",(actor_id,)).fetchall()]
    return {'enrollments':enrollments,'teachers':teachers,'certifications':certs,'transmission_lines':transmissions,'knowledge_access':access}
