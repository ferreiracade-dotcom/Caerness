from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol

from .interactions import adjust_relationship, create_interaction, relationship_view
from .motives import derive_actor_motives
from .domain_actions import DomainActionOption, domain_action_options, execute_domain_action


@dataclass(frozen=True)
class DecisionProposal:
    action_type: str
    score: float
    rationale: str
    goal_id: int | None = None
    pressure_id: int | None = None
    canon_chunk_ids: tuple[int, ...] = ()
    effects: dict | None = None
    target_actor_id: int | None = None
    interaction_type: str | None = None


class DecisionProvider(Protocol):
    def choose(self, conn: sqlite3.Connection, actor_id: int, tier: str, day: int) -> DecisionProposal:
        ...


def _rng(conn: sqlite3.Connection, actor_id: int, day: int) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 1_000_003 + actor_id * 9_973 + day * 37_219)


def _drive_row(conn: sqlite3.Connection, actor_id: int) -> dict[str, float]:
    row = conn.execute("SELECT * FROM actor_drives WHERE actor_id=?", (actor_id,)).fetchone()
    if not row:
        return {
            "aggression": 0.5,
            "risk_tolerance": 0.5,
            "patience": 0.5,
            "loyalty": 0.5,
            "ambition": 0.5,
            "pragmatism": 0.5,
        }
    return {k: float(row[k]) for k in ("aggression","risk_tolerance","patience","loyalty","ambition","pragmatism")}


def _actor_context_query(conn: sqlite3.Connection, actor_id: int) -> str:
    actor = conn.execute(
        """SELECT a.*,hl.name home_name,cl.name current_name
           FROM actors a
           LEFT JOIN locations hl ON hl.id=a.home_location_id
           LEFT JOIN locations cl ON cl.id=a.current_location_id
           WHERE a.id=?""",
        (actor_id,),
    ).fetchone()
    if not actor:
        return "Caerness institutions culture"
    goals = [r[0] for r in conn.execute(
        "SELECT description FROM goals WHERE actor_id=? AND status='active' ORDER BY priority DESC LIMIT 3", (actor_id,)
    )]
    pressures = [r[0] for r in conn.execute(
        "SELECT description FROM pressures WHERE actor_id=? ORDER BY intensity DESC LIMIT 3", (actor_id,)
    )]
    terms = [actor["name"], actor["subtype"] or actor["actor_type"], actor["home_name"] or "", actor["current_name"] or ""]
    terms.extend(goals)
    terms.extend(pressures)
    return " ".join(t for t in terms if t)


