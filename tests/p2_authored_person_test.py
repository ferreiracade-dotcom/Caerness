"""P2: an authored person keeps the work as stated, takes the matching trade and the place the work names, holds nothing,
and speaking to them returns how they feel, what they want and what stands open between them."""
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
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("authored", package="saintjude")
        made = server.author("a1", "protagonist", {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill",
                                                   "work": "mechanic", "accept": True})
        assert made["status"] == "created", made
        me = made["actor_id"]
        paul = server.author("a2", "person", {"name": "Paul Ricci", "sex": "male", "age": 41,
                                              "work": "Owner of a busy restaurant on the east side"})
        assert paul["status"] == "created" and "held_thing_id" not in paul, paul
        assert paul["location"] == "The Eastside" and paul["work"] == "hospitality", paul
        assert "restaurant" in paul["role"], paul
        collector = server.author("a3", "person", {"name": "Tullio Bruni", "sex": "male", "age": 35, "place": "South Hill",
                                                   "work": "Collector and go-between for the Pellegrino social club"})
        assert collector["status"] == "created" and collector["work"] == "criminal", collector
        who = server.lookup("Tullio Bruni")
        assert "go-between" in str(who), who

        with connect() as conn:
            day = conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
            there = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0]
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (there, collector["actor_id"]))
            conn.execute("INSERT INTO goals(actor_id,description,priority,progress,status,created_day) "
                         "VALUES (?,'Get the club its money back',90,0,'active',?)", (collector["actor_id"], day))
            conn.commit()
        said = server.act("s1", "speak", "pass the time of day", target_actor_id=collector["actor_id"])
        assert said["status"] == "applied", said
        about = said["them"]
        assert about["toward_you"] and "Get the club its money back" in about["wants"], said
    print("PASS p2_authored_person_test")


if __name__ == "__main__":
    main()
