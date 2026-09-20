from __future__ import annotations

import json
import sqlite3
from typing import Any


RESOLUTION_LEVELS = ("LATENT", "STRUCTURAL", "TRACKED", "ACTIVE", "SCENE")
_RESOLUTION_RANK = {name: i for i, name in enumerate(RESOLUTION_LEVELS)}


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _entity_exists(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> bool:
    tables = {
        "actor": "actors",
        "institution": "actors",
        "location": "locations",
        "possession": "possessions",
        "thread": "threads",
        "cohort": "cohorts",
    }
    table = tables.get(entity_kind)
    if not table:
        return False
    row = conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (entity_id,)).fetchone()
    if not row:
        return False
    if entity_kind == "institution":
        actor = conn.execute("SELECT actor_type FROM actors WHERE id=?", (entity_id,)).fetchone()
        return bool(actor and actor[0] == "institution")
    return True


def upsert_continuity_core(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: int,
    core: dict[str, Any],
    *,
    core_type: str = "general",
    historical_depth: str = "present",
    day: int | None = None,
    crystallized_day: int | None = None,
    source_kind: str = "engine",
    notes: str | None = None,
) -> int:
    if not _entity_exists(conn, entity_kind, entity_id):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    if historical_depth not in {"present", "shallow", "developed", "deep"}:
        raise ValueError("Invalid historical_depth")
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    conn.execute(
        """
        INSERT INTO continuity_cores(
            entity_kind,entity_id,core_type,core_json,historical_depth,last_crystallized_day,last_updated_day,source_kind,notes
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entity_kind,entity_id,core_type) DO UPDATE SET
            core_json=excluded.core_json,
            historical_depth=excluded.historical_depth,
            last_crystallized_day=COALESCE(excluded.last_crystallized_day,continuity_cores.last_crystallized_day),
            last_updated_day=excluded.last_updated_day,
            source_kind=excluded.source_kind,
            notes=COALESCE(excluded.notes,continuity_cores.notes)
        """,
        (entity_kind, entity_id, core_type, _dumps(core), historical_depth, crystallized_day, day, source_kind, notes),
    )
    row = conn.execute(
        "SELECT id FROM continuity_cores WHERE entity_kind=? AND entity_id=? AND core_type=?",
        (entity_kind, entity_id, core_type),
    ).fetchone()
    return int(row[0])


def continuity_core(conn: sqlite3.Connection, entity_kind: str, entity_id: int, *, core_type: str = "general") -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM continuity_cores WHERE entity_kind=? AND entity_id=? AND core_type=?",
        (entity_kind, entity_id, core_type),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["core"] = _loads(result.pop("core_json"), {})
    return result


