from __future__ import annotations

import json
import sqlite3
from typing import Any


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def ensure_agency_profile(conn: sqlite3.Connection, institution_actor_id: int, *, governance_mode: str = "institutional",
                          inheritance: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
    row = conn.execute("SELECT actor_type FROM actors WHERE id=?", (institution_actor_id,)).fetchone()
    if not row or str(row[0]) != "institution":
        raise ValueError("organization agency requires an institution actor")
    conn.execute(
        """INSERT INTO organization_agency_profiles(institution_actor_id,institutional_inheritance_json,governance_mode,last_review_day,metadata_json)
           VALUES (?,?,?,?,?) ON CONFLICT(institution_actor_id) DO UPDATE SET
           governance_mode=excluded.governance_mode,
           institutional_inheritance_json=CASE WHEN organization_agency_profiles.institutional_inheritance_json='{}'
                THEN excluded.institutional_inheritance_json ELSE organization_agency_profiles.institutional_inheritance_json END,
           metadata_json=excluded.metadata_json""",
        (institution_actor_id, json.dumps(inheritance or {}, sort_keys=True), governance_mode, _day(conn), json.dumps(metadata or {}, sort_keys=True)),
    )


def start_regime(conn: sqlite3.Connection, institution_actor_id: int, *, leader_actor_id: int | None = None,
                 regime_kind: str = "continuity", mandate: dict[str, Any] | None = None,
                 worldview: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    active = conn.execute("SELECT id,leader_actor_id,regime_kind FROM organization_regimes WHERE institution_actor_id=? AND status='active'", (institution_actor_id,)).fetchone()
    if active and (active["leader_actor_id"] == leader_actor_id) and str(active["regime_kind"]) == regime_kind:
        return int(active["id"])
    if active:
        conn.execute("UPDATE organization_regimes SET status='ended',ended_day=? WHERE id=?", (day, int(active["id"])))
    cur = conn.execute(
        """INSERT INTO organization_regimes(institution_actor_id,leader_actor_id,regime_kind,mandate_json,worldview_json,started_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,'active',?)""",
        (institution_actor_id, leader_actor_id, regime_kind, json.dumps(mandate or {}, sort_keys=True),
         json.dumps(worldview or {}, sort_keys=True), day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def set_capability(conn: sqlite3.Connection, institution_actor_id: int, capability_key: str, domain: str,
                   capacity: float, readiness: float | None = None, *, basis: dict[str, Any] | None = None) -> None:
    readiness = capacity if readiness is None else readiness
    conn.execute(
        """INSERT INTO organization_capabilities(institution_actor_id,capability_key,domain,capacity,readiness,basis_json,updated_day)
           VALUES (?,?,?,?,?,?,?) ON CONFLICT(institution_actor_id,capability_key) DO UPDATE SET domain=excluded.domain,
           capacity=excluded.capacity,readiness=excluded.readiness,basis_json=excluded.basis_json,updated_day=excluded.updated_day""",
        (institution_actor_id, capability_key, domain, max(0.0,min(100.0,float(capacity))), max(0.0,min(100.0,float(readiness))),
         json.dumps(basis or {}, sort_keys=True), _day(conn)),
    )


def capability(conn: sqlite3.Connection, institution_actor_id: int, capability_key: str) -> tuple[float, float]:
    row = conn.execute("SELECT capacity,readiness FROM organization_capabilities WHERE institution_actor_id=? AND capability_key=?",
                       (institution_actor_id, capability_key)).fetchone()
    return (float(row[0]), float(row[1])) if row else (0.0, 0.0)


def set_strategy_position(conn: sqlite3.Connection, institution_actor_id: int, issue_key: str, domain: str,
                          position: dict[str, Any], *, target_kind: str | None = None, target_id: int | None = None,
                          confidence: float = .5, metadata: dict[str, Any] | None = None) -> None:
    conn.execute(
        """INSERT INTO organization_strategy_positions(institution_actor_id,issue_key,domain,target_kind,target_id,position_json,confidence,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(institution_actor_id,issue_key) DO UPDATE SET domain=excluded.domain,target_kind=excluded.target_kind,
           target_id=excluded.target_id,position_json=excluded.position_json,confidence=excluded.confidence,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
        (institution_actor_id, issue_key, domain, target_kind, target_id, json.dumps(position, sort_keys=True),
         max(0.0,min(1.0,float(confidence))), _day(conn), json.dumps(metadata or {}, sort_keys=True)),
    )


def _unique_institution_name(conn: sqlite3.Connection, base: str, key: str) -> str:
    name = base.strip() or f"Criminal organization {key}"
    if not conn.execute("SELECT 1 FROM actors WHERE name=?", (name,)).fetchone():
        return name
    return f"{name} [{key}]"


def ensure_underworld_institution_identities(conn: sqlite3.Connection) -> int:
    day = _day(conn)
    created = 0
    rows = conn.execute("SELECT * FROM underworld_organizations WHERE status NOT IN ('destroyed','merged') ORDER BY id").fetchall()
    for org in rows:
        iid = org["institution_actor_id"]
        if iid is None:
            display = str(org["name"] or org["organization_key"])
            actor_name = _unique_institution_name(conn, display, str(org["organization_key"]))
            cur = conn.execute(
                """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
                   VALUES (?,'institution',?,?,?,'active',?,0)""",
                (actor_name, f"underworld_{org['organization_type']}", org["primary_location_id"], org["primary_location_id"],
                 "STRUCTURAL institution identity for existing underworld organization; does not alter organization form or canon status."),
            )
            iid = int(cur.lastrowid)
            conn.execute("UPDATE underworld_organizations SET institution_actor_id=?,updated_day=? WHERE id=?", (iid, day, int(org["id"])))
            conn.execute(
                """INSERT OR IGNORE INTO institution_profiles(actor_id,institution_kind,founded_day,primary_location_id,governance_json,culture_json,capacity_json,trajectory,last_review_day,notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (iid, f"underworld_{org['organization_type']}", int(org["created_day"] or 0), org["primary_location_id"],
                 json.dumps({"authority":"criminal_command"}), json.dumps({"organization_form":org["organization_type"]}),
                 json.dumps({"member_count_estimate":float(org["member_count_estimate"])}), "stable", day,
                 "Resolution identity for a pre-existing criminal organization."),
            )
            conn.execute(
                """INSERT OR IGNORE INTO entity_resolution(entity_kind,entity_id,resolution_level,reason,review_cadence_days,next_review_day,last_changed_day,metadata_json)
                   VALUES ('institution',?,'STRUCTURAL','underworld organization identity bridge',NULL,NULL,?,?)""",
                (iid, day, json.dumps({"underworld_organization_id":int(org["id"]),"bridge":"ORGIDENT-01"}, sort_keys=True)),
            )
            created += 1
        ensure_agency_profile(conn, int(iid), governance_mode="criminal_command",
                              inheritance={"organization_form":str(org["organization_type"]), "continuity":"historical_not_destiny"},
                              metadata={"underworld_organization_id":int(org["id"]),"authority":"ENGINE_STRUCTURAL"})
        leader = org["current_leader_actor_id"] if "current_leader_actor_id" in org.keys() else None
        start_regime(conn, int(iid), leader_actor_id=int(leader) if leader is not None else None,
                     regime_kind="criminal_leadership", metadata={"underworld_organization_id":int(org["id"])})
        # Capability is derived from concrete organization state, not aspiration.
        cap_rows = {
            "territorial_authority": float(org["territorial_presence"]),
            "enforcement": max(float(org["violence_capacity"]), float(org["reputation_deterrence"])*.65),
            "racket_operations": float(org["racket_breadth"]),
            "front_business": float(org["front_depth"]),
            "corruption_access": float(org["corrupt_access"]),
            "recruitment": max(0.0,min(100.0,float(org["member_count_estimate"])*1.5 + float(org["membership_stability"])*.35)),
            "organizational_continuity": max(float(org["cohesion"]), float(org["succession_depth"])),
        }
        for key, value in cap_rows.items():
            set_capability(conn, int(iid), key, "underworld", value, basis={"underworld_organization_id":int(org["id"]),"derived_from_persisted_state":True})
    return created


def _infer_institution_governance(conn: sqlite3.Connection, iid: int) -> tuple[str, int | None]:
    prow = conn.execute("SELECT id,ruler_actor_id FROM political_polities WHERE institution_actor_id=? AND status!='dissolved'", (iid,)).fetchone()
    if prow:
        return "state", int(prow["ruler_actor_id"]) if prow["ruler_actor_id"] is not None else None
    urow = conn.execute("SELECT current_leader_actor_id FROM underworld_organizations WHERE institution_actor_id=? AND status NOT IN ('destroyed','merged')", (iid,)).fetchone()
    if urow:
        return "criminal_command", int(urow[0]) if urow[0] is not None else None
    # We do not invent a head from membership ordering. Missing leadership stays unresolved.
    return "institutional", None


def activate_shared_organization_agency(conn: sqlite3.Connection) -> dict[str, int]:
    created_underworld = ensure_underworld_institution_identities(conn)
    day = _day(conn)
    profiles = regimes = 0
    for row in conn.execute("SELECT ip.actor_id,ip.institution_kind,ip.culture_json,ip.governance_json,ip.capacity_json FROM institution_profiles ip JOIN actors a ON a.id=ip.actor_id WHERE a.status='active' ORDER BY ip.actor_id").fetchall():
        iid = int(row["actor_id"])
        governance, leader = _infer_institution_governance(conn, iid)
        before = conn.execute("SELECT 1 FROM organization_agency_profiles WHERE institution_actor_id=?", (iid,)).fetchone()
        ensure_agency_profile(conn, iid, governance_mode=governance,
                              inheritance={"culture":_json(row["culture_json"]),"governance":_json(row["governance_json"]),"institution_kind":str(row["institution_kind"])},
                              metadata={"activated_from_institution_profile":True})
        if not before:
            profiles += 1
        if not conn.execute("SELECT 1 FROM organization_regimes WHERE institution_actor_id=? AND status='active'", (iid,)).fetchone():
            start_regime(conn, iid, leader_actor_id=leader, regime_kind="opening_continuity", metadata={"opening_activation":True})
            regimes += 1
        # Every institution receives only generic structural capabilities. Domain modules can add richer ones.
        cap = _json(row["capacity_json"])
        if cap:
            numeric = [float(v) for v in cap.values() if isinstance(v,(int,float))]
            if numeric:
                set_capability(conn, iid, "institutional_capacity", "general", sum(numeric)/len(numeric), basis={"source":"institution_profiles.capacity_json"})
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('organization_agency_activation_version','1')")
    return {"underworld_institution_identities_created":created_underworld,"organization_agency_profiles_created":profiles,"organization_regimes_created":regimes}
