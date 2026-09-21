from __future__ import annotations

import json
import sqlite3
from typing import Any

from .interactions import create_interaction
from .reputation import value as reputation_value


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def institution_decision_actor(conn: sqlite3.Connection, institution_actor_id: int) -> int | None:
    """Return the current person/structural actor who can receive or make proposals for an institution."""
    row = conn.execute(
        """SELECT pga.decision_actor_id FROM political_polities p
           JOIN polity_government_actors pga ON pga.polity_id=p.id
           WHERE p.institution_actor_id=? AND p.status!='dissolved' LIMIT 1""",
        (institution_actor_id,),
    ).fetchone()
    if row and row[0] is not None:
        return int(row[0])
    row = conn.execute(
        "SELECT current_leader_actor_id FROM underworld_organizations WHERE institution_actor_id=? AND status NOT IN ('destroyed','merged') LIMIT 1",
        (institution_actor_id,),
    ).fetchone()
    if row and row[0] is not None:
        return int(row[0])
    row = conn.execute(
        """SELECT leader_actor_id FROM organization_regimes
           WHERE institution_actor_id=? AND status='active' AND leader_actor_id IS NOT NULL
           ORDER BY started_day DESC,id DESC LIMIT 1""",
        (institution_actor_id,),
    ).fetchone()
    if row:
        return int(row[0])
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='institutional_authority_slots'").fetchone():
        slot = conn.execute(
            "SELECT authority_kind,incumbent_actor_id FROM institutional_authority_slots WHERE institution_actor_id=? AND authority_key='head' AND status='active' ORDER BY id LIMIT 1",
            (institution_actor_id,),
        ).fetchone()
        if slot:
            if slot["incumbent_actor_id"] is not None:
                return int(slot["incumbent_actor_id"])
            if str(slot["authority_kind"]) == "collective":
                return int(institution_actor_id)
            if str(slot["authority_kind"]) in {"unresolved_incumbent", "vacant"}:
                return None
    row = conn.execute(
        """SELECT member_actor_id FROM institution_memberships
           WHERE institution_actor_id=? AND status='active'
             AND (lower(coalesce(role_text,'')) GLOB '*head*' OR lower(coalesce(role_text,'')) GLOB '*master*')
           ORDER BY id LIMIT 1""",
        (institution_actor_id,),
    ).fetchone()
    return int(row[0]) if row else None


