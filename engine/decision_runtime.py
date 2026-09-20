from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from .domain_actions import domain_action_options


@dataclass(frozen=True)
class DecisionCandidate:
    key: str
    provider_key: str
    action_kind: str
    utility: float
    rationale: str
    execution_kind: str  # domain_action | interaction | underworld_action | merchant_action | growth_action | war_action | political_action | hold
    target_actor_id: int | None = None
    interaction_type: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    information_basis: dict[str, Any] = field(default_factory=dict)
    claim_ids: tuple[int, ...] = ()
    evidence_ids: tuple[int, ...] = ()
    tags: tuple[str, ...] = ()
    estimated_cost: float = 0.0
    risk: float = 0.0


Provider = Callable[[sqlite3.Connection, int, str, int, dict[str, Any]], list[DecisionCandidate]]
_PROVIDERS: list[tuple[str, Provider]] = []


def register_provider(key: str, provider: Provider) -> None:
    global _PROVIDERS
    _PROVIDERS = [(k, p) for k, p in _PROVIDERS if k != key]
    _PROVIDERS.append((key, provider))


def clear_providers() -> None:
    _PROVIDERS.clear()


def _rng(conn: sqlite3.Connection, actor_id: int, day: int) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 1_000_003 + actor_id * 9_973 + day * 37_219 + 63 * 65_537)


