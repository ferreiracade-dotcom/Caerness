from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass

from .information import register_event_information
from .relationships import (relationship_view, adjust_relationship, adjust_relationship_pair,
                            record_relationship_effect, record_relationship_pair_effect)


INTERACTION_TYPES = {
    "conversation",
    "offer",
    "request",
    "contract",
    "alliance",
    "negotiation",
    "mediation",
    "demand",
    "threat",
    "investigation",
    "attack",
}


@dataclass(frozen=True)
class InteractionResult:
    interaction_id: int
    status: str
    response: str
    summary: str
    child_interaction_id: int | None = None
    agreement_id: int | None = None
    event_id: int | None = None


def _name(conn: sqlite3.Connection, actor_id: int) -> str:
    row = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not row:
        raise ValueError(f"unknown actor_id {actor_id}")
    return str(row[0])


def _drives(conn: sqlite3.Connection, actor_id: int) -> dict[str, float]:
    row = conn.execute("SELECT * FROM actor_drives WHERE actor_id=?", (actor_id,)).fetchone()
    keys = ("aggression", "risk_tolerance", "patience", "loyalty", "ambition", "pragmatism")
    if not row:
        return {k: 0.5 for k in keys}
    return {k: float(row[k]) for k in keys}


def _rng(conn: sqlite3.Connection, salt: int, day: int) -> random.Random:
    row = conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()
    seed = int(row[0]) if row else 812197
    return random.Random(seed * 1_000_003 + salt * 9_973 + day * 37_219)


def _effective_tier(conn: sqlite3.Connection, actor_id: int, day: int) -> str:
    row = conn.execute(
        "SELECT tier,forced_tier,forced_until_day FROM simulation_profiles WHERE actor_id=?",
        (actor_id,),
    ).fetchone()
    if not row:
        return "STRATEGIC"
    if row["forced_tier"] and row["forced_until_day"] is not None and day <= int(row["forced_until_day"]):
        return str(row["forced_tier"])
    return str(row["tier"])


def _response_delay(conn: sqlite3.Connection, recipient_id: int, urgency: int, day: int) -> int:
    tier = _effective_tier(conn, recipient_id, day)
    base = {"ACTIVE": 2, "STRATEGIC": 5, "DORMANT": 12}[tier]
    # High urgency compresses response time, but even dormant recipients respond eventually.
    return max(1, base - max(0, urgency - 2) * 2)


def _link(
    conn: sqlite3.Connection,
    day: int,
    source_kind: str,
    source_id: int,
    target_kind: str,
    target_id: int,
    relation: str = "caused",
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO causal_links(day,source_kind,source_id,target_kind,target_id,relation)
           VALUES (?,?,?,?,?,?)""",
        (day, source_kind, source_id, target_kind, target_id, relation),
    )


def _record_action(
    conn: sqlite3.Connection,
    interaction_id: int,
    day: int,
    actor_id: int,
    action_type: str,
    summary: str,
    detail: dict | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO interaction_actions(interaction_id,day,actor_id,action_type,summary,detail_json)
           VALUES (?,?,?,?,?,?)""",
        (interaction_id, day, actor_id, action_type, summary, json.dumps(detail or {})),
    )
    return int(cur.lastrowid)


def _wake_recipient(conn: sqlite3.Connection, actor_id: int, stakes: int, day: int) -> None:
    row = conn.execute(
        "SELECT tier,wake_threshold FROM simulation_profiles WHERE actor_id=?", (actor_id,)
    ).fetchone()
    if not row or stakes < int(row["wake_threshold"]):
        return
    tier = str(row["tier"])
    if tier == "DORMANT":
        forced = "ACTIVE" if stakes >= 5 else "STRATEGIC"
        duration = 21 if forced == "ACTIVE" else 45
    elif tier == "STRATEGIC" and stakes >= 5:
        forced, duration = "ACTIVE", 21
    else:
        return
    conn.execute(
        """UPDATE simulation_profiles
           SET forced_tier=?,forced_until_day=?,next_review_day=MIN(next_review_day,?)
           WHERE actor_id=?""",
        (forced, day + duration, day + 1, actor_id),
    )



def _interaction_subject_key(interaction_type: str, terms: dict | None) -> str:
    payload = terms or {}
    po = payload.get("player_operation")
    if isinstance(po, dict):  # the protagonist's own offers are told apart by what is offered and on what terms
        import hashlib
        sig = json.dumps({"op": po.get("op"), "d": po.get("details")}, sort_keys=True, default=str)
        return f"{interaction_type}:op:{po.get('op')}:{hashlib.sha1(sig.encode()).hexdigest()[:10]}"
    subject = payload.get("opportunity_proposal_id") or payload.get("purpose") or payload.get("domain_action_kind") or payload.get("goal_id") or ""
    return f"{interaction_type}:{subject}"

def _reapproach_blocked(conn: sqlite3.Connection, proposer: int, recipient: int, interaction_type: str, day: int, terms: dict | None) -> int | None:
    """Return the recent refusal that closes an unchanged approach after repeated rejection.

    This is a generic safety net. Domain candidate providers should also learn from rejection, but
    repeated identical approaches must not be able to generate hundreds of meaningless interactions.
    """
    if (terms or {}).get("force_reapproach"):
        return None
    key = _interaction_subject_key(interaction_type, terms)
    rows = conn.execute(
        """SELECT id,created_day,resolved_day,terms_json,status FROM interactions
           WHERE proposer_actor_id=? AND recipient_actor_id=? AND interaction_type=?
             AND status='rejected' AND COALESCE(resolved_day,created_day)>=?
           ORDER BY COALESCE(resolved_day,created_day) DESC,id DESC LIMIT 8""",
        (proposer, recipient, interaction_type, max(0, int(day)-365)),
    ).fetchall()
    matching=[]
    for row in rows:
        try:
            old_terms=json.loads(row['terms_json'] or '{}')
        except Exception:
            old_terms={}
        if _interaction_subject_key(interaction_type, old_terms)==key:
            matching.append(row)
    if len(matching) < 3:
        return None
    latest_day=int(matching[0]['resolved_day'] if matching[0]['resolved_day'] is not None else matching[0]['created_day'])
    return int(matching[0]['id']) if day-latest_day < 180 else None