def create_proposal(
    conn: sqlite3.Connection,
    proposer_actor_id: int,
    proposal_kind: str,
    domain_key: str,
    title: str,
    *,
    proposer_institution_actor_id: int | None = None,
    target_actor_id: int | None = None,
    target_institution_actor_id: int | None = None,
    source_attention_case_id: int | None = None,
    parent_proposal_id: int | None = None,
    source_kind: str | None = None,
    source_id: int | None = None,
    expires_in_days: int | None = 90,
    metadata: dict[str, Any] | None = None,
) -> int:
    if target_actor_id is None and target_institution_actor_id is None:
        raise ValueError("proposal requires a person or institution target")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO opportunity_proposals(
               proposer_actor_id,proposer_institution_actor_id,target_actor_id,target_institution_actor_id,
               proposal_kind,domain_key,title,status,source_attention_case_id,parent_proposal_id,source_kind,source_id,
               created_day,expires_day,metadata_json
           ) VALUES (?,?,?,?,?,?,?,'draft',?,?,?,?,?,?,?)""",
        (
            proposer_actor_id, proposer_institution_actor_id, target_actor_id, target_institution_actor_id,
            proposal_kind, domain_key, title, source_attention_case_id, parent_proposal_id, source_kind, source_id,
            day, None if expires_in_days is None else day + int(expires_in_days), _j(metadata or {}),
        ),
    )
    return int(cur.lastrowid)


def add_term(
    conn: sqlite3.Connection,
    proposal_id: int,
    term_kind: str,
    *,
    subject_kind: str | None = None,
    subject_id: int | None = None,
    value: dict[str, Any] | None = None,
    required: bool = True,
    execution_order: int = 100,
) -> int:
    cur = conn.execute(
        """INSERT INTO opportunity_proposal_terms(
               proposal_id,term_kind,subject_kind,subject_id,required,execution_order,value_json,status
           ) VALUES (?,?,?,?,?,?,?,'proposed')""",
        (proposal_id, term_kind, subject_kind, subject_id, 1 if required else 0, int(execution_order), _j(value or {})),
    )
    return int(cur.lastrowid)


def present_proposal(conn: sqlite3.Connection, proposal_id: int, *, day: int | None = None, rationale: str | None = None) -> int:
    day = _day(conn) if day is None else int(day)
    p = conn.execute("SELECT * FROM opportunity_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not p:
        raise ValueError("unknown proposal")
    if str(p["status"]) not in {"draft", "countered"}:
        existing = _proposal_interaction(conn, proposal_id, pending_only=True)
        if existing:
            return int(existing["id"])
        raise ValueError("proposal is not presentable")
    recipient = int(p["target_actor_id"]) if p["target_actor_id"] is not None else institution_decision_actor(conn, int(p["target_institution_actor_id"]))
    if recipient is None:
        raise ValueError("target institution has no current decision actor")
    terms = conn.execute("SELECT * FROM opportunity_proposal_terms WHERE proposal_id=? ORDER BY execution_order,id", (proposal_id,)).fetchall()
    summary = [
        {
            "term_kind": str(t["term_kind"]), "subject_kind": t["subject_kind"], "subject_id": t["subject_id"],
            "required": bool(t["required"]), "value": _loads(t["value_json"], {}),
        }
        for t in terms
    ]
    iid = create_interaction(
        conn, int(p["proposer_actor_id"]), recipient, "offer", day,
        urgency=2, stakes=4,
        terms={
            "purpose": str(p["title"]),
            "opportunity_proposal_id": int(proposal_id),
            "proposal_kind": str(p["proposal_kind"]),
            "domain_key": str(p["domain_key"]),
            "proposal_terms": summary,
            "domain_action": {
                "kind": "accept_opportunity_proposal",
                "initiator_actor_id": int(p["proposer_actor_id"]),
                "payload": {"proposal_id": int(proposal_id)},
            },
        },
        rationale=rationale or "A concrete opportunity has been proposed with explicit terms and causal transfer consequences.",
    )
    conn.execute("UPDATE opportunity_proposals SET status='pending' WHERE id=?", (proposal_id,))
    return iid


def _proposal_interaction(conn: sqlite3.Connection, proposal_id: int, *, pending_only: bool = False) -> sqlite3.Row | None:
    sql = "SELECT * FROM interactions" + (" WHERE status='pending'" if pending_only else "") + " ORDER BY id DESC LIMIT 300"
    for row in conn.execute(sql).fetchall():
        if int(_loads(row["terms_json"], {}).get("opportunity_proposal_id") or 0) == int(proposal_id):
            return row
    return None


def counter_proposal(
    conn: sqlite3.Connection,
    original_proposal_id: int,
    countering_actor_id: int,
    *,
    title: str | None = None,
    term_overrides: list[dict[str, Any]] | None = None,
    day: int | None = None,
) -> int:
    day = _day(conn) if day is None else int(day)
    p = conn.execute("SELECT * FROM opportunity_proposals WHERE id=?", (original_proposal_id,)).fetchone()
    if not p or str(p["status"]) not in {"pending", "countered"}:
        raise ValueError("proposal cannot be countered")
    if p["target_actor_id"] is not None and int(p["target_actor_id"]) != int(countering_actor_id):
        inst = p["target_institution_actor_id"]
        if inst is None or institution_decision_actor(conn, int(inst)) != int(countering_actor_id):
            raise ValueError("countering actor is not the proposal recipient")
    new_target_actor = int(p["proposer_actor_id"])
    new_target_inst = int(p["proposer_institution_actor_id"]) if p["proposer_institution_actor_id"] is not None else None
    cid = create_proposal(
        conn, countering_actor_id, str(p["proposal_kind"]), str(p["domain_key"]), title or f"Counter: {p['title']}",
        target_actor_id=new_target_actor, target_institution_actor_id=new_target_inst,
        parent_proposal_id=original_proposal_id, source_kind="counter_proposal", source_id=original_proposal_id,
        metadata={"counter_to": original_proposal_id},
    )
    originals = conn.execute("SELECT * FROM opportunity_proposal_terms WHERE proposal_id=? ORDER BY execution_order,id", (original_proposal_id,)).fetchall()
    overrides = {(x.get("term_kind"), x.get("subject_kind"), x.get("subject_id")): x for x in (term_overrides or [])}
    for t in originals:
        key = (str(t["term_kind"]), t["subject_kind"], t["subject_id"])
        ov = overrides.get(key)
        if ov and ov.get("remove"):
            continue
        add_term(
            conn, cid, str(t["term_kind"]), subject_kind=t["subject_kind"], subject_id=t["subject_id"],
            value=(ov.get("value") if ov else _loads(t["value_json"], {})),
            required=bool(ov.get("required", bool(t["required"]))) if ov else bool(t["required"]),
            execution_order=int(ov.get("execution_order", t["execution_order"])) if ov else int(t["execution_order"]),
        )
    for ov in (term_overrides or []):
        key = (ov.get("term_kind"), ov.get("subject_kind"), ov.get("subject_id"))
        if key in {(str(t["term_kind"]), t["subject_kind"], t["subject_id"]) for t in originals} or ov.get("remove"):
            continue
        add_term(conn, cid, str(ov["term_kind"]), subject_kind=ov.get("subject_kind"), subject_id=ov.get("subject_id"),
                 value=ov.get("value") or {}, required=bool(ov.get("required", True)), execution_order=int(ov.get("execution_order", 100)))
    conn.execute("UPDATE opportunity_proposals SET status='countered' WHERE id=?", (original_proposal_id,))
    return cid


def _end_enterprise_interests(conn: sqlite3.Connection, enterprise_id: int, kind: str, day: int) -> None:
    conn.execute(
        "UPDATE enterprise_control_interests SET status='ended',ended_day=? WHERE enterprise_id=? AND interest_kind=? AND status='active'",
        (day, enterprise_id, kind),
    )


def _insert_enterprise_interest(conn: sqlite3.Connection, enterprise_id: int, kind: str, holder_kind: str, holder_id: int,
                                share: float, day: int, proposal_id: int) -> None:
    conn.execute(
        """INSERT INTO enterprise_control_interests(
               enterprise_id,holder_actor_id,holder_institution_actor_id,interest_kind,share,started_day,status,source_proposal_id,metadata_json
           ) VALUES (?,?,?,?,?,?,'active',?,?)""",
        (enterprise_id, holder_id if holder_kind == "actor" else None, holder_id if holder_kind == "institution" else None,
         kind, max(0.0, min(1.0, float(share))), day, proposal_id, _j({"opportunity01": True})),
    )


def _create_appointment_from_term(conn: sqlite3.Connection, p: sqlite3.Row, term: sqlite3.Row, value: dict[str, Any], day: int, interaction_id: int) -> int:
    institution = int(value.get("institution_actor_id") or p["proposer_institution_actor_id"] or 0)
    holder = int(value.get("holder_actor_id") or p["target_actor_id"] or 0)
    if not institution or not holder:
        raise ValueError("appointment term lacks institution/holder")
    key = str(value.get("appointment_key") or f"opportunity_{p['id']}")
    role_id = int(value.get("role_id") or 0) or None
    if role_id is not None:
        role = conn.execute("SELECT * FROM institutional_roles WHERE id=? AND institution_actor_id=? AND status='active'", (role_id, institution)).fetchone()
        if not role:
            raise ValueError("appointment role is unavailable or belongs to another institution")
        filled = int(conn.execute("SELECT COUNT(*) FROM institutional_appointments WHERE role_id=? AND status='active'", (role_id,)).fetchone()[0])
        if filled >= int(role["capacity_slots"]):
            raise ValueError("appointment role has no open slot")
        key = str(role["role_key"])
        value = dict(value)
        value.setdefault("appointment_kind", str(role["role_kind"]))
        value.setdefault("title", str(role["title"]))
    title = str(value.get("title") or p["title"])
    existing = conn.execute(
        """SELECT id FROM institutional_appointments WHERE appointing_institution_actor_id=? AND holder_actor_id=?
           AND appointment_key=? AND status='active' ORDER BY id LIMIT 1""",
        (institution, holder, key),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO institutional_appointments(
               appointing_institution_actor_id,holder_actor_id,appointment_key,title,domain_key,appointment_kind,
               source_interaction_id,started_day,stipend,exclusivity,status,obligations_json,privileges_json,metadata_json,role_id
           ) VALUES (?,?,?,?,?,?,?, ?,?,?,'active',?,?,?,?)""",
        (institution, holder, key, title, str(p["domain_key"]), str(value.get("appointment_kind") or "technical_office"),
         interaction_id, day, max(0.0, float(value.get("stipend") or 0)), max(0.0, min(1.0, float(value.get("exclusivity") or 0))),
         _j(value.get("obligations", {})), _j(value.get("privileges", {})), _j({"opportunity01": True, "proposal_id": int(p["id"])}), role_id),
    )
    aid = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json)
           VALUES (?,?,'appointed_office',?,'active',?,?,?)
           ON CONFLICT(institution_actor_id,member_actor_id,membership_kind) DO UPDATE SET role_text=excluded.role_text,status='active',left_day=NULL,metadata_json=excluded.metadata_json""",
        (institution, holder, title, day, _j(["OPPORTUNITY-01 accepted appointment"]), _j({"institutional_appointment_id": aid, "proposal_id": int(p["id"])})),
    )
    return aid


def _execute_term(conn: sqlite3.Connection, p: sqlite3.Row, term: sqlite3.Row, day: int, interaction_id: int) -> dict[str, Any]:
    kind = str(term["term_kind"]); value = _loads(term["value_json"], {})
    sid = int(term["subject_id"]) if term["subject_id"] is not None else None
    skind = str(term["subject_kind"]) if term["subject_kind"] is not None else None
    if kind in {"enterprise_legal_ownership", "enterprise_beneficial_control", "enterprise_operation"}:
        if skind != "enterprise" or sid is None:
            raise ValueError(f"{kind} requires enterprise subject")
        holder_kind = str(value.get("holder_kind") or "institution")
        holder_id = int(value.get("holder_id") or (p["proposer_institution_actor_id"] if holder_kind == "institution" else p["proposer_actor_id"]))
        interest = {"enterprise_legal_ownership":"legal_owner", "enterprise_beneficial_control":"beneficial_controller", "enterprise_operation":"operator"}[kind]
        if bool(value.get("replace", True)):
            _end_enterprise_interests(conn, sid, interest, day)
        _insert_enterprise_interest(conn, sid, interest, holder_kind, holder_id, float(value.get("share", 1.0)), day, int(p["id"]))
        if interest == "legal_owner" and float(value.get("share", 1.0)) >= 0.999:
            conn.execute("UPDATE civilian_enterprises SET owner_actor_id=?,updated_day=? WHERE id=?", (holder_id if holder_kind == "actor" else None, day, sid))
        return {"enterprise_id": sid, "interest": interest, "holder_kind": holder_kind, "holder_id": holder_id}
    if kind == "appointment":
        return {"appointment_id": _create_appointment_from_term(conn, p, term, value, day, interaction_id)}
    if kind == "membership":
        institution = int(value.get("institution_actor_id") or p["proposer_institution_actor_id"] or 0)
        member = int(value.get("member_actor_id") or p["target_actor_id"] or 0)
        if not institution or not member: raise ValueError("membership term lacks institution/member")
        mkey = str(value.get("membership_kind") or "member")
        conn.execute(
            """INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json)
               VALUES (?,?,?,?, 'active',?,?,?)
               ON CONFLICT(institution_actor_id,member_actor_id,membership_kind) DO UPDATE SET status='active',left_day=NULL,role_text=excluded.role_text,metadata_json=excluded.metadata_json""",
            (institution, member, mkey, value.get("role_text"), day, _j(["OPPORTUNITY-01 agreement"]), _j({"proposal_id": int(p["id"])})),
        )
        return {"institution_actor_id": institution, "member_actor_id": member, "membership_kind": mkey}
    if kind in {"first_refusal", "exclusivity", "asset_use_right", "access_right", "noncompete"}:
        right_kind = {"asset_use_right":"use_right"}.get(kind, kind)
        grantor_kind = str(value.get("grantor_kind") or ("actor" if p["target_actor_id"] is not None else "institution"))
        grantor_id = int(value.get("grantor_id") or (p["target_actor_id"] if grantor_kind == "actor" else p["target_institution_actor_id"]))
        grantee_kind = str(value.get("grantee_kind") or ("institution" if p["proposer_institution_actor_id"] is not None else "actor"))
        grantee_id = int(value.get("grantee_id") or (p["proposer_institution_actor_id"] if grantee_kind == "institution" else p["proposer_actor_id"]))
        cur = conn.execute(
            """INSERT INTO contractual_rights(
                   grantor_actor_id,grantor_institution_actor_id,grantee_actor_id,grantee_institution_actor_id,
                   right_kind,subject_kind,subject_id,scope_json,started_day,ended_day,status,source_proposal_id
               ) VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)""",
            (grantor_id if grantor_kind=="actor" else None, grantor_id if grantor_kind=="institution" else None,
             grantee_id if grantee_kind=="actor" else None, grantee_id if grantee_kind=="institution" else None,
             right_kind, skind or "other", sid, _j(value.get("scope", value)), day,
             day + int(value["duration_days"]) if value.get("duration_days") is not None else None, int(p["id"])),
        )
        return {"contractual_right_id": int(cur.lastrowid), "right_kind": right_kind}
    if kind == "asset_transfer":
        if skind != "asset" or sid is None: raise ValueError("asset_transfer requires asset subject")
        holder_kind = str(value.get("new_owner_kind") or "institution")
        holder_id = int(value.get("new_owner_id") or (p["proposer_institution_actor_id"] if holder_kind=="institution" else p["proposer_actor_id"]))
        conn.execute(
            "UPDATE strategic_assets SET owner_actor_id=?,owner_institution_actor_id=?,updated_day=? WHERE id=? AND status='active'",
            (holder_id if holder_kind=="actor" else None, holder_id if holder_kind=="institution" else None, day, sid),
        )
        if conn.total_changes == 0: raise ValueError("asset transfer target unavailable")
        return {"asset_id": sid, "new_owner_kind": holder_kind, "new_owner_id": holder_id}
    if kind == "service_commitment":
        provider_kind = skind if skind in {"actor","institution","enterprise"} else str(value.get("provider_kind") or "actor")
        provider_id = sid if sid is not None else int(value.get("provider_id") or 0)
        if not provider_id: raise ValueError("service commitment lacks provider")
        duration = value.get("duration_days")
        cur = conn.execute(
            """INSERT INTO service_engagements(client_actor_id,client_institution_actor_id,provider_kind,provider_id,domain_key,service_kind,scope_json,compensation_json,exclusivity,started_day,end_day,status,source_proposal_id,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?)""",
            (int(p["proposer_actor_id"]) if p["proposer_institution_actor_id"] is None else None,
             int(p["proposer_institution_actor_id"]) if p["proposer_institution_actor_id"] is not None else None,
             provider_kind,provider_id,str(p["domain_key"]),str(value.get("service_kind") or p["domain_key"]),
             _j(value.get("scope",{})),_j(value.get("compensation",{})),max(0,min(1,float(value.get("exclusivity") or 0))),
             day,day+int(duration) if duration is not None else None,int(p["id"]),_j({"opportunity01":True})),
        )
        engagement_id = int(cur.lastrowid)
        if p["proposer_institution_actor_id"] is not None and provider_kind in {"institution", "enterprise"} and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='structural_provider_contracts'").fetchone():
            provider_inst = provider_id if provider_kind == "institution" else None
            provider_ent = provider_id if provider_kind == "enterprise" else None
            conn.execute(
                "INSERT INTO structural_provider_contracts(consumer_institution_actor_id,provider_institution_actor_id,provider_enterprise_id,domain_key,authority_kind,started_day,ended_day,status,terms_json,metadata_json) VALUES (?,?,?,?,'collective_contractual',?,?,'active',?,?)",
                (int(p["proposer_institution_actor_id"]), provider_inst, provider_ent, str(p["domain_key"]), day,
                 day + int(duration) if duration is not None else None,
                 _j({"service_kind":str(value.get("service_kind") or p["domain_key"]),"scope":value.get("scope",{}),"compensation":value.get("compensation",{})}),
                 _j({"source_service_engagement_id":engagement_id,"source_proposal_id":int(p["id"]),"no_person_required":True})),
            )
        return {"service_engagement_id":engagement_id,"provider_kind":provider_kind,"provider_id":provider_id}
    if kind in {"supply_commitment", "duration", "residence", "termination_right", "recurring_stipend", "revenue_share", "land_grant", "cash_payment", "other"}:
        # These terms remain authoritative in the agreement snapshot until their domain owner is available.
        return {"persisted_term": kind, "value": value}
    raise ValueError(f"unsupported opportunity term {kind}")


def accept_proposal(conn: sqlite3.Connection, proposal_id: int, accepting_actor_id: int, interaction_id: int, *, day: int | None = None) -> dict[str, Any]:
    day = _day(conn) if day is None else int(day)
    p = conn.execute("SELECT * FROM opportunity_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not p or str(p["status"]) != "pending":
        raise ValueError("proposal is not pending")
    recipient = int(p["target_actor_id"]) if p["target_actor_id"] is not None else institution_decision_actor(conn, int(p["target_institution_actor_id"]))
    if recipient != int(accepting_actor_id):
        raise ValueError("accepting actor is not the proposal recipient")
    if p["expires_day"] is not None and day > int(p["expires_day"]):
        conn.execute("UPDATE opportunity_proposals SET status='expired' WHERE id=?", (proposal_id,))
        raise ValueError("proposal expired")
    terms = conn.execute("SELECT * FROM opportunity_proposal_terms WHERE proposal_id=? ORDER BY execution_order,id", (proposal_id,)).fetchall()
    if not terms:
        raise ValueError("proposal has no terms")
    executed: list[dict[str, Any]] = []
    conn.execute("SAVEPOINT opportunity_accept")
    try:
        for term in terms:
            try:
                result = _execute_term(conn, p, term, day, interaction_id)
                conn.execute("UPDATE opportunity_proposal_terms SET status='executed' WHERE id=?", (int(term["id"]),))
                executed.append({"term_id": int(term["id"]), "term_kind": str(term["term_kind"]), "result": result})
            except Exception:
                if bool(term["required"]):
                    raise
                conn.execute("UPDATE opportunity_proposal_terms SET status='waived' WHERE id=?", (int(term["id"]),))
        snap = [
            {"term_kind": str(t["term_kind"]), "subject_kind": t["subject_kind"], "subject_id": t["subject_id"], "required": bool(t["required"]), "value": _loads(t["value_json"], {})}
            for t in terms
        ]
        patronage_id = None
        if str(p["proposal_kind"]) == "patronage":
            from .patronage import materialize_from_proposal
            patronage_id = materialize_from_proposal(conn, p, day)
            if patronage_id is not None:
                executed.append({"term_id": None, "term_kind": "patronage_relationship", "result": {"patronage_id": patronage_id}})
        cur = conn.execute(
            """INSERT INTO opportunity_agreements(proposal_id,agreement_kind,effective_day,status,terms_snapshot_json,metadata_json)
               VALUES (?,?,?,'active',?,?)""",
            (proposal_id, str(p["proposal_kind"]), day, _j(snap), _j({"interaction_id": interaction_id, "executed": executed, "patronage_id": patronage_id})),
        )
        agreement_id = int(cur.lastrowid)
        conn.execute("UPDATE opportunity_proposals SET status='accepted',accepted_day=? WHERE id=?", (day, proposal_id))
        if p["source_attention_case_id"] is not None:
            conn.execute("UPDATE strategic_attention_cases SET status='fulfilled',last_review_day=?,next_review_day=? WHERE id=?", (day, day, int(p["source_attention_case_id"])))
        conn.execute("RELEASE SAVEPOINT opportunity_accept")
        return {"proposal_id": proposal_id, "agreement_id": agreement_id, "executed": executed}
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT opportunity_accept")
        conn.execute("RELEASE SAVEPOINT opportunity_accept")
        raise


def register_asset(
    conn: sqlite3.Connection, asset_kind: str, name: str, *, owner_actor_id: int | None = None,
    owner_institution_actor_id: int | None = None, location_id: int | None = None, quality: float = 50,
    rarity: float = 50, public_visibility: float = 0, estimated_value: float = 0, offered_for_sale: bool = False,
    metadata: dict[str, Any] | None = None,
) -> int:
    if owner_actor_id is None and owner_institution_actor_id is None:
        raise ValueError("asset needs an owner")
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO strategic_assets(asset_kind,name,owner_actor_id,owner_institution_actor_id,location_id,quality,rarity,
               public_visibility,estimated_value,offered_for_sale,status,created_day,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
        (asset_kind, name, owner_actor_id, owner_institution_actor_id, location_id,
         max(0,min(100,float(quality))), max(0,min(100,float(rarity))), max(0,min(100,float(public_visibility))),
         max(0,float(estimated_value)), 1 if offered_for_sale else 0, day, day, _j(metadata or {})),
    )
    return int(cur.lastrowid)



def register_capability(
    conn: sqlite3.Connection, subject_kind: str, subject_id: int, domain_key: str, capability_key: str, *,
    quality: float = 50, capacity: float = 50, public_visibility: float = 0, availability: float = 100,
    status: str = "active", source_kind: str | None = None, source_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT INTO opportunity_capabilities(subject_kind,subject_id,domain_key,capability_key,quality,capacity,public_visibility,availability,status,source_kind,source_id,updated_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(subject_kind,subject_id,domain_key,capability_key) DO UPDATE SET
             quality=excluded.quality,capacity=excluded.capacity,public_visibility=excluded.public_visibility,availability=excluded.availability,
             status=excluded.status,source_kind=excluded.source_kind,source_id=excluded.source_id,updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
        (subject_kind,int(subject_id),domain_key,capability_key,max(0,min(100,float(quality))),max(0,min(100,float(capacity))),
         max(0,min(100,float(public_visibility))),max(0,min(100,float(availability))),status,source_kind,source_id,day,_j(metadata or {})),
    )
    return int(conn.execute("SELECT id FROM opportunity_capabilities WHERE subject_kind=? AND subject_id=? AND domain_key=? AND capability_key=?",
                            (subject_kind,int(subject_id),domain_key,capability_key)).fetchone()[0])


def create_search(
    conn: sqlite3.Connection, seeker_actor_id: int, search_kind: str, domain_key: str, *,
    seeker_institution_actor_id: int | None = None, role_key: str | None = None, min_quality: float = 0,
    intensity: float = 50, preferred_location_id: int | None = None, willingness_to_poach: float = 0,
    expires_in_days: int | None = 180, metadata: dict[str, Any] | None = None,
) -> int:
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO opportunity_searches(seeker_actor_id,seeker_institution_actor_id,search_kind,domain_key,role_key,min_quality,
               intensity,preferred_location_id,willingness_to_poach,status,created_day,next_review_day,expires_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,'searching',?,?,?,?)""",
        (seeker_actor_id, seeker_institution_actor_id, search_kind, domain_key, role_key,
         max(0,min(100,float(min_quality))), max(0,min(100,float(intensity))), preferred_location_id,
         max(0,min(100,float(willingness_to_poach))), day, day, None if expires_in_days is None else day+int(expires_in_days), _j(metadata or {})),
    )
    return int(cur.lastrowid)


