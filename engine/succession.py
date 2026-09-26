from __future__ import annotations

import json
import sqlite3
from typing import Any

from .organization_agency import record_organization_pressure, ensure_organization_faction, start_regime
from .organization_lifecycle import record_lifecycle_event

_STAGE_RANK = {None: 0, "": 0, "First": 1, "Temper": 2, "Third": 3, "Breach": 4, "Fifth": 5, "Sixth": 6}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def open_authority_transition(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    *,
    authority_key: str = "head",
    trigger_kind: str,
    trigger_actor_id: int | None = None,
    source_kind: str | None = None,
    source_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    day = _day(conn)
    row = conn.execute(
        "SELECT id FROM leadership_transition_cases WHERE institution_actor_id=? AND authority_key=? AND status IN ('open','deferred') ORDER BY id LIMIT 1",
        (institution_actor_id, authority_key),
    ).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        """INSERT INTO leadership_transition_cases(
               institution_actor_id,authority_key,trigger_kind,trigger_actor_id,source_kind,source_id,status,opened_day,metadata_json)
           VALUES (?,?,?,?,?,?,'open',?,?)""",
        (institution_actor_id, authority_key, trigger_kind, trigger_actor_id, source_kind, source_id, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


# A clan or house "is fundamentally reproduced through kinship, inheritance, marriage", but has "no simple
# eldest-child succession: capability, branch acceptance, martial inheritance and household politics all
# matter".  Close kin of the former head therefore gain standing without overriding Stage.
_KIN_BONUS = {"child": 20.0, "sibling": 12.0, "spouse": 6.0}


def _lineage_kin_bonus(conn: sqlite3.Connection, institution_actor_id: int, former_actor_id: int | None) -> dict[int, float]:
    from .opening_family import LINEAGE_KINDS
    kind = conn.execute("SELECT institution_kind FROM institution_profiles WHERE actor_id=?", (institution_actor_id,)).fetchone()
    if former_actor_id is None or not kind or str(kind[0]) not in LINEAGE_KINDS:
        return {}
    out: dict[int, float] = {}
    for r in conn.execute("SELECT actor_b_id,kin_kind FROM kinship_links WHERE actor_a_id=? AND legal_status IN ('recognized','former')",
                          (former_actor_id,)):
        rel = {"parent": "child", "adoptive_parent": "child"}.get(str(r[1]), str(r[1]))
        if rel in _KIN_BONUS:
            out[int(r[0])] = max(out.get(int(r[0]), 0.0), _KIN_BONUS[rel])
    if not any(b == _KIN_BONUS["child"] for b in out.values()):
        # The former head's adult children are members of the house by blood; reveal the eldest if still latent.
        from .opening_family import reveal_latent_adult_child
        child = reveal_latent_adult_child(conn, former_actor_id, reason="lineage succession",
                                          institution_actor_id=institution_actor_id)
        if child is not None:
            out[child] = _KIN_BONUS["child"]
    return out


def _candidate_rows(conn: sqlite3.Connection, institution_actor_id: int, required_stage: str | None,
                    former_actor_id: int | None = None) -> list[tuple[float, int, str]]:
    kin_bonus = _lineage_kin_bonus(conn, institution_actor_id, former_actor_id)
    rows = conn.execute(
        """SELECT m.member_actor_id,m.role_text,m.joined_day,cp.current_stage
           FROM institution_memberships m
           JOIN actors a ON a.id=m.member_actor_id
           LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id
           LEFT JOIN cultivation_profiles cp ON cp.actor_id=a.id
           WHERE m.institution_actor_id=? AND m.status='active' AND a.status='active'
             AND (lp.life_status IS NULL OR lp.life_status='living')
           ORDER BY m.id""",
        (institution_actor_id,),
    ).fetchall()
    required_rank = _STAGE_RANK.get(required_stage, 0)
    day = _day(conn)
    out: list[tuple[float, int, str]] = []
    role_bonus = {
        "heir": 36, "successor": 34, "deputy": 28, "underboss": 28, "lieutenant": 22,
        "elder": 18, "senior master": 18, "master": 12, "officer": 10, "member": 0,
    }
    for r in rows:
        aid = int(r["member_actor_id"])
        stage = str(r["current_stage"] or "")
        rank = _STAGE_RANK.get(stage, 0)
        if required_rank and rank < required_rank:
            continue
        role = str(r["role_text"] or "member").strip().lower()
        bonus = max((v for k, v in role_bonus.items() if k in role), default=0)
        # Stage matters strongly for martial heads; long-standing membership is a smaller continuity signal.
        joined = int(r["joined_day"]) if r["joined_day"] is not None else 0
        tenure_bonus = min(8.0, max(0.0, (day - joined) / 3650.0 * 8.0)) if joined <= day else 0.0
        score = rank * 12.0 + bonus + tenure_bonus + kin_bonus.get(aid, 0.0)
        out.append((score, aid, role))
    return sorted(out, key=lambda x: (-x[0], x[1]))


def resolve_authority_transition(conn: sqlite3.Connection, case_id: int, *, clear_margin: float = 6.0) -> int | None:
    case = conn.execute("SELECT * FROM leadership_transition_cases WHERE id=?", (case_id,)).fetchone()
    if not case:
        raise ValueError("unknown leadership transition case")
    if str(case["status"]) == "resolved":
        return int(case["chosen_actor_id"]) if case["chosen_actor_id"] is not None else None
    iid = int(case["institution_actor_id"])
    key = str(case["authority_key"])
    slot = conn.execute(
        "SELECT * FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key=? ORDER BY id LIMIT 1",
        (iid, key),
    ).fetchone()
    required = str(slot["required_stage"]) if slot and slot["required_stage"] is not None else None
    former = int(case["trigger_actor_id"]) if case["trigger_actor_id"] is not None else None
    candidates = _candidate_rows(conn, iid, required, former)
    day = _day(conn)
    if not candidates:
        conn.execute(
            "UPDATE leadership_transition_cases SET status='deferred',metadata_json=json_patch(metadata_json,?) WHERE id=?",
            (json.dumps({"deferred_reason": "no qualified pre-existing member", "last_review_day": day}), case_id),
        )
        return None
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < clear_margin:
        # A close contest becomes real institutional structure rather than a random winner.
        for score, aid, role in candidates[:2]:
            ensure_organization_faction(
                conn, iid, f"succession:{case_id}:{aid}", name=f"Supporters of actor #{aid}", sponsor_actor_id=aid,
                influence=min(65.0, 20.0 + score * .35), cohesion=58.0,
                positions={"authority_key": key, "supports_actor_id": aid},
                metadata={"leadership_transition_case_id": case_id, "causal": True, "candidate_role": role},
            )
        record_organization_pressure(
            conn, iid, f"succession_contest:{key}", "leadership", intensity_delta=24.0, urgency=72.0,
            source_kind="leadership_transition_case", source_id=case_id,
            metadata={"candidate_actor_ids": [candidates[0][1], candidates[1][1]]},
        )
        conn.execute(
            "UPDATE leadership_transition_cases SET status='deferred',metadata_json=json_patch(metadata_json,?) WHERE id=?",
            (json.dumps({"deferred_reason": "contested qualified candidates", "last_review_day": day}), case_id),
        )
        return None

    chosen = int(candidates[0][1])
    if slot:
        conn.execute(
            "UPDATE institutional_authority_slots SET authority_kind='named_incumbent',incumbent_actor_id=?,status='active',metadata_json=json_patch(metadata_json,?) WHERE id=?",
            (chosen, json.dumps({"succession02_case_id": case_id, "appointed_day": day}), int(slot["id"])),
        )
    else:
        conn.execute(
            """INSERT INTO institutional_authority_slots(institution_actor_id,authority_key,authority_kind,incumbent_actor_id,status,created_day,metadata_json)
               VALUES (?,?, 'named_incumbent',?,'active',?,?)""",
            (iid, key, chosen, day, json.dumps({"succession02_case_id": case_id}, sort_keys=True)),
        )

    # Synchronize domain-specific leader pointers without inventing separate candidates.
    polity = conn.execute("SELECT id FROM political_polities WHERE institution_actor_id=? AND status!='dissolved'", (iid,)).fetchone()
    if polity:
        from .politics import set_ruler
        set_ruler(conn, int(polity["id"]), chosen, reason=f"SUCCESSION-02 authority transition case #{case_id} resolved.")
    uw = conn.execute("SELECT id FROM underworld_organizations WHERE institution_actor_id=? AND status NOT IN ('destroyed','merged')", (iid,)).fetchone()
    if uw:
        conn.execute("UPDATE underworld_organizations SET current_leader_actor_id=?,updated_day=? WHERE id=?", (chosen, day, int(uw["id"])))
        conn.execute("UPDATE underworld_personnel SET role_kind='boss',authority=100 WHERE organization_id=? AND actor_id=?", (int(uw["id"]), chosen))

    if not polity:
        # set_ruler already starts the political regime and records its lifecycle event.
        start_regime(conn, iid, leader_actor_id=chosen, regime_kind="succession", metadata={"leadership_transition_case_id": case_id})
        record_lifecycle_event(
            conn, iid, "leadership_transition", f"Authority '{key}' passed to actor #{chosen}.",
            cause_kind="leadership_transition_case", cause_id=case_id,
            detail={"chosen_actor_id": chosen, "trigger_kind": str(case["trigger_kind"])},
        )
    conn.execute(
        "UPDATE leadership_transition_cases SET status='resolved',resolved_day=?,chosen_actor_id=? WHERE id=?",
        (day, chosen, case_id),
    )
    # Vacancy pressure is no longer active after a clean resolution.
    conn.execute(
        "UPDATE organization_pressures SET status='resolved',updated_day=? WHERE institution_actor_id=? AND pressure_key=? AND status='active'",
        (day, iid, f"authority_vacancy:{key}"),
    )
    return chosen


def handle_actor_death_authority(conn: sqlite3.Connection, actor_id: int, *, source_kind: str = "death", source_id: int | None = None) -> list[int]:
    """Turn a leader's death into vacancies/succession pressure instead of leaving stale authority pointers."""
    day = _day(conn)
    cases: list[int] = []
    slots = conn.execute(
        "SELECT * FROM institutional_authority_slots WHERE incumbent_actor_id=? AND status='active' ORDER BY id",
        (actor_id,),
    ).fetchall()
    for slot in slots:
        iid = int(slot["institution_actor_id"]); key = str(slot["authority_key"])
        conn.execute(
            "UPDATE institutional_authority_slots SET authority_kind='vacant',incumbent_actor_id=NULL,status='vacant',metadata_json=json_patch(metadata_json,?) WHERE id=?",
            (json.dumps({"vacated_day": day, "vacated_by_death_actor_id": actor_id}), int(slot["id"])),
        )
        cid = open_authority_transition(
            conn, iid, authority_key=key, trigger_kind="incumbent_death", trigger_actor_id=actor_id,
            source_kind=source_kind, source_id=source_id, metadata={"authority_slot_id": int(slot["id"])},
        )
        cases.append(cid)
        record_organization_pressure(
            conn, iid, f"authority_vacancy:{key}", "leadership", intensity_delta=35.0, urgency=90.0,
            source_kind="leadership_transition_case", source_id=cid, target_kind="actor", target_id=actor_id,
            metadata={"trigger": "incumbent_death"},
        )
        # Domain-specific succession owners remain authoritative where they already exist.
        is_polity = conn.execute("SELECT 1 FROM political_polities WHERE institution_actor_id=? AND status!='dissolved'", (iid,)).fetchone() is not None
        is_underworld = conn.execute("SELECT 1 FROM underworld_organizations WHERE institution_actor_id=? AND status NOT IN ('destroyed','merged')", (iid,)).fetchone() is not None
        if not is_polity and not is_underworld:
            resolve_authority_transition(conn, cid)

    # Political rulers and underworld leaders may predate/gap the generic authority slot bridge.
    # Politics keeps the dead ruler pointer until its review so the established claim resolver sees the vacancy.
    for p in conn.execute("SELECT id,institution_actor_id FROM political_polities WHERE ruler_actor_id=? AND status!='dissolved'", (actor_id,)).fetchall():
        conn.execute("UPDATE political_polities SET status='succession_crisis' WHERE id=?", (int(p["id"]),))
        if not any(int(s["institution_actor_id"]) == int(p["institution_actor_id"]) for s in slots):
            cid = open_authority_transition(conn, int(p["institution_actor_id"]), trigger_kind="ruler_death", trigger_actor_id=actor_id, source_kind=source_kind, source_id=source_id)
            cases.append(cid)
    for u in conn.execute("SELECT id,institution_actor_id FROM underworld_organizations WHERE current_leader_actor_id=? AND status NOT IN ('destroyed','merged')", (actor_id,)).fetchall():
        conn.execute("UPDATE underworld_organizations SET current_leader_actor_id=NULL,updated_day=? WHERE id=?", (day, int(u["id"])))
        cid = None
        if u["institution_actor_id"] is not None:
            iid = int(u["institution_actor_id"])
            existing = conn.execute("SELECT id FROM leadership_transition_cases WHERE institution_actor_id=? AND authority_key='head' AND status IN ('open','deferred') ORDER BY id LIMIT 1", (iid,)).fetchone()
            cid = int(existing[0]) if existing else open_authority_transition(conn, iid, trigger_kind="underworld_leader_death", trigger_actor_id=actor_id, source_kind=source_kind, source_id=source_id)
            if cid not in cases: cases.append(cid)
        # Existing underworld succession can resolve from actual personnel. Synchronize if it finds a leader.
        from .underworld_rebuild import ensure_organization_leader
        chosen = ensure_organization_leader(conn, int(u["id"]))
        if chosen is not None and cid is not None:
            conn.execute("UPDATE leadership_transition_cases SET status='resolved',resolved_day=?,chosen_actor_id=? WHERE id=?", (day, chosen, cid))
            conn.execute("UPDATE institutional_authority_slots SET authority_kind='named_incumbent',incumbent_actor_id=?,status='active',metadata_json=json_patch(metadata_json,?) WHERE institution_actor_id=? AND authority_key='head'", (chosen, json.dumps({'succession02_case_id':cid,'underworld_owner':True}), int(u['institution_actor_id'])))
    return cases
