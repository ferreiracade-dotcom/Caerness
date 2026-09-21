from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.competence import add_intention, add_obligation
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.expertise import set_actor_competence
from engine.player import set_player
from engine.simulation import seed_demo
from engine.timeskip import prepare_time_skip, resolve_time_skip


def _actor(conn, name: str):
    return conn.execute("SELECT * FROM actors WHERE name=?", (name,)).fetchone()


def _fresh():
    reset_db()
    init_db()
    seed_demo()
    init_db()


def run():
    # Ordinary focused time skip completes, advances the whole world, and accumulates exposure without free skill gain.
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {"0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0","0.56.0","0.58.0","0.59.0","0.60.0"}
        assert conn.execute("SELECT value FROM engine_meta WHERE key='engine_version'").fetchone()[0] in {"0.12.0", "0.13.0", "0.14.0", "0.15.0", "0.15.1", "0.16.0", "0.17.0", "0.18.0", "0.19.0", "0.19.1", "0.20.0", "0.20.1", "0.21.0", "0.22.0", "0.23.0","0.24.0", "0.25.0", "0.26.0", "0.26.1", "0.27.1", "0.28.0", "0.29.0", "0.30.0", "0.31.0","0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.37.0", "0.38.0", "0.39.0", "0.40.0", "0.41.0", "0.42.0", "0.43.0", "0.44.0", "0.45.0", "0.46.0", "0.47.0", "0.58.0","0.59.0","0.60.0"}
        player = _actor(conn, "[DEMO] Player Wanderer")
        assert player
        set_player(conn, int(player["id"]), "Time Skip Test")
        set_actor_competence(conn, int(player["id"]), "commerce", 48, source_kind="campaign")
        run_id = prepare_time_skip(
            conn, int(player["id"]), 60,
            focus=[{"key":"trade_study","description":"Focus on trade work and study","domain":"commerce","weight":1.0}],
            max_chunk_days=20,
        )
        result = resolve_time_skip(conn, run_id)
        assert result["status"] == "completed"
        assert result["actual_end_day"] == 60
        assert round(result["focus_progress"][0]["accumulated_days"], 3) == 60.0
        comp = conn.execute(
            """SELECT ac.score,ac.experience_json FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
               WHERE ac.actor_id=? AND d.domain_key='commerce'""",
            (player["id"],),
        ).fetchone()
        assert float(comp["score"]) == 48.0
        assert '"time_skip_focus_days": 60.0' in comp["experience_json"]
        anchor = conn.execute(
            "SELECT * FROM historical_anchors WHERE entity_kind='actor' AND entity_id=? AND anchor_type='time_skip_period' ORDER BY id DESC LIMIT 1",
            (player["id"],),
        ).fetchone()
        assert anchor and anchor["start_day"] == 0 and anchor["end_day"] == 60
        conn.commit()

    # A high-importance non-routine obligation interrupts at its due day rather than being summarized past it.
    _fresh()
    with connect() as conn:
        player = _actor(conn, "[DEMO] Player Wanderer")
        set_player(conn, int(player["id"]), "Obligation Interrupt")
        iid = add_intention(
            conn, int(player["id"]), "decide whether to accept the succession offer",
            intention_kind="decision", due_day=10, trigger_kind="due_day", auto_policy="manual",
        )
        oid = add_obligation(
            conn, int(player["id"]), "Answer the succession offer", due_day=10, importance=5, intention_id=iid,
        )
        run_id = prepare_time_skip(conn, int(player["id"]), 90, max_chunk_days=30)
        result = resolve_time_skip(conn, run_id)
        assert result["status"] == "interrupted"
        assert result["actual_end_day"] == 10
        assert result["interruptions"][0]["source_kind"] in {"obligation","competence"}
        assert conn.execute("SELECT status FROM obligations WHERE id=?", (oid,)).fetchone()[0] == "active"
        conn.commit()

    # A routine competence intention is allowed to resolve during compression instead of forcing a false interruption.
    _fresh()
    with connect() as conn:
        player = _actor(conn, "[DEMO] Player Wanderer")
        set_player(conn, int(player["id"]), "Routine Followthrough")
        iid = add_intention(
            conn, int(player["id"]), "submit the ordinary monthly account",
            intention_kind="follow_through", due_day=5, trigger_kind="due_day", auto_policy="routine",
        )
        add_obligation(conn, int(player["id"]), "Submit the ordinary monthly account", due_day=5, importance=5, intention_id=iid)
        run_id = prepare_time_skip(conn, int(player["id"]), 10, max_chunk_days=10)
        result = resolve_time_skip(conn, run_id)
        assert result["status"] == "completed"
        assert result["actual_end_day"] == 10
        assert conn.execute("SELECT status FROM character_intentions WHERE id=?", (iid,)).fetchone()[0] == "fulfilled"
        conn.commit()

    # A severe direct event discovered inside a large preview chunk rolls back and resumes exactly to the event day.
    _fresh()
    with connect() as conn:
        player = _actor(conn, "[DEMO] Player Wanderer")
        set_player(conn, int(player["id"]), "Event Interrupt")
        conn.execute(
            """INSERT INTO clocks(title,due_day,owner_actor_id,severity,resolution_type,payload_json,status,created_day)
               VALUES ('Major personal summons',7,?,5,'summons','{"summary":"A major summons reaches you and requires a personal decision."}','pending',0)""",
            (player["id"],),
        )
        run_id = prepare_time_skip(conn, int(player["id"]), 40, max_chunk_days=30)
        result = resolve_time_skip(conn, run_id)
        assert result["status"] == "interrupted"
        assert result["actual_end_day"] == 7
        assert result["interruptions"][0]["source_kind"] == "event"
        assert conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0] == 7
        conn.commit()

    print("v12_test: PASS")


if __name__ == "__main__":
    run()