def _actor_obligation_load(conn: sqlite3.Connection, actor_id: int) -> tuple[float, list[str]]:
    blockers: list[str] = []
    load = 0.0
    n = int(conn.execute("SELECT COUNT(*) FROM institutional_appointments WHERE holder_actor_id=? AND status='active'", (actor_id,)).fetchone()[0])
    if n: load += min(.55, .22*n); blockers.append(f"{n} active appointment(s)")
    n = int(conn.execute("SELECT COUNT(*) FROM enterprise_staff WHERE actor_id=? AND status='active'", (actor_id,)).fetchone()[0])
    if n: load += min(.35, .15*n); blockers.append(f"{n} active enterprise role(s)")
    n = int(conn.execute("SELECT COUNT(*) FROM institution_memberships WHERE member_actor_id=? AND status='active'", (actor_id,)).fetchone()[0])
    if n: load += min(.30, .08*n); blockers.append(f"{n} active institutional membership(s)")
    return min(.92, load), blockers


def discover_search(conn: sqlite3.Connection, search_id: int) -> list[dict[str, Any]]:
    s = conn.execute("SELECT * FROM opportunity_searches WHERE id=?", (search_id,)).fetchone()
    if not s: raise ValueError("unknown search")
    if str(s["status"]) != "searching": return []
    day = _day(conn); kind = str(s["search_kind"]); out: list[dict[str, Any]] = []
    conn.execute("DELETE FROM opportunity_search_results WHERE search_id=?", (search_id,))
    if kind == "talent":
        rows = conn.execute(
            """SELECT a.id,a.name,a.subtype,a.current_location_id,ac.score
               FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id JOIN actors a ON a.id=ac.actor_id
               WHERE d.domain_key=? AND a.status='active' AND a.actor_type='character' AND ac.score>=?
               ORDER BY ac.score DESC,a.id""",
            (str(s["domain_key"]), float(s["min_quality"])),
        ).fetchall()
        for r in rows:
            aid = int(r["id"])
            if aid == int(s["seeker_actor_id"]): continue
            rep = reputation_value(conn, "actor", aid, [str(s["domain_key"]), "professional", "public"], default=28)
            load, blockers = _actor_obligation_load(conn, aid)
            independent_bonus = 12.0 if load < .15 else 0.0
            poach = float(s["willingness_to_poach"])/100.0
            availability = max(.03, 1.0 - load*(1.0-poach*.7))
            loc_bonus = 0.0
            if s["preferred_location_id"] is not None and r["current_location_id"] is not None and int(s["preferred_location_id"]) == int(r["current_location_id"]): loc_bonus = 7.0
            fit = float(r["score"])*.58 + rep*.24 + availability*18 + independent_bonus + loc_bonus
            confidence = min(.95, .30 + rep/160.0)
            conn.execute(
                "INSERT INTO opportunity_search_results(search_id,candidate_kind,candidate_id,fit_score,confidence,availability,discovered_day,blockers_json,metadata_json) VALUES (?,'actor',?,?,?,?,?,?,?)",
                (search_id, aid, fit, confidence, availability, day, _j(blockers), _j({"competence": float(r["score"]), "reputation": rep, "subtype": r["subtype"]})),
            )
            out.append({"candidate_kind":"actor","candidate_id":aid,"fit_score":fit,"availability":availability,"blockers":blockers,"name":r["name"]})
    elif kind == "service_provider":
        capability_key = str(s["role_key"] or s["domain_key"])
        rows = conn.execute(
            """SELECT * FROM opportunity_capabilities WHERE status IN ('active','strained') AND domain_key=?
               AND capability_key=? AND quality>=? ORDER BY quality DESC,public_visibility DESC,id""",
            (str(s["domain_key"]), capability_key, float(s["min_quality"])),
        ).fetchall()
        for r in rows:
            sk=str(r["subject_kind"]); sid=int(r["subject_id"]); visibility=float(r["public_visibility"]); availability=float(r["availability"])/100.0
            if visibility < 20 and availability < .8:
                continue
            if sk=='actor' and sid==int(s["seeker_actor_id"]):
                continue
            confidence=min(.97,.25+visibility/125.0)
            fit=float(r["quality"])*.55 + float(r["capacity"])*.15 + visibility*.18 + availability*12
            blockers=[]
            if str(r["status"])=='strained': blockers.append('provider is strained')
            if availability < .35: blockers.append('limited current availability')
            candidate_kind = 'institution' if sk=='institution' else ('enterprise' if sk=='enterprise' else 'actor')
            conn.execute(
                "INSERT INTO opportunity_search_results(search_id,candidate_kind,candidate_id,fit_score,confidence,availability,discovered_day,blockers_json,metadata_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (search_id,candidate_kind,sid,fit,confidence,availability,day,_j(blockers),_j({"capability_id":int(r["id"]),"capability_key":capability_key,"quality":float(r["quality"]),"capacity":float(r["capacity"])})),
            )
            out.append({"candidate_kind":candidate_kind,"candidate_id":sid,"fit_score":fit,"availability":availability,"blockers":blockers,"name":None})
    elif kind == "asset":
        rows = conn.execute(
            """SELECT * FROM strategic_assets WHERE status='active' AND asset_kind=? AND quality>=? ORDER BY quality DESC,rarity DESC,id""",
            (str(s["domain_key"]), float(s["min_quality"])),
        ).fetchall()
        for r in rows:
            visibility=float(r["public_visibility"]); offered=bool(r["offered_for_sale"])
            # Unlisted assets are still discoverable if sufficiently visible/renowned.
            if not offered and visibility < 35: continue
            confidence=min(.97,.28+visibility/130.0)
            availability=.92 if offered else .28
            fit=float(r["quality"])*.52+float(r["rarity"])*.28+visibility*.14+availability*6
            blockers=[] if offered else ["owner has not offered asset for sale"]
            conn.execute(
                "INSERT INTO opportunity_search_results(search_id,candidate_kind,candidate_id,fit_score,confidence,availability,discovered_day,blockers_json,metadata_json) VALUES (?,'asset',?,?,?,?,?,?,?)",
                (search_id,int(r["id"]),fit,confidence,availability,day,_j(blockers),_j({"offered_for_sale":offered,"owner_actor_id":r["owner_actor_id"],"owner_institution_actor_id":r["owner_institution_actor_id"]})),
            )
            out.append({"candidate_kind":"asset","candidate_id":int(r["id"]),"fit_score":fit,"availability":availability,"blockers":blockers,"name":r["name"]})
    else:
        raise ValueError(f"search kind {kind} is not yet projected by OPPORTUNITY-01")
    return sorted(out, key=lambda x:(-float(x["fit_score"]), int(x["candidate_id"])))


