import json

from engine.canon import DEFAULT_CANON, index_canon
from engine.db import connect, init_db, reset_db
from engine.simulation import advance, seed_demo


def run():
    reset_db()
    init_db()
    index_canon(DEFAULT_CANON)
    seed_demo()
    advance(90)
    with connect() as conn:
        decision_count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        assert decision_count > 10, "Reviewed actors should make persisted decisions."

        dormant_decisions = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE tier='DORMANT'"
        ).fetchone()[0]
        assert dormant_decisions > 0, "Dormant actors must still make coarse decisions."

        contexts = conn.execute("SELECT COUNT(*) FROM actor_context_cache").fetchone()[0]
        assert contexts > 0, "Decision reviews should cache inspectable actor context."

        # DEC-01 firewall: World-Bible chunks are no longer injected into NPC personal knowledge.
        assert conn.execute("SELECT COUNT(*) FROM decisions WHERE canon_chunk_ids_json <> '[]'").fetchone()[0] == 0
        contexts_rows = conn.execute("SELECT context_json FROM actor_context_cache").fetchall()
        assert contexts_rows and all(json.loads(r[0]).get('canon') == [] for r in contexts_rows)
        assert conn.execute("SELECT COUNT(*) FROM decision_evaluations").fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM decision_candidate_audit").fetchone()[0] > 0
        generic = conn.execute("SELECT COUNT(*) FROM decisions WHERE action_type IN ('advance_goal','force_goal','address_pressure','work_relationship')").fetchone()[0]
        assert generic == 0, "DEC-01 default runtime must not use abstract generic progress actions."

        remote_id = conn.execute(
            "SELECT id FROM actors WHERE name='[DEMO] Remote Reed Sect'"
        ).fetchone()[0]
        strategic_after_wake = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE actor_id=? AND tier='STRATEGIC' AND day>37",
            (remote_id,),
        ).fetchone()[0]
        assert strategic_after_wake >= 2, "Wake-up promotion must increase actual review frequency."

        interaction_count = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        causal = conn.execute("SELECT COUNT(*) FROM causal_links WHERE source_kind='decision' AND target_kind='interaction'").fetchone()[0]
        assert causal <= interaction_count
        selected = conn.execute("SELECT COUNT(*) FROM decision_candidate_audit WHERE selected=1").fetchone()[0]
        assert selected == conn.execute("SELECT COUNT(*) FROM decision_evaluations").fetchone()[0]

    print("Decision test passed: information-bounded candidates persist, weighted selections audit, and dormant actors continue acting.")


if __name__ == "__main__":
    run()
