"""The people near a new protagonist have something to live with: money on them and, among those who live in one district,
people they know besides him, so that things happen to them and not only between them and him. Done once, and for a save that
already has its protagonist as much as for a new one."""
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
        from engine import life_matters as lm, texture
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("circle", package="saintjude")
        made = server.author("a1", "protagonist", {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill",
                                                   "work": "mechanic", "accept": True, "people": [
                                                       {"name": "Frank Moretti", "relation": "best friend", "age": 24},
                                                       {"name": "Sal Greco", "relation": "friend", "age": 26}]})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            lm.weekly(conn, day + 7)
            close = texture.circle(conn, me)
            grown = [a for a, born in conn.execute(
                f"SELECT actor_id,birth_day FROM actor_life_profiles WHERE life_status='living' AND actor_id IN ({','.join('?' * len(close))})",
                list(close)) if (day - born) / 365 >= 18]
            assert len(grown) >= 5, grown
            for a in grown:
                assert conn.execute("SELECT 1 FROM resources WHERE actor_id=? AND resource_type='cash'", (a,)).fetchone() or \
                    conn.execute("SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?", (a,)).fetchone(), a
            among = [a for a in grown if set(lm.contacts(conn, a)) & (set(close) - {a})]
            assert len(among) >= 0.7 * len(grown), (len(among), len(grown))
            count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            cash = conn.execute("SELECT SUM(amount) FROM resources WHERE resource_type='cash'").fetchone()[0]
            before = dict(texture.circle(conn, me))
            lm.settle_circle(lm._Pass(conn, day + 14))
            if set(texture.circle(conn, me)) == set(before):  # nobody new: nothing added a second time
                assert conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0] == count
                assert conn.execute("SELECT SUM(amount) FROM resources WHERE resource_type='cash'").fetchone()[0] == cash
    print("PASS p2_circle_alive_test")


if __name__ == "__main__":
    main()