def propose_talent_recruitment(
    conn: sqlite3.Connection, search_id: int, candidate_actor_id: int, *, proposal_kind: str = "appointment",
    title: str, appointment_key: str | None = None, appointment_kind: str = "technical_office",
    obligations: dict[str, Any] | None = None, privileges: dict[str, Any] | None = None,
    stipend: float = 0, exclusivity: float = 0, role_id: int | None = None,
) -> tuple[int,int]:
    s=conn.execute("SELECT * FROM opportunity_searches WHERE id=?",(search_id,)).fetchone()
    if not s or str(s["status"])!='searching': raise ValueError("search is not active")
    r=conn.execute("SELECT * FROM opportunity_search_results WHERE search_id=? AND candidate_kind='actor' AND candidate_id=?",(search_id,candidate_actor_id)).fetchone()
    if not r: raise ValueError("candidate was not discovered by this search")
    pid=create_proposal(conn,int(s["seeker_actor_id"]),proposal_kind,str(s["domain_key"]),title,
        proposer_institution_actor_id=int(s["seeker_institution_actor_id"]) if s["seeker_institution_actor_id"] is not None else None,
        target_actor_id=candidate_actor_id,source_kind="opportunity_search",source_id=search_id,
        metadata={"search_id":search_id,"fit_score":float(r["fit_score"]),"availability":float(r["availability"])})
    if proposal_kind in {"appointment","employment","permanent_service","retainership"}:
        add_term(conn,pid,"appointment",subject_kind="actor",subject_id=candidate_actor_id,execution_order=50,value={
            "institution_actor_id": int(s["seeker_institution_actor_id"]) if s["seeker_institution_actor_id"] is not None else None,
            "holder_actor_id": candidate_actor_id,"appointment_key":appointment_key or str(s["role_key"] or "recruited_specialist"),
            "title":title,"appointment_kind":appointment_kind,"stipend":stipend,"exclusivity":exclusivity,
            "obligations":obligations or {},"privileges":privileges or {},"role_id":role_id,
        })
    iid=present_proposal(conn,pid,rationale="The seeker searched the existing world for real talent and approached this discovered candidate rather than spawning a role-filler.")
    conn.execute("UPDATE opportunity_searches SET status='approaching' WHERE id=?",(search_id,))
    return pid,iid