def build_actor_context(conn: sqlite3.Connection, actor_id: int, day: int, canon_limit: int = 5) -> dict:
    """Build the DEC-01 actor-safe information envelope.

    `canon_limit` is retained for API compatibility but canon text is deliberately not retrieved:
    World-Bible truth is not personal NPC knowledge. Own goals/resources/relationships are
    self-state; external propositions enter through BELIEF-01 actor-relative evidence.
    """
    actor = conn.execute(
        """SELECT a.*,hl.name home_name,cl.name current_name
           FROM actors a
           LEFT JOIN locations hl ON hl.id=a.home_location_id
           LEFT JOIN locations cl ON cl.id=a.current_location_id
           WHERE a.id=?""", (actor_id,),
    ).fetchone()
    if not actor:
        raise ValueError(f"unknown actor_id {actor_id}")
    goals = [dict(r) for r in conn.execute(
        "SELECT * FROM goals WHERE actor_id=? AND status='active' ORDER BY priority DESC,id", (actor_id,)
    )]
    pressures = [dict(r) for r in conn.execute(
        "SELECT * FROM pressures WHERE actor_id=? ORDER BY intensity DESC,id", (actor_id,)
    )]
    resources = {r["resource_type"]: float(r["amount"]) for r in conn.execute(
        "SELECT * FROM resources WHERE actor_id=?", (actor_id,)
    )}
    relationships = [dict(r) for r in conn.execute(
        """SELECT r.id,r.actor_a_id,r.actor_b_id,r.stance,r.familiarity,r.trust,r.affection,r.respect,r.fear,r.loyalty,r.resentment,r.obligation,r.professional_confidence,r.updated_day,b.name actor_b_name
           FROM relationships r JOIN actors b ON b.id=r.actor_b_id
           WHERE r.actor_a_id=?
           ORDER BY ABS(r.stance)+ABS(r.obligation)+ABS(r.resentment)+ABS(r.loyalty) DESC LIMIT 12""", (actor_id,)
    )]
    constraints = [dict(r) for r in conn.execute(
        "SELECT * FROM actor_constraints WHERE actor_id=? AND active=1 ORDER BY constraint_type,weight DESC", (actor_id,)
    )]
    try:
        from .belief import actor_belief_envelope
        beliefs = actor_belief_envelope(conn, actor_id, limit=100)
    except sqlite3.OperationalError:
        beliefs = []
    try:
        from .emergence import important_memories
        memories = important_memories(conn, actor_id, limit=10)
    except Exception:
        memories = []
    try:
        from .presence import assess_presence
        loc = actor["current_location_id"]
        pa = assess_presence(conn, actor_id, int(loc), day=day) if loc is not None else None
        presence = None if pa is None else {
            "location_id": pa.location_id, "resolution": pa.resolution, "probability": pa.probability,
            "plausible": pa.plausible, "basis": list(pa.basis),
        }
    except Exception:
        presence = None
    context = {
        "day": day, "actor": dict(actor), "drives": _drive_row(conn, actor_id), "goals": goals,
        "pressures": pressures, "resources": resources, "relationships": relationships,
        "constraints": constraints, "derived_motives": derive_actor_motives(conn, actor_id, limit=12),
        "memories": memories, "beliefs": beliefs, "presence": presence,
        "canon": [],
        "information_guardrails": {
            "world_bible_as_personal_knowledge": False,
            "external_claims_require_actor_evidence": True,
            "authoritative_truth_links_exposed": False,
        },
    }
    conn.execute(
        """INSERT INTO actor_context_cache(actor_id,generated_day,canon_query,canon_chunk_ids_json,context_json)
           VALUES (?,?,?,?,?)
           ON CONFLICT(actor_id) DO UPDATE SET generated_day=excluded.generated_day,
             canon_query=excluded.canon_query,canon_chunk_ids_json=excluded.canon_chunk_ids_json,
             context_json=excluded.context_json,updated_at=CURRENT_TIMESTAMP""",
        (actor_id, day, "DEC01 actor-safe envelope", "[]", json.dumps(_inspectable_context(context), default=str)),
    )
    return context


def _inspectable_context(context: dict[str, Any]) -> dict[str, Any]:
    """The persisted inspection copy keeps each belief's claim, stance and confidence but counts its evidence
    instead of copying it (PERF-01: the full envelope was ~70 KB per person, the largest table in a long run)."""
    slim = dict(context)
    beliefs = list(context.get("beliefs") or [])
    slim["belief_count"] = len(beliefs)
    # Most recent ten only (the envelope is ordered oldest-first); the full set is recomputable on demand.
    slim["beliefs"] = [
        {**{k: v for k, v in b.items() if k != "evidence"}, "evidence_count": len(b.get("evidence") or [])}
        if isinstance(b, dict) else b
        for b in beliefs[-10:]
    ]
    return slim

def _resource_strength(resources: dict[str, float]) -> float:
    if not resources:
        return 0.5
    # Resources have heterogeneous units. We only infer whether the actor is resource-poor or comfortable.
    positives = [max(0.0, v) for v in resources.values()]
    return min(1.0, sum(math.log1p(v) for v in positives) / max(1.0, 8.0 * len(positives)))


