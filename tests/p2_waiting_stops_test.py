"""A matter that turns to the protagonist stops an ordinary skip the week it reaches him, while it is still open."""
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
        from engine import hearsay, life_matters as lm, org_lifecycle
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("waits", package="saintjude")
        made = server.author("a1", "protagonist", {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill",
                                                   "work": "mechanic", "accept": True,
                                                   "people": [{"name": "Rosa Greco", "relation": "friend", "age": 23, "sex": "female"}]})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            rosa = conn.execute("SELECT id FROM actors WHERE name='Rosa Greco'").fetchone()[0]

        def takes_a_liking(conn, d):  # in the first week of the skip; the check against the table survives the preview rollback
            if d <= day + 9 and not conn.execute("SELECT 1 FROM life_matters WHERE subject_actor_id=? AND opened_day>?", (rosa, day)).fetchone():
                p = lm._Pass(conn, d)
                lm._wait(p, lm._open(p, "romance", rosa, me, random.Random(1)), "interest_in_him")
                hearsay.reach(conn, me, d)

        org_lifecycle.on_week(takes_a_liking)
        got = server.advance("s1", 30, "work at the garage", from_day=day)  # no interrupt asked: the ordinary skip
        assert got["interrupted"] and got["elapsed_days"] <= 9, got
        assert "Rosa Greco" in got["interruption"], got
        assert any(i["about"] == "romance" and i.get("open") == "waits on your answer" for i in got["material"]), got
        with connect() as conn:
            m = conn.execute("SELECT status,awaiting FROM life_matters WHERE subject_actor_id=? AND kind='romance'", (rosa,)).fetchone()
            assert tuple(m) == ("open", 1), tuple(m)
        # once he has heard it, it does not stop the next skip a second time
        again = server.advance("s2", 5, "work at the garage", from_day=got["day_ended"])
        assert not (again["interrupted"] and "Rosa Greco" in again.get("interruption", "")), again
    print("PASS p2_waiting_stops_test")


if __name__ == "__main__":
    main()
