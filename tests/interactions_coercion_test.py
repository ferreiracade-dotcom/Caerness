from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "coerce.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine import interactions as it

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            a, b = [int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE status NOT IN ('deceased','dead') ORDER BY id LIMIT 2")]
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])

            def rate(terms: dict, kind: str = "demand", n: int = 200) -> float:
                ok = 0
                for i in range(n):
                    conn.execute("SAVEPOINT r")  # each draw independent of the relationship drift of the others
                    conn.execute(
                        """INSERT INTO interactions(id,created_day,proposer_actor_id,recipient_actor_id,interaction_type,status,
                               urgency,stakes,terms_json,rationale,canon_chunk_ids_json,response_due_day)
                           VALUES (?,?,?,?,?, 'pending',2,2,?,'',?,?)""",
                        (5000000 + i, day, a, b, kind, json.dumps(terms), "[]", day))
                    res = it.resolve_interaction(conn, 5000000 + i, day)
                    ok += res.response in ("comply", "accept")
                    conn.execute("ROLLBACK TO r")
                    conn.execute("RELEASE r")
                return ok / n

            lo, hi = rate({"coercion": 0}), rate({"coercion": 3})
            assert hi - lo >= 0.25, (lo, hi)

            # no key == the old formula: same row resolves identically with and without an explicit zero
            def one(terms):
                cur = conn.execute(
                    """INSERT INTO interactions(id,created_day,proposer_actor_id,recipient_actor_id,interaction_type,status,
                           urgency,stakes,terms_json,rationale,canon_chunk_ids_json,response_due_day)
                       VALUES (9999999,?,?,?,'demand','pending',2,2,?,'','[]',?)""",
                    (day, a, b, json.dumps(terms), day))
                conn.execute("SAVEPOINT s")
                r = it.resolve_interaction(conn, 9999999, day)
                conn.execute("ROLLBACK TO s")
                conn.execute("RELEASE s")
                conn.execute("DELETE FROM interactions WHERE id=9999999")
                return r.response, r.summary
            assert one({}) == one({"coercion": 0}) == one({"incentive": 0.0})

            # coercion never moves other kinds
            r0 = rate({"coercion": 0}, "offer", 50)
            r3 = rate({"coercion": 3}, "offer", 50)
            assert r0 == r3, (r0, r3)
    print("interactions_coercion_test passed")


if __name__ == "__main__":
    run()
