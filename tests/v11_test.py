from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.expertise import (
    actor_competence_profile,
    add_advisor_judgment,
    advisor_judgments,
    build_scene_competence_packet,
    decision_context,
    prepare_professional_reading,
    professional_reading,
    record_professional_reading,
    set_actor_competence,
)
from engine.player import build_scene_packet, set_player
from engine.simulation import seed_demo
from engine.turns import build_narration_envelope


def _actor(conn, name: str):
    return conn.execute("SELECT * FROM actors WHERE name=?", (name,)).fetchone()


def run():
    reset_db()
    init_db()
    seed_demo()
    init_db()

    with connect() as conn:
        assert ENGINE_VERSION in {"0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0","0.60.0"}
        assert conn.execute("SELECT value FROM engine_meta WHERE key='engine_version'").fetchone()[0] in {"0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0", "0.58.0","0.59.0"}

        player = _actor(conn, "[DEMO] Player Wanderer")
        advisor = _actor(conn, "[DEMO] River Lantern Escort Company")
        assert player and advisor
        set_player(conn, int(player["id"]), "Expertise Test")

        # Domain competence is explicit and independent: trade expertise does not imply politics or command.
        set_actor_competence(
            conn, int(player["id"]), "commerce", 72,
            specialty="long-distance trade", experience={"years": 12}, training={"route_accounting": True},
            source_kind="campaign",
        )
        set_actor_competence(conn, int(player["id"]), "politics", 24, source_kind="campaign")
        profile = actor_competence_profile(conn, int(player["id"]))
        commerce = next(x for x in profile if x["domain_key"] == "commerce")
        politics = next(x for x in profile if x["domain_key"] == "politics")
        assert commerce["band"]["key"] == "experienced"
        assert politics["band"]["key"] == "novice"
        assert commerce["experience"]["years"] == 12

        # A professional reading is constrained by competence + evidence and cannot invent hidden facts.
        packet = prepare_professional_reading(
            conn,
            int(player["id"]),
            "commerce",
            "A wool shipment is late while freight premiums are rising.",
            evidence=[
                {"kind": "report", "text": "Shipment is six days late", "reliability": 0.8},
                {"kind": "quote", "text": "Freight premium increased", "reliability": 0.9},
            ],
            stakes=3,
            uncertainty=0.35,
        )
        assert packet["competence"]["band"]["key"] == "experienced"
        assert packet["interpretation_contract"]["may_invent_hidden_facts"] is False
        assert packet["interpretation_contract"]["may_override_player_choice"] is False

        resolved = record_professional_reading(
            conn,
            packet["reading_id"],
            summary="The pattern is concerning but does not yet prove a production collapse.",
            observations=["Shipment delay", "Higher freight premium"],
            inferences=["Transport risk may be rising"],
            unknowns=["Whether production itself has fallen"],
            options=[{"approach": "seek corroborating route reports"}],
            confidence=0.99,  # must be capped by the grounded packet
            provider="local",
        )
        stored = professional_reading(conn, packet["reading_id"])
        assert stored and stored["result"]["confidence"] == resolved["confidence"]
        assert resolved["confidence"] <= packet["reading_confidence"]
        assert "production itself" in stored["result"]["unknowns"][0]

        # Advisor judgment is a separate named opinion, not merged into character expertise or truth.
        judgment_id = add_advisor_judgment(
            conn,
            int(player["id"]),
            int(advisor["id"]),
            "commerce",
            "wool-delay-1",
            "I think the delays are temporary and would not abandon the route yet.",
            confidence=0.62,
            assumptions=["No border closure has occurred"],
            communicated=True,
        )
        assert judgment_id > 0
        judgments = advisor_judgments(
            conn, int(player["id"]), situation_key="wool-delay-1", domain_key="commerce"
        )
        assert len(judgments) == 1
        assert judgments[0]["advisor_name"] == "[DEMO] River Lantern Escort Company"
        ctx = decision_context(
            conn, int(player["id"]), "commerce", "wool-delay-1", reading_id=packet["reading_id"]
        )
        assert ctx["character_professional_reading"]["result"]["summary"] != judgments[0]["judgment_text"]
        assert "distinct layers" in ctx["separation_rule"]

        # Request-sensitive scene packets expose relevant competence but not hidden information.
        cpacket = build_scene_competence_packet(
            conn, int(player["id"]), "Should I buy more wool while the shipment is late?"
        )
        assert any(x["domain"] == "commerce" for x in cpacket["relevant_domains"])
        assert any("hidden world state" in r for r in cpacket["rules"])

        scene = build_scene_packet(conn, "Should I buy more wool while the shipment is late?")
        assert "professional_context" in scene
        assert any(x["domain"] == "commerce" for x in scene["professional_context"]["relevant_domains"])
        envelope = build_narration_envelope(
            scene["request"], scene,
            {"summary": "You consider the position.", "status": "applied", "action_type": "observe"},
            scene,
        )
        assert "professional_context" in envelope
        assert any("advisor" in rule.lower() for rule in envelope["narration_rules"])
        conn.commit()

    print("v11_test: PASS")


if __name__ == "__main__":
    run()