def create_interaction(
    conn: sqlite3.Connection,
    proposer_actor_id: int,
    recipient_actor_id: int,
    interaction_type: str,
    day: int,
    *,
    urgency: int = 2,
    stakes: int = 2,
    terms: dict | None = None,
    rationale: str = "",
    canon_chunk_ids: tuple[int, ...] | list[int] = (),
    parent_interaction_id: int | None = None,
    thread_id: int | None = None,
    response_due_day: int | None = None,
) -> int:
    if interaction_type not in INTERACTION_TYPES:
        raise ValueError(f"unsupported interaction_type: {interaction_type}")
    if proposer_actor_id == recipient_actor_id:
        raise ValueError("an actor cannot initiate an interaction with itself")
    # A counterproposal answers a live thread; it is not a fresh re-approach.
    blocked_by = None if parent_interaction_id is not None else _reapproach_blocked(conn, proposer_actor_id, recipient_actor_id, interaction_type, day, terms)
    if blocked_by is not None:
        return blocked_by
    proposer_name = _name(conn, proposer_actor_id)
    recipient_name = _name(conn, recipient_actor_id)
    urgency = max(1, min(5, int(urgency)))
    stakes = max(1, min(5, int(stakes)))
    if response_due_day is None:
        response_due_day = day + _response_delay(conn, recipient_actor_id, urgency, day)
    cur = conn.execute(
        """INSERT INTO interactions(
               created_day,proposer_actor_id,recipient_actor_id,interaction_type,status,thread_id,
               parent_interaction_id,urgency,stakes,terms_json,rationale,canon_chunk_ids_json,response_due_day
           ) VALUES (?,?,?,?, 'pending', ?,?,?,?,?,?,?,?)""",
        (
            day,
            proposer_actor_id,
            recipient_actor_id,
            interaction_type,
            thread_id,
            parent_interaction_id,
            urgency,
            stakes,
            json.dumps(terms or {}),
            rationale,
            json.dumps(list(canon_chunk_ids)),
            response_due_day,
        ),
    )
    interaction_id = int(cur.lastrowid)
    if parent_interaction_id is not None:
        _link(conn, day, "interaction", int(parent_interaction_id), "interaction", interaction_id, "countered_by")
    purpose = (terms or {}).get("purpose")
    suffix = f" concerning {purpose}" if purpose else ""
    _record_action(
        conn,
        interaction_id,
        day,
        proposer_actor_id,
        "propose",
        f"{proposer_name} initiated a {interaction_type} with {recipient_name}{suffix}.",
        {"urgency": urgency, "stakes": stakes},
    )
    _wake_recipient(conn, recipient_actor_id, stakes, day)
    return interaction_id


def _capacity(conn: sqlite3.Connection, actor_id: int) -> float:
    resources = conn.execute("SELECT amount FROM resources WHERE actor_id=?", (actor_id,)).fetchall()
    resource_score = sum(math.log1p(max(0.0, float(r[0]))) for r in resources)
    profile = conn.execute("SELECT agency FROM simulation_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    agency = float(profile[0]) if profile else 0.5
    return 1.0 + resource_score + 4.0 * agency


def _create_agreement(
    conn: sqlite3.Connection,
    interaction: sqlite3.Row,
    day: int,
    agreement_type: str,
) -> int:
    terms = json.loads(interaction["terms_json"] or "{}")
    duration = int(terms.get("duration_days", 90))
    expiry = None if duration <= 0 else day + duration
    terms_json = interaction["terms_json"] or "{}"

    # Do not mint duplicate relationship objects when repeated negotiations are advancing
    # the same ongoing arrangement. Multiple interactions may point to one agreement.
    existing = conn.execute(
        """SELECT id FROM agreements
           WHERE status='active' AND agreement_type=? AND terms_json=?
             AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))
           ORDER BY id LIMIT 1""",
        (
            agreement_type, terms_json,
            interaction["proposer_actor_id"], interaction["recipient_actor_id"],
            interaction["recipient_actor_id"], interaction["proposer_actor_id"],
        ),
    ).fetchone()
    if existing:
        return int(existing["id"])

    cur = conn.execute(
        """INSERT INTO agreements(
               agreement_type,actor_a_id,actor_b_id,created_day,expiry_day,status,terms_json,source_interaction_id
           ) VALUES (?,?,?,?,?,'active',?,?)""",
        (
            agreement_type,
            interaction["proposer_actor_id"],
            interaction["recipient_actor_id"],
            day,
            expiry,
            terms_json,
            interaction["id"],
        ),
    )
    return int(cur.lastrowid)


def _ensure_conflict_thread(conn: sqlite3.Connection, interaction: sqlite3.Row, day: int) -> int:
    if interaction["thread_id"]:
        return int(interaction["thread_id"])
    a = _name(conn, int(interaction["proposer_actor_id"]))
    b = _name(conn, int(interaction["recipient_actor_id"]))
    cur = conn.execute(
        """INSERT INTO threads(title,scope,status,progress,severity,created_day,updated_day,notes)
           VALUES (?,?, 'active',0,?,?,?,?)""",
        (f"Conflict: {a} / {b}", "inter-actor", int(interaction["stakes"]), day, day, "Created by a direct hostile interaction."),
    )
    thread_id = int(cur.lastrowid)
    conn.execute("INSERT OR IGNORE INTO thread_actors(thread_id,actor_id,role) VALUES (?,?,?)", (thread_id, interaction["proposer_actor_id"], "initiator"))
    conn.execute("INSERT OR IGNORE INTO thread_actors(thread_id,actor_id,role) VALUES (?,?,?)", (thread_id, interaction["recipient_actor_id"], "target"))
    conn.execute("UPDATE interactions SET thread_id=? WHERE id=?", (thread_id, interaction["id"]))
    return thread_id


def _log_event(
    conn: sqlite3.Connection,
    day: int,
    event_type: str,
    title: str,
    summary: str,
    severity: int,
    source_actor_id: int | None,
    target_actor_ids: tuple[int, ...] = (),
) -> int:
    location_id = None
    # For interactions, the recipient's location is usually where the consequence lands.
    if target_actor_ids:
        row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (target_actor_ids[0],)).fetchone()
        if row and row[0] is not None:
            location_id = int(row[0])
    if location_id is None and source_actor_id is not None:
        row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (source_actor_id,)).fetchone()
        if row and row[0] is not None:
            location_id = int(row[0])
    cur = conn.execute(
        """INSERT INTO events(day,event_type,title,summary,severity,location_id,source_actor_id)
           VALUES (?,?,?,?,?,?,?)""",
        (day, event_type, title, summary, severity, location_id, source_actor_id),
    )
    event_id = int(cur.lastrowid)
    for actor_id in target_actor_ids:
        conn.execute(
            "INSERT OR IGNORE INTO event_targets(event_id,actor_id,impact) VALUES (?,?,?)",
            (event_id, actor_id, "direct"),
        )
        _wake_recipient(conn, actor_id, severity, day)
    register_event_information(conn, event_id, day=day)
    return event_id