def propose_service_contract(
    conn: sqlite3.Connection, search_id: int, candidate_kind: str, candidate_id: int, *, title: str,
    service_kind: str, duration_days: int | None = None, exclusivity: float = 0.0, scope: dict[str, Any] | None = None,
) -> tuple[int,int]:
    s=conn.execute("SELECT * FROM opportunity_searches WHERE id=?",(search_id,)).fetchone()
    if not s or str(s["status"])!='searching': raise ValueError("search is not active")
    r=conn.execute("SELECT * FROM opportunity_search_results WHERE search_id=? AND candidate_kind=? AND candidate_id=?",(search_id,candidate_kind,candidate_id)).fetchone()
    if not r: raise ValueError("provider was not discovered by this search")
    target_actor = candidate_id if candidate_kind=='actor' else None
    target_inst = candidate_id if candidate_kind=='institution' else None
    if candidate_kind=='enterprise':
        erow=conn.execute("SELECT owner_actor_id,institution_actor_id FROM civilian_enterprises WHERE id=? AND status IN ('active','strained')",(candidate_id,)).fetchone()
        if not erow: raise ValueError("enterprise provider unavailable")
        target_actor=int(erow["owner_actor_id"]) if erow["owner_actor_id"] is not None else None
        target_inst=int(erow["institution_actor_id"]) if target_actor is None and erow["institution_actor_id"] is not None else None
    pid=create_proposal(conn,int(s["seeker_actor_id"]),'temporary_service',str(s["domain_key"]),title,
        proposer_institution_actor_id=int(s["seeker_institution_actor_id"]) if s["seeker_institution_actor_id"] is not None else None,
        target_actor_id=target_actor,target_institution_actor_id=target_inst,source_kind='opportunity_search',source_id=search_id,
        metadata={"search_id":search_id,"provider_candidate_kind":candidate_kind,"provider_candidate_id":candidate_id})
    add_term(conn,pid,'service_commitment',subject_kind=candidate_kind if candidate_kind!='enterprise' else 'enterprise',subject_id=candidate_id,execution_order=20,
             value={"service_kind":service_kind,"duration_days":duration_days,"scope":scope or {},"exclusivity":float(exclusivity)})
    if exclusivity>0:
        add_term(conn,pid,'exclusivity',subject_kind='service',subject_id=None,required=False,execution_order=30,
                 value={"grantor_kind":'institution' if candidate_kind=='institution' else 'actor',"grantor_id":candidate_id if candidate_kind!='enterprise' else target_actor,
                        "grantee_kind":'institution' if s["seeker_institution_actor_id"] is not None else 'actor',
                        "grantee_id":int(s["seeker_institution_actor_id"]) if s["seeker_institution_actor_id"] is not None else int(s["seeker_actor_id"]),
                        "duration_days":duration_days,"scope":{"service_kind":service_kind,"fraction":float(exclusivity)}})
    iid=present_proposal(conn,pid,rationale='A real service provider was discovered from its persisted capability and approached with explicit scope and terms.')
    conn.execute("UPDATE opportunity_searches SET status='approaching' WHERE id=?",(search_id,))
    return pid,iid


