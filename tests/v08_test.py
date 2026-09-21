from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.continuity import (
    add_career_stage,
    add_cohort_member,
    add_historical_anchor,
    add_public_narrative,
    advance_career_stage,
    continuity_core,
    create_career_track,
    create_cohort,
    create_latent_entity,
    historical_anchors,
    resolution_state,
    set_institution_profile,
    set_resolution,
    start_career,
    upsert_continuity_core,
)
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.simulation import seed_demo


def _actor(conn, name: str):
    return conn.execute("SELECT * FROM actors WHERE name=?", (name,)).fetchone()


def run():
    reset_db()
    init_db()
    seed_demo()
    init_db()  # migration seed must also work after actors/profiles already exist

    with connect() as conn:
        assert ENGINE_VERSION in {"0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0","0.60.0"}
        assert conn.execute("SELECT value FROM engine_meta WHERE key='engine_version'").fetchone()[0] in {"0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0", "0.58.0","0.59.0","0.60.0"}

        player = _actor(conn, "[DEMO] Player Wanderer")
        company = _actor(conn, "[DEMO] River Lantern Escort Company")
        assert player and company

        # Existing v0.7 simulation profiles seed the broader v0.8 resolution layer.
        seeded = resolution_state(conn, "actor", int(player["id"]))
        assert seeded is not None
        assert seeded["resolution_level"] == "ACTIVE"

        # Continuity cores persist compact person/institution state independently of prose.
        core_id = upsert_continuity_core(
            conn,
            "actor",
            int(player["id"]),
            {
                "temperament": {"rudeness": 0.7, "patience": 0.3},
                "identity": {"origin": "demo"},
                "unresolved": ["prove reliability"],
            },
            historical_depth="developed",
            crystallized_day=0,
            source_kind="campaign",
        )
        assert core_id > 0
        core = continuity_core(conn, "actor", int(player["id"]))
        assert core["historical_depth"] == "developed"
        assert core["core"]["temperament"]["rudeness"] == 0.7

        # Anchors are append-only facts suitable for later historical crystallization.
        a1 = add_historical_anchor(
            conn,
            "actor",
            int(player["id"]),
            "apprenticeship",
            "Entered an escort-company apprenticeship.",
            start_day=-1800,
            end_day=-900,
            detail={"institution": int(company["id"])},
            source_kind="crystallization",
        )
        a2 = add_historical_anchor(
            conn,
            "actor",
            int(player["id"]),
            "career_turn",
            "Left formal apprenticeship for independent work.",
            start_day=-899,
            source_kind="crystallization",
        )
        assert a2 > a1
        anchors = historical_anchors(conn, "actor", int(player["id"]))
        assert len(anchors) == 2
        assert anchors[0]["anchor_type"] == "apprenticeship"

        # Cohorts carry shared history without simulating every person individually.
        cohort_id = create_cohort(
            conn,
            "[DEMO] Toll's Reach escort trainees, cohort A",
            "apprenticeship",
            institution_actor_id=int(company["id"]),
            location_id=int(player["current_location_id"]),
            start_day=-1800,
            end_day=-900,
            population_estimate=18,
            shared_context={"trade_pressure": "high", "road_conditions": "unstable"},
            historical_summary="A training generation shaped by dangerous northern road work.",
        )
        add_cohort_member(conn, cohort_id, int(player["id"]), role="trainee", joined_day=-1800, left_day=-900, membership_status="former")
        assert conn.execute("SELECT COUNT(*) FROM cohort_memberships WHERE cohort_id=?", (cohort_id,)).fetchone()[0] == 1

        # Career tracks support changing life-stage play rather than one permanent occupation tag.
        track_id = create_career_track(
            conn,
            "demo_merchant",
            "Merchant Career",
            "commerce",
            typical_entry_age=16,
            institution_kind="merchant_house",
            stage_model={"progression": "experience-and-opportunity"},
        )
        apprentice = add_career_stage(conn, track_id, "apprentice", "Apprentice", 10)
        factor = add_career_stage(conn, track_id, "factor", "Factor", 20)
        career_id = start_career(conn, int(player["id"]), track_id, stage_id=apprentice, institution_actor_id=int(company["id"]), started_day=-1000)
        advance_career_stage(conn, career_id, factor, day=-300)
        career = conn.execute("SELECT * FROM actor_careers WHERE id=?", (career_id,)).fetchone()
        assert int(career["current_stage_id"]) == factor
        assert int(career["stage_started_day"]) == -300

        # Institutions act as compression nodes for pipelines, culture and capacity.
        set_institution_profile(
            conn,
            int(company["id"]),
            "escort_company",
            primary_location_id=int(company["current_location_id"]),
            culture={"initiative": "moderate", "reliability": "valued"},
            pipeline={"entry": "apprenticeship", "senior_path": "field promotion"},
            capacity={"simultaneous_contracts": 4},
            trajectory="stable",
        )
        inst = conn.execute("SELECT * FROM institution_profiles WHERE actor_id=?", (company["id"],)).fetchone()
        assert inst is not None
        assert json.loads(inst["pipeline_json"])["entry"] == "apprenticeship"

        # Resolution changes are explicit and historical, but locked minima prevent accidental over-demotion.
        set_resolution(conn, "actor", int(player["id"]), "SCENE", day=5, reason="direct conversation", source_kind="player", locked_min_level="TRACKED")
        assert resolution_state(conn, "actor", int(player["id"]))["resolution_level"] == "SCENE"
        set_resolution(conn, "actor", int(player["id"]), "TRACKED", day=6, reason="scene ended")
        try:
            set_resolution(conn, "actor", int(player["id"]), "STRUCTURAL", day=7, reason="invalid deep demotion")
        except ValueError:
            pass
        else:
            raise AssertionError("locked minimum did not prevent demotion")
        transitions = conn.execute("SELECT * FROM resolution_transitions WHERE entity_kind='actor' AND entity_id=? ORDER BY id", (player["id"],)).fetchall()
        assert len(transitions) >= 2

        # Latent populations are constrained existence, not freshly spawned lives.
        latent_id = create_latent_entity(
            conn,
            "person_pool",
            "experienced caravan masters",
            location_id=int(player["current_location_id"]),
            count_estimate=9,
            constraints={"age_range": [40, 70], "career_domain": "trade_transport"},
            historical_context={"war_generation": "northern road crisis"},
        )
        latent = conn.execute("SELECT * FROM latent_entities WHERE id=?", (latent_id,)).fetchone()
        assert latent["status"] == "latent"
        assert json.loads(latent["constraints_json"])["age_range"] == [40, 70]

        # Public narrative is explicitly separate from objective event/history state.
        nid = add_public_narrative(
            conn,
            "demo.player.reputation",
            "actor",
            int(player["id"]),
            "The wanderer is thought reliable on the north road.",
            day=6,
            scope_kind="location",
            scope_id=int(player["current_location_id"]),
            confidence=0.6,
            prevalence=0.4,
        )
        assert nid > 0
        narrative = conn.execute("SELECT * FROM public_narratives WHERE id=?", (nid,)).fetchone()
        assert narrative["claim_text"].startswith("The wanderer")

        conn.commit()

    print("v08_test: PASS")


if __name__ == "__main__":
    run()
