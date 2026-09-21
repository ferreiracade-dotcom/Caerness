from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.embodiment import (
    assess_autonomous_expression,
    get_embodiment_profile,
    prepare_speech_mediation,
    recent_speech_mediations,
    record_expression,
    update_embodiment_profile,
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
        assert ENGINE_VERSION in {"0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0","0.60.0"}
        assert conn.execute("SELECT value FROM engine_meta WHERE key='engine_version'").fetchone()[0] in {"0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0", "0.58.0","0.59.0"}

        player = _actor(conn, "[DEMO] Player Wanderer")
        company = _actor(conn, "[DEMO] River Lantern Escort Company")
        assert player and company
        set_player(conn, int(player["id"]), "Embodiment Test")

        # Persistent protagonist profile exists and may be merged rather than overwritten wholesale.
        base = get_embodiment_profile(conn, int(player["id"]))
        assert base["expression_policy"]["major_commitments_require_player"] is True
        updated = update_embodiment_profile(
            conn,
            int(player["id"]),
            {
                "voice": {"register": "plain", "humor": "dry"},
                "temperament": {"rudeness": 0.75, "self_control": 0.7},
                "habits": {"greeting": "brief nod"},
                "social": {"formal_speech": "competent", "intimate_speech": "guarded"},
                "relationship_style": {"strangers": "cool", "trusted_people": "protective"},
            },
            source_kind="campaign",
        )
        assert updated["voice"]["register"] == "plain"
        assert updated["voice"]["humor"] == "dry"
        assert updated["temperament"]["rudeness"] == 0.75

        # Low-stakes, high-confidence expression can be inferred.
        allowed = assess_autonomous_expression(
            conn, int(player["id"]), expression_kind="gesture", confidence=0.92, stakes=1
        )
        assert allowed.result == "allow"
        # Major commitments are blocked regardless of strong character fit.
        blocked = assess_autonomous_expression(
            conn, int(player["id"]), expression_kind="speech", confidence=0.99, stakes=5,
            irreversible=True, commitment_kind="oath",
        )
        assert blocked.result == "block"
        assert blocked.commitment_risk == "high"

        audit = record_expression(
            conn, int(player["id"]), "Gives the familiar brief nod rather than a warm greeting.",
            expression_kind="greeting", confidence=0.91, stakes=1,
        )
        assert audit["assessment"]["result"] == "allow"
        assert conn.execute("SELECT COUNT(*) FROM embodiment_expressions WHERE actor_id=?", (player["id"],)).fetchone()[0] == 1

        # Intent speech is not treated as a literal transcript.
        med = prepare_speech_mediation(
            conn, int(player["id"]), "Tell him I support the plan if he keeps his word.",
            mode="intent", intended_tone="controlled", social_objective="conditional support",
        )
        assert med["preserve_exact_words"] is False
        assert med["voice"]["humor"] == "dry"
        assert med["autonomy"]["result"] == "allow"
        # Exact speech preserves the player's wording.
        exact_text = "You had one duty."
        exact = prepare_speech_mediation(conn, int(player["id"]), exact_text, mode="exact")
        assert exact["preserve_exact_words"] is True
        assert exact["raw_input"] == exact_text
        # A marriage/oath/etc. speech packet does not authorize the commitment itself.
        oath = prepare_speech_mediation(
            conn, int(player["id"]), "Swear loyalty to him.", mode="intent", commitment_kind="oath"
        )
        assert oath["autonomy"]["result"] == "block"

        history = recent_speech_mediations(conn, int(player["id"]), 5)
        assert len(history) >= 3

        # Scene and narration packets carry embodiment without exposing hidden NPC internals.
        scene = build_scene_packet(conn, "Tell the company representative we can discuss terms.")
        assert scene["embodiment"]["profile"]["voice"]["register"] == "plain"
        assert "rendering_rules" in scene["embodiment"]
        envelope = build_narration_envelope(
            scene["request"], scene, {"summary": "You speak.", "status": "applied", "action_type": "speak"}, scene
        )
        assert envelope["protagonist_embodiment"]["profile"]["actor_id"] == int(player["id"])
        assert any("major commitments" in rule for rule in envelope["narration_rules"])
        conn.commit()

    print("v10_test: PASS")


if __name__ == "__main__":
    run()
