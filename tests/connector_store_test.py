from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.canon import DEFAULT_CANON, index_canon
from engine.db import connect, init_db, reset_db
from engine.simulation import seed_demo


def _conn():
    conn = connect()
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def run():
    from connector.store import add_note, ensure_connector_schema, notes_for, recent_operations, run_once

    reset_db()
    init_db()
    index_canon(DEFAULT_CANON)
    seed_demo()
    with _conn() as conn:
        ensure_connector_schema(conn)
        ensure_connector_schema(conn)  # idempotent

        counter = {"n": 0}

        def fn():
            counter["n"] += 1
            return {"summary": f"did {counter['n']}", "x": "é"}

        r1 = run_once(conn, "c1", "act", {"a": 1}, fn)
        r2 = run_once(conn, "c1", "act", {"a": 1}, fn)
        assert counter["n"] == 1 and r2.get("replayed") is True and "replayed" not in r1
        assert r2["summary"] == "did 1" and r2["x"] == "é"
        for tool, req in (("act", {"a": 2}), ("advance", {"a": 1})):
            try:
                run_once(conn, "c1", tool, req, fn)
            except ValueError as e:
                assert "call_id reused" in str(e)
            else:
                raise AssertionError("reuse with different arguments was accepted")
        assert counter["n"] == 1

        def boom():
            raise RuntimeError("boom")

        try:
            run_once(conn, "c2", "act", {}, boom)
        except RuntimeError:
            pass
        assert conn.execute("SELECT COUNT(*) FROM connector_calls WHERE call_id='c2'").fetchone()[0] == 0
        assert run_once(conn, "c2", "act", {}, fn)["summary"] == "did 2"
        ops = recent_operations(conn, 3)
        assert [o["call_id"] for o in ops] == ["c2", "c1"] and ops[0]["summary"] == "did 2"

        actor = conn.execute("SELECT id FROM actors ORDER BY id LIMIT 1").fetchone()[0]
        n = add_note(conn, "actor", actor, "  keeps bees  ", "n1")
        conn.commit()
        assert n["subject_kind"] == "actor" and n["note_id"]
        assert notes_for(conn, "actor", actor) == ["keeps bees"]
        add_note(conn, "general", None, "weather is dry", "n2")
        for args in (("actor", 99999999, "x"), ("location", 99999999, "x"), ("actor", actor, "y" * 501),
                     ("actor", actor, "   "), ("bogus", None, "x")):
            try:
                add_note(conn, args[0], args[1], args[2], "nx")
            except ValueError:
                pass
            else:
                raise AssertionError(f"accepted {args[0]}/{args[1]}")

        conn.commit()
        # Concurrency: another connection holds the write lock for 1 s; run_once must wait, not fail.
        import sqlite3
        from engine.db import database_path
        other = sqlite3.connect(database_path(), check_same_thread=False)
        other.execute("BEGIN IMMEDIATE")
        released = threading.Event()

        def hold():
            time.sleep(1.0)
            other.rollback()
            released.set()

        t = threading.Thread(target=hold)
        t.start()
        t0 = time.time()
        res = run_once(conn, "c3", "note", {"k": 1}, lambda: {"summary": "waited"})
        assert res["summary"] == "waited" and time.time() - t0 >= 0.8 and released.is_set()
        t.join()
        other.close()
    print("connector_store_test passed")


if __name__ == "__main__":
    run()