def add_historical_anchor(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: int,
    anchor_type: str,
    summary: str,
    *,
    start_day: int | None = None,
    end_day: int | None = None,
    detail: dict[str, Any] | None = None,
    source_kind: str = "crystallization",
    source_id: int | None = None,
    certainty: float = 1.0,
    canon_scope: str = "campaign",
    immutable: bool = True,
    created_day: int | None = None,
) -> int:
    if not _entity_exists(conn, entity_kind, entity_id):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    if not 0 <= certainty <= 1:
        raise ValueError("certainty must be between 0 and 1")
    if created_day is None:
        created_day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    cur = conn.execute(
        """
        INSERT INTO historical_anchors(
            entity_kind,entity_id,anchor_type,start_day,end_day,summary,detail_json,source_kind,source_id,
            certainty,canon_scope,immutable,created_day
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            entity_kind, entity_id, anchor_type, start_day, end_day, summary, _dumps(detail), source_kind,
            source_id, certainty, canon_scope, 1 if immutable else 0, created_day,
        ),
    )
    return int(cur.lastrowid)


def historical_anchors(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM historical_anchors
           WHERE entity_kind=? AND entity_id=?
           ORDER BY COALESCE(start_day,created_day),id""",
        (entity_kind, entity_id),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["detail"] = _loads(item.pop("detail_json"), {})
        result.append(item)
    return result


def create_cohort(
    conn: sqlite3.Connection,
    name: str,
    cohort_type: str,
    *,
    institution_actor_id: int | None = None,
    location_id: int | None = None,
    start_day: int | None = None,
    end_day: int | None = None,
    population_estimate: int | None = None,
    shared_context: dict[str, Any] | None = None,
    historical_summary: str | None = None,
    status: str = "historical",
    is_canon: bool = False,
) -> int:
    if institution_actor_id is not None and not _entity_exists(conn, "institution", institution_actor_id):
        raise ValueError("institution_actor_id must reference an institution actor")
    if location_id is not None and not _entity_exists(conn, "location", location_id):
        raise ValueError("Unknown location")
    cur = conn.execute(
        """
        INSERT INTO cohorts(
            name,cohort_type,institution_actor_id,location_id,start_day,end_day,population_estimate,
            shared_context_json,historical_summary,status,is_canon
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (name, cohort_type, institution_actor_id, location_id, start_day, end_day, population_estimate,
         _dumps(shared_context), historical_summary, status, 1 if is_canon else 0),
    )
    return int(cur.lastrowid)


def add_cohort_member(
    conn: sqlite3.Connection,
    cohort_id: int,
    actor_id: int,
    *,
    role: str | None = None,
    joined_day: int | None = None,
    left_day: int | None = None,
    membership_status: str = "member",
    significance: float = 0.5,
    notes: str | None = None,
) -> None:
    if not _entity_exists(conn, "cohort", cohort_id):
        raise ValueError("Unknown cohort")
    if not _entity_exists(conn, "actor", actor_id):
        raise ValueError("Unknown actor")
    conn.execute(
        """
        INSERT INTO cohort_memberships(cohort_id,actor_id,role,joined_day,left_day,membership_status,significance,notes)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(cohort_id,actor_id) DO UPDATE SET
            role=excluded.role,joined_day=excluded.joined_day,left_day=excluded.left_day,
            membership_status=excluded.membership_status,significance=excluded.significance,notes=excluded.notes
        """,
        (cohort_id, actor_id, role, joined_day, left_day, membership_status, significance, notes),
    )


def create_career_track(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    domain: str,
    *,
    description: str | None = None,
    typical_entry_age: int | None = None,
    institution_kind: str | None = None,
    stage_model: dict[str, Any] | None = None,
    is_canon: bool = False,
) -> int:
    conn.execute(
        """
        INSERT INTO career_tracks(key,name,domain,description,typical_entry_age,institution_kind,stage_model_json,is_canon)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET
            name=excluded.name,domain=excluded.domain,description=excluded.description,
            typical_entry_age=excluded.typical_entry_age,institution_kind=excluded.institution_kind,
            stage_model_json=excluded.stage_model_json,is_canon=excluded.is_canon
        """,
        (key, name, domain, description, typical_entry_age, institution_kind, _dumps(stage_model), 1 if is_canon else 0),
    )
    return int(conn.execute("SELECT id FROM career_tracks WHERE key=?", (key,)).fetchone()[0])


def add_career_stage(
    conn: sqlite3.Connection,
    track_id: int,
    stage_key: str,
    stage_name: str,
    sequence_index: int,
    *,
    description: str | None = None,
    entry_requirements: dict[str, Any] | None = None,
    responsibilities: dict[str, Any] | None = None,
    exit_paths: list[Any] | None = None,
) -> int:
    conn.execute(
        """
        INSERT INTO career_stages(
            track_id,stage_key,stage_name,sequence_index,description,entry_requirements_json,responsibilities_json,exit_paths_json
        ) VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(track_id,stage_key) DO UPDATE SET
            stage_name=excluded.stage_name,sequence_index=excluded.sequence_index,description=excluded.description,
            entry_requirements_json=excluded.entry_requirements_json,responsibilities_json=excluded.responsibilities_json,
            exit_paths_json=excluded.exit_paths_json
        """,
        (track_id, stage_key, stage_name, sequence_index, description, _dumps(entry_requirements),
         _dumps(responsibilities), json.dumps(exit_paths or [], ensure_ascii=False)),
    )
    return int(conn.execute(
        "SELECT id FROM career_stages WHERE track_id=? AND stage_key=?", (track_id, stage_key)
    ).fetchone()[0])


def start_career(
    conn: sqlite3.Connection,
    actor_id: int,
    track_id: int,
    *,
    stage_id: int | None = None,
    institution_actor_id: int | None = None,
    mentor_actor_id: int | None = None,
    started_day: int | None = None,
    notes: str | None = None,
) -> int:
    if not _entity_exists(conn, "actor", actor_id):
        raise ValueError("Unknown actor")
    if started_day is None:
        started_day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    cur = conn.execute(
        """
        INSERT INTO actor_careers(
            actor_id,track_id,current_stage_id,institution_actor_id,mentor_actor_id,started_day,stage_started_day,notes
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (actor_id, track_id, stage_id, institution_actor_id, mentor_actor_id, started_day, started_day, notes),
    )
    return int(cur.lastrowid)


def advance_career_stage(conn: sqlite3.Connection, career_id: int, stage_id: int, *, day: int | None = None) -> None:
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    career = conn.execute("SELECT * FROM actor_careers WHERE id=?", (career_id,)).fetchone()
    if not career:
        raise ValueError("Unknown career")
    stage = conn.execute("SELECT * FROM career_stages WHERE id=? AND track_id=?", (stage_id, career["track_id"])).fetchone()
    if not stage:
        raise ValueError("Stage does not belong to career track")
    conn.execute(
        "UPDATE actor_careers SET current_stage_id=?,stage_started_day=? WHERE id=?",
        (stage_id, day, career_id),
    )


def set_institution_profile(
    conn: sqlite3.Connection,
    actor_id: int,
    institution_kind: str,
    *,
    founded_day: int | None = None,
    parent_institution_actor_id: int | None = None,
    primary_location_id: int | None = None,
    governance: dict[str, Any] | None = None,
    culture: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
    capacity: dict[str, Any] | None = None,
    economic: dict[str, Any] | None = None,
    reputation: dict[str, Any] | None = None,
    succession: dict[str, Any] | None = None,
    trajectory: str = "stable",
    last_review_day: int | None = None,
    notes: str | None = None,
) -> None:
    if not _entity_exists(conn, "institution", actor_id):
        raise ValueError("institution profile requires actor_type='institution'")
    if last_review_day is None:
        last_review_day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    conn.execute(
        """
        INSERT INTO institution_profiles(
            actor_id,institution_kind,founded_day,parent_institution_actor_id,primary_location_id,
            governance_json,culture_json,pipeline_json,capacity_json,economic_json,reputation_json,
            succession_json,trajectory,last_review_day,notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(actor_id) DO UPDATE SET
            institution_kind=excluded.institution_kind,founded_day=excluded.founded_day,
            parent_institution_actor_id=excluded.parent_institution_actor_id,primary_location_id=excluded.primary_location_id,
            governance_json=excluded.governance_json,culture_json=excluded.culture_json,pipeline_json=excluded.pipeline_json,
            capacity_json=excluded.capacity_json,economic_json=excluded.economic_json,reputation_json=excluded.reputation_json,
            succession_json=excluded.succession_json,trajectory=excluded.trajectory,last_review_day=excluded.last_review_day,
            notes=excluded.notes
        """,
        (actor_id, institution_kind, founded_day, parent_institution_actor_id, primary_location_id,
         _dumps(governance), _dumps(culture), _dumps(pipeline), _dumps(capacity), _dumps(economic),
         _dumps(reputation), _dumps(succession), trajectory, last_review_day, notes),
    )


def set_resolution(
    conn: sqlite3.Connection,
    entity_kind: str,
    entity_id: int,
    level: str,
    *,
    day: int | None = None,
    reason: str | None = None,
    source_kind: str = "engine",
    source_id: int | None = None,
    review_cadence_days: int | None = None,
    next_review_day: int | None = None,
    locked_min_level: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if level not in _RESOLUTION_RANK:
        raise ValueError("Invalid resolution level")
    if locked_min_level is not None and locked_min_level not in _RESOLUTION_RANK:
        raise ValueError("Invalid locked_min_level")
    if not _entity_exists(conn, entity_kind, entity_id):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    old = conn.execute(
        "SELECT * FROM entity_resolution WHERE entity_kind=? AND entity_id=?", (entity_kind, entity_id)
    ).fetchone()
    old_level = str(old["resolution_level"]) if old else None
    effective_lock = locked_min_level if locked_min_level is not None else (old["locked_min_level"] if old else None)
    if effective_lock and _RESOLUTION_RANK[level] < _RESOLUTION_RANK[str(effective_lock)]:
        raise ValueError(f"Cannot demote below locked minimum {effective_lock}")
    conn.execute(
        """
        INSERT INTO entity_resolution(
            entity_kind,entity_id,resolution_level,previous_level,reason,promoted_by_kind,promoted_by_id,
            review_cadence_days,next_review_day,last_changed_day,locked_min_level,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entity_kind,entity_id) DO UPDATE SET
            previous_level=entity_resolution.resolution_level,
            resolution_level=excluded.resolution_level,
            reason=excluded.reason,
            promoted_by_kind=excluded.promoted_by_kind,
            promoted_by_id=excluded.promoted_by_id,
            review_cadence_days=COALESCE(excluded.review_cadence_days,entity_resolution.review_cadence_days),
            next_review_day=COALESCE(excluded.next_review_day,entity_resolution.next_review_day),
            last_changed_day=excluded.last_changed_day,
            locked_min_level=COALESCE(excluded.locked_min_level,entity_resolution.locked_min_level),
            metadata_json=excluded.metadata_json
        """,
        (entity_kind, entity_id, level, old_level, reason, source_kind, source_id, review_cadence_days,
         next_review_day, day, locked_min_level, _dumps(metadata)),
    )
    if old_level != level:
        conn.execute(
            """INSERT INTO resolution_transitions(
                   day,entity_kind,entity_id,from_level,to_level,reason,source_kind,source_id
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (day, entity_kind, entity_id, old_level, level, reason, source_kind, source_id),
        )


def resolution_state(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM entity_resolution WHERE entity_kind=? AND entity_id=?", (entity_kind, entity_id)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["metadata"] = _loads(result.pop("metadata_json"), {})
    return result


def create_latent_entity(
    conn: sqlite3.Connection,
    latent_kind: str,
    archetype: str,
    *,
    location_id: int | None = None,
    institution_actor_id: int | None = None,
    cohort_id: int | None = None,
    count_estimate: int = 1,
    constraints: dict[str, Any] | None = None,
    historical_context: dict[str, Any] | None = None,
    day: int | None = None,
    notes: str | None = None,
) -> int:
    if day is None:
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    cur = conn.execute(
        """INSERT INTO latent_entities(
               latent_kind,archetype,location_id,institution_actor_id,cohort_id,count_estimate,
               constraints_json,historical_context_json,created_day,updated_day,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (latent_kind, archetype, location_id, institution_actor_id, cohort_id, count_estimate,
         _dumps(constraints), _dumps(historical_context), day, day, notes),
    )
    return int(cur.lastrowid)


def add_public_narrative(
    conn: sqlite3.Connection,
    narrative_key: str,
    subject_kind: str,
    subject_id: int,
    claim_text: str,
    *,
    day: int,
    scope_kind: str = "world",
    scope_id: int | None = None,
    confidence: float = 0.5,
    prevalence: float = 0.5,
    valence: float = 0.0,
    origin_kind: str | None = None,
    origin_id: int | None = None,
) -> int:
    conn.execute(
        """INSERT INTO public_narratives(
               narrative_key,scope_kind,scope_id,subject_kind,subject_id,claim_text,confidence,prevalence,valence,
               first_day,last_reinforced_day,origin_kind,origin_id
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (narrative_key, scope_kind, scope_id, subject_kind, subject_id, claim_text, confidence, prevalence,
         valence, day, day, origin_kind, origin_id),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
