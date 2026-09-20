from __future__ import annotations

import sqlite3
from typing import Any


def derive_actor_motives(conn: sqlite3.Connection, actor_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
    """Derive decision-facing motives from authoritative domain state without duplicating truth.

    These are read-only adapters. They do not create generic goals/pressures, and their source
    fields point back to the owning subsystem so downstream decision/narration layers can reason
    from real state without inventing a second ontology.
    """
    motives: list[dict[str, Any]] = []

    def add(domain: str, kind: str, priority: float, description: str, owner: str, source_id: int | None = None) -> None:
        motives.append({
            "domain": domain, "kind": kind, "priority": max(0.0, min(100.0, float(priority))),
            "description": description, "authoritative_owner": owner, "source_id": source_id,
        })

    # Health: severe unresolved conditions create direct practical pressure.
    for r in conn.execute(
        """SELECT id,label,severity,status FROM health_conditions
           WHERE actor_id=? AND status IN ('active','recovering','chronic') ORDER BY severity DESC,id LIMIT 3""", (actor_id,)
    ).fetchall():
        add("health", "pressure", 45 + float(r["severity"]) * 0.5,
            f"Manage {r['label']} ({r['status']}).", "health_conditions", int(r["id"]))

    # Household: low cohesion/liquidity or being the household head generates local responsibilities.
    hh = conn.execute(
        """SELECT h.* FROM households h JOIN household_members hm ON hm.household_id=h.id
           WHERE hm.actor_id=? AND hm.status='active' AND h.status NOT IN ('dissolved','historical')
           ORDER BY hm.authority DESC,h.id LIMIT 1""", (actor_id,)
    ).fetchone()
    if hh:
        if int(hh["head_actor_id"] or 0) == actor_id:
            add("household", "goal", 55, f"Maintain {hh['name']} and its continuity.", "households", int(hh["id"]))
        if float(hh["cohesion"]) < 40:
            add("household", "pressure", 70 - float(hh["cohesion"]) * 0.5,
                f"Household cohesion is strained in {hh['name']}.", "households", int(hh["id"]))
        if float(hh["liquidity"]) < 0:
            add("household", "pressure", 85, f"{hh['name']} has negative liquidity.", "households", int(hh["id"]))

    # Enterprise ownership / governance.
    for r in conn.execute(
        """SELECT id,name,status,cash,debt,reputation FROM civilian_enterprises
           WHERE owner_actor_id=? AND status IN ('active','strained','insolvent') ORDER BY
           CASE status WHEN 'insolvent' THEN 0 WHEN 'strained' THEN 1 ELSE 2 END,id LIMIT 3""", (actor_id,)
    ).fetchall():
        if r["status"] == "insolvent":
            add("business", "pressure", 95, f"{r['name']} is insolvent.", "civilian_enterprises", int(r["id"]))
        elif r["status"] == "strained":
            add("business", "pressure", 78, f"{r['name']} is under commercial strain.", "civilian_enterprises", int(r["id"]))
        else:
            add("business", "goal", 46, f"Sustain {r['name']} as a going concern.", "civilian_enterprises", int(r["id"]))

    # Religion: only explicit obligations, never inferred belief.
    for r in conn.execute(
        """SELECT ro.id,ro.obligation_kind,ro.description,ro.due_day,a.name institution_name
           FROM religious_obligations ro
           LEFT JOIN actors a ON a.id=ro.institution_actor_id
           WHERE ro.actor_id=? AND ro.status IN ('pending','overdue') ORDER BY ro.due_day,ro.id LIMIT 3""", (actor_id,)
    ).fetchall():
        due = "" if r["due_day"] is None else f" due day {r['due_day']}"
        add("religion", "goal", 55 if r["due_day"] is None else 70,
            f"Fulfil religious obligation: {r['description']}{due}.", "religious_obligations", int(r["id"]))

    # Travel: an active plan is an already-committed practical goal, not a new commitment.
    tr = conn.execute(
        """SELECT tp.id,tp.status,l.name destination FROM travel_plans tp
           LEFT JOIN locations l ON l.id=tp.destination_location_id
           WHERE tp.subject_kind='actor' AND tp.subject_id=? AND tp.status IN ('active','stalled') ORDER BY tp.id DESC LIMIT 1""", (actor_id,)
    ).fetchone()
    if tr:
        add("travel", "goal" if tr["status"] != "stalled" else "pressure", 65 if tr["status"] != "stalled" else 80,
            f"Continue travel toward {tr['destination'] or 'the established destination'} ({tr['status']}).",
            "travel_plans", int(tr["id"]))

    # Education and transmission.
    for r in conn.execute(
        """SELECT e.id,e.status,p.name program_name FROM education_enrollments e
           JOIN education_programs p ON p.id=e.program_id
           WHERE e.actor_id=? AND e.status IN ('active','paused') ORDER BY e.id LIMIT 3""", (actor_id,)
    ).fetchall():
        add("education", "goal" if r["status"] == "active" else "pressure", 52 if r["status"] == "active" else 68,
            f"{('Continue' if r['status']=='active' else 'Resolve interruption in')} {r['program_name']}.",
            "education_enrollments", int(r["id"]))

    # Political office / succession claims.
    for r in conn.execute(
        """SELECT p.id,a.name polity_name,p.status FROM political_polities p
           JOIN actors a ON a.id=p.institution_actor_id WHERE p.ruler_actor_id=?""", (actor_id,)
    ).fetchall():
        add("politics", "goal", 72, f"Govern {r['polity_name']} through its current {r['status']} condition.",
            "political_polities", int(r["id"]))
    for r in conn.execute(
        """SELECT sc.id,a.name polity_name,sc.status FROM political_succession_claims sc
           JOIN political_polities p ON p.id=sc.polity_id JOIN actors a ON a.id=p.institution_actor_id
           WHERE sc.claimant_actor_id=? AND sc.status='active' ORDER BY sc.priority DESC,sc.id LIMIT 2""", (actor_id,)
    ).fetchall():
        add("politics", "goal", 66, f"Maintain or advance the established succession claim in {r['polity_name']}.",
            "political_succession_claims", int(r["id"]))

    motives.sort(key=lambda x: (-x["priority"], x["domain"], x["description"]))
    return motives[: max(1, int(limit))]
