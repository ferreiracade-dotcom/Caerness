from engine.canon import DEFAULT_CANON, index_canon
from engine.db import reset_db, init_db, connect
from engine.simulation import seed_demo, advance


def run():
    reset_db()
    init_db()
    index_canon(DEFAULT_CANON)
    seed_demo()
    advance(90)
    with connect() as conn:
        day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
        assert day == 90
        dormant_events = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type LIKE 'background:%'"
        ).fetchone()[0]
        assert dormant_events > 0, "Dormant actors should create background events while off-screen."
        resolved_clock = conn.execute(
            "SELECT COUNT(*) FROM clocks WHERE status='resolved' AND title='[DEMO] Remote sect succession meeting'"
        ).fetchone()[0]
        assert resolved_clock == 1, "Dormant-owned clocks must still resolve."
        dormant_decisions = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE tier='DORMANT'"
        ).fetchone()[0]
        assert dormant_decisions > 0, "Dormant actors should make coarse decisions as well as drift."
    print("Smoke test passed: dormant simulation is not frozen.")


if __name__ == "__main__":
    run()