def _depth(conn: sqlite3.Connection, interaction: sqlite3.Row) -> int:
    depth = 0
    parent = interaction["parent_interaction_id"]
    while parent and depth < 10:
        depth += 1
        row = conn.execute("SELECT parent_interaction_id FROM interactions WHERE id=?", (parent,)).fetchone()
        parent = row[0] if row else None
    return depth


_STANDING_CAP = 0.6


def _standing_term(conn: sqlite3.Connection, proposer: int, recipient: int, kind: str, day: int, interaction_id: int) -> float:
    """What the recipient's view of the proposer adds to the score: respect, felt fear, kin, household
    authority, and how the proposer has treated them.  Obligations run both ways (kin or servants are never
    simply obedient), and the total is clamped so standing never decides alone."""
    from .standing import _children, _parents, _siblings, _spouses

    r = relationship_view(conn, recipient, proposer)  # the recipient's feeling toward the proposer
    t = 0.0
    if kind in {"request", "offer"}:
        t += 0.20 * r["respect"] / 100.0
    if kind in {"demand", "threat"}:
        t += 0.25 * max(0.0, r["fear"]) / 100.0
    is_kin = (proposer in _parents(conn, recipient) or proposer in _children(conn, recipient)
              or proposer in _siblings(conn, recipient) or proposer in _spouses(conn, recipient))
    if is_kin and kind in {"request", "offer"}:
        t += -0.15 if r["resentment"] >= 50 else 0.30
    if not is_kin and kind in {"request", "demand"}:
        authority = conn.execute(
            """SELECT 1 FROM households h WHERE h.head_actor_id=? AND h.status='active' AND (
                   EXISTS (SELECT 1 FROM household_service_terms s WHERE s.household_id=h.id AND s.actor_id=? AND s.status='active')
                OR EXISTS (SELECT 1 FROM household_members m WHERE m.household_id=h.id AND m.actor_id=? AND m.status='active' AND m.role='member'))
               LIMIT 1""", (proposer, recipient, recipient)).fetchone()
        if authority:
            t += 0.25 * max(0.0, 1.0 - max(0.0, r["resentment"]) / 100.0)
    harmed = conn.execute(
        """SELECT (SELECT COUNT(*) FROM interactions WHERE proposer_actor_id=? AND recipient_actor_id=? AND id<>?
                      AND interaction_type IN ('threat','demand') AND status<>'pending' AND created_day>=?)
                + (SELECT COUNT(*) FROM harm_incidents h JOIN events e ON h.source_kind='player_operation' AND e.id=h.source_ref_id
                      WHERE e.source_actor_id=? AND h.actor_id=? AND h.day>=?)""",
        (proposer, recipient, interaction_id, day - 365, proposer, recipient, day - 365)).fetchone()[0]
    t -= min(0.4, 0.10 * int(harmed or 0))
    return max(-_STANDING_CAP, min(_STANDING_CAP, t))


