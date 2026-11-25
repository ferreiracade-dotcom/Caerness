"""P2.23: a night out is an outing settled the same evening: real people of the place are there and can be spoken to, women can be
approached and may dance, turn him down, give a number or leave with him, trouble comes up, and the same happens to everyone
else (flings and scuffles). The engine proposes and never moves for him.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"o{_n[0]:04d}"


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine import company, life_matters as lm
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("outing", package="saintjude")
        made = server.author(cid(), "protagonist", {
            "name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic",
            "people": [{"name": "Frank Moretti", "relation": "best friend", "since": "since boyhood", "age": 24}], "accept": True})
        assert made["status"] == "created", made
        me = made["actor_id"]

        outcomes, kinds, venues = set(), set(), set()
        pending = None
        for night in range(40):
            out = server.act(cid(), "outing", "I go out for a few drinks")
            assert out["status"] == "applied", out
            venues.add(out["venue"])
            there = out["there"]
            assert len(there) >= 3 and all(p["age"] >= 18 for p in there), there
            with connect() as conn:
                assert all(company.is_with(conn, me, p["id"]) for p in there)
                known = set(lm.contacts(conn, me)) & {p["id"] for p in there}  # anyone he knows is run into, close or not
                met = {h["id"] for h in out.get("happenings", []) if h["kind"] in ("familiar", "chance")}
                assert known <= met, (known, out["happenings"])
            for h in out.get("happenings", []):
                kinds.add(h["kind"])
            if night == 0:
                spoke = server.act(cid(), "speak", "How is your evening going?", target_actor_id=there[0]["id"])
                assert spoke["status"] != "refused", spoke
            women = [h for h in out.get("happenings", []) if h["kind"] == "woman"]
            if women:
                who = women[0]["id"]
                for move in ("dance", "leave together" if night % 2 else "ask for her number"):
                    got = server.act(cid(), "outing", f"I {move}", target_actor_id=who, details={"move": move})
                    assert got["status"] == "applied", got
                    outcomes.add(got["outcome"])
                    if got.get("follow_up"):
                        pending = who
            with connect() as conn:  # the next evening
                conn.execute("UPDATE world_state SET current_day=current_day+1")
                conn.commit()
        print("venues", venues, "\nkinds", kinds, "\noutcomes", outcomes)
        assert {"woman", "trouble", "familiar"} <= kinds, kinds
        assert "turned_down" in outcomes and outcomes & {"number", "night"} and outcomes & {"danced", "night"}, outcomes
        assert pending is not None

        with connect() as conn:  # a street with no bar of its own still goes out to the ones around it
            import random

            from engine import outings
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            here = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
            assert not [v for v in outings.venues(conn) if v["location_id"] == here], "pick a home place without a venue"
            assert outings._where(lm._Pass(conn, day), me, random.Random(1)) is not None
            assert not conn.execute("SELECT 1 FROM household_unions WHERE actor_a_id=? OR actor_b_id=?", (me, me)).fetchone()
            assert conn.execute("""SELECT 1 FROM life_matters WHERE kind='fling' AND status='open' AND awaiting=1
                                   AND (subject_actor_id=? OR other_actor_id=?)""", (me, me)).fetchone()
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            for week in range(day + 7, day + 7 * 27, 7):
                conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (week,))
                lm.weekly(conn, week)
            conn.commit()
            stages = {(r[0], r[1]) for r in conn.execute("""SELECT m.kind,s.stage FROM life_matter_steps s
                      JOIN life_matters m ON m.id=s.matter_id WHERE m.kind IN ('fling','scuffle')""")}
            print(sorted(stages))
            assert ("fling", "faded") in stages and ("fling", "night") in stages, stages
            assert ("scuffle", "words") in stages and ("scuffle", "fight") in stages, stages
            # what he left unanswered faded
            assert not conn.execute("""SELECT 1 FROM life_matters WHERE kind='fling' AND status='open' AND awaiting=1 AND opened_day<?
                                       AND (subject_actor_id=? OR other_actor_id=?)""", (day - 60, me, me)).fetchone()
        with connect() as conn:  # a challenge he walks past can still land: the other man's move is not his
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            conn.execute("UPDATE life_matters SET status='closed' WHERE status='open' AND kind='scuffle'")
            for seed in range(40):
                outings._open_scuffle(lm._Pass(conn, day), me, random.Random(seed))
                if conn.execute("SELECT 1 FROM life_matters WHERE kind='scuffle' AND status='open' AND awaiting=1 AND other_actor_id=?", (me,)).fetchone():
                    break
            row = conn.execute("SELECT id FROM life_matters WHERE kind='scuffle' AND status='open' AND awaiting=1 AND other_actor_id=?", (me,)).fetchone()
            assert row, "a man squares up to him and waits"
            real = lm._Pass.f
            lm._Pass.f = lambda p, key: 10.0 if key == "lm_scuffle_fight" else real(p, key)
            try:
                conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (day + 7,))
                lm.weekly(conn, day + 7)
            finally:
                lm._Pass.f = real
            got = conn.execute("SELECT stage,status FROM life_matters WHERE id=?", (row[0],)).fetchone()
            assert got["status"] == "closed" and got["stage"] == "fight", tuple(got)
            hurt = conn.execute("SELECT actor_id FROM harm_incidents WHERE source_kind='life_matter' AND source_ref_id=?", (row[0],)).fetchone()
            assert hurt, "someone was hurt"
            assert conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (me,)).fetchone()[0] == "living"

        with connect() as conn:  # a boy is not drawn into a night of this kind
            conn.execute("UPDATE actor_life_profiles SET birth_day=(SELECT current_day FROM world_state WHERE id=1)-16*365 WHERE actor_id=?", (me,))
            conn.commit()
        young = server.act(cid(), "outing", "I go out for a few drinks")
        assert young["status"] == "refused", young
    print("PASS p2_outings_test")


if __name__ == "__main__":
    main()
