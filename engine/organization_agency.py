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



def record_organization_pressure(
    conn: sqlite3.Connection, institution_actor_id: int, pressure_key: str, domain: str, *,
    intensity_delta: float, urgency: float, source_kind: str | None = None, source_id: int | None = None,
    target_kind: str | None = None, target_id: int | None = None, metadata: dict[str, Any] | None = None,
) -> int:
    """Accumulate event-derived institutional pressure without dictating the response."""
    day = _day(conn)
    ensure_agency_profile(conn, institution_actor_id)
    row = conn.execute(
        "SELECT * FROM organization_pressures WHERE institution_actor_id=? AND pressure_key=? AND status='active' ORDER BY id LIMIT 1",
        (institution_actor_id, str(pressure_key)),
    ).fetchone()
    if row:
        new_intensity = max(0.0, min(100.0, float(row['intensity']) + float(intensity_delta)))
        new_urgency = max(float(row['urgency']), max(0.0, min(100.0, float(urgency))))
        old_meta = _json(row['metadata_json'])
        old_meta.update(metadata or {})
        old_meta['last_source_kind'] = source_kind
        old_meta['last_source_id'] = source_id
        conn.execute(
            """UPDATE organization_pressures SET intensity=?,urgency=?,target_kind=COALESCE(?,target_kind),
               target_id=COALESCE(?,target_id),source_kind=?,source_id=?,updated_day=?,metadata_json=? WHERE id=?""",
            (new_intensity, new_urgency, target_kind, target_id, source_kind, source_id, day, json.dumps(old_meta, sort_keys=True), int(row['id'])),
        )
        pid = int(row['id'])
    else:
        cur = conn.execute(
            """INSERT INTO organization_pressures(institution_actor_id,pressure_key,domain,target_kind,target_id,intensity,urgency,source_kind,source_id,status,created_day,updated_day,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
            (institution_actor_id, str(pressure_key), str(domain), target_kind, target_id,
             max(0.0, min(100.0, float(intensity_delta))), max(0.0, min(100.0, float(urgency))),
             source_kind, source_id, day, day, json.dumps(metadata or {}, sort_keys=True)),
        )
        pid = int(cur.lastrowid)
    # Wake lifecycle review sooner; pressure changes future organizational decisions, not the past event itself.
    try:
        conn.execute(
            "UPDATE organization_lifecycle_profiles SET next_review_day=MIN(next_review_day,?) WHERE institution_actor_id=?",
            (day + 1, institution_actor_id),
        )
    except sqlite3.OperationalError:
        pass
    return pid

def ensure_organization_faction(
    conn: sqlite3.Connection, institution_actor_id: int, faction_key: str, *, name: str | None = None,
    sponsor_actor_id: int | None = None, influence: float = 20.0, cohesion: float = 55.0,
    positions: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None,
) -> int:
    """Persist a causally justified faction. Never invent a sponsor merely to populate the table."""
    day = _day(conn)
    conn.execute(
        """INSERT INTO organization_factions(institution_actor_id,faction_key,name,sponsor_actor_id,influence,cohesion,positions_json,status,created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,'active',?,?,?)
           ON CONFLICT(institution_actor_id,faction_key) DO UPDATE SET
             name=COALESCE(excluded.name,organization_factions.name),
             sponsor_actor_id=COALESCE(excluded.sponsor_actor_id,organization_factions.sponsor_actor_id),
             influence=MAX(organization_factions.influence,excluded.influence),
             cohesion=excluded.cohesion,positions_json=excluded.positions_json,status='active',updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
        (institution_actor_id, str(faction_key), name, sponsor_actor_id, max(0,min(100,float(influence))),
         max(0,min(100,float(cohesion))), json.dumps(positions or {}, sort_keys=True), day, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(conn.execute(
        "SELECT id FROM organization_factions WHERE institution_actor_id=? AND faction_key=?",
        (institution_actor_id, str(faction_key)),
    ).fetchone()[0])

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


def project_internal_duel_consequences(conn: sqlite3.Connection, engagement_id: int) -> dict[str, Any]:
    """Project a resolved internal duel into social memory and institutional pressure.

    The duel never directly removes a leader. It can make later succession/faction/lifecycle
    decisions different by recording the prestige/legitimacy consequence of what happened.
    """
    eng = conn.execute("SELECT * FROM combat_engagements WHERE id=? AND engagement_kind='duel' AND status='resolved'", (engagement_id,)).fetchone()
    if not eng:
        return {"projected": False, "reason": "duel not resolved"}
    outcome = _json(eng['outcome_json'])
    winner = outcome.get('winner_actor_id')
    if winner is None:
        return {"projected": False, "reason": "no winner"}
    winner = int(winner)
    cs = conn.execute("SELECT actor_id FROM duel_combatants WHERE engagement_id=? ORDER BY id", (engagement_id,)).fetchall()
    if len(cs) != 2:
        return {"projected": False, "reason": "not two combatants"}
    ids = [int(r[0]) for r in cs]
    loser = ids[1] if ids[0] == winner else ids[0]
    if winner not in ids:
        return {"projected": False, "reason": "winner not combatant"}
    day = _day(conn)
    from .relationships import record_relationship_pair_effect
    stakes = int(eng['stakes'] or 2)
    record_relationship_pair_effect(
        conn, winner, loser, day, source_kind='duel', source_id=engagement_id,
        a_to_b={'familiarity_delta': 2.0, 'respect_delta': 1.5 + stakes * .5, 'professional_confidence_delta': 1.0},
        b_to_a={'familiarity_delta': 2.0, 'respect_delta': 2.0 + stakes, 'resentment_delta': max(0.0, stakes - 2) * .75},
        summary_a="A resolved duel changed the winner's evaluation of the opponent.",
        summary_b="Defeat in a resolved duel changed the loser's evaluation of the winner.",
        metadata={'engagement_id': engagement_id, 'controlled_context': True},
    )
    common = conn.execute(
        """SELECT mw.institution_actor_id FROM institution_memberships mw
           JOIN institution_memberships ml ON ml.institution_actor_id=mw.institution_actor_id
           WHERE mw.member_actor_id=? AND ml.member_actor_id=? AND mw.status='active' AND ml.status='active'
           ORDER BY mw.institution_actor_id""",
        (winner, loser),
    ).fetchall()
    pressures: list[int] = []
    for row in common:
        iid = int(row[0])
        head = conn.execute(
            "SELECT incumbent_actor_id FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key='head' AND status='active'",
            (iid,),
        ).fetchone()
        if not head or head[0] is None or int(head[0]) != loser:
            continue
        # A member publicly defeating the incumbent creates legitimacy pressure, not automatic replacement.
        stage = conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?", (winner,)).fetchone()
        high_stage = str(stage[0]) in {'Fifth','Sixth'} if stage else False
        intensity = 8.0 + stakes * 5.0 + (8.0 if high_stage else 0.0)
        pid = record_organization_pressure(
            conn, iid, 'leadership_legitimacy', 'leadership', intensity_delta=intensity, urgency=min(95.0, 35.0 + stakes * 10.0),
            source_kind='duel', source_id=engagement_id, target_kind='actor', target_id=loser,
            metadata={'winner_actor_id': winner, 'loser_head_actor_id': loser, 'public_defeat': True, 'does_not_force_succession': True},
        )
        pressures.append(pid)
    return {'projected': True, 'winner_actor_id': winner, 'loser_actor_id': loser, 'institution_pressure_ids': pressures}
