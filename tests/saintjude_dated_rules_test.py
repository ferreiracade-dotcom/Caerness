"""Saint Jude dated rules and real-name vetoes: a timeline item not yet in existence, a real person and a real town that
does not exist in this world are refused with the rule and its date; Caerness and ordinary acts are untouched."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "sj.db"
        os.environ["CAERNESS_DB_PATH"] = str(db)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from tools.build_opening import build_opening
        build_opening(db, package="saintjude")
        from connector import store
        from connector.acting import act
        from connector.authoring import author
        from engine import veto
        from engine.db import connect
        from engine.player import set_player
        from engine.world_package import load_package, not_yet_mentions, timeline_mentions, timeline_status

        pkg = load_package("saintjude")
        start = date.fromisoformat(pkg.calendar["start"])

        # helpers
        text = "ask the judge to hold him without bail"
        found = [e["name"] for e, _ in timeline_mentions(pkg, text)]
        assert "federal preventive detention" in found, found
        assert timeline_status(pkg, "federal preventive detention", "1979-06-01") == "not_yet"
        assert timeline_status(pkg, "federal preventive detention", "1985-06-01") == "available"
        assert [e["name"] for e, _ in not_yet_mentions(pkg, text, "1979-06-01")] == ["federal preventive detention"]
        assert not not_yet_mentions(pkg, text, "1985-06-01")
        assert not timeline_mentions(pkg, "he will crack the safe and pay by CD"), "common words must not match"

        with connect() as conn:
            store.ensure_connector_schema(conn)
            row = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()
            set_player(conn, int(row["id"]))
            sab = conn.execute("SELECT id FROM actors WHERE name LIKE '%Sabatini%' AND actor_type='character' ORDER BY id LIMIT 1").fetchone()
            conn.commit()

            def at(y, m, d):
                conn.execute("UPDATE world_state SET current_day=? WHERE id=1", ((date(y, m, d) - start).days,))

            req = "Ask a federal judge to hold Sabatini without bail as dangerous"
            at(1979, 6, 1)
            r = act(conn, "d1", "observe", req)
            assert r["status"] == "refused" and r["reason_kind"] == "contradiction", r
            assert "12 October 1984" in r["summary"] and "does not exist yet" in r["summary"], r["summary"]
            with_det = act(conn, "d1b", "observe", "Think it over", details={"subject": "Bail Reform Act of 1984"})
            assert with_det["status"] == "refused" and "1984" in with_det["summary"], with_det

            at(1985, 6, 1)
            r = act(conn, "d2", "observe", req)
            assert "does not exist yet" not in str(r.get("summary")), r

            at(1979, 6, 1)
            r = act(conn, "o1", "observe", "Buy a coffee at the counter")
            assert r["status"] != "refused", r

            # a real town that does not exist here
            r = act(conn, "t1", "observe", "Meet him at a diner in Red Bank")
            assert r["status"] == "refused" and "Red Bank does not exist" in r["summary"] and "neighbourhood" in r["summary"], r
            assert "Saint Jude" in r["summary"] or "the city stands" in r["summary"], r["summary"]
            r = act(conn, "t2", "observe", "Take the ferry to Point Pleasant")
            assert r["status"] != "refused", r  # real places outside the footprint exist
            for ok in ("A good deal on a car", "He sells Marlboro cigarettes"):
                veto.check_world_text(conn, ok)
            try:
                veto.check_world_text(conn, "A meeting in Deal, NJ")
                raise AssertionError("Deal, NJ must be refused")
            except veto.Contradiction:
                pass
            # author: setting and real names
            out = author(conn, "a1", "person", {"name": "Brendan Byrne", "work": "clerk", "age": 40})
            assert out["status"] == "refused" and "real person" in out["reason"], out
            out = author(conn, "a2", "business", {"name": "Dock Supply", "trade": "shop", "place": "Red Bank"})
            assert out["status"] == "refused", out
            try:
                veto.check_proposal(conn, {"name": "Carlo Gambino", "age": 40, "place": "x"})
                raise AssertionError("real person must be refused")
            except veto.Contradiction as e:
                assert "real person" in str(e), e
            try:
                veto.check_proposal(conn, {"name": "Tom Reilly", "age": 40, "place": "Red Bank"})
                raise AssertionError("Red Bank must be refused")
            except veto.Contradiction as e:
                assert "Red Bank does not exist" in str(e), e
            try:
                veto.check_proposal(conn, {"name": "Tom Reilly", "age": 40, "place": "x", "notes": "arrested under the Bail Reform Act of 1984"})
                raise AssertionError("dated rule must be refused")
            except veto.Contradiction as e:
                assert "1984" in str(e), e
            conn.rollback()

    # Caerness (no gazetteer, no timeline) is unaffected
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "c.db"
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from tools.build_opening import build_opening
        build_opening(db)
        from engine import veto
        from engine.db import connect
        with connect() as conn:
            veto.check_world_text(conn, "Meet in Red Bank under the Bail Reform Act of 1984")
            veto.canon_figure(conn, "Brendan Byrne")
    print("saintjude_dated_rules_test passed")


if __name__ == "__main__":
    run()
