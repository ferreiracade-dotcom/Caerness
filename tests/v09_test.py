from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.continuity import (
    add_career_stage, create_career_track, create_cohort, create_latent_entity,
    historical_anchors, set_institution_profile,
)
from engine.crystallization import (
    apply_crystallization_proposal, crystallization_run, export_crystallization_packet,
    parse_crystallization_response, prepare_crystallization_context, validate_crystallization_proposal,
)
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.simulation import SimEvent, log_event, seed_demo


def _actor(conn, name: str):
    return conn.execute("SELECT * FROM actors WHERE name=?", (name,)).fetchone()


def run():
    reset_db()
    init_db()
    seed_demo()
    init_db()

    with connect() as conn:
        assert ENGINE_VERSION in {"0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0"}
        company = _actor(conn, "[DEMO] River Lantern Escort Company")
        player = _actor(conn, "[DEMO] Player Wanderer")
        assert company and player
        loc = int(company["current_location_id"])

        set_institution_profile(
            conn, int(company["id"]), "merchant_escort_house", primary_location_id=loc,
            pipeline={"entry": "apprenticeship"}, culture={"reliability": "valued"}, capacity={"trainees": 20},
        )
        cohort_id = create_cohort(
            conn, "[DEMO] Caravan generation 52", "apprenticeship",
            institution_actor_id=int(company["id"]), location_id=loc,
            start_day=-15000, end_day=-13500, population_estimate=22,
            shared_context={"roads": "volatile", "trade": "expanding"},
            historical_summary="A caravan generation shaped by rapid trade growth and dangerous roads.",
        )
        track_id = create_career_track(conn, "demo_trade_transport", "Trade Transport", "trade_transport", typical_entry_age=16)
        junior = add_career_stage(conn, track_id, "junior", "Junior Caravan Hand", 10)
        master = add_career_stage(conn, track_id, "master", "Caravan Master", 40)

        event_id = log_event(conn, SimEvent(
            day=-11000, event_type="demo:road_crisis", title="[DEMO] Northern road crisis",
            summary="Several routes became unreliable for a season.", severity=3, location_id=loc,
        ))

        latent_id = create_latent_entity(
            conn, "person_pool", "experienced caravan masters", location_id=loc,
            institution_actor_id=int(company["id"]), cohort_id=cohort_id, count_estimate=2,
            constraints={"age_range": [50, 60], "career_domain": "trade_transport"},
            historical_context={"generation": "road-crisis veterans"},
        )
        context = prepare_crystallization_context(conn, latent_id, requested_depth="developed", trigger_kind="test")
        run_id = context["run_id"]
        assert context["cohort"]["id"] == cohort_id
        assert context["institution"]["id"] == int(company["id"])
        assert any(x["id"] == track_id for x in context["career_tracks"])
        assert any(x["id"] == event_id for x in context["local_events"])

        birth_day = context["birth_window"]["earliest_day"] + 1000
        bad = {
            "name": "[DEMO] Edren Badlink",
            "actor_type": "character",
            "birth_day": birth_day,
            "continuity": {"temperament": {"patience": 0.8}},
            "anchors": [],
            "connections": [{"actor_id": int(player["id"]), "trust": 60}],
        }
        result = validate_crystallization_proposal(conn, run_id, bad)
        assert not result["valid"]
        assert any("convenient retroactive connections" in e for e in result["errors"])

        good = {
            "name": "[DEMO] Edren Vaul",
            "actor_type": "character",
            "subtype": "caravan_master",
            "birth_day": birth_day,
            "home_location_id": loc,
            "current_location_id": loc,
            "continuity": {
                "temperament": {"patience": 0.75, "vanity": 0.2},
                "values": ["reliability", "professional independence"],
                "identity": {"origin": "roadside trading household"},
            },
            "anchors": [
                {
                    "anchor_type": "apprenticeship",
                    "start_day": birth_day + 16 * 365,
                    "end_day": birth_day + 20 * 365,
                    "summary": "Entered the River Lantern training generation as a young caravan hand.",
                    "basis": [{"kind": "cohort", "id": cohort_id}, {"kind": "institution", "id": int(company["id"])}],
                },
                {
                    "anchor_type": "career_turn",
                    "start_day": -11000,
                    "summary": "The northern road crisis established his reputation for completing difficult routes.",
                    "basis": [{"kind": "event", "id": event_id}],
                },
            ],
            "career": {
                "track_id": track_id,
                "stage_id": master,
                "institution_actor_id": int(company["id"]),
                "started_day": birth_day + 16 * 365,
                "experience": {"road_years": 30},
                "reputation": {"regional_trade": 0.72},
            },
            "connections": [],
            "resolution_level": "TRACKED",
        }
        result = validate_crystallization_proposal(conn, run_id, good)
        assert result["valid"], result
        actor_id = apply_crystallization_proposal(conn, run_id)
        actor = conn.execute("SELECT * FROM actors WHERE id=?", (actor_id,)).fetchone()
        assert actor["name"] == "[DEMO] Edren Vaul"
        assert actor["subtype"] == "caravan_master"

        anchors = historical_anchors(conn, "actor", actor_id)
        assert [a["anchor_type"] for a in anchors][:1] == ["birth"]
        assert {a["anchor_type"] for a in anchors} >= {"birth", "apprenticeship", "career_turn"}
        core = conn.execute("SELECT * FROM continuity_cores WHERE entity_kind='actor' AND entity_id=?", (actor_id,)).fetchone()
        assert core["historical_depth"] == "developed"
        career = conn.execute("SELECT * FROM actor_careers WHERE actor_id=?", (actor_id,)).fetchone()
        assert int(career["current_stage_id"]) == master
        membership = conn.execute("SELECT * FROM cohort_memberships WHERE cohort_id=? AND actor_id=?", (cohort_id, actor_id)).fetchone()
        assert membership is not None
        latent = conn.execute("SELECT * FROM latent_entities WHERE id=?", (latent_id,)).fetchone()
        assert latent["status"] == "partially_crystallized"
        assert int(latent["count_estimate"]) == 1
        resolution = conn.execute("SELECT * FROM entity_resolution WHERE entity_kind='actor' AND entity_id=?", (actor_id,)).fetchone()
        assert resolution["resolution_level"] == "TRACKED"

        applied = crystallization_run(conn, run_id)
        assert applied["status"] == "applied"
        assert applied["crystallized_entity_id"] == actor_id
        assert applied["lineage"]

        packet_path = export_crystallization_packet(conn, run_id) if False else None
        # Response parser accepts bare JSON and fenced JSON.
        parsed = parse_crystallization_response('```json\n{"name":"X"}\n```')
        assert parsed["name"] == "X"
        conn.commit()

    print("v09_test: PASS")


if __name__ == "__main__":
    run()
