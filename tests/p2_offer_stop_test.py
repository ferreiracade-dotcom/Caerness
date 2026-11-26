"""A skip stopped by something put to him says who put it and what it is."""
from __future__ import annotations

import os
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
        from engine import org_lifecycle
        from engine.db import connect
        from engine.interactions import create_interaction

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("offers", package="saintjude")
        made = server.author("a1", "protagonist", {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill",
                                                   "work": "mechanic", "accept": True,
                                                   "people": [{"name": "Sal Moretti", "relation": "friend", "age": 25, "sex": "male"}]})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            sal = conn.execute("SELECT id FROM actors WHERE name='Sal Moretti'").fetchone()[0]

        def puts_it_to_him(conn, d):
            if d <= day + 9 and not conn.execute("SELECT 1 FROM interactions WHERE proposer_actor_id=?", (sal,)).fetchone():
                create_interaction(conn, sal, me, "offer", d, stakes=4, response_due_day=d + 14,
                                   terms={"purpose": "a half share in a tow truck"})

        org_lifecycle.on_week(puts_it_to_him)
        got = server.advance("s1", 30, "work at the garage", from_day=day)
        assert got["interrupted"], got
        why = got["interruption"]
        assert "Sal Moretti" in why and "offer" in why and "a half share in a tow truck" in why, why
        with connect() as conn:
            iid = conn.execute("SELECT id FROM interactions WHERE proposer_actor_id=?", (sal,)).fetchone()[0]
        assert str(iid) in why, why  # the number to answer it by
    print("PASS p2_offer_stop_test")


if __name__ == "__main__":
    main()