def _social_response(conn: sqlite3.Connection, interaction: sqlite3.Row, day: int) -> InteractionResult:
    proposer = int(interaction["proposer_actor_id"])
    recipient = int(interaction["recipient_actor_id"])
    kind = str(interaction["interaction_type"])
    stakes = int(interaction["stakes"])
    rel = relationship_view(conn, proposer, recipient)
    drives = _drives(conn, recipient)
    terms = json.loads(interaction["terms_json"] or "{}")
    incentive = float(terms.get("incentive", 0.0))
    burden = float(terms.get("burden", 0.0))
    rng = _rng(conn, int(interaction["id"]) * 17 + recipient, day)

    base = {
        "conversation": 0.9,
        "offer": 0.7,
        "request": 0.25,
        "contract": 0.45,
        "alliance": 0.10,
        "negotiation": 0.30,
        "mediation": 0.20,
        "demand": -0.45,
        "threat": -0.90,
    }[kind]
    score = (
        base
        + rel["trust"] / 55.0
        + rel["stance"] / 75.0
        + rel["obligation"] / 90.0
        + 0.55 * drives["pragmatism"]
        + 0.25 * drives["loyalty"]
        - 0.22 * drives["risk_tolerance"] * stakes
        + 0.30 * incentive
        - 0.30 * burden
        + rng.uniform(-0.25, 0.25)
        + _standing_term(conn, proposer, recipient, kind, day, int(interaction["id"]))
    )

    if kind in {"demand", "threat"}:
        # Pragmatic recipients may comply with a costly demand without liking the proposer.
        score += 0.20 * drives["pragmatism"] - 0.30 * drives["aggression"]
        # Force behind the demand (0-3, set by player operations); callers that never set it are unchanged.
        score += 0.45 * max(0.0, min(3.0, float(terms.get("coercion", 0) or 0)))

    proposer_name = _name(conn, proposer)
    recipient_name = _name(conn, recipient)
    depth = _depth(conn, interaction)

    if score >= 1.0:
        response = "accept" if kind not in {"demand", "threat"} else "comply"
        agreement_id = None
        if kind == "conversation":
            agreement_id = None
        elif kind == "contract":
            agreement_id = _create_agreement(conn, interaction, day, "contract")
        elif kind == "alliance":
            agreement_id = _create_agreement(conn, interaction, day, "alliance")
        elif kind in {"offer", "request"}:
            agreement_id = _create_agreement(conn, interaction, day, "service")
        elif kind in {"negotiation", "mediation"}:
            agreement_id = _create_agreement(conn, interaction, day, "understanding")
        elif kind in {"demand", "threat"}:
            agreement_id = _create_agreement(conn, interaction, day, "concession")

        # A successful interaction can materially satisfy the goal that caused it.
        goal_id = terms.get("goal_id")
        if goal_id:
            goal = conn.execute("SELECT id,progress,status FROM goals WHERE id=? AND actor_id=?", (int(goal_id), proposer)).fetchone()
            if goal and goal["status"] == "active":
                if kind in {"contract", "alliance"}:
                    conn.execute("UPDATE goals SET progress=100,status='completed' WHERE id=?", (goal["id"],))
                else:
                    new_progress = min(100.0, float(goal["progress"]) + 18.0 + 4.0 * stakes)
                    conn.execute(
                        "UPDATE goals SET progress=?,status=? WHERE id=?",
                        (new_progress, "completed" if new_progress >= 100 else "active", goal["id"]),
                    )

        if kind in {"demand", "threat"}:
            record_relationship_pair_effect(
                conn, proposer, recipient, day, source_kind="interaction", source_id=int(interaction["id"]),
                a_to_b={"familiarity_delta":1.0,"professional_confidence_delta":0.5},
                b_to_a={"familiarity_delta":1.0,"trust_delta":-2.0,"stance_delta":-2.0,"fear_delta":4.0,"resentment_delta":2.0},
                summary_a="Compliance changed the initiator's evaluation of the recipient.",
                summary_b="Compliance under pressure created fear and resentment toward the initiator.",
                metadata={"interaction_type":kind,"outcome":"complied"},
            )
        else:
            a_obligation = 2.0 if kind == "request" else (1.0 if kind == "contract" else 0.0)
            b_obligation = 2.0 if kind == "offer" else (1.0 if kind == "contract" else 0.0)
            record_relationship_pair_effect(
                conn, proposer, recipient, day, source_kind="interaction", source_id=int(interaction["id"]),
                a_to_b={"familiarity_delta":2.0,"trust_delta":3.0,"stance_delta":2.0,"respect_delta":1.0,"professional_confidence_delta":1.0,"obligation_delta":a_obligation},
                b_to_a={"familiarity_delta":2.0,"trust_delta":2.0,"stance_delta":1.0,"respect_delta":0.5,"professional_confidence_delta":2.0,"obligation_delta":b_obligation},
                summary_a="A successful interaction strengthened confidence in the recipient.",
                summary_b="A successful interaction strengthened confidence in the initiator.",
                metadata={"interaction_type":kind,"outcome":"accepted"},
            )
        if kind == "conversation":
            summary = f"{recipient_name} engaged with {proposer_name}'s approach."
        elif response == "accept":
            summary = f"{recipient_name} accepted {proposer_name}'s {kind}."
        else:
            summary = f"{recipient_name} complied with {proposer_name}'s {kind}."
        _record_action(conn, int(interaction["id"]), day, recipient, response, summary)
        conn.execute(
            "UPDATE interactions SET status='accepted',resolved_day=?,resolution_summary=? WHERE id=?",
            (day, summary, interaction["id"]),
        )
        # v0.28: an accepted social proposal may carry a validated domain action. The
        # callback delegates to the authoritative subsystem (education/health/household/etc.).
        try:
            from .domain_actions import apply_accepted_interaction_domain_action
            domain_result = apply_accepted_interaction_domain_action(conn, interaction, day)
            if domain_result is not None:
                if domain_result.get("blocked"):
                    summary += f" The agreed domain action could not be applied: {domain_result.get('reason','state changed')}."
                else:
                    summary += " The agreed domain action was applied to authoritative state."
                conn.execute("UPDATE interactions SET resolution_summary=? WHERE id=?", (summary, interaction["id"]))
        except Exception as exc:
            # Social acceptance remains historical fact even if the downstream state changed.
            # The domain-action ledger records normal validation failures; this guard prevents
            # an observability/integration error from rolling back the interaction itself.
            conn.execute("INSERT OR REPLACE INTO runtime_flags(key,value,updated_at) VALUES ('last_domain_action_error',?,CURRENT_TIMESTAMP)", (str(exc),))
        if "player_operation" in terms:  # the protagonist's own offer, accepted by the other side during the simulation
            from .player_operations import settle_npc_accepted
            settled = settle_npc_accepted(conn, interaction)
            if settled is not None:
                summary += f" {settled.get('summary', '')}"
                conn.execute("UPDATE interactions SET resolution_summary=? WHERE id=?", (summary, interaction["id"]))
        if agreement_id is not None:
            _link(conn, day, "interaction", int(interaction["id"]), "agreement", agreement_id, "created")
        event_id = None
        if stakes >= 3 or kind in {"contract", "alliance", "threat"}:
            event_id = _log_event(
                conn,
                day,
                f"interaction:{kind}",
                f"{kind.title()} resolved: {proposer_name} / {recipient_name}",
                summary,
                min(5, max(2, stakes)),
                proposer,
                (recipient,),
            )
            _link(conn, day, "interaction", int(interaction["id"]), "event", event_id, "produced")
        return InteractionResult(int(interaction["id"]), "accepted", response, summary, agreement_id=agreement_id, event_id=event_id)

    if score >= -0.15 and depth < 2 and kind not in {"threat", "conversation"}:
        opportunity_pid = int(terms.get("opportunity_proposal_id") or 0)
        if opportunity_pid:
            from .opportunity import counter_proposal, present_proposal
            counter_pid = counter_proposal(conn, opportunity_pid, recipient, title=f"Counterproposal to {terms.get('purpose') or 'opportunity'}")
            child_id = present_proposal(conn, counter_pid, day=day, rationale=f"Counterproposal to opportunity proposal #{opportunity_pid}")
            summary = f"{recipient_name} countered {proposer_name}'s {kind} rather than accepting or refusing outright."
            _record_action(conn, int(interaction["id"]), day, recipient, "counter", summary, {"child_interaction_id": child_id, "counter_proposal_id": counter_pid})
            conn.execute("UPDATE interactions SET status='countered',resolved_day=?,resolution_summary=? WHERE id=?", (day, summary, interaction["id"]))
            record_relationship_pair_effect(
                conn, proposer, recipient, day, source_kind="interaction", source_id=int(interaction["id"]),
                a_to_b={"familiarity_delta":1.0,"trust_delta":0.5,"respect_delta":0.5},
                b_to_a={"familiarity_delta":1.0,"respect_delta":0.5},
                summary_a="A counterproposal kept negotiation open.", summary_b="A counterproposal kept negotiation open.",
                metadata={"interaction_type":kind,"outcome":"countered"},
            )
            return InteractionResult(int(interaction["id"]), "countered", "counter", summary, child_interaction_id=child_id)
        counter_terms = dict(terms)
        counter_terms["counter_depth"] = depth + 1
        counter_terms["burden"] = max(0.0, burden - 0.25)
        counter_terms["incentive"] = incentive + 0.20
        if isinstance(terms.get("player_operation"), dict):  # concrete terms: what he asks instead, and what accepting it will do
            from .player_operations import counter_terms_for
            new_po, said = counter_terms_for(conn, terms["player_operation"], interaction)
            if new_po is not None:
                counter_terms["player_operation"] = new_po
                counter_terms["counter_terms"] = said
        child_id = create_interaction(
            conn,
            recipient,
            proposer,
            kind,
            day,
            urgency=max(1, int(interaction["urgency"]) - 1),
            stakes=stakes,
            terms=counter_terms,
            rationale=f"Counterproposal to interaction {interaction['id']}",
            canon_chunk_ids=tuple(json.loads(interaction["canon_chunk_ids_json"] or "[]")),
            parent_interaction_id=int(interaction["id"]),
            thread_id=interaction["thread_id"],
        )
        summary = f"{recipient_name} countered {proposer_name}'s {kind} rather than accepting or refusing outright."
        _record_action(conn, int(interaction["id"]), day, recipient, "counter", summary, {"child_interaction_id": child_id})
        conn.execute(
            "UPDATE interactions SET status='countered',resolved_day=?,resolution_summary=? WHERE id=?",
            (day, summary, interaction["id"]),
        )
        record_relationship_pair_effect(
            conn, proposer, recipient, day, source_kind="interaction", source_id=int(interaction["id"]),
            a_to_b={"familiarity_delta":1.0,"trust_delta":0.5,"respect_delta":0.5},
            b_to_a={"familiarity_delta":1.0,"respect_delta":0.5},
            summary_a="A counterproposal kept negotiation open.", summary_b="A counterproposal kept negotiation open.",
            metadata={"interaction_type":kind,"outcome":"countered"},
        )
        return InteractionResult(int(interaction["id"]), "countered", "counter", summary, child_interaction_id=child_id)

    response = "reject" if kind not in {"demand", "threat"} else "refuse"
    if kind in {"demand", "threat"}:
        record_relationship_pair_effect(
            conn, proposer, recipient, day, source_kind="interaction", source_id=int(interaction["id"]),
            a_to_b={"familiarity_delta":1.0,"trust_delta":-5.0,"stance_delta":-4.0,"resentment_delta":4.0},
            b_to_a={"familiarity_delta":1.0,"trust_delta":-2.0,"stance_delta":-2.0,"fear_delta":2.0,"resentment_delta":2.0},
            summary_a="Refusal of coercion increased hostility toward the recipient.",
            summary_b="Receiving and refusing coercion increased fear and resentment toward the initiator.",
            metadata={"interaction_type":kind,"outcome":"refused"},
        )
    else:
        record_relationship_pair_effect(
            conn, proposer, recipient, day, source_kind="interaction", source_id=int(interaction["id"]),
            a_to_b={"familiarity_delta":0.5,"trust_delta":-2.0,"stance_delta":-1.0,"resentment_delta":1.0},
            b_to_a={"familiarity_delta":0.5,"professional_confidence_delta":-0.5},
            summary_a="Rejection reduced confidence and created some resentment.",
            summary_b="Rejecting the approach changed confidence in the initiator.",
            metadata={"interaction_type":kind,"outcome":"rejected"},
        )
    summary = f"{recipient_name} {response}d {proposer_name}'s {kind}."
    _record_action(conn, int(interaction["id"]), day, recipient, response, summary)
    conn.execute(
        "UPDATE interactions SET status='rejected',resolved_day=?,resolution_summary=? WHERE id=?",
        (day, summary, interaction["id"]),
    )
    opportunity_pid = int(terms.get("opportunity_proposal_id") or 0)
    if opportunity_pid:
        conn.execute("UPDATE opportunity_proposals SET status='rejected' WHERE id=? AND status='pending'", (opportunity_pid,))
    event_id = None
    if kind in {"demand", "threat"} or stakes >= 4:
        thread_id = _ensure_conflict_thread(conn, interaction, day)
        event_id = _log_event(
            conn,
            day,
            f"interaction:{kind}:rejected",
            f"{kind.title()} refused: {proposer_name} / {recipient_name}",
            summary + " The refusal adds pressure to the relationship but does not determine what either side does next.",
            min(5, max(2, stakes)),
            proposer,
            (recipient,),
        )
        conn.execute("UPDATE threads SET severity=MAX(severity,?),updated_day=? WHERE id=?", (stakes, day, thread_id))
        _link(conn, day, "interaction", int(interaction["id"]), "thread", thread_id, "escalated")
        _link(conn, day, "interaction", int(interaction["id"]), "event", event_id, "produced")
    return InteractionResult(int(interaction["id"]), "rejected", response, summary, event_id=event_id)


