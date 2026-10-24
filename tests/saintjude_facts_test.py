"""Saint Jude facts store: Fixed/Open/Example rows, an Open office held once, and a Fixed fact changed only with a cause."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
        db = tmp / "sj.db"
        from build_opening import build_opening
        build_opening(db, package="saintjude")
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from connector import store, views
        from connector.authoring import author
        from connector.campaign import connect_campaign
        from engine import facts
        from engine.player import set_player
        from engine.simulation import advance_connection

        conn = connect_campaign()
        store.ensure_connector_schema(conn)
        assert facts.exists(conn)
        tags = {r[0]: r[1] for r in conn.execute("SELECT tag,COUNT(*) FROM world_facts GROUP BY tag")}
        assert tags.get("Fixed", 0) > 10 and tags.get("Open", 0) >= 10 and tags.get("Example", 0) >= 40, tags
        slot = facts.resolve(conn, "Killbuck County Prosecutor", open_only=True)
        assert slot is not None and slot["tag"] == "Open" and slot["holder_actor_id"] is None
        assert facts.holder_of(conn, slot["key"]) is None
        # claims carry the tag from the bible, and an Example person is marked as one
        assert conn.execute("SELECT tag FROM world_facts WHERE key='claim:founding-1640s'").fetchone()[0] == "Fixed"

        # an Open office unfilled: lookup says so
        got = views.lookup(conn, "Killbuck County Prosecutor")
        assert got["found"] is False and got.get("open") and "not yet decided" in got["fact"], got

        me = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0]
        set_player(conn, int(me))
        conn.commit()
        ex = conn.execute("SELECT name FROM actors WHERE id=?", (me,)).fetchone()[0]
        assert views.lookup(conn, ex).get("tag") == "Example"

        out = author(conn, "a1", "person", {"work": "prosecutor", "age": 52, "sex": "male", "holds": "Killbuck County Prosecutor"})
        assert out.get("status") == "created" and out.get("holds") == "Killbuck County Prosecutor", out
        aid = out["actor_id"]
        assert facts.holder_of(conn, slot["key"])["actor_id"] == aid
        got = views.lookup(conn, "County Prosecutor")
        assert got.get("found") and got["id"] == aid and got.get("office") == ["Killbuck County Prosecutor"], got

        advance_connection(conn, 30)
        conn.commit()
        got = views.lookup(conn, "the Killbuck County Prosecutor")
        assert got.get("found") and got["id"] == aid, got
        assert views.lookup(conn, "prosecutor").get("found") in (True, False)

        dup = author(conn, "a2", "person", {"work": "prosecutor", "age": 45, "sex": "male", "holds": "County Prosecutor"})
        assert dup.get("status") == "refused" and "held by" in dup["reason"] and out["name"] in dup["reason"], dup
        assert conn.execute("SELECT COUNT(*) FROM authored_entities WHERE call_id='a2'").fetchone()[0] == 0
        bad = author(conn, "a3", "person", {"age": 40, "sex": "male", "holds": "Grand Vizier"})
        assert bad.get("status") == "refused" and bad["reason_kind"] == "input_gap", bad

        red = author(conn, "a4", "business", {"name": "Red Bank Diner", "trade": "a diner in Red Bank", "amount": 100})
        assert red.get("status") == "refused" and red["reason_kind"] == "contradiction", red

        # a Fixed fact is changed only with a stated cause
        def note(cid, **kw):
            try:
                return store.run_once(conn, cid, "note", {"cid": cid, **kw},
                                      lambda: store.record(conn, "fact", kw["text"], cid, field=kw["field"], cause=kw.get("cause")))
            except ValueError as e:
                return {"refused": str(e)}
        r = note("n1", text="The cathedral was built 1900 to 1910.", field="claim:cathedral-1868-1884")
        assert "refused" in r and "cause" in r["refused"], r
        r = note("n2", text="The cathedral was rebuilt after the fire.", field="claim:cathedral-1868-1884", cause="a fire gutted it in 1969 and the nave was rebuilt")
        assert r.get("overridden") and r.get("cause"), r
        assert conn.execute("SELECT COUNT(*) FROM world_fact_overrides").fetchone()[0] == 1
        r = note("n3", text="Fog all week.", field=conn.execute("SELECT key FROM world_facts WHERE tag='Weather' LIMIT 1").fetchone()[0])
        assert r.get("overridden"), r
        conn.close()
    print("saintjude_facts_test passed")


if __name__ == "__main__":
    run()
