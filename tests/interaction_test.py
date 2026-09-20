from engine.canon import DEFAULT_CANON, index_canon
from engine.db import connect, init_db, reset_db
from engine.interactions import create_interaction
from engine.simulation import advance, seed_demo


def _fresh():
    reset_db()
    init_db()
    index_canon(DEFAULT_CANON)
    seed_demo()


def _ids(conn):
    return {r["name"]: int(r["id"]) for r in conn.execute("SELECT id,name FROM actors")}


def run():
    # 1. Cooperative interactions can become persistent agreements.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        iid = create_interaction(
            conn,
            ids["[DEMO] River Lantern Escort Company"],
            ids["[DEMO] House of Seven Ledgers"],
            "contract",
            0,
            urgency=5,
            stakes=3,
            terms={"purpose": "test contract", "duration_days": 45},
            response_due_day=1,
        )
        conn.commit()
    advance(1)
    with connect() as conn:
        row = conn.execute("SELECT * FROM interactions WHERE id=?", (iid,)).fetchone()
        assert row["status"] == "accepted", "Positive counterpart should be able to accept a contract."
        agreement = conn.execute("SELECT id FROM agreements WHERE source_interaction_id=?", (iid,)).fetchone()
        assert agreement is not None, "Accepted contract should create a persistent agreement."
        link = conn.execute(
            "SELECT 1 FROM causal_links WHERE source_kind='interaction' AND source_id=? AND target_kind='agreement'",
            (iid,),
        ).fetchone()
        assert link is not None, "Interaction -> agreement causality should be inspectable."

    # 2. Borderline negotiations produce a real counterproposal, not a cosmetic response string.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        a = ids["[DEMO] House of Seven Ledgers"]
        b = ids["[DEMO] River Lantern Escort Company"]
        conn.execute(
            """UPDATE relationships SET stance=0,trust=0,obligation=0
               WHERE (actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)""",
            (a, b, b, a),
        )
        iid = create_interaction(
            conn, a, b, "negotiation", 0,
            urgency=5, stakes=2, terms={"purpose": "test terms"}, response_due_day=1,
        )
        conn.commit()
    advance(1)
    with connect() as conn:
        parent = conn.execute("SELECT status FROM interactions WHERE id=?", (iid,)).fetchone()
        assert parent["status"] == "countered", "Borderline negotiation should create a counterproposal in the deterministic demo."
        child = conn.execute("SELECT id FROM interactions WHERE parent_interaction_id=?", (iid,)).fetchone()
        assert child is not None, "Counterproposal must be a new causal interaction."
        link = conn.execute(
            """SELECT 1 FROM causal_links WHERE source_kind='interaction' AND source_id=?
               AND target_kind='interaction' AND target_id=? AND relation='countered_by'""",
            (iid, child["id"]),
        ).fetchone()
        assert link is not None

    # 3. Open hostile action creates a conflict thread, pressures, event, and wakes a dormant target.
    _fresh()
    with connect() as conn:
        ids = _ids(conn)
        attacker = ids["[DEMO] North Road Brotherhood"]
        target = ids["[DEMO] Remote Reed Sect"]
        iid = create_interaction(
            conn, attacker, target, "attack", 0,
            urgency=5, stakes=5, terms={"purpose": "test conflict"}, response_due_day=1,
        )
        conn.commit()
    advance(1)
    with connect() as conn:
        row = conn.execute("SELECT * FROM interactions WHERE id=?", (iid,)).fetchone()
        assert row["status"] == "resolved" and row["thread_id"] is not None
        assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='inter_actor_conflict'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pressures WHERE actor_id=?", (target,)).fetchone()[0] > 0
        profile = conn.execute("SELECT forced_tier FROM simulation_profiles WHERE actor_id=?", (target,)).fetchone()
        assert profile["forced_tier"] == "ACTIVE", "Severe incoming action should wake a dormant target to active resolution."

    # 4. Dormant actors can originate interactions of their own on coarse review cadence.
    _fresh()
    advance(120)
    with connect() as conn:
        ids = _ids(conn)
        north = ids["[DEMO] North Road Brotherhood"]
        originating = conn.execute(
            "SELECT COUNT(*) FROM interactions WHERE proposer_actor_id=?", (north,)
        ).fetchone()[0]
        assert originating > 0, "Dormant actors must be able to initiate causal interactions off-screen."
        dormant_decisions = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE actor_id=? AND tier='DORMANT' AND action_type='initiate_interaction'",
            (north,),
        ).fetchone()[0]
        assert dormant_decisions > 0

    print("Interaction test passed: agreements, counters, conflict, wake-up, and dormant-origin interactions all work.")


if __name__ == "__main__":
    run()