def _resolve_investigation(conn: sqlite3.Connection, interaction: sqlite3.Row, day: int) -> InteractionResult:
    proposer = int(interaction["proposer_actor_id"])
    recipient = int(interaction["recipient_actor_id"])
    p = _drives(conn, proposer)
    r = _drives(conn, recipient)
    stakes = int(interaction["stakes"])
    rng = _rng(conn, int(interaction["id"]) * 31, day)
    success_score = 0.8 * p["pragmatism"] + 0.5 * p["patience"] + rng.uniform(-0.25, 0.25)
    confidence = max(0.25, min(0.95, 0.45 + success_score / 3.0))
    proposer_name = _name(conn, proposer)
    recipient_name = _name(conn, recipient)
    purpose = json.loads(interaction["terms_json"] or "{}").get("purpose", "the target's current affairs")
    belief = f"Investigation concerning {recipient_name}: {purpose}."
    conn.execute(
        """INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day)
           VALUES (?,?,?,?,?)
           ON CONFLICT(knower_actor_id,fact_key) DO UPDATE SET belief_text=excluded.belief_text,
             confidence=excluded.confidence,learned_day=excluded.learned_day""",
        (proposer, f"investigation:{interaction['id']}", belief, confidence, day),
    )
    knowledge_id = int(conn.execute(
        "SELECT id FROM knowledge WHERE knower_actor_id=? AND fact_key=?",
        (proposer, f"investigation:{interaction['id']}"),
    ).fetchone()[0])
    _link(conn, day, "interaction", int(interaction["id"]), "knowledge", knowledge_id, "revealed")
    detected = rng.random() < (0.20 + 0.35 * r["pragmatism"] + 0.08 * stakes)
    if detected:
        adjust_relationship(conn, recipient, proposer, day, trust_delta=-3.0, stance_delta=-2.0, resentment_delta=2.0)
    summary = (
        f"{proposer_name} completed an investigation concerning {recipient_name}. "
        + (f"{recipient_name} detected the scrutiny." if detected else "The scrutiny was not clearly detected.")
    )
    _record_action(conn, int(interaction["id"]), day, proposer, "investigate", summary, {"confidence": confidence, "detected": detected})
    conn.execute(
        "UPDATE interactions SET status='resolved',resolved_day=?,resolution_summary=? WHERE id=?",
        (day, summary, interaction["id"]),
    )
    event_id = None
    if detected and stakes >= 3:
        event_id = _log_event(
            conn,
            day,
            "interaction:investigation:detected",
            f"Investigation detected: {proposer_name} / {recipient_name}",
            summary,
            min(5, stakes),
            proposer,
            (recipient,),
        )
        _link(conn, day, "interaction", int(interaction["id"]), "event", event_id, "produced")
    return InteractionResult(int(interaction["id"]), "resolved", "investigate", summary, event_id=event_id)