def make_unsolicited_asset_offer(
    conn: sqlite3.Connection, proposer_actor_id: int, asset_id: int, *, proposer_institution_actor_id: int | None = None,
    price: float | None = None, title: str | None = None,
) -> tuple[int,int]:
    a=conn.execute("SELECT * FROM strategic_assets WHERE id=? AND status='active'",(asset_id,)).fetchone()
    if not a: raise ValueError("asset is unavailable")
    target_actor=int(a["owner_actor_id"]) if a["owner_actor_id"] is not None else None
    target_inst=int(a["owner_institution_actor_id"]) if a["owner_institution_actor_id"] is not None else None
    pid=create_proposal(conn,proposer_actor_id,"asset_purchase",str(a["asset_kind"]),title or f"Offer to purchase {a['name']}",
        proposer_institution_actor_id=proposer_institution_actor_id,target_actor_id=target_actor,target_institution_actor_id=target_inst,
        source_kind="unsolicited_asset_interest",source_id=asset_id,metadata={"asset_was_listed":bool(a["offered_for_sale"]),"asset_visibility":float(a["public_visibility"])})
    if price is not None:
        add_term(conn,pid,"cash_payment",subject_kind="asset",subject_id=asset_id,value={"amount":float(price)},required=False,execution_order=10)
    add_term(conn,pid,"asset_transfer",subject_kind="asset",subject_id=asset_id,value={"new_owner_kind":"institution" if proposer_institution_actor_id is not None else "actor","new_owner_id":proposer_institution_actor_id or proposer_actor_id},execution_order=50)
    iid=present_proposal(conn,pid,rationale="The asset was known and strategically desirable even though its owner had not listed it for sale.")
    return pid,iid


