from __future__ import annotations

import json

from engine.canon import DEFAULT_CANON, index_canon
from engine.db import connect, init_db, reset_db
from engine.information import process_information
from engine.player import build_scene_packet
from engine.simulation import SimEvent, advance, log_event, seed_demo


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
    # 1. Private world truth is known to participants but is not dumped into the player's scene packet.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        locs = _locs(conn)
        secret_target = ids["[DEMO] House of Seven Ledgers"]
        eid = log_event(conn, SimEvent(
            day=0,
            event_type="internal:succession",
            title="Hidden succession bargain",
            summary="The merchant house privately committed to a hidden succession bargain.",
            severity=4,
            source_actor_id=secret_target,
            target_actor_ids=(secret_target,),
            location_id=locs["Cairnholt"],
            visibility="private",
            rumorability=0.0,
        ))
        process_information(conn, 0)
        packet = build_scene_packet(conn, "What is happening around me?")
        raw = json.dumps(packet)
        assert "Hidden succession bargain" not in raw, "Private NPC truth must not leak into the player scene packet."
        npc_knows = conn.execute(
            "SELECT 1 FROM knowledge WHERE knower_actor_id=? AND truth_event_id=?",
            (secret_target, eid),
        ).fetchone()
        assert npc_knows is not None, "A participant should know its own private event."

    # 2. Public/limited events can become rumours and travel without the player or actors following them.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        locs = _locs(conn)
        eid = log_event(conn, SimEvent(
            day=0,
            event_type="public:caravan_loss",
            title="Caravan missing from Cairnholt road",
            summary="A prominent caravan failed to arrive from the Cairnholt road.",
            severity=3,
            source_actor_id=ids["[DEMO] House of Seven Ledgers"],
            location_id=locs["Cairnholt"],
            visibility="public",
            rumorability=0.95,
            reliability=0.9,
        ))
        process_information(conn, 0)
        assert conn.execute("SELECT COUNT(*) FROM rumours WHERE truth_event_id=?", (eid,)).fetchone()[0] == 1
        conn.commit()
    advance(5)
    with connect() as conn:
        locs = _locs(conn)
        at_toll = conn.execute(
            """SELECT COUNT(*) FROM rumour_locations rl JOIN rumours r ON r.id=rl.rumour_id
               WHERE r.truth_event_id=? AND rl.location_id=?""",
            (eid, locs["Toll's Reach"]),
        ).fetchone()[0]
        assert at_toll == 1, "Rumour should propagate from Cairnholt to Toll's Reach along persisted routes."
        packet = build_scene_packet(conn, "Listen for road news.")
        assert any("caravan" in r["text"].lower() for r in packet["known_rumours"]), "Player should be able to hear local propagated rumours."
        link = conn.execute(
            "SELECT 1 FROM information_links WHERE source_kind='event' AND source_id=? AND target_kind='rumour'",
            (eid,),
        ).fetchone()
        assert link is not None, "Event -> rumour provenance must be inspectable."

    # 3. A private event directly involving the player is visible to the player despite not being public.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        locs = _locs(conn)
        player_id = ids["[DEMO] Player Wanderer"]
        eid = log_event(conn, SimEvent(
            day=0,
            event_type="private:warning",
            title="Private warning",
            summary="The player received a private warning from an escort captain.",
            severity=2,
            source_actor_id=ids["[DEMO] River Lantern Escort Company"],
            target_actor_ids=(player_id,),
            location_id=locs["Toll's Reach"],
            visibility="private",
            rumorability=0.0,
        ))
        packet = build_scene_packet(conn, "Review what I know.")
        assert any(e["id"] == eid for e in packet["known_events"]), "Direct private knowledge should appear for the player involved."

    # 4. Scene packets expose visible identity, not hidden NPC simulation state.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        toll = _locs(conn)["Toll's Reach"]
        # Move the merchant house into the same location so it appears in present_actors.
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (toll, ids["[DEMO] House of Seven Ledgers"]))
        packet = build_scene_packet(conn, "Who is here?")
        assert any(a["name"] == "[DEMO] House of Seven Ledgers" for a in packet["present_actors"])
        raw = json.dumps(packet)
        assert "Expand influence among caravan brokers" not in raw, "NPC hidden goals must not leak through scene packets."
        assert "aggression" not in raw and "risk_tolerance" not in raw, "NPC drive fields must not leak."

    # 5. The engine must not autonomously play the player's character or auto-answer incoming business.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        player_id = ids["[DEMO] Player Wanderer"]
        before = conn.execute("SELECT COUNT(*) FROM decisions WHERE actor_id=?", (player_id,)).fetchone()[0]
        # Create a pending offer addressed to the player.
        from engine.interactions import create_interaction
        iid = create_interaction(
            conn, ids["[DEMO] House of Seven Ledgers"], player_id, "offer", 0,
            urgency=5, stakes=2, terms={"purpose": "player-facing job offer"}, response_due_day=1,
        )
        conn.commit()
    advance(5)
    with connect() as conn:
        player_id = _ids(conn)["[DEMO] Player Wanderer"]
        after = conn.execute("SELECT COUNT(*) FROM decisions WHERE actor_id=?", (player_id,)).fetchone()[0]
        assert after == before, "The autonomous decision engine must never choose actions for the configured player."
        state = conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()[0]
        assert state == "pending", "Incoming player interactions must remain pending until the player answers them."
        packet = build_scene_packet(conn, "Check for messages.")
        assert any(i["id"] == iid for i in packet["pending_player_interactions"]), "Pending player interactions must surface in scene state."

    # 6. Dormant-origin events are still registered into the information ecology off-screen.
    _fresh()
    advance(90)
    with connect() as conn:
        background = conn.execute("SELECT COUNT(*) FROM events WHERE event_type LIKE 'background:%'").fetchone()[0]
        registered = conn.execute(
            """SELECT COUNT(*) FROM event_information ei JOIN events e ON e.id=ei.event_id
               WHERE e.event_type LIKE 'background:%'"""
        ).fetchone()[0]
        assert background > 0 and registered == background, "Dormant world events must enter information processing, not remain invisible engine-only state."

    print("Information test passed: privacy, rumours, propagation, provenance, player knowledge, scene guardrails, and dormant information all work.")


if __name__ == "__main__":
    run()
