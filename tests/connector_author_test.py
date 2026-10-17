"""The author tool: idempotent, refusals stored and replayed, provenance recorded, new people really in the scene."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "author.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine.player import set_player
        from connector import store
        from connector.authoring import author
        from connector.views import lookup

        init_db()
        conn = connect()
        conn.execute("PRAGMA busy_timeout=30000")
        store.ensure_connector_schema(conn)
        me = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0])
        set_player(conn, me)
        conn.commit()

        n0 = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        det = {"sex": "female", "age": 36}
        r = author(conn, "au-1", "person", det)
        assert r["status"] == "created" and r["kind"] == "person" and r["name"], r
        again = author(conn, "au-1", "person", det)
        assert again["replayed"] and again["actor_id"] == r["actor_id"]
        assert conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == n0 + 1  # one actor for two calls
        row = conn.execute("SELECT kind,entity_table,entity_id FROM authored_entities WHERE call_id='au-1'").fetchone()
        assert tuple(row) == ("person", "actors", r["actor_id"]), tuple(row)

        # A refusal comes back as data, is stored, and replays; it leaves nothing behind.
        bad = author(conn, "au-2", "person", {"sex": "male", "stage": "Sixth"})
        assert bad["status"] == "refused" and bad["kind"] == "person" and bad["reason"], bad
        assert author(conn, "au-2", "person", {"sex": "male", "stage": "Sixth"})["replayed"]
        assert conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == n0 + 1
        assert conn.execute("SELECT COUNT(*) FROM authored_entities").fetchone()[0] == 1
        try:
            author(conn, "au-2", "person", {"sex": "male"}); raise AssertionError("call_id reuse accepted")
        except ValueError as e:
            assert "reused" in str(e), e

        # Provenance shows in lookup as one key, no numbers.
        out = lookup(conn, r["name"])
        assert out["found"] and out["authored"] is True, out
        plain = lookup(conn, conn.execute("SELECT name FROM actors WHERE id=?", (me,)).fetchone()[0])
        assert "authored" not in plain

        # The other kinds record provenance in their own tables.
        b = author(conn, "au-3", "business", {"name": "Quill & Sons", "trade": "ink", "enterprise_kind": "shop", "owner_actor_id": r["actor_id"]})
        assert b["status"] == "created" and conn.execute("SELECT entity_table FROM authored_entities WHERE call_id='au-3'").fetchone()[0] == "civilian_enterprises"
        assert lookup(conn, "Quill & Sons").get("authored") is True
        m = author(conn, "au-4", "rumour", {"text": "Ink is going short.", "heard_by": [r["actor_id"]]})
        assert m["status"] == "created" and conn.execute("SELECT entity_table FROM authored_entities WHERE call_id='au-4'").fetchone()[0] == "rumours"

        # The new person is a real, present, speak-able actor.
        from connector.acting import act
        s = act(conn, "au-5", "speak", "I greet her.", target_actor_id=r["actor_id"])
        assert s["status"] != "refused" and "not plausibly present" not in s["summary"], s
        from connector.views import compact_scene
        scene = compact_scene(conn)
        assert "error" not in scene
        conn.close()


if __name__ == "__main__":
    run()
    print("connector_author_test: ok")