def summary(conn: sqlite3.Connection) -> dict[str,int]:
    q=lambda sql:int(conn.execute(sql).fetchone()[0])
    return {
        "pending_proposals":q("SELECT COUNT(*) FROM opportunity_proposals WHERE status='pending'"),
        "active_agreements":q("SELECT COUNT(*) FROM opportunity_agreements WHERE status='active'"),
        "active_contractual_rights":q("SELECT COUNT(*) FROM contractual_rights WHERE status='active'"),
        "active_searches":q("SELECT COUNT(*) FROM opportunity_searches WHERE status IN ('searching','approaching')"),
        "strategic_assets":q("SELECT COUNT(*) FROM strategic_assets WHERE status='active'"),
    }


def _institutions_decided_by(conn: sqlite3.Connection, actor_id: int) -> list[int]:
    ids: set[int] = set()
    for r in conn.execute("SELECT institution_actor_id FROM organization_regimes WHERE leader_actor_id=? AND status='active'", (actor_id,)).fetchall():
        ids.add(int(r[0]))
    for r in conn.execute(
        """SELECT p.institution_actor_id FROM political_polities p
           JOIN polity_government_actors g ON g.polity_id=p.id WHERE g.decision_actor_id=? AND p.status!='dissolved'""",
        (actor_id,),
    ).fetchall():
        ids.add(int(r[0]))
    return sorted(ids)


