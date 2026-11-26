"""An ordinary enquiry waits for him without stopping a meaningful skip; what turns on him personally stops it."""
from __future__ import annotations

import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine import hearsay, life_matters as lm
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("enquiries", package="saintjude")
        made = server.author("a1", "protagonist", {
            "name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic", "accept": True,
            "family": {"parents": {"father": "alive", "mother": "alive"}},
            "people": [{"name": "Rosa Greco", "relation": "friend", "age": 23, "sex": "female"}]})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            rosa = conn.execute("SELECT id FROM actors WHERE name='Rosa Greco'").fetchone()[0]
            kin = conn.execute("""SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='child' AND ended_day IS NULL
                                  ORDER BY actor_b_id LIMIT 1""", (me,)).fetchone() or conn.execute(
                "SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND ended_day IS NULL ORDER BY actor_a_id LIMIT 1", (me,)).fetchone()
            kin = int(kin[0])
            big = lm._Pass(conn, day).f("lm_big_money_usd")

        def asks_for_job(d, amount):
            with connect() as conn:
                p = lm._Pass(conn, d)
                m = lm._open(p, "work", me, rosa, random.Random(amount))
                m["amount"], m["data"] = amount, {"trade": "auto repair garage", "job": "the brakes", "enterprise_id": 1}
                lm._wait(p, m, "asked")
                hearsay.reach(conn, me, d)
                return m["id"]

        def found(start, end, every=False):
            with connect() as conn:
                return [x["reason"] for x in hearsay.asks(conn, me, start, end, every=every)]

        asks_for_job(day + 1, 60)
        assert not found(day, day + 5), found(day, day + 5)
        assert any("the brakes" in r for r in found(day, day + 5, every=True))
        asks_for_job(day + 2, int(big) + 1)  # real money is another matter
        assert len(found(day, day + 5)) == 1, found(day, day + 5)
        # a death in the family reaches him and stops the skip, though nothing waits on him
        with connect() as conn:
            p = lm._Pass(conn, day + 3)
            m = lm._open(p, "illness", kin, None, random.Random(3))
            m["data"] = {"label": "pneumonia"}
            lm._step(p, m, "died", close=True)
            hearsay.reach(conn, me, day + 3)
            conn.execute("""INSERT OR IGNORE INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,truth_event_id,learned_day)
                            SELECT ?,'step:' || id || ':test',text,1.0,NULL,? FROM life_matter_steps WHERE matter_id=?
                              AND NOT EXISTS(SELECT 1 FROM knowledge k WHERE k.knower_actor_id=? AND k.fact_key LIKE 'step:' || life_matter_steps.id || ':%')""",
                         (me, day + 3, m["id"], me))
        assert any("has died" in r for r in found(day + 2, day + 3)), found(day + 2, day + 3)
        with connect() as conn:
            # clear what was staged above: the skip starts with nothing in it
            conn.execute("DELETE FROM knowledge WHERE knower_actor_id=? AND fact_key LIKE 'step:%' AND learned_day>?", (me, day))
            conn.execute("DELETE FROM life_matters WHERE opened_day>?", (day,))

        # a thirty day skip with only an ordinary enquiry in it runs its course; the enquiry is still open when he hears of it
        from engine import org_lifecycle
        first = []

        def enquiry(conn, d):
            now = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            if not conn.execute("SELECT 1 FROM life_matters WHERE kind='work' AND subject_actor_id=?", (me,)).fetchone():
                p = lm._Pass(conn, d)
                m = lm._open(p, "work", me, rosa, random.Random(7))
                m["amount"], m["data"] = 60, {"trade": "auto repair garage", "job": "the brakes", "enterprise_id": 1}
                lm._wait(p, m, "asked")
                hearsay.reach(conn, me, d)
                first.append((d, now))

        org_lifecycle.on_week(enquiry)
        with connect() as conn:
            start = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        got = server.advance("s1", 30, "work at the garage", from_day=start)
        with connect() as conn:
            row = conn.execute("SELECT status,awaiting,next_day FROM life_matters WHERE kind='work' AND subject_actor_id=?", (me,)).fetchone()
        assert "brakes" not in str(got.get("interruption", "")), got
        if got["elapsed_days"] == 30:
            assert row["status"] == "open" and row["awaiting"] == 1, dict(row)
            assert row["next_day"] >= got["day_ended"] + 14, (dict(row), got["day_ended"])
            assert any("brakes" in str(w) for w in got["waiting_on_you"]), got
            assert any(i.get("open") == "waits on your answer" and i["about"] == "work" for i in got["material"]), got["material"]
        else:
            raise AssertionError(("something else stopped the skip", got.get("interruption")))
    print("PASS p2_enquiries_accrue_test")


if __name__ == "__main__":
    main()
