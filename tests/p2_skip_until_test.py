"""P2.20: "skip until something happens" stops on the day something worth playing reaches the protagonist, and every
piece of news names who it happened to and who brought it, all of them real people tied to him."""
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
        from engine import texture
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("skip", package="saintjude")
        made = server.author("a1", "protagonist", {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill",
                                                   "work": "mechanic", "accept": True, "people": [
                                                       {"name": "Frank Moretti", "relation": "best friend", "age": 24, "since": "since they were nine"},
                                                       {"name": "Sal Greco", "relation": "friend", "age": 26}]})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])

        stopped, told, heard = 0, 0, []
        for n in range(12):  # under a year; whether the few near him do anything in a given month is a draw
            if n >= 6 and stopped >= 2 and told >= 2:
                break
            got = server.advance(f"s{n}", 30, "work at the garage and see people", interrupt="something", from_day=day)
            assert "error" not in got and got["elapsed_days"] >= 1, got
            day = got["day_ended"]
            with connect() as conn:
                close = texture.circle(conn, me)
                for item in got.get("material", []):
                    heard.append(item)
                    for p in item["people"]:
                        assert conn.execute("SELECT 1 FROM actors WHERE id=? AND name=?", (p["id"], p["name"])).fetchone(), item
                    if item["involves_you"]:
                        continue
                    told += 1
                    carrier = item["told_by"]
                    assert carrier["id"] in close and carrier["relation"], (carrier, item)
                    alive = conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (carrier["id"],)).fetchone()
                    assert alive and alive[0] in ("living", "dead"), item
            if got["interrupted"]:
                stopped += 1
                assert got["interruption"] and (got.get("remaining_days", 0) > 0 or got["elapsed_days"] == 30), got
            else:
                assert got["quiet"], got
        print(f"{stopped} stops, {len(heard)} pieces of news, {told} brought by someone")
        for item in heard[:12]:
            print(" ", item["date"], "|", item["what"], "|", (item.get("told_by") or {}).get("name"), (item.get("told_by") or {}).get("relation"))
        assert stopped >= 2, "skip-until stops when something happens"
        assert told >= 2, "other people's lives reach him through people who know him"
    print("PASS p2_skip_until_test")


if __name__ == "__main__":
    main()
