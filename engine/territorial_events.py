from __future__ import annotations

"""EVENTS-01 territorial event-sourcing spike.

This is deliberately a bounded sidecar over the existing underworld territorial owner.
It does not cut the engine over to event sourcing. Current SQL tables remain authoritative;
this module proves that controller/challenger/permission state can be reconstructed from an
immutable event stream, snapshotted, replayed after restart, and branched.
"""

import json
import sqlite3
from copy import deepcopy
from typing import Any

BASE_BRANCH_KEY = "main"
CURRENT_EVENT_VERSIONS = {
    "territory.zone_control_set": 2,
    "territory.challenger_added": 1,
    "territory.permission_granted": 1,
    "territory.permission_revoked": 1,
}


def _j(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def _day(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()
    return int(row[0]) if row else 0


def ensure_base_branch(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM territorial_event_branches WHERE branch_key=?", (BASE_BRANCH_KEY,)).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        """INSERT INTO territorial_event_branches(branch_key,parent_branch_id,fork_event_id,created_day,status,metadata_json)
           VALUES (?,NULL,NULL,?,'active','{}')""",
        (BASE_BRANCH_KEY, _day(conn)),
    )
    return int(cur.lastrowid)


def branch_id(conn: sqlite3.Connection, key: str = BASE_BRANCH_KEY) -> int:
    row = conn.execute("SELECT id FROM territorial_event_branches WHERE branch_key=?", (key,)).fetchone()
    if not row:
        if key == BASE_BRANCH_KEY:
            return ensure_base_branch(conn)
        raise ValueError(f"unknown territorial event branch: {key}")
    return int(row[0])


def _stream_sequence(conn: sqlite3.Connection, branch: int, stream_key: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(stream_sequence),0)+1 FROM territorial_domain_events WHERE branch_id=? AND stream_key=?",
        (branch, stream_key),
    ).fetchone()
    return int(row[0])


def _upcast(event_type: str, version: int, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Return the current event version + payload without mutating persisted history."""
    current = CURRENT_EVENT_VERSIONS.get(event_type, version)
    out = deepcopy(payload)
    v = int(version)
    if event_type == "territory.zone_control_set" and v == 1:
        # v1 called the controller simply organization_id and did not persist the three
        # claim dimensions. v2 names the semantic role and carries explicit projection data.
        if "new_controller_organization_id" not in out:
            out["new_controller_organization_id"] = out.pop("organization_id", None)
        out.setdefault("strength", 60.0)
        out.setdefault("local_support", 45.0)
        out.setdefault("fear", 55.0)
        out.setdefault("started_day", out.get("day"))
        v = 2
    if v != current:
        raise ValueError(f"no upcaster for {event_type} v{version} -> v{current}")
    return v, out


def empty_state() -> dict[str, Any]:
    return {"zones": {}, "permissions": {}}


def _zone(state: dict[str, Any], zone_id: int) -> dict[str, Any]:
    key = str(int(zone_id))
    return state["zones"].setdefault(key, {"controller": None, "challengers": {}})


def apply_event_to_state(state: dict[str, Any], event_type: str, version: int, payload: dict[str, Any]) -> dict[str, Any]:
    _, p = _upcast(event_type, int(version), payload)
    if event_type == "territory.zone_control_set":
        z = _zone(state, int(p["zone_id"]))
        z["controller"] = {
            "organization_id": int(p["new_controller_organization_id"]),
            "strength": float(p.get("strength", 60.0)),
            "local_support": float(p.get("local_support", 45.0)),
            "fear": float(p.get("fear", 55.0)),
            "started_day": int(p.get("started_day") or 0),
        }
    elif event_type == "territory.challenger_added":
        z = _zone(state, int(p["zone_id"]))
        oid = str(int(p["organization_id"]))
        prior = z["challengers"].get(oid)
        strength = float(p.get("strength", 35.0))
        z["challengers"][oid] = {
            "strength": max(float(prior["strength"]), strength) if prior else strength,
            "started_day": int((prior or {}).get("started_day") or p.get("started_day") or 0),
        }
    elif event_type == "territory.permission_granted":
        pid = str(int(p["permission_id"]))
        state["permissions"][pid] = {
            "zone_id": int(p["zone_id"]),
            "controller_organization_id": int(p["controller_organization_id"]),
            "guest_organization_id": int(p["guest_organization_id"]),
            "activity_kind": str(p["activity_kind"]),
            "tribute_rate": float(p.get("tribute_rate", 0.0)),
            "started_day": int(p.get("started_day") or 0),
            "expiry_day": int(p["expiry_day"]) if p.get("expiry_day") is not None else None,
        }
    elif event_type == "territory.permission_revoked":
        state["permissions"].pop(str(int(p["permission_id"])), None)
    else:
        raise ValueError(f"unsupported territorial domain event type: {event_type}")
    return state


def _write_projection(conn: sqlite3.Connection, branch: int, state: dict[str, Any], last_event_id: int | None) -> None:
    conn.execute("DELETE FROM territorial_projection_permissions WHERE branch_id=?", (branch,))
    conn.execute("DELETE FROM territorial_projection_challengers WHERE branch_id=?", (branch,))
    conn.execute("DELETE FROM territorial_projection_zones WHERE branch_id=?", (branch,))
    for zone_key, data in sorted(state.get("zones", {}).items(), key=lambda kv: int(kv[0])):
        zid = int(zone_key)
        controller = data.get("controller")
        conn.execute(
            """INSERT INTO territorial_projection_zones(
                   branch_id,zone_id,controller_organization_id,strength,local_support,fear,started_day,contested,last_event_id
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (branch, zid,
             int(controller["organization_id"]) if controller else None,
             float(controller["strength"]) if controller else None,
             float(controller["local_support"]) if controller else None,
             float(controller["fear"]) if controller else None,
             int(controller["started_day"]) if controller else None,
             1 if data.get("challengers") else 0,
             last_event_id),
        )
        for oid, challenger in sorted(data.get("challengers", {}).items(), key=lambda kv: int(kv[0])):
            conn.execute(
                """INSERT INTO territorial_projection_challengers(branch_id,zone_id,organization_id,strength,started_day,last_event_id)
                   VALUES (?,?,?,?,?,?)""",
                (branch, zid, int(oid), float(challenger["strength"]), int(challenger["started_day"]), last_event_id),
            )
    for pid, p in sorted(state.get("permissions", {}).items(), key=lambda kv: int(kv[0])):
        conn.execute(
            """INSERT INTO territorial_projection_permissions(
                   branch_id,permission_id,zone_id,controller_organization_id,guest_organization_id,activity_kind,
                   tribute_rate,started_day,expiry_day,last_event_id
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (branch, int(pid), int(p["zone_id"]), int(p["controller_organization_id"]), int(p["guest_organization_id"]),
             str(p["activity_kind"]), float(p["tribute_rate"]), int(p["started_day"]), p["expiry_day"], last_event_id),
        )


def _effective_event_rows(conn: sqlite3.Connection, branch: int) -> list[sqlite3.Row]:
    b = conn.execute("SELECT * FROM territorial_event_branches WHERE id=?", (branch,)).fetchone()
    if not b:
        raise ValueError("unknown branch")
    rows: list[sqlite3.Row] = []
    if b["parent_branch_id"] is not None:
        parent_rows = _effective_event_rows(conn, int(b["parent_branch_id"]))
        fork = int(b["fork_event_id"]) if b["fork_event_id"] is not None else None
        rows.extend(r for r in parent_rows if fork is None or int(r["id"]) <= fork)
    rows.extend(conn.execute(
        "SELECT * FROM territorial_domain_events WHERE branch_id=? ORDER BY id", (branch,)
    ).fetchall())
    rows.sort(key=lambda r: int(r["id"]))
    return rows


def replay_territorial_state(conn: sqlite3.Connection, branch: int | None = None, *, through_event_id: int | None = None) -> dict[str, Any]:
    branch = ensure_base_branch(conn) if branch is None else int(branch)
    state = empty_state()
    for row in _effective_event_rows(conn, branch):
        if through_event_id is not None and int(row["id"]) > int(through_event_id):
            continue
        apply_event_to_state(state, str(row["event_type"]), int(row["event_version"]), _loads(row["payload_json"]))
    return state


def rebuild_territorial_projection(conn: sqlite3.Connection, branch: int | None = None) -> dict[str, Any]:
    branch = ensure_base_branch(conn) if branch is None else int(branch)
    rows = _effective_event_rows(conn, branch)
    state = empty_state()
    for row in rows:
        apply_event_to_state(state, str(row["event_type"]), int(row["event_version"]), _loads(row["payload_json"]))
    _write_projection(conn, branch, state, int(rows[-1]["id"]) if rows else None)
    return state


def append_territorial_event(
    conn: sqlite3.Connection,
    event_type: str,
    payload: dict[str, Any],
    *,
    branch: int | None = None,
    day: int | None = None,
    event_version: int | None = None,
    cause_kind: str | None = None,
    cause_id: int | None = None,
) -> int:
    branch = ensure_base_branch(conn) if branch is None else int(branch)
    if event_type not in CURRENT_EVENT_VERSIONS:
        raise ValueError(f"unsupported territorial event type: {event_type}")
    version = int(event_version or CURRENT_EVENT_VERSIONS[event_type])
    # Validate/upcast now so a malformed historical version never enters the stream.
    _upcast(event_type, version, dict(payload))
    zid = payload.get("zone_id")
    stream_key = f"zone:{int(zid)}" if zid is not None else "territory:global"
    seq = _stream_sequence(conn, branch, stream_key)
    cur = conn.execute(
        """INSERT INTO territorial_domain_events(
               branch_id,stream_key,stream_sequence,day,event_type,event_version,payload_json,cause_kind,cause_id
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (branch, stream_key, seq, _day(conn) if day is None else int(day), event_type, version, _j(payload), cause_kind, cause_id),
    )
    event_id = int(cur.lastrowid)
    # Keep the sidecar projection hot. Rebuild first if this is the first branch-local event.
    if not conn.execute("SELECT 1 FROM territorial_projection_zones WHERE branch_id=? LIMIT 1", (branch,)).fetchone() and branch != ensure_base_branch(conn):
        rebuild_territorial_projection(conn, branch)
    else:
        # Applying to an in-memory state and replacing projection is intentionally simple in the
        # spike. If cut over later, owner-specific incremental projectors can replace this.
        state = replay_territorial_state(conn, branch)
        _write_projection(conn, branch, state, event_id)
    return event_id


def authoritative_territorial_state(conn: sqlite3.Connection) -> dict[str, Any]:
    """Current SQL owner rendered into the same shape as the event-sourced projection."""
    state = empty_state()
    for r in conn.execute(
        """SELECT zone_id,organization_id,strength,local_support,fear,started_day
           FROM underworld_zone_claims WHERE claim_kind='controller' AND status='active' ORDER BY zone_id,id"""
    ).fetchall():
        _zone(state, int(r["zone_id"]))["controller"] = {
            "organization_id": int(r["organization_id"]), "strength": float(r["strength"]),
            "local_support": float(r["local_support"]), "fear": float(r["fear"]), "started_day": int(r["started_day"]),
        }
    for r in conn.execute(
        """SELECT zone_id,organization_id,strength,started_day FROM underworld_zone_claims
           WHERE claim_kind='challenger' AND status='active' ORDER BY zone_id,organization_id,id"""
    ).fetchall():
        _zone(state, int(r["zone_id"]))["challengers"][str(int(r["organization_id"]))] = {
            "strength": float(r["strength"]), "started_day": int(r["started_day"]),
        }
    for r in conn.execute(
        """SELECT id,zone_id,controller_organization_id,guest_organization_id,activity_kind,tribute_rate,started_day,expiry_day
           FROM underworld_operating_permissions WHERE status='active' ORDER BY id"""
    ).fetchall():
        state["permissions"][str(int(r["id"]))] = {
            "zone_id": int(r["zone_id"]), "controller_organization_id": int(r["controller_organization_id"]),
            "guest_organization_id": int(r["guest_organization_id"]), "activity_kind": str(r["activity_kind"]),
            "tribute_rate": float(r["tribute_rate"]), "started_day": int(r["started_day"]),
            "expiry_day": int(r["expiry_day"]) if r["expiry_day"] is not None else None,
        }
    return state


def projection_state(conn: sqlite3.Connection, branch: int | None = None) -> dict[str, Any]:
    branch = ensure_base_branch(conn) if branch is None else int(branch)
    state = empty_state()
    for r in conn.execute("SELECT * FROM territorial_projection_zones WHERE branch_id=? ORDER BY zone_id", (branch,)).fetchall():
        z = _zone(state, int(r["zone_id"]))
        if r["controller_organization_id"] is not None:
            z["controller"] = {
                "organization_id": int(r["controller_organization_id"]), "strength": float(r["strength"]),
                "local_support": float(r["local_support"]), "fear": float(r["fear"]), "started_day": int(r["started_day"]),
            }
    for r in conn.execute("SELECT * FROM territorial_projection_challengers WHERE branch_id=? ORDER BY zone_id,organization_id", (branch,)).fetchall():
        _zone(state, int(r["zone_id"]))["challengers"][str(int(r["organization_id"]))] = {
            "strength": float(r["strength"]), "started_day": int(r["started_day"]),
        }
    for r in conn.execute("SELECT * FROM territorial_projection_permissions WHERE branch_id=? ORDER BY permission_id", (branch,)).fetchall():
        state["permissions"][str(int(r["permission_id"]))] = {
            "zone_id": int(r["zone_id"]), "controller_organization_id": int(r["controller_organization_id"]),
            "guest_organization_id": int(r["guest_organization_id"]), "activity_kind": str(r["activity_kind"]),
            "tribute_rate": float(r["tribute_rate"]), "started_day": int(r["started_day"]),
            "expiry_day": int(r["expiry_day"]) if r["expiry_day"] is not None else None,
        }
    return state


def create_snapshot(conn: sqlite3.Connection, branch: int | None = None) -> int:
    branch = ensure_base_branch(conn) if branch is None else int(branch)
    rows = _effective_event_rows(conn, branch)
    through = int(rows[-1]["id"]) if rows else 0
    state = replay_territorial_state(conn, branch, through_event_id=through)
    cur = conn.execute(
        "INSERT INTO territorial_event_snapshots(branch_id,through_event_id,day,state_json) VALUES (?,?,?,?)",
        (branch, through, _day(conn), _j(state)),
    )
    return int(cur.lastrowid)


def replay_from_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> dict[str, Any]:
    snap = conn.execute("SELECT * FROM territorial_event_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    if not snap:
        raise ValueError("unknown territorial snapshot")
    state = _loads(snap["state_json"])
    through = int(snap["through_event_id"])
    for row in _effective_event_rows(conn, int(snap["branch_id"])):
        if int(row["id"]) <= through:
            continue
        apply_event_to_state(state, str(row["event_type"]), int(row["event_version"]), _loads(row["payload_json"]))
    return state


def create_branch(conn: sqlite3.Connection, branch_key: str, *, parent_branch: int | None = None, fork_event_id: int | None = None, metadata: dict[str, Any] | None = None) -> int:
    parent = ensure_base_branch(conn) if parent_branch is None else int(parent_branch)
    if conn.execute("SELECT 1 FROM territorial_event_branches WHERE branch_key=?", (branch_key,)).fetchone():
        raise ValueError("territorial branch key already exists")
    parent_rows = _effective_event_rows(conn, parent)
    max_parent = int(parent_rows[-1]["id"]) if parent_rows else 0
    fork = max_parent if fork_event_id is None else int(fork_event_id)
    if fork > max_parent:
        raise ValueError("fork event is beyond parent branch history")
    cur = conn.execute(
        """INSERT INTO territorial_event_branches(branch_key,parent_branch_id,fork_event_id,created_day,status,metadata_json)
           VALUES (?,?,?,?, 'active',?)""",
        (branch_key, parent, fork, _day(conn), _j(metadata or {})),
    )
    bid = int(cur.lastrowid)
    inherited = replay_territorial_state(conn, parent, through_event_id=fork)
    _write_projection(conn, bid, inherited, fork or None)
    return bid


def event_count(conn: sqlite3.Connection, branch: int | None = None) -> int:
    branch = ensure_base_branch(conn) if branch is None else int(branch)
    return int(conn.execute("SELECT COUNT(*) FROM territorial_domain_events WHERE branch_id=?", (branch,)).fetchone()[0])
