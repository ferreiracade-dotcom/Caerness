from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .relationships import ensure_relationship
from .continuity import (
    add_cohort_member,
    add_historical_anchor,
    set_resolution,
    start_career,
    upsert_continuity_core,
)

DAY_PER_YEAR = 365
_ALLOWED_DEPTHS = {"shallow", "developed", "deep"}
_ALLOWED_BASIS = {"cohort", "institution", "event", "anchor", "record", "relationship", "canon", "latent_constraint"}


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _world_day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def _latent(conn: sqlite3.Connection, latent_entity_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM latent_entities WHERE id=?", (latent_entity_id,)).fetchone()
    if not row:
        raise ValueError(f"Unknown latent entity #{latent_entity_id}")
    if row["status"] == "retired":
        raise ValueError("Latent entity pool is retired")
    return row


def _career_candidates(conn: sqlite3.Connection, constraints: dict[str, Any]) -> list[dict[str, Any]]:
    domain = constraints.get("career_domain") or constraints.get("domain")
    if domain:
        rows = conn.execute("SELECT * FROM career_tracks WHERE domain=? ORDER BY is_canon DESC,name", (domain,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM career_tracks ORDER BY is_canon DESC,name LIMIT 40").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["stage_model"] = _loads(item.pop("stage_model_json"), {})
        item["stages"] = [dict(x) for x in conn.execute(
            "SELECT id,stage_key,stage_name,sequence_index,description FROM career_stages WHERE track_id=? ORDER BY sequence_index,id",
            (row["id"],),
        ).fetchall()]
        result.append(item)
    return result


def _event_context(conn: sqlite3.Connection, location_id: int | None, earliest_day: int, latest_day: int) -> list[dict[str, Any]]:
    if location_id is None:
        return []
    rows = conn.execute(
        """SELECT id,day,event_type,title,summary,severity,location_id,source_actor_id
           FROM events WHERE location_id=? AND day BETWEEN ? AND ?
           ORDER BY day,id LIMIT 120""",
        (location_id, earliest_day, latest_day),
    ).fetchall()
    return [dict(r) for r in rows]


def _institution_context(conn: sqlite3.Connection, latent: sqlite3.Row) -> dict[str, Any] | None:
    iid = latent["institution_actor_id"]
    if iid is None:
        return None
    actor = conn.execute("SELECT id,name,subtype,home_location_id,current_location_id,status FROM actors WHERE id=?", (iid,)).fetchone()
    if not actor:
        return None
    result = dict(actor)
    profile = conn.execute("SELECT * FROM institution_profiles WHERE actor_id=?", (iid,)).fetchone()
    if profile:
        p = dict(profile)
        for key in ("governance_json", "culture_json", "pipeline_json", "capacity_json", "economic_json", "reputation_json", "succession_json"):
            p[key.removesuffix("_json")] = _loads(p.pop(key), {})
        result["profile"] = p
    else:
        result["profile"] = None
    return result


def _cohort_context(conn: sqlite3.Connection, cohort_id: int | None) -> dict[str, Any] | None:
    if cohort_id is None:
        return None
    row = conn.execute("SELECT * FROM cohorts WHERE id=?", (cohort_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["shared_context"] = _loads(result.pop("shared_context_json"), {})
    return result


def prepare_crystallization_context(
    conn: sqlite3.Connection,
    latent_entity_id: int,
    *,
    requested_depth: str = "shallow",
    trigger_kind: str = "engine",
    trigger_id: int | None = None,
) -> dict[str, Any]:
    """Build and persist a bounded historical context for one latent pool.

    This does not create a person. It freezes the constraints a proposal must obey,
    so later generation cannot opportunistically broaden the past to fit a scene.
    """
    if requested_depth not in _ALLOWED_DEPTHS:
        raise ValueError("Invalid crystallization depth")
    latent = _latent(conn, latent_entity_id)
    constraints = _loads(latent["constraints_json"], {})
    historical = _loads(latent["historical_context_json"], {})
    current_day = _world_day(conn)

    age_range = constraints.get("age_range") or [18, 85]
    try:
        min_age, max_age = int(age_range[0]), int(age_range[1])
    except Exception:
        min_age, max_age = 18, 85
    min_age = max(0, min_age)
    max_age = max(min_age, max_age)
    earliest_birth = current_day - max_age * DAY_PER_YEAR
    latest_birth = current_day - min_age * DAY_PER_YEAR

    location = None
    if latent["location_id"] is not None:
        location = _rowdict(conn.execute("SELECT * FROM locations WHERE id=?", (latent["location_id"],)).fetchone())

    context = {
        "context_version": 1,
        "prepared_day": current_day,
        "requested_depth": requested_depth,
        "latent": {
            "id": int(latent["id"]),
            "latent_kind": latent["latent_kind"],
            "archetype": latent["archetype"],
            "count_estimate": int(latent["count_estimate"]),
            "constraints": constraints,
            "historical_context": historical,
            "status": latent["status"],
        },
        "birth_window": {"earliest_day": earliest_birth, "latest_day": latest_birth, "age_range": [min_age, max_age]},
        "location": location,
        "institution": _institution_context(conn, latent),
        "cohort": _cohort_context(conn, latent["cohort_id"]),
        "career_tracks": _career_candidates(conn, constraints),
        "local_events": _event_context(conn, latent["location_id"], earliest_birth, current_day),
        "guardrails": {
            "identity_facing_history": True,
            "no_convenient_connections": True,
            "existing_references_require_basis": True,
            "campaign_scope_only": True,
            "max_anchor_counts": {"shallow": 4, "developed": 8, "deep": 14},
        },
    }
    cur = conn.execute(
        """INSERT INTO crystallization_runs(
               latent_entity_id,target_kind,requested_depth,trigger_kind,trigger_id,status,context_json,created_day
           ) VALUES (?,?,?,?,?,'prepared',?,?)""",
        (latent_entity_id, "actor", requested_depth, trigger_kind, trigger_id, _dumps(context), current_day),
    )
    context["run_id"] = int(cur.lastrowid)
    return context


def _ref_exists(conn: sqlite3.Connection, basis_kind: str, ref_id: int) -> bool:
    table = {
        "cohort": "cohorts",
        "institution": "actors",
        "event": "events",
        "anchor": "historical_anchors",
        "record": "documentary_records",
        "relationship": "relationships",
    }.get(basis_kind)
    if not table:
        return basis_kind in {"canon", "latent_constraint"}
    row = conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (ref_id,)).fetchone()
    if not row:
        return False
    if basis_kind == "institution":
        actor = conn.execute("SELECT actor_type FROM actors WHERE id=?", (ref_id,)).fetchone()
        return bool(actor and actor[0] == "institution")
    return True


def validate_crystallization_proposal(
    conn: sqlite3.Connection,
    run_id: int,
    proposal: dict[str, Any],
    *,
    strict: bool = True,
) -> dict[str, Any]:
    run = conn.execute("SELECT * FROM crystallization_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Unknown crystallization run #{run_id}")
    if run["status"] in {"applied", "cancelled"}:
        raise ValueError(f"Crystallization run is already {run['status']}")
    context = _loads(run["context_json"], {})
    errors: list[str] = []
    warnings: list[str] = []

    name = str(proposal.get("name") or "").strip()
    if not name:
        errors.append("proposal.name is required")
    elif conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        errors.append(f"actor name already exists: {name}")

    if proposal.get("actor_type", "character") != "character":
        errors.append("historical person crystallization currently supports actor_type='character' only")

    birth_day = proposal.get("birth_day")
    window = context.get("birth_window", {})
    if birth_day is None:
        errors.append("proposal.birth_day is required")
    else:
        birth_day = int(birth_day)
        if not int(window.get("earliest_day", birth_day)) <= birth_day <= int(window.get("latest_day", birth_day)):
            errors.append("birth_day falls outside the latent pool age constraints")

    latent = context.get("latent", {})
    constraints = latent.get("constraints", {})
    expected_location = (context.get("location") or {}).get("id")
    home_location_id = proposal.get("home_location_id", expected_location)
    current_location_id = proposal.get("current_location_id", expected_location)
    if strict and expected_location is not None and home_location_id not in {None, expected_location}:
        warnings.append("home_location differs from latent pool location; requires explicit historical basis")
    for key, value in (("home_location_id", home_location_id), ("current_location_id", current_location_id)):
        if value is not None and not conn.execute("SELECT 1 FROM locations WHERE id=?", (int(value),)).fetchone():
            errors.append(f"{key} references unknown location #{value}")

    max_anchors = int(context.get("guardrails", {}).get("max_anchor_counts", {}).get(run["requested_depth"], 4))
    anchors = proposal.get("anchors") or []
    if len(anchors) > max_anchors:
        errors.append(f"too many anchors for {run['requested_depth']} crystallization: {len(anchors)} > {max_anchors}")

    previous_start: int | None = None
    for i, anchor in enumerate(anchors):
        if not str(anchor.get("anchor_type") or "").strip():
            errors.append(f"anchors[{i}].anchor_type is required")
        if not str(anchor.get("summary") or "").strip():
            errors.append(f"anchors[{i}].summary is required")
        start = anchor.get("start_day")
        if start is not None:
            start = int(start)
            if birth_day is not None and start < int(birth_day):
                errors.append(f"anchors[{i}] predates birth_day")
            if start > int(context.get("prepared_day", _world_day(conn))):
                errors.append(f"anchors[{i}] lies in the future")
            if previous_start is not None and start < previous_start:
                warnings.append("anchors are not chronological")
            previous_start = start
        end = anchor.get("end_day")
        if end is not None and start is not None and int(end) < int(start):
            errors.append(f"anchors[{i}].end_day precedes start_day")
        basis = anchor.get("basis") or []
        for j, item in enumerate(basis):
            kind = str(item.get("kind") or "")
            ref_id = item.get("id")
            if kind not in _ALLOWED_BASIS:
                errors.append(f"anchors[{i}].basis[{j}] has invalid kind {kind!r}")
                continue
            if kind not in {"canon", "latent_constraint"}:
                if ref_id is None or not _ref_exists(conn, kind, int(ref_id)):
                    errors.append(f"anchors[{i}].basis[{j}] references missing {kind} #{ref_id}")

    # Anti-convenience: strong existing-actor connections need explicit historical basis.
    connections = proposal.get("connections") or []
    for i, connection in enumerate(connections):
        actor_id = connection.get("actor_id")
        if actor_id is None or not conn.execute("SELECT 1 FROM actors WHERE id=?", (int(actor_id),)).fetchone():
            errors.append(f"connections[{i}] references unknown actor")
            continue
        basis = connection.get("basis") or []
        if not basis:
            errors.append(f"connections[{i}] has no historical basis; convenient retroactive connections are forbidden")
            continue
        valid_basis = False
        for item in basis:
            kind = str(item.get("kind") or "")
            ref_id = item.get("id")
            if kind in _ALLOWED_BASIS and (kind in {"canon", "latent_constraint"} or (ref_id is not None and _ref_exists(conn, kind, int(ref_id)))):
                valid_basis = True
        if not valid_basis:
            errors.append(f"connections[{i}] has no valid basis")

    career = proposal.get("career")
    if career:
        track_id = int(career.get("track_id", 0))
        track = conn.execute("SELECT * FROM career_tracks WHERE id=?", (track_id,)).fetchone()
        if not track:
            errors.append("career.track_id is unknown")
        else:
            expected_domain = constraints.get("career_domain") or constraints.get("domain")
            if strict and expected_domain and track["domain"] != expected_domain:
                errors.append(f"career domain {track['domain']} violates latent constraint {expected_domain}")
            stage_id = career.get("stage_id")
            if stage_id is not None and not conn.execute("SELECT 1 FROM career_stages WHERE id=? AND track_id=?", (int(stage_id), track_id)).fetchone():
                errors.append("career.stage_id does not belong to career.track_id")
            institution_actor_id = career.get("institution_actor_id")
            if institution_actor_id is not None:
                inst = conn.execute("SELECT actor_type FROM actors WHERE id=?", (int(institution_actor_id),)).fetchone()
                if not inst or inst[0] != "institution":
                    errors.append("career.institution_actor_id must reference an institution")

    continuity = proposal.get("continuity") or {}
    if not isinstance(continuity, dict):
        errors.append("proposal.continuity must be an object")

    result = {"valid": not errors, "errors": errors, "warnings": warnings, "checked_day": _world_day(conn), "strict": strict}
    conn.execute(
        "UPDATE crystallization_runs SET proposal_json=?,validation_json=?,status=? WHERE id=?",
        (_dumps(proposal), _dumps(result), "validated" if not errors else "rejected", run_id),
    )
    return result


def _add_lineage(conn: sqlite3.Connection, run_id: int, fact_kind: str, produced_kind: str, produced_id: int, *, ref_kind: str | None = None, ref_id: int | None = None, summary: str | None = None, day: int) -> None:
    conn.execute(
        """INSERT INTO crystallization_lineage(run_id,fact_kind,fact_ref_kind,fact_ref_id,produced_kind,produced_id,summary,created_day)
           VALUES (?,?,?,?,?,?,?,?)""",
        (run_id, fact_kind, ref_kind, ref_id, produced_kind, produced_id, summary, day),
    )


def apply_crystallization_proposal(conn: sqlite3.Connection, run_id: int) -> int:
    """Commit a previously validated person proposal as campaign history.

    Application is transactional under the caller's transaction. It never mutates setting canon.
    """
    run = conn.execute("SELECT * FROM crystallization_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise ValueError(f"Unknown crystallization run #{run_id}")
    if run["status"] != "validated":
        raise ValueError("Crystallization must validate successfully before application")
    proposal = _loads(run["proposal_json"], {})
    validation = _loads(run["validation_json"], {})
    if not validation.get("valid"):
        raise ValueError("Stored crystallization validation is not valid")
    latent = _latent(conn, int(run["latent_entity_id"]))
    day = _world_day(conn)

    location_id = proposal.get("current_location_id")
    if location_id is None:
        location_id = latent["location_id"]
    home_location_id = proposal.get("home_location_id")
    if home_location_id is None:
        home_location_id = latent["location_id"]

    cur = conn.execute(
        """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
           VALUES (?,'character',?,?,?,?,?,0)""",
        (proposal["name"], proposal.get("subtype"), home_location_id, location_id, proposal.get("status", "active"), proposal.get("notes")),
    )
    actor_id = int(cur.lastrowid)

    core = dict(proposal.get("continuity") or {})
    core.setdefault("identity", {})
    core["identity"].setdefault("birth_day", int(proposal["birth_day"]))
    core["identity"].setdefault("crystallized_from_latent_id", int(latent["id"]))
    upsert_continuity_core(
        conn, "actor", actor_id, core,
        historical_depth=str(run["requested_depth"]), crystallized_day=day, source_kind="campaign",
        notes="Created by historical crystallization v0.9",
    )
    _add_lineage(conn, run_id, "latent_pool", "continuity_core", actor_id, ref_kind="latent_entity", ref_id=int(latent["id"]), summary="Identity crystallized from latent pool", day=day)

    birth_anchor = add_historical_anchor(
        conn, "actor", actor_id, "birth", f"Born: {proposal['name']}", start_day=int(proposal["birth_day"]),
        detail={"home_location_id": home_location_id}, source_kind="crystallization", canon_scope="campaign",
    )
    _add_lineage(conn, run_id, "birth", "historical_anchor", birth_anchor, summary="Birth anchor", day=day)

    for anchor in proposal.get("anchors") or []:
        detail = dict(anchor.get("detail") or {})
        detail["basis"] = anchor.get("basis") or []
        anchor_id = add_historical_anchor(
            conn, "actor", actor_id, str(anchor["anchor_type"]), str(anchor["summary"]),
            start_day=anchor.get("start_day"), end_day=anchor.get("end_day"), detail=detail,
            source_kind="crystallization", certainty=float(anchor.get("certainty", 1.0)), canon_scope="campaign",
        )
        for basis in anchor.get("basis") or []:
            _add_lineage(conn, run_id, "anchor_basis", "historical_anchor", anchor_id, ref_kind=basis.get("kind"), ref_id=basis.get("id"), summary=str(anchor["summary"]), day=day)

    cohort_id = latent["cohort_id"]
    if cohort_id is not None:
        add_cohort_member(conn, int(cohort_id), actor_id, role=proposal.get("cohort_role"), membership_status="former")
        _add_lineage(conn, run_id, "cohort", "actor", actor_id, ref_kind="cohort", ref_id=int(cohort_id), summary="Inherited latent cohort membership", day=day)

    career = proposal.get("career")
    if career:
        career_id = start_career(
            conn, actor_id, int(career["track_id"]), stage_id=career.get("stage_id"),
            institution_actor_id=career.get("institution_actor_id") or latent["institution_actor_id"],
            mentor_actor_id=career.get("mentor_actor_id"), started_day=career.get("started_day"), notes=career.get("notes"),
        )
        conn.execute(
            "UPDATE actor_careers SET status=?,experience_json=?,reputation_json=? WHERE id=?",
            (career.get("status", "active"), _dumps(career.get("experience")), _dumps(career.get("reputation")), career_id),
        )
        _add_lineage(conn, run_id, "career", "actor_career", career_id, ref_kind="career_track", ref_id=int(career["track_id"]), summary="Crystallized career", day=day)

    for connection in proposal.get("connections") or []:
        other = int(connection["actor_id"])
        stance = float(connection.get("stance", 0))
        trust = float(connection.get("trust", 0))
        obligation = float(connection.get("obligation", 0))
        rid = ensure_relationship(conn, actor_id, other, day)
        conn.execute(
            "UPDATE relationships SET stance=?,trust=?,obligation=?,updated_day=? WHERE id=?",
            (stance, trust, obligation, day, rid),
        )
        for basis in connection.get("basis") or []:
            _add_lineage(conn, run_id, "connection_basis", "relationship", int(conn.execute("SELECT id FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (actor_id, other)).fetchone()[0]), ref_kind=basis.get("kind"), ref_id=basis.get("id"), summary=connection.get("summary"), day=day)

    set_resolution(conn, "actor", actor_id, proposal.get("resolution_level", "TRACKED"), day=day, reason="historical crystallization", source_kind="crystallization", source_id=run_id)

    remaining = int(latent["count_estimate"]) - 1
    if remaining <= 0:
        conn.execute(
            """UPDATE latent_entities SET status='crystallized',crystallized_entity_kind='actor',crystallized_entity_id=?,updated_day=? WHERE id=?""",
            (actor_id, day, latent["id"]),
        )
    else:
        conn.execute(
            """UPDATE latent_entities SET count_estimate=?,status='partially_crystallized',crystallized_entity_kind='actor',crystallized_entity_id=?,updated_day=? WHERE id=?""",
            (remaining, actor_id, day, latent["id"]),
        )

    conn.execute(
        """UPDATE crystallization_runs SET status='applied',crystallized_entity_kind='actor',crystallized_entity_id=?,applied_day=?,applied_at=CURRENT_TIMESTAMP WHERE id=?""",
        (actor_id, day, run_id),
    )
    return actor_id


def crystallization_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM crystallization_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["context"] = _loads(result.pop("context_json"), {})
    result["proposal"] = _loads(result.pop("proposal_json"), None)
    result["validation"] = _loads(result.pop("validation_json"), {})
    result["lineage"] = [dict(x) for x in conn.execute("SELECT * FROM crystallization_lineage WHERE run_id=? ORDER BY id", (run_id,)).fetchall()]
    return result


def export_crystallization_packet(conn: sqlite3.Connection, run_id: int, path: str | None = None) -> str:
    run = crystallization_run(conn, run_id)
    if not run:
        raise ValueError(f"Unknown crystallization run #{run_id}")
    if run["status"] not in {"prepared", "rejected", "validated"}:
        raise ValueError(f"Cannot export run in status {run['status']}")
    packet = f"""# Caerness Historical Crystallization Request #{run_id}\n\nYou are proposing historical detail for an entity that already existed latently in the world.\nDo not change world truth. Do not create convenient connections to solve the current scene.\nUse only the supplied context as historical constraint. Return JSON only.\n\n## Context\n```json\n{json.dumps(run['context'], ensure_ascii=False, indent=2, sort_keys=True)}\n```\n\n## Required JSON shape\n```json\n{{\n  \"name\": \"Unique Name\",\n  \"actor_type\": \"character\",\n  \"subtype\": \"profession or social subtype\",\n  \"birth_day\": -19000,\n  \"home_location_id\": null,\n  \"current_location_id\": null,\n  \"continuity\": {{\n    \"identity\": {{}},\n    \"temperament\": {{}},\n    \"values\": [],\n    \"goals\": [],\n    \"relationships_summary\": []\n  }},\n  \"anchors\": [\n    {{\n      \"anchor_type\": \"apprenticeship\",\n      \"start_day\": -14000,\n      \"end_day\": -13000,\n      \"summary\": \"...\",\n      \"detail\": {{}},\n      \"certainty\": 1.0,\n      \"basis\": [{{\"kind\": \"cohort\", \"id\": 1}}]\n    }}\n  ],\n  \"career\": null,\n  \"connections\": [],\n  \"resolution_level\": \"TRACKED\"\n}}\n```\n\nRules:\n- History is identity-facing, not plot-facing.\n- Never invent an existing-actor connection without explicit basis.\n- Do not exceed the anchor limit in context.guardrails.\n- Do not contradict age, location, cohort, institution, career, or event constraints.\n- This creates campaign history only, never setting canon.\n"""
    if path is None:
        path = f"game/campaign_01/crystallization_{run_id}.md"
    from pathlib import Path
    out = Path(path)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent.parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(packet, encoding="utf-8")
    return str(out)


def parse_crystallization_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        first = text.find("\n")
        last = text.rfind("```")
        if first >= 0 and last > first:
            text = text[first + 1:last].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Crystallization response must be one JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Crystallization response must be a JSON object")
    return data
