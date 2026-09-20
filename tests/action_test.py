from __future__ import annotations

from engine.canon import DEFAULT_CANON, index_canon
from engine.db import connect, init_db, reset_db
from engine.interactions import create_interaction
from engine.player import build_scene_packet
from engine.simulation import advance, seed_demo
from engine.turns import play_turn
from engine.world import world_activity_summary


def _fresh():
    reset_db()
    init_db()
    index_canon(DEFAULT_CANON)
    seed_demo()


def _ids(conn):
    return {r["name"]: int(r["id"]) for r in conn.execute("SELECT id,name FROM actors")}


def _locs(conn):
    return {r["name"]: int(r["id"]) for r in conn.execute("SELECT id,name FROM locations")}


def run():
    # 1. Waiting advances the whole world, not just the player's local scene.
    _fresh()
    with connect() as conn:
        result = play_turn(conn, "I wait here for 90 days.")
        conn.commit()
        assert result["day_started"] == 0 and result["day_ended"] == 90
        assert result["action_result"]["action_type"] == "wait"
        # A location-owned process in faraway Dunmoor must have moved without the player there.
        dunmoor = _locs(conn)["Dunmoor"]
        metric = conn.execute(
            "SELECT value FROM location_metrics WHERE location_id=? AND key='border_pressure'",
            (dunmoor,),
        ).fetchone()
        assert metric is not None and float(metric[0]) > 0
        world_events = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type LIKE 'world:%' AND location_id=?",
            (dunmoor,),
        ).fetchone()[0]
        assert world_events > 0, "Faraway place-level simulation must create events off-camera."

    # 2. Travel uses the persisted route graph, advances world time, and moves only the player.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        remote = ids["[DEMO] Remote Reed Sect"]
        profile_before = dict(conn.execute("SELECT * FROM simulation_profiles WHERE actor_id=?", (remote,)).fetchone())
        result = play_turn(conn, "I travel to Cairnholt.")
        conn.commit()
        assert result["day_ended"] == 6, "Demo Toll's Reach -> Cairnholt route is six days."
        player = conn.execute(
            """SELECT l.name FROM player_state ps JOIN locations l ON l.id=ps.current_location_id WHERE ps.id=1"""
        ).fetchone()[0]
        assert player == "Cairnholt"
        profile_after = dict(conn.execute("SELECT * FROM simulation_profiles WHERE actor_id=?", (remote,)).fetchone())
        # Time may update review counters, but camera motion must not alter base tier/cadence merely because it moved.
        assert profile_after["tier"] == profile_before["tier"]
        assert profile_after["cadence_days"] == profile_before["cadence_days"]

    # 3. The player can explicitly accept an incoming interaction; the engine never chooses this for them.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        iid = create_interaction(
            conn,
            ids["[DEMO] House of Seven Ledgers"],
            ids["[DEMO] Player Wanderer"],
            "contract",
            0,
            urgency=5,
            stakes=3,
            terms={"purpose": "guard a caravan", "duration_days": 30},
            response_due_day=1,
        )
        conn.commit()
        result = play_turn(conn, f"I accept interaction #{iid}.")
        conn.commit()
        assert result["action_result"]["action_type"] == "respond"
        assert conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()[0] == "accepted"
        assert conn.execute("SELECT COUNT(*) FROM agreements WHERE source_interaction_id=?", (iid,)).fetchone()[0] == 1

    # 4. Direct conversation is a causal exchange, not prose-only state mutation.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        locs = _locs(conn)
        merchant = ids["[DEMO] House of Seven Ledgers"]
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (locs["Toll's Reach"], merchant))
        result = play_turn(conn, "I speak to House of Seven Ledgers about the road.")
        conn.commit()
        assert result["action_result"]["action_type"] == "speak"
        iid = result["action_result"]["interaction_id"]
        row = conn.execute("SELECT interaction_type,status FROM interactions WHERE id=?", (iid,)).fetchone()
        assert row["interaction_type"] == "conversation" and row["status"] != "pending"
        assert conn.execute("SELECT COUNT(*) FROM agreements WHERE source_interaction_id=?", (iid,)).fetchone()[0] == 0

    # 5. Unknown freeform is never silently invented into permanent state.
    _fresh()
    with connect() as conn:
        day_before = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
        event_before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        result = play_turn(conn, "I perform an elaborate improvised maneuver nobody has modeled yet.")
        conn.commit()
        assert result["action_result"]["status"] == "needs_interpretation"
        assert conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0] == day_before
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == event_before

    # 6. Scene observation itself is epistemic only: opening the camera cannot wake actors.
    _fresh()
    with connect() as conn:
        remote = _ids(conn)["[DEMO] Remote Reed Sect"]
        before = dict(conn.execute(
            "SELECT tier,forced_tier,forced_until_day,next_review_day FROM simulation_profiles WHERE actor_id=?", (remote,)
        ).fetchone())
        build_scene_packet(conn, "What do I see?")
        after = dict(conn.execute(
            "SELECT tier,forced_tier,forced_until_day,next_review_day FROM simulation_profiles WHERE actor_id=?", (remote,)
        ).fetchone())
        assert before == after, "Camera attention must not alter simulation state."

    # 7. The world runs even with no configured player at all.
    _fresh()
    with connect() as conn:
        conn.execute("DELETE FROM player_state WHERE id=1")
        conn.commit()
    advance(90)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type LIKE 'world:%'").fetchone()[0] > 0
        pulse = world_activity_summary(conn, 0)
        assert pulse["npc_decisions"] > 0
        assert pulse["regional_world_events"] > 0

    print("Action test passed: freeform actions, explicit player agency, travel/time, and camera-not-protagonist simulation all work.")


if __name__ == "__main__":
    run()
