"""Player intentions use the existing opportunity/social executors, never model writes.

This first slice fills existing roles with existing members. Role creation, promised
pay, recruitment and new divisions need their own causal executors in later slices.
"""
from __future__ import annotations

import json
import re
import sqlite3

from .adaptive_planning import role_open_slots
from .opportunity import institution_decision_actor


def validate_appointment(conn, proposer, holder, role_id):
    role = conn.execute("SELECT * FROM institutional_roles WHERE id=? AND status='active'", (role_id,)).fetchone()
    if not role:
        raise ValueError("That responsibility is not an existing active role.")
    institution = int(role["institution_actor_id"])
    if institution_decision_actor(conn, institution) != proposer:
        raise ValueError("You do not hold the authority to appoint someone for this organisation.")
    for aid in (proposer, holder, institution):
        if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (aid,)).fetchone():
            raise ValueError("A participant or the organisation is no longer active.")
    if holder == proposer or not conn.execute("SELECT 1 FROM actors WHERE id=? AND actor_type='character'", (holder,)).fetchone():
        raise ValueError("This offer requires another living person as its recipient.")
    if not conn.execute("SELECT 1 FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND status='active'", (institution, holder)).fetchone():
        raise ValueError("The recipient is not an existing member of this organisation; recruitment is a separate proposal.")
    if float(role["minimum_candidate_quality"]) > 0:
        skill = conn.execute("""SELECT ac.score FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
            WHERE ac.actor_id=? AND d.domain_key=?""", (holder, role["domain_key"])).fetchone()
        if skill is None or float(skill[0]) < float(role["minimum_candidate_quality"]):
            raise ValueError("The recipient has not demonstrated the competence required for this role.")
    if role_open_slots(conn, role_id) < 1:
        raise ValueError("That role has no vacant place. No existing holder has been displaced.")
    if conn.execute("SELECT 1 FROM institutional_appointments WHERE holder_actor_id=? AND role_id=? AND status='active'", (holder, role_id)).fetchone():
        raise ValueError("The recipient already holds this responsibility.")
    # Requirements belong to the persisted remit, not to model-authored terms.
    remit = json.loads(role["remit_json"])
    for resource, required in remit.get("required_resources", {}).items():
        row = conn.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type=?", (institution, resource)).fetchone()
        if row is None or float(row[0]) < float(required):
            raise ValueError(f"The organisation lacks the {resource} required for this responsibility.")
    return role


def appointment_options(conn, player_id):
    """Own organisational roles are safe; no NPC thoughts or remote rosters are exposed."""
    return [dict(row) for row in conn.execute("""SELECT r.id role_id, a.name institution_name,
            r.title role_title, r.domain_key FROM institutional_roles r
            JOIN actors a ON a.id=r.institution_actor_id
            WHERE r.status='active' AND a.status='active' ORDER BY r.id""")
            if institution_decision_actor(conn, int(conn.execute(
                "SELECT institution_actor_id FROM institutional_roles WHERE id=?", (row["role_id"],)).fetchone()[0])) == player_id]


def known_appointments(conn, player_id):
    """Rediscover one's own offices and appointments issued under one's command."""
    rows = conn.execute("""SELECT ap.id, ap.holder_actor_id, ap.appointing_institution_actor_id,
        h.name holder_name, i.name institution_name, ap.title, ap.started_day, ap.status
        FROM institutional_appointments ap JOIN actors h ON h.id=ap.holder_actor_id
        JOIN actors i ON i.id=ap.appointing_institution_actor_id WHERE ap.status='active'""").fetchall()
    return [{k: row[k] for k in ("id", "holder_name", "institution_name", "title", "started_day", "status")}
            for row in rows if row["holder_actor_id"] == player_id or
            institution_decision_actor(conn, int(row["appointing_institution_actor_id"])) == player_id]