def candidate_to_proposal(candidate, evaluation_id: int | None = None) -> DecisionProposal:
    common = {
        "candidate_key": candidate.key, "provider_key": candidate.provider_key, "action_kind": candidate.action_kind,
        "information_basis": candidate.information_basis, "claim_ids": list(candidate.claim_ids),
        "evidence_ids": list(candidate.evidence_ids), "tags": list(candidate.tags),
        "estimated_cost": candidate.estimated_cost, "risk": candidate.risk,
    }
    if evaluation_id is not None:
        common["decision_evaluation_id"] = int(evaluation_id)
    if candidate.execution_kind == "domain_action":
        return DecisionProposal(
            "domain_action", candidate.utility, candidate.rationale, effects={
                **common, "domain_action_kind": candidate.action_kind,
                "domain_action_mode": str(candidate.payload.get("mode") or "direct"),
                "domain_action_payload": candidate.payload.get("payload") if isinstance(candidate.payload.get("payload"), dict) else {},
            }, target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    if candidate.execution_kind == "underworld_action":
        return DecisionProposal(
            "underworld_action", candidate.utility, candidate.rationale,
            effects={**common, "underworld_action_kind":candidate.action_kind, "underworld_action_payload":candidate.payload},
            target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    if candidate.execution_kind == "merchant_action":
        return DecisionProposal(
            "merchant_action", candidate.utility, candidate.rationale,
            effects={**common, "merchant_action_kind":candidate.action_kind, "merchant_action_payload":candidate.payload},
            target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    if candidate.execution_kind == "growth_action":
        return DecisionProposal(
            "growth_action", candidate.utility, candidate.rationale,
            effects={**common, "growth_action_kind":candidate.action_kind, "growth_action_payload":candidate.payload},
            target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    if candidate.execution_kind == "war_action":
        return DecisionProposal(
            "war_action", candidate.utility, candidate.rationale,
            effects={**common, "war_action_kind":candidate.action_kind, "war_action_payload":candidate.payload},
            target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    if candidate.execution_kind == "political_action":
        return DecisionProposal(
            "political_action", candidate.utility, candidate.rationale,
            effects={**common, "political_action_kind":candidate.action_kind, "political_action_payload":candidate.payload},
            target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    if candidate.execution_kind == "opportunity_action":
        return DecisionProposal(
            "opportunity_action", candidate.utility, candidate.rationale,
            effects={**common, "opportunity_action_kind":candidate.action_kind, "opportunity_action_payload":candidate.payload},
            target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    if candidate.execution_kind == "interaction":
        return DecisionProposal(
            "initiate_interaction", candidate.utility, candidate.rationale, effects={**common, **candidate.payload},
            target_actor_id=candidate.target_actor_id, interaction_type=candidate.interaction_type,
        )
    return DecisionProposal("consolidate", candidate.utility, candidate.rationale, effects=common)


class InformationBoundedDecisionProvider:
    """DEC-01 provider: actor evidence -> domain candidates -> weighted selection.

    This class intentionally does not invent abstract goal-progress actions. Providers expose
    concrete feasible choices tied to existing world objects; the selector samples among plausible
    candidates with deterministic actor RNG, and domain owners perform mutations.
    """
    def choose(self, conn: sqlite3.Connection, actor_id: int, tier: str, day: int) -> DecisionProposal:
        from .decision_runtime import choose_candidate
        context = build_actor_context(conn, actor_id, day)
        candidate, evaluation_id = choose_candidate(conn, actor_id, tier, day, context)
        return candidate_to_proposal(candidate, evaluation_id)


# Backward import compatibility; default semantics are DEC-01, not the old heuristic argmax.
HeuristicDecisionProvider = InformationBoundedDecisionProvider

def _apply_goal_progress(conn: sqlite3.Connection, goal_id: int, amount: float, day: int) -> str:
    goal = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
    if not goal or goal["status"] != "active":
        return "No active goal remained to advance."
    new_progress = min(100.0, float(goal["progress"]) + amount)
    status = "completed" if new_progress >= 100.0 else "active"
    conn.execute("UPDATE goals SET progress=?,status=? WHERE id=?", (new_progress, status, goal_id))
    return f"Goal progress moved from {float(goal['progress']):.1f} to {new_progress:.1f}." + (" Goal completed." if status == "completed" else "")


def _apply_pressure_relief(conn: sqlite3.Connection, pressure_id: int, amount: float, day: int) -> str:
    row = conn.execute("SELECT * FROM pressures WHERE id=?", (pressure_id,)).fetchone()
    if not row:
        return "The targeted pressure no longer existed."
    new_value = max(0.0, float(row["intensity"]) - amount)
    conn.execute("UPDATE pressures SET intensity=?,updated_day=? WHERE id=?", (new_value, day, pressure_id))
    return f"Pressure fell from {float(row['intensity']):.1f} to {new_value:.1f}."


def apply_decision(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, proposal: DecisionProposal) -> int:
    profile = conn.execute("SELECT agency,volatility,last_review_day FROM simulation_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    elapsed = max(1, day - int(profile["last_review_day"])) if profile else 1
    agency = float(profile["agency"]) if profile else 0.5
    volatility = float(profile["volatility"]) if profile else 0.25
    drives = _drive_row(conn, actor_id)
    rng = _rng(conn, actor_id * 13, day)
    base = max(0.5, elapsed / 30.0 * (3.0 + 4.0 * agency))
    outcome_parts: list[str] = []
    interaction_id_created: int | None = None

    if proposal.action_type == "advance_goal" and proposal.goal_id:
        amount = base * (0.8 + 0.5 * drives["ambition"]) * rng.uniform(0.85, 1.15)
        outcome_parts.append(_apply_goal_progress(conn, proposal.goal_id, amount, day))
    elif proposal.action_type == "force_goal" and proposal.goal_id:
        amount = base * (1.25 + 0.7 * drives["aggression"]) * rng.uniform(0.8, 1.2)
        outcome_parts.append(_apply_goal_progress(conn, proposal.goal_id, amount, day))
        if rng.random() < 0.25 + 0.35 * volatility:
            existing = conn.execute(
                "SELECT id,intensity FROM pressures WHERE actor_id=? AND kind='overreach' ORDER BY intensity DESC LIMIT 1", (actor_id,)
            ).fetchone()
            if existing:
                conn.execute("UPDATE pressures SET intensity=intensity+1.0,updated_day=? WHERE id=?", (day, existing["id"]))
            else:
                conn.execute(
                    "INSERT INTO pressures(actor_id,kind,description,intensity,threshold,updated_day) VALUES (?,?,?,?,?,?)",
                    (actor_id, "overreach", "Costs and enemies created by aggressive action", 1.0, 8.0, day),
                )
            outcome_parts.append("The aggressive push also created additional overreach pressure.")
    elif proposal.action_type == "address_pressure" and proposal.pressure_id:
        amount = base * (0.9 + 0.7 * drives["pragmatism"]) * rng.uniform(0.85, 1.15)
        outcome_parts.append(_apply_pressure_relief(conn, proposal.pressure_id, amount, day))
    elif proposal.action_type == "work_relationship":
        target = int((proposal.effects or {}).get("relationship_actor_id", 0))
        if target:
            rel = relationship_view(conn, actor_id, target)
            gain = 0.5 + 1.5 * drives["loyalty"] + rng.uniform(0.0, 0.8)
            adjust_relationship(conn, actor_id, target, day, trust_delta=gain)
            outcome_parts.append(f"Trust with the selected counterpart rose from {rel['trust']:.1f} by {gain:.1f}.")
    elif proposal.action_type == "domain_action":
        effects = proposal.effects or {}
        dopt = DomainActionOption(
            kind=str(effects.get("domain_action_kind") or ""),
            score=float(proposal.score),
            rationale=proposal.rationale,
            mode=str(effects.get("domain_action_mode") or "direct"),
            target_actor_id=proposal.target_actor_id,
            interaction_type=proposal.interaction_type,
            payload=effects.get("domain_action_payload") if isinstance(effects.get("domain_action_payload"), dict) else {},
        )
        dresult = execute_domain_action(conn, actor_id, dopt, day, canon_chunk_ids=proposal.canon_chunk_ids)
        outcome_parts.append(str(dresult.get("summary") or "Domain action resolved."))
        if dresult.get("interaction_id") is not None:
            interaction_id_created = int(dresult["interaction_id"])
    elif proposal.action_type == "merchant_action":
        effects = proposal.effects or {}
        from .merchant import execute_merchant_action
        mresult = execute_merchant_action(
            conn, actor_id, str(effects.get("merchant_action_kind") or ""),
            effects.get("merchant_action_payload") if isinstance(effects.get("merchant_action_payload"), dict) else {}, day,
        )
        outcome_parts.append(str(mresult.get("summary") or "Merchant action resolved."))
    elif proposal.action_type == "growth_action":
        effects = proposal.effects or {}
        from .growth import execute_growth_action
        gresult = execute_growth_action(
            conn, actor_id, str(effects.get("growth_action_kind") or ""),
            effects.get("growth_action_payload") if isinstance(effects.get("growth_action_payload"), dict) else {}, day,
        )
        outcome_parts.append(str(gresult.get("summary") or "Regional public action resolved."))
    elif proposal.action_type == "war_action":
        effects = proposal.effects or {}
        from .war import execute_war_action
        wresult = execute_war_action(
            conn, actor_id, str(effects.get("war_action_kind") or ""),
            effects.get("war_action_payload") if isinstance(effects.get("war_action_payload"), dict) else {}, day,
        )
        outcome_parts.append(str(wresult.get("summary") or "War action resolved."))
    elif proposal.action_type == "political_action":
        effects = proposal.effects or {}
        from .conflict import execute_political_action
        presult = execute_political_action(
            conn, actor_id, str(effects.get("political_action_kind") or ""),
            effects.get("political_action_payload") if isinstance(effects.get("political_action_payload"), dict) else {}, day,
        )
        outcome_parts.append(str(presult.get("summary") or "Political action resolved."))
    elif proposal.action_type == "opportunity_action":
        effects = proposal.effects or {}
        from .opportunity import execute_opportunity_action
        oresult = execute_opportunity_action(
            conn, actor_id, str(effects.get("opportunity_action_kind") or ""),
            effects.get("opportunity_action_payload") if isinstance(effects.get("opportunity_action_payload"), dict) else {}, day,
        )
        outcome_parts.append(str(oresult.get("summary") or "Opportunity action resolved."))
        if oresult.get("interaction_id") is not None:
            interaction_id_created = int(oresult["interaction_id"])
    elif proposal.action_type == "underworld_action":
        effects = proposal.effects or {}
        from .underworld_decisions import execute_underworld_action
        uresult = execute_underworld_action(
            conn, actor_id, str(effects.get("underworld_action_kind") or ""),
            effects.get("underworld_action_payload") if isinstance(effects.get("underworld_action_payload"), dict) else {}, day,
        )
        outcome_parts.append(str(uresult.get("summary") or "Underworld action resolved."))
    elif proposal.action_type == "initiate_interaction" and proposal.target_actor_id and proposal.interaction_type:
        stakes = 2
        if proposal.interaction_type in {"alliance", "threat", "investigation"}:
            stakes = 3
        elif proposal.interaction_type == "attack":
            stakes = 5
        urgency = 3 if proposal.interaction_type in {"threat", "attack"} else 2
        interaction_id = create_interaction(
            conn, actor_id, proposal.target_actor_id, proposal.interaction_type, day,
            urgency=urgency, stakes=stakes, terms=proposal.effects or {},
            rationale=proposal.rationale, canon_chunk_ids=proposal.canon_chunk_ids,
        )
        interaction_id_created = interaction_id
        target_name = conn.execute("SELECT name FROM actors WHERE id=?", (proposal.target_actor_id,)).fetchone()[0]
        outcome_parts.append(
            f"Created interaction #{interaction_id}: {proposal.interaction_type} directed toward {target_name}."
        )
    else:  # consolidate
        row = conn.execute(
            "SELECT id,intensity FROM pressures WHERE actor_id=? ORDER BY intensity DESC LIMIT 1", (actor_id,)
        ).fetchone()
        if row:
            relief = 0.4 * base * (1.0 + drives["patience"])
            new_value = max(0.0, float(row["intensity"]) - relief)
            conn.execute("UPDATE pressures SET intensity=?,updated_day=? WHERE id=?", (new_value, day, row["id"]))
            outcome_parts.append(f"Consolidation reduced the highest pressure to {new_value:.1f}.")
        else:
            outcome_parts.append("The actor consolidated without a major state change.")

    outcome = " ".join(outcome_parts)
    cur = conn.execute(
        """INSERT INTO decisions(day,actor_id,tier,action_type,target_goal_id,target_pressure_id,score,rationale,
           canon_chunk_ids_json,effects_json,outcome_summary,status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,'applied')""",
        (
            day, actor_id, tier, proposal.action_type, proposal.goal_id, proposal.pressure_id,
            proposal.score, proposal.rationale, json.dumps(list(proposal.canon_chunk_ids)),
            json.dumps(proposal.effects or {}), outcome,
        ),
    )
    decision_id = int(cur.lastrowid)
    evaluation_id = (proposal.effects or {}).get("decision_evaluation_id")
    if evaluation_id is not None:
        try:
            conn.execute("UPDATE decision_evaluations SET decision_id=? WHERE id=? AND actor_id=?", (decision_id, int(evaluation_id), actor_id))
        except sqlite3.OperationalError:
            pass
    if interaction_id_created is not None:
        conn.execute(
            """INSERT OR IGNORE INTO causal_links(day,source_kind,source_id,target_kind,target_id,relation)
               VALUES (?,'decision',?,'interaction',?,'initiated')""",
            (day, decision_id, interaction_id_created),
        )
    return decision_id


def decide_actor(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, provider: DecisionProvider | None = None) -> int:
    provider = provider or InformationBoundedDecisionProvider()
    proposal = provider.choose(conn, actor_id, tier, day)
    return apply_decision(conn, actor_id, tier, day, proposal)


def recent_decisions(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT d.*,a.name actor_name FROM decisions d JOIN actors a ON a.id=d.actor_id
           ORDER BY d.day DESC,d.id DESC LIMIT ?""", (limit,)
    ).fetchall()
    return [dict(r) for r in reversed(rows)]