def _upsert_pressure(conn: sqlite3.Connection, actor_id: int, kind: str, description: str, delta: float, day: int) -> None:
    row = conn.execute(
        "SELECT id,intensity FROM pressures WHERE actor_id=? AND kind=? ORDER BY id LIMIT 1",
        (actor_id, kind),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE pressures SET intensity=?,updated_day=? WHERE id=?",
            (max(0.0, float(row["intensity"]) + delta), day, row["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO pressures(actor_id,kind,description,intensity,threshold,updated_day) VALUES (?,?,?,?,?,?)",
            (actor_id, kind, description, max(0.0, delta), 10.0, day),
        )


def _resolve_attack(conn: sqlite3.Connection, interaction: sqlite3.Row, day: int) -> InteractionResult:
    proposer = int(interaction["proposer_actor_id"])
    recipient = int(interaction["recipient_actor_id"])
    proposer_name = _name(conn, proposer)
    recipient_name = _name(conn, recipient)
    stakes = int(interaction["stakes"])
    rng = _rng(conn, int(interaction["id"]) * 47, day)
    p_cap = _capacity(conn, proposer) * (0.8 + 0.4 * _drives(conn, proposer)["aggression"])
    r_cap = _capacity(conn, recipient) * (0.85 + 0.3 * _drives(conn, recipient)["risk_tolerance"])
    ratio = p_cap / max(0.01, r_cap)
    roll = ratio * rng.uniform(0.75, 1.25)
    if roll > 1.35:
        outcome = "gained the upper hand"
        _upsert_pressure(conn, recipient, "external_conflict", f"Pressure from conflict with {proposer_name}", 1.5 + stakes * 0.5, day)
        _upsert_pressure(conn, proposer, "conflict_cost", f"Costs from conflict with {recipient_name}", 0.5 + stakes * 0.2, day)
    elif roll < 0.75:
        outcome = "failed to force a favorable result"
        _upsert_pressure(conn, proposer, "conflict_cost", f"Costs from conflict with {recipient_name}", 1.5 + stakes * 0.5, day)
        _upsert_pressure(conn, recipient, "external_conflict", f"Pressure from conflict with {proposer_name}", 0.5 + stakes * 0.2, day)
    else:
        outcome = "produced no decisive advantage"
        _upsert_pressure(conn, proposer, "conflict_cost", f"Costs from conflict with {recipient_name}", 0.8 + stakes * 0.3, day)
        _upsert_pressure(conn, recipient, "external_conflict", f"Pressure from conflict with {proposer_name}", 0.8 + stakes * 0.3, day)

    thread_id = _ensure_conflict_thread(conn, interaction, day)
    conn.execute(
        "UPDATE threads SET progress=MIN(100,progress+?),severity=MAX(severity,?),updated_day=? WHERE id=?",
        (8.0 + stakes * 4.0, stakes, day, thread_id),
    )
    adjust_relationship_pair(
        conn, proposer, recipient, day,
        a_to_b={"trust_delta": -12.0, "stance_delta": -15.0, "resentment_delta": 8.0},
        b_to_a={"trust_delta": -15.0, "stance_delta": -18.0, "fear_delta": 5.0, "resentment_delta": 12.0},
    )
    summary = f"{proposer_name} moved openly against {recipient_name} and {outcome}."
    _record_action(conn, int(interaction["id"]), day, proposer, "attack_resolved", summary, {"capacity_ratio": ratio})
    conn.execute(
        "UPDATE interactions SET status='resolved',resolved_day=?,resolution_summary=? WHERE id=?",
        (day, summary, interaction["id"]),
    )
    event_id = _log_event(
        conn,
        day,
        "inter_actor_conflict",
        f"Open conflict: {proposer_name} / {recipient_name}",
        summary,
        max(3, stakes),
        proposer,
        (recipient,),
    )
    _link(conn, day, "interaction", int(interaction["id"]), "thread", thread_id, "created_or_escalated")
    _link(conn, day, "interaction", int(interaction["id"]), "event", event_id, "produced")
    return InteractionResult(int(interaction["id"]), "resolved", "attack", summary, event_id=event_id)


def resolve_interaction(conn: sqlite3.Connection, interaction_id: int, day: int) -> InteractionResult:
    interaction = conn.execute("SELECT * FROM interactions WHERE id=?", (interaction_id,)).fetchone()
    if not interaction:
        raise ValueError(f"unknown interaction_id {interaction_id}")
    if interaction["status"] != "pending":
        return InteractionResult(
            int(interaction["id"]),
            str(interaction["status"]),
            "noop",
            str(interaction["resolution_summary"] or "Interaction already resolved."),
        )
    kind = str(interaction["interaction_type"])
    if kind == "investigation":
        return _resolve_investigation(conn, interaction, day)
    if kind == "attack":
        return _resolve_attack(conn, interaction, day)
    return _social_response(conn, interaction, day)


def process_due_interactions(conn: sqlite3.Connection, day: int) -> list[InteractionResult]:
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id = int(player[0]) if player and player[0] is not None else None
    rows = conn.execute(
        """SELECT id,recipient_actor_id FROM interactions
           WHERE status='pending' AND response_due_day<=?
           ORDER BY response_due_day,id""",
        (day,),
    ).fetchall()
    # Incoming player interactions become scene hooks. They are never silently answered by
    # the world simulator merely because their nominal response date arrived.
    rows = [r for r in rows if player_id is None or int(r["recipient_actor_id"]) != player_id]
    results: list[InteractionResult] = []
    for row in rows:
        results.append(resolve_interaction(conn, int(row["id"]), day))
    return results


def recent_interactions(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT i.*,p.name proposer_name,r.name recipient_name
           FROM interactions i
           JOIN actors p ON p.id=i.proposer_actor_id
           JOIN actors r ON r.id=i.recipient_actor_id
           ORDER BY i.created_day DESC,i.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def interaction_history(conn: sqlite3.Connection, interaction_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT ia.*,a.name actor_name FROM interaction_actions ia
           JOIN actors a ON a.id=ia.actor_id
           WHERE ia.interaction_id=? ORDER BY ia.day,ia.id""",
        (interaction_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def apply_player_response(
    conn: sqlite3.Connection,
    interaction_id: int,
    player_actor_id: int,
    choice: str,
    day: int,
    *,
    counter_terms: dict | None = None,
) -> InteractionResult:
    """Apply an explicit player choice to a pending social interaction.

    The simulation never selects this choice. This function only executes a choice the
    player already made. Tactical attacks and investigations aimed at the player are left
    for later scene-specific resolvers rather than being converted into social responses.
    """
    choice = choice.lower().strip()
    if choice not in {"accept", "reject", "counter"}:
        raise ValueError("choice must be accept, reject, or counter")
    interaction = conn.execute("SELECT * FROM interactions WHERE id=?", (interaction_id,)).fetchone()
    if not interaction:
        raise ValueError(f"unknown interaction_id {interaction_id}")
    if interaction["status"] != "pending":
        raise ValueError("interaction is no longer pending")
    if int(interaction["recipient_actor_id"]) != int(player_actor_id):
        raise ValueError("the configured player is not the recipient of this interaction")
    kind = str(interaction["interaction_type"])
    if kind == "attack" and json.loads(interaction["terms_json"] or "{}").get("underworld_attempt"):
        # An attempt on the protagonist is played in a scene: he yields (accept), stands (reject) or runs (counter).
        from .underworld_aggression import resolve_attempt
        return resolve_attempt(conn, interaction, choice, day)
    if kind in {"attack", "investigation"}:
        raise ValueError(f"{kind} requires a scene-specific resolver, not accept/reject/counter")

    proposer = int(interaction["proposer_actor_id"])
    player_name = _name(conn, player_actor_id)
    proposer_name = _name(conn, proposer)
    stakes = int(interaction["stakes"])

    if choice == "accept":
        agreement_type = {
            "contract": "contract",
            "alliance": "alliance",
            "offer": "service",
            "request": "service",
            "negotiation": "understanding",
            "mediation": "understanding",
            "demand": "concession",
            "threat": "concession",
        }.get(kind, "other")
        agreement_id = None if kind == "conversation" else _create_agreement(conn, interaction, day, agreement_type)
        summary = (
            f"{player_name} explicitly engaged with {proposer_name}'s approach."
            if kind == "conversation" else f"{player_name} explicitly accepted {proposer_name}'s {kind}."
        )
        _record_action(conn, interaction_id, day, player_actor_id, "player_accept", summary)
        conn.execute(
            "UPDATE interactions SET status='accepted',resolved_day=?,resolution_summary=? WHERE id=?",
            (day, summary, interaction_id),
        )
        try:
            from .domain_actions import apply_accepted_interaction_domain_action
            domain_result = apply_accepted_interaction_domain_action(conn, interaction, day)
            if domain_result is not None:
                if domain_result.get("blocked"):
                    summary += f" The agreed domain action could not be applied: {domain_result.get('reason','state changed')}."
                else:
                    summary += " The agreed domain action was applied to authoritative state."
                conn.execute("UPDATE interactions SET resolution_summary=? WHERE id=?", (summary, interaction_id))
        except Exception as exc:
            conn.execute("INSERT OR REPLACE INTO runtime_flags(key,value,updated_at) VALUES ('last_domain_action_error',?,CURRENT_TIMESTAMP)", (str(exc),))
        # A counter to one of the protagonist's own operations (hire, lend, demand) completes that operation.
        from .player_operations import settle_accepted
        settled = settle_accepted(conn, interaction, player_actor_id)
        if settled is not None:
            summary += f" {settled.get('summary', '')}"
            conn.execute("UPDATE interactions SET resolution_summary=? WHERE id=?", (summary, interaction_id))
        adjust_relationship(
            conn, proposer, player_actor_id, day,
            trust_delta=2.0 if kind not in {"demand", "threat"} else -1.0,
            stance_delta=1.0 if kind not in {"demand", "threat"} else -1.0,
        )
        if agreement_id is not None:
            _link(conn, day, "interaction", interaction_id, "agreement", agreement_id, "created")
        event_id = None
        if stakes >= 3 or kind in {"contract", "alliance", "threat"}:
            event_id = _log_event(
                conn, day, f"interaction:{kind}:player_accept",
                f"{kind.title()} resolved: {proposer_name} / {player_name}",
                summary, min(5, max(2, stakes)), proposer, (player_actor_id,),
            )
            _link(conn, day, "interaction", interaction_id, "event", event_id, "produced")
        return InteractionResult(interaction_id, "accepted", "accept", summary, agreement_id=agreement_id, event_id=event_id)

    if choice == "reject":
        terms = dict(json.loads(interaction["terms_json"] or "{}"))
        summary = f"{player_name} explicitly rejected {proposer_name}'s {kind}."
        _record_action(conn, interaction_id, day, player_actor_id, "player_reject", summary)
        conn.execute(
            "UPDATE interactions SET status='rejected',resolved_day=?,resolution_summary=? WHERE id=?",
            (day, summary, interaction_id),
        )
        opportunity_pid = int(terms.get("opportunity_proposal_id") or 0)
        if opportunity_pid:
            conn.execute("UPDATE opportunity_proposals SET status='rejected' WHERE id=? AND status='pending'", (opportunity_pid,))
        adjust_relationship(
            conn, proposer, player_actor_id, day,
            trust_delta=-2.0 if kind not in {"demand", "threat"} else -4.0,
            stance_delta=-1.0 if kind not in {"demand", "threat"} else -3.0,
        )
        event_id = None
        if stakes >= 4 or kind in {"demand", "threat"}:
            event_id = _log_event(
                conn, day, f"interaction:{kind}:player_reject",
                f"{kind.title()} refused: {proposer_name} / {player_name}",
                summary, min(5, max(2, stakes)), proposer, (player_actor_id,),
            )
            _link(conn, day, "interaction", interaction_id, "event", event_id, "produced")
        return InteractionResult(interaction_id, "rejected", "reject", summary, event_id=event_id)

    terms = dict(json.loads(interaction["terms_json"] or "{}"))
    opportunity_pid = int(terms.get("opportunity_proposal_id") or 0)
    if opportunity_pid:
        from .opportunity import counter_proposal, present_proposal
        counter_payload = counter_terms or {}
        counter_pid = counter_proposal(
            conn, opportunity_pid, player_actor_id, title=counter_payload.get("title"),
            term_overrides=counter_payload.get("proposal_term_overrides") if isinstance(counter_payload.get("proposal_term_overrides"), list) else None, day=day,
        )
        child_id = present_proposal(conn, counter_pid, day=day, rationale=f"Explicit player counterproposal to opportunity proposal #{opportunity_pid}")
        summary = f"{player_name} explicitly countered {proposer_name}'s {kind}."
        _record_action(conn, interaction_id, day, player_actor_id, "player_counter", summary, {"child_interaction_id": child_id, "counter_proposal_id": counter_pid})
        conn.execute("UPDATE interactions SET status='countered',resolved_day=?,resolution_summary=? WHERE id=?", (day, summary, interaction_id))
        adjust_relationship(conn, proposer, player_actor_id, day, trust_delta=0.25)
        return InteractionResult(interaction_id, "countered", "counter", summary, child_interaction_id=child_id)
    changes = (counter_terms or {}).get("changes")
    if isinstance(changes, dict) and isinstance(terms.get("player_operation"), dict):  # the protagonist's own new terms
        po = dict(terms["player_operation"])
        po["details"] = {**(po.get("details") or {}), **changes}
        terms["player_operation"] = po
    terms.update({k: v for k, v in (counter_terms or {}).items() if k != "changes"})
    child_id = create_interaction(
        conn,
        player_actor_id,
        proposer,
        kind,
        day,
        urgency=max(1, int(interaction["urgency"])),
        stakes=stakes,
        terms=terms,
        rationale=f"Explicit player counterproposal to interaction {interaction_id}",
        canon_chunk_ids=tuple(json.loads(interaction["canon_chunk_ids_json"] or "[]")),
        parent_interaction_id=interaction_id,
        thread_id=interaction["thread_id"],
    )
    summary = f"{player_name} explicitly countered {proposer_name}'s {kind}."
    _record_action(conn, interaction_id, day, player_actor_id, "player_counter", summary, {"child_interaction_id": child_id})
    conn.execute(
        "UPDATE interactions SET status='countered',resolved_day=?,resolution_summary=? WHERE id=?",
        (day, summary, interaction_id),
    )
    adjust_relationship(conn, proposer, player_actor_id, day, trust_delta=0.25)
    return InteractionResult(interaction_id, "countered", "counter", summary, child_interaction_id=child_id)