def execute_appointment(conn: sqlite3.Connection, player_id, day, action_id, proposal):
    from .actions import PlayerActionResult
    from .interactions import resolve_interaction
    from .opportunity import create_proposal, add_term, present_proposal, _actor_obligation_load
    from .presence import actor_is_present_candidate

    def blocked(reason):
        return PlayerActionResult(action_id, "blocked", "appoint", reason,
                                  detail={"committed": False})

    if proposal.additional_terms or re.search(r"\b(gold|coins?|money|pay|salary|stipend|transfer)\b|\bnew (division|company|role)\b", proposal.raw_text, re.I):
        return blocked("This first appointment flow cannot yet execute extra pay, transfers or a new division. Nothing has been promised or created.")
    if proposal.target_actor_id is None or not proposal.role_title:
        return blocked("Name the existing subordinate and the existing responsibility you want to offer.")
    sql = """SELECT r.* FROM institutional_roles r JOIN actors a ON a.id=r.institution_actor_id
             WHERE lower(r.title)=lower(?) AND r.status='active'"""
    args = [proposal.role_title]
    if proposal.institution_name:
        sql += " AND lower(a.name)=lower(?)"
        args.append(proposal.institution_name)
    roles = conn.execute(sql, args).fetchall()
    if len(roles) != 1:
        return blocked("That responsibility is unknown or ambiguous. Specify one existing organisation and role; no new role was created.")
    role = roles[0]
    holder = proposal.target_actor_id
    try:
        validate_appointment(conn, player_id, holder, int(role["id"]))
    except ValueError as exc:
        return blocked(str(exc))
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (player_id,)).fetchone()[0]
    if loc is None or not actor_is_present_candidate(conn, holder, int(loc), purpose=f"player_appointment:{player_id}:{holder}"):
        return blocked("The subordinate is not available for a direct offer here. Meet them before presenting it.")
    pid = create_proposal(conn, player_id, "appointment", str(role["domain_key"]),
        f"Offer {role['title']}", proposer_institution_actor_id=int(role["institution_actor_id"]),
        target_actor_id=holder, source_kind="player_action", source_id=action_id,
        metadata={"player_appointment": True, "role_id": int(role["id"]),
                  "appointing_actor_id": player_id, "holder_actor_id": holder})
    add_term(conn, pid, "appointment", subject_kind="actor", subject_id=holder, value={
        "institution_actor_id": int(role["institution_actor_id"]), "holder_actor_id": holder,
        "role_id": int(role["id"]), "title": str(role["title"]),
        "appointment_kind": str(role["role_kind"]), "obligations": json.loads(role["remit_json"]),
    })
    iid = present_proposal(conn, pid, day=day)
    # The established social resolver evaluates directional relationship, motives and
    # seeded uncertainty. Workload adds a real cost; the interpreter supplies no score.
    if conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()[0] == "pending":
        load, _ = _actor_obligation_load(conn, holder)
        terms = json.loads(conn.execute("SELECT terms_json FROM interactions WHERE id=?", (iid,)).fetchone()[0])
        terms["burden"] = 1.0 + load * 3.0
        conn.execute("UPDATE interactions SET terms_json=? WHERE id=?", (json.dumps(terms), iid))
    ir = resolve_interaction(conn, iid, day)
    ap = conn.execute("SELECT id FROM institutional_appointments WHERE source_interaction_id=? AND role_id=? AND status='active'", (iid, role["id"])).fetchone()
    target_name = conn.execute("SELECT name FROM actors WHERE id=?", (holder,)).fetchone()[0]
    if ap:
        status, summary = "applied", f"{target_name} accepted the offer and now holds {role['title']}. The appointment is recorded."
    elif ir.status == "accepted":
        status, summary = "blocked", "The subordinate consented, but the appointment could not be committed because its prerequisites changed. No appointment was created."
    elif ir.status == "countered":
        status, summary = "countered", f"{target_name} countered the offer of {role['title']}. No appointment has been made; the counterproposal awaits your response."
    else:
        status, summary = "refused", f"{target_name} declined the offer of {role['title']}. No appointment was made."
    return PlayerActionResult(action_id, status, "appoint", summary, interaction_id=iid,
        event_ids=(ir.event_id,) if ir.event_id else (), detail={"proposal_id": pid,
        "consent": ir.response, "committed": bool(ap), "appointment_id": int(ap[0]) if ap else None,
        "child_interaction_id": ir.child_interaction_id})