def _ordinary_domain_provider(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    drives = envelope.get("drives") or {}
    out: list[DecisionCandidate] = []
    for opt in domain_action_options(conn, actor_id, tier, day, context=envelope, drives=drives):
        out.append(DecisionCandidate(
            key=f"ordinary:{opt.kind}:{opt.target_actor_id or 0}:{json.dumps(opt.payload or {}, sort_keys=True, default=str)}",
            provider_key="ordinary_domain",
            action_kind=opt.kind,
            utility=float(opt.score),
            rationale=opt.rationale,
            execution_kind="domain_action",
            target_actor_id=opt.target_actor_id,
            interaction_type=opt.interaction_type,
            payload={"mode": opt.mode, "payload": opt.payload or {}},
            information_basis={"kind": "owned_or_observed_domain_state"},
            tags=("domain_owned",),
        ))
    return out


def _relationship_provider(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    """Concrete social options from the actor's own relationship/goals, never a generic relationship tick."""
    rels = list(envelope.get("relationships") or [])
    goals = list(envelope.get("goals") or [])
    pressures = list(envelope.get("pressures") or [])
    drives = envelope.get("drives") or {}
    out: list[DecisionCandidate] = []
    for rel in rels[:3]:
        target = int(rel["actor_b_id"])
        if conn.execute("SELECT 1 FROM interactions WHERE status='pending' AND proposer_actor_id=? AND recipient_actor_id=?", (actor_id, target)).fetchone():
            continue
        stance = float(rel.get("stance") or 0)
        familiarity = float(rel.get("familiarity") or 0)
        trust = float(rel.get("trust") or 0)
        resentment = float(rel.get("resentment") or 0)
        obligation = float(rel.get("obligation") or 0)
        target_name = str(rel.get("actor_b_name") or f"actor #{target}")
        purpose = str(goals[0]["description"]) if goals else (str(pressures[0]["description"]) if pressures else "maintain the relationship")
        adverse = max(resentment / 35.0, max(0.0, -trust) / 30.0, max(0.0, -stance) / 40.0)
        if (resentment > 35 or trust < -15 or stance < -25) and (goals or pressures):
            interaction_type = "demand" if float(drives.get("aggression", .5)) >= .55 and (resentment > 20 or stance < -25) else "negotiation"
            utility = 4.0 + adverse + float(drives.get("pragmatism", .5))
        elif obligation > 25 or trust > 20:
            interaction_type = "request" if pressures else "offer"
            utility = 3.2 + max(0.0, trust) / 45.0 + max(0.0, obligation) / 45.0 + float(drives.get("loyalty", .5))
        elif familiarity >= 25 and (goals or pressures):
            # A persisted, familiar counterpart is enough to make a bounded approach plausible.
            # This represents an arrangeable request/negotiation, not proof of exact co-presence.
            interaction_type = "request" if pressures else "negotiation"
            utility = 3.0 + familiarity / 100.0 + float(drives.get("pragmatism", .5))
        else:
            continue
        out.append(DecisionCandidate(
            key=f"social:{interaction_type}:{target}", provider_key="relationship", action_kind=f"social_{interaction_type}",
            utility=utility, rationale=f"Open a concrete {interaction_type} with {target_name} concerning {purpose}.",
            execution_kind="interaction", target_actor_id=target, interaction_type=interaction_type,
            payload={"purpose": purpose, "burden": 0.15, "incentive": 0.15},
            information_basis={"relationship_edge_id": int(rel["id"]), "own_goal_or_pressure": bool(goals or pressures)},
            tags=("social", "specific_counterpart"),
        ))
    return out


def _belief_investigation_provider(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    """Investigate uncertain claims only through a source actor the decision-maker actually knows supplied evidence."""
    out: list[DecisionCandidate] = []
    for belief in envelope.get("beliefs") or []:
        if str(belief.get("stance")) != "uncertain" and float(belief.get("confidence") or 0) >= .45:
            continue
        source = None
        evidence_ids: list[int] = []
        for ev in belief.get("evidence") or []:
            evidence_ids.append(int(ev["id"]))
            if ev.get("source_actor_id") is not None:
                source = int(ev["source_actor_id"])
                break
        if source is None or source == actor_id:
            continue
        if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (source,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM interactions WHERE status='pending' AND proposer_actor_id=? AND recipient_actor_id=? AND interaction_type='investigation'", (actor_id, source)).fetchone():
            continue
        cid = int(belief["claim_id"])
        out.append(DecisionCandidate(
            key=f"belief:investigate:{cid}:{source}", provider_key="belief_investigation", action_kind="investigate_claim",
            utility=4.0 + (1.0 - float(belief.get("confidence") or 0)) * 2.0,
            rationale=f"Seek clarification of an uncertain claim from a source already represented in the actor's evidence trail.",
            execution_kind="interaction", target_actor_id=source, interaction_type="investigation",
            payload={"claim_id": cid, "purpose": str(belief.get("proposition_text") or "clarify uncertain information")},
            information_basis={"claim_id": cid, "source_actor_id": source}, claim_ids=(cid,), evidence_ids=tuple(evidence_ids),
            tags=("belief_bounded", "investigation"),
        ))
        if len(out) >= 2:
            break
    return out


def _builtin_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    out: list[DecisionCandidate] = []
    out.extend(_ordinary_domain_provider(conn, actor_id, tier, day, envelope))
    out.extend(_relationship_provider(conn, actor_id, tier, day, envelope))
    out.extend(_belief_investigation_provider(conn, actor_id, tier, day, envelope))
    try:
        from .underworld_decisions import underworld_decision_candidates
        out.extend(underworld_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .merchant import merchant_decision_candidates
        out.extend(merchant_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .craft import craft_decision_candidates
        out.extend(craft_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .growth import growth_decision_candidates
        out.extend(growth_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .war import war_decision_candidates
        out.extend(war_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .conflict import polity_conflict_decision_candidates
        out.extend(polity_conflict_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    try:
        from .opportunity import opportunity_decision_candidates
        out.extend(opportunity_decision_candidates(conn, actor_id, tier, day, envelope))
    except (ImportError, sqlite3.OperationalError):
        pass
    for _, provider in _PROVIDERS:
        out.extend(provider(conn, actor_id, tier, day, envelope))
    return out


def generate_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    candidates = _builtin_candidates(conn, actor_id, tier, day, envelope)
    # One concrete no-new-commitment candidate is always legal; it is not a hidden goal-progress action.
    candidates.append(DecisionCandidate(
        key="hold:current_commitments", provider_key="baseline", action_kind="hold_position", utility=2.6,
        rationale="Make no new strategic commitment this review and continue existing obligations.", execution_kind="hold",
        information_basis={"kind": "self_state"}, tags=("baseline",),
    ))
    # Deterministic de-duplication protects against provider overlap.
    dedup: dict[str, DecisionCandidate] = {}
    for c in candidates:
        prior = dedup.get(c.key)
        if prior is None or c.utility > prior.utility:
            dedup[c.key] = c
    return [dedup[k] for k in sorted(dedup)]


def choose_candidate(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> tuple[DecisionCandidate, int]:
    candidates = generate_candidates(conn, actor_id, tier, day, envelope)
    if not candidates:
        raise RuntimeError("decision runtime produced no candidates")
    max_u = max(c.utility for c in candidates)
    plausible = [c for c in candidates if c.utility >= max_u - 4.0]
    temperature = {"ACTIVE": .85, "STRATEGIC": .95, "DORMANT": 1.10}.get(tier, .95)
    raw_weights = [math.exp((c.utility - max_u) / max(.15, temperature)) for c in plausible]
    total = sum(raw_weights) or 1.0
    probabilities = [w / total for w in raw_weights]
    rng = _rng(conn, actor_id, day)
    draw = rng.random()
    cumulative = 0.0
    chosen = plausible[-1]
    for c, p in zip(plausible, probabilities):
        cumulative += p
        if draw <= cumulative:
            chosen = c
            break

    summary = {
        "belief_count": len(envelope.get("beliefs") or []),
        "relationship_count": len(envelope.get("relationships") or []),
        "goal_count": len(envelope.get("goals") or []),
        "pressure_count": len(envelope.get("pressures") or []),
        "canon_chunk_count": len(envelope.get("canon") or []),
        "information_rule": "actor_accessible_only",
    }
    cur = conn.execute(
        """INSERT INTO decision_evaluations(day,actor_id,tier,temperature,random_draw,selected_candidate_key,envelope_summary_json)
           VALUES (?,?,?,?,?,?,?)""",
        (day, actor_id, tier, temperature, draw, chosen.key, json.dumps(summary, sort_keys=True)),
    )
    evaluation_id = int(cur.lastrowid)
    prob_by_key = {c.key: p for c, p in zip(plausible, probabilities)}
    for c in candidates:
        conn.execute(
            """INSERT INTO decision_candidate_audit(evaluation_id,candidate_key,provider_key,action_kind,utility,selection_probability,
                   plausible,selected,target_actor_id,interaction_type,information_basis_json,payload_json,tags_json,estimated_cost,risk)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (evaluation_id, c.key, c.provider_key, c.action_kind, c.utility, prob_by_key.get(c.key, 0.0),
             1 if c in plausible else 0, 1 if c.key == chosen.key else 0, c.target_actor_id, c.interaction_type,
             json.dumps(c.information_basis, sort_keys=True, default=str), json.dumps(c.payload, sort_keys=True, default=str),
             json.dumps(list(c.tags)), float(c.estimated_cost), float(c.risk)),
        )
    return chosen, evaluation_id


def record_external_selection(
    conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any],
    candidates: list[DecisionCandidate], selected_key: str,
) -> int:
    """Audit a bounded external/manual selector that chooses from engine-generated candidates."""
    selected = next((c for c in candidates if c.key == selected_key), None)
    if selected is None:
        raise ValueError("selected candidate is not currently feasible")
    summary = {
        "belief_count": len(envelope.get("beliefs") or []), "relationship_count": len(envelope.get("relationships") or []),
        "goal_count": len(envelope.get("goals") or []), "pressure_count": len(envelope.get("pressures") or []),
        "canon_chunk_count": len(envelope.get("canon") or []), "information_rule":"actor_accessible_only",
        "selector":"external_bounded_candidate_choice",
    }
    cur=conn.execute(
        """INSERT INTO decision_evaluations(day,actor_id,tier,temperature,random_draw,selected_candidate_key,envelope_summary_json)
           VALUES (?,?,?,?,?,?,?)""", (day,actor_id,tier,1.0,0.0,selected_key,json.dumps(summary,sort_keys=True))
    )
    eid=int(cur.lastrowid)
    for c in candidates:
        conn.execute(
            """INSERT INTO decision_candidate_audit(evaluation_id,candidate_key,provider_key,action_kind,utility,selection_probability,
                   plausible,selected,target_actor_id,interaction_type,information_basis_json,payload_json,tags_json,estimated_cost,risk)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid,c.key,c.provider_key,c.action_kind,c.utility,1.0 if c.key==selected_key else 0.0,1,1 if c.key==selected_key else 0,
             c.target_actor_id,c.interaction_type,json.dumps(c.information_basis,sort_keys=True,default=str),json.dumps(c.payload,sort_keys=True,default=str),
             json.dumps(list(c.tags)),float(c.estimated_cost),float(c.risk)),
        )
    return eid