def opportunity_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]):
    """DEC-01 bridge: institution-owned pressures may request a concrete search/approach.

    OPPORTUNITY never invents the need. A domain must persist an organization pressure whose metadata
    contains `opportunity_need`; this layer only turns that owned need into search and relationship formation.
    """
    from .decision_runtime import DecisionCandidate
    out: list[DecisionCandidate] = []
    institutions = _institutions_decided_by(conn, actor_id)
    for iid in institutions:
        pressures = conn.execute(
            "SELECT * FROM organization_pressures WHERE institution_actor_id=? AND status='active' ORDER BY intensity DESC,urgency DESC,id LIMIT 6",
            (iid,),
        ).fetchall()
        for pr in pressures:
            meta = _loads(pr["metadata_json"], {})
            need = meta.get("opportunity_need") if isinstance(meta, dict) else None
            if not isinstance(need, dict):
                continue
            existing = conn.execute(
                """SELECT id,status FROM opportunity_searches WHERE seeker_actor_id=? AND seeker_institution_actor_id=?
                   AND source_kind='organization_pressure' AND source_id=? AND status IN ('searching','approaching') ORDER BY id DESC LIMIT 1"""
                if False else
                """SELECT id,status FROM opportunity_searches WHERE seeker_actor_id=? AND seeker_institution_actor_id=?
                   AND json_extract(metadata_json,'$.source_pressure_id')=? AND status IN ('searching','approaching') ORDER BY id DESC LIMIT 1""",
                (actor_id, iid, int(pr["id"])),
            ).fetchone()
            base_u = 3.2 + min(3.0, float(pr["intensity"])/35.0) + float(pr["urgency"])/70.0
            if not existing:
                out.append(DecisionCandidate(
                    key=f"opportunity:start_search:{iid}:{int(pr['id'])}", provider_key="opportunity",
                    action_kind="start_opportunity_search", utility=base_u,
                    rationale=f"Respond to institutional pressure '{pr['pressure_key']}' by searching the real world for a suitable {need.get('role_key') or need.get('search_kind') or 'provider'}.",
                    execution_kind="opportunity_action", payload={"institution_actor_id":iid,"pressure_id":int(pr["id"]),"need":need},
                    information_basis={"organization_pressure_id":int(pr["id"]),"institution_actor_id":iid}, tags=("institutional_need","search"),
                ))
                continue
            search_id = int(existing["id"])
            if str(existing["status"]) != "searching":
                continue
            best = conn.execute(
                "SELECT * FROM opportunity_search_results WHERE search_id=? ORDER BY fit_score DESC,candidate_id LIMIT 1",
                (search_id,),
            ).fetchone()
            if not best:
                continue
            ckind=str(best["candidate_kind"]); cid=int(best["candidate_id"])
            target = cid if ckind=='actor' else (institution_decision_actor(conn,cid) if ckind=='institution' else None)
            out.append(DecisionCandidate(
                key=f"opportunity:approach:{search_id}:{ckind}:{cid}", provider_key="opportunity",
                action_kind="approach_opportunity_candidate", utility=base_u + min(2.0,float(best["fit_score"])/60.0),
                rationale=f"Approach the best currently discovered {ckind} candidate for institutional pressure '{pr['pressure_key']}'.",
                execution_kind="opportunity_action", target_actor_id=target,
                payload={"institution_actor_id":iid,"pressure_id":int(pr["id"]),"search_id":search_id,"candidate_kind":ckind,"candidate_id":cid,"need":need},
                information_basis={"organization_pressure_id":int(pr["id"]),"search_id":search_id,"fit_score":float(best["fit_score"])},
                tags=("institutional_need","matched_candidate"),
            ))
    return out


def execute_opportunity_action(conn: sqlite3.Connection, actor_id: int, action_kind: str, payload: dict[str, Any], day: int) -> dict[str, Any]:
    iid=int(payload.get("institution_actor_id") or 0); pressure_id=int(payload.get("pressure_id") or 0); need=payload.get("need") if isinstance(payload.get("need"),dict) else {}
    if not iid or institution_decision_actor(conn,iid) != int(actor_id):
        raise ValueError("actor does not currently decide for the opportunity-seeking institution")
    if action_kind == "start_opportunity_search":
        pr=conn.execute("SELECT * FROM organization_pressures WHERE id=? AND institution_actor_id=? AND status='active'",(pressure_id,iid)).fetchone()
        if not pr: raise ValueError("source institutional pressure is no longer active")
        search_id=create_search(
            conn,actor_id,str(need.get("search_kind") or "talent"),str(need.get("domain_key") or pr["domain"]),
            seeker_institution_actor_id=iid,role_key=need.get("role_key"),min_quality=float(need.get("min_quality") or 0),
            intensity=min(100,float(pr["intensity"])),preferred_location_id=need.get("preferred_location_id"),
            willingness_to_poach=float(need.get("willingness_to_poach") or 0),expires_in_days=int(need.get("expires_in_days") or 180),
            metadata={"source_pressure_id":pressure_id,"proposal":need.get("proposal") or {},"opportunity_need":need},
        )
        results=discover_search(conn,search_id)
        return {"summary":f"Opened opportunity search #{search_id} from institutional pressure and found {len(results)} current candidate(s).","search_id":search_id,"candidate_count":len(results)}
    if action_kind == "approach_opportunity_candidate":
        search_id=int(payload["search_id"]); ckind=str(payload["candidate_kind"]); cid=int(payload["candidate_id"])
        sr=conn.execute("SELECT * FROM opportunity_searches WHERE id=? AND seeker_actor_id=? AND seeker_institution_actor_id=? AND status='searching'",(search_id,actor_id,iid)).fetchone()
        if not sr: raise ValueError("opportunity search is no longer open")
        proposal=need.get("proposal") if isinstance(need.get("proposal"),dict) else _loads(sr["metadata_json"],{}).get("proposal",{})
        if str(sr["search_kind"])=='talent':
            if ckind!='actor': raise ValueError("talent search candidate is not a person")
            if isinstance(need.get("adaptive_plan"), dict):
                from .adaptive_planning import adapt_and_propose_talent
                planned = adapt_and_propose_talent(conn, search_id, cid, need, day=day)
                return {"summary": planned["summary"], "proposal_id": planned["proposal_id"], "interaction_id": planned["interaction_id"],
                        "adaptation_id": planned["adaptation_id"], "adaptation_kind": planned["adaptation_kind"],
                        "program_id": planned.get("program_id"), "role_id": planned.get("role_id")}
            pid,interaction=propose_talent_recruitment(
                conn,search_id,cid,proposal_kind=str(proposal.get("proposal_kind") or "appointment"),
                title=str(proposal.get("title") or sr["role_key"] or "Institutional specialist"),
                appointment_key=proposal.get("appointment_key") or sr["role_key"],appointment_kind=str(proposal.get("appointment_kind") or "technical_office"),
                obligations=proposal.get("obligations") or {},privileges=proposal.get("privileges") or {},
                stipend=float(proposal.get("stipend") or 0),exclusivity=float(proposal.get("exclusivity") or 0),
            )
        elif str(sr["search_kind"])=='service_provider':
            pid,interaction=propose_service_contract(
                conn,search_id,ckind,cid,title=str(proposal.get("title") or f"{sr['role_key'] or sr['domain_key']} service"),
                service_kind=str(proposal.get("service_kind") or sr["role_key"] or sr["domain_key"]),
                duration_days=proposal.get("duration_days"),exclusivity=float(proposal.get("exclusivity") or 0),scope=proposal.get("scope") or {},
            )
        else:
            raise ValueError("autonomous approach currently supports talent and service-provider searches")
        return {"summary":f"Approached a discovered {ckind} candidate with proposal #{pid}.","proposal_id":pid,"interaction_id":interaction}
    raise ValueError(f"unknown opportunity action {action_kind}")
