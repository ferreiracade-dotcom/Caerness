"""P2: travel arrives where it was aimed; those with the protagonist, those shown in the scene, their household at home and the
people of their workplace are there; a stranger far off is not; a thin place takes a business; a place refusal lists places."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}}, "accept": True}
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"p{_n[0]:03d}"


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine.actions import nearest_on
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("places", package="saintjude")
        me = server.author(cid(), "protagonist", PROTAGONIST)["actor_id"]

        def one(sql, *args):
            with connect() as conn:
                row = conn.execute(sql, args).fetchone()
                return row[0] if row else None

        def place(name):
            return one("SELECT id FROM locations WHERE name=?", name)

        def at(actor):
            return one("SELECT current_location_id FROM actors WHERE id=?", actor)

        def person(name, where):
            got = server.author(cid(), "person", {"name": name, "sex": "male", "age": 30, "place": where, "from_elsewhere": True})
            assert got.get("status") == "created", got
            return got["actor_id"]

        def speak(target):
            return server.act(cid(), "speak", "A word.", target_actor_id=target)

        def go(**kw):
            got = server.act(cid(), "travel", "Head over.", **kw)
            assert got["status"] == "applied", (kw, got)
            return got

        home = at(me)
        with connect() as conn:
            walked = conn.execute("SELECT id,name,kind FROM locations WHERE kind<>'region'").fetchall()
            moved = [(r["name"], nearest_on(conn, home, r["id"])) for r in walked if nearest_on(conn, home, r["id"]) is not None]
        assert not moved, moved
        for name in ("Greenwood", "Killbuck Flats", "Eastside Auto Crush", "Oakridge"):
            go(target_location_id=place(name))
            assert at(me) == place(name), (name, at(me))
        go(target_location_id=home)

        # a stranger across town is not here
        far = person("Hollis Vance", "Point Pleasant")
        got = speak(far)
        assert got["status"] != "applied", got
        got = server.act(cid(), "demand", "Ask for the money.", target_actor_id=far, details={"what": "payment", "amount": "$5"})
        assert got["status"] == "refused" and "not here" in got["summary"], got

        # whoever the scene shows can be spoken to
        shown = [p["id"] for p in server.scene()["present"]]
        assert shown
        for who in shown:
            got = speak(who)
            assert got["status"] == "applied", (who, got)
            got = server.act(cid(), "demand", "Ask.", target_actor_id=who, details={"what": "payment", "amount": "$1"})
            assert "not here" not in got["summary"], (who, got)

        # household at home
        brother = person("Nico Basile", "South Hill")
        with connect() as conn:
            conn.execute("UPDATE household_members SET status='left' WHERE actor_id=?", (brother,))
            conn.execute("""INSERT INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status)
                            SELECT household_id,?,'member',0,0,0,'active' FROM household_members
                            WHERE actor_id=? AND status='active' LIMIT 1""", (brother, me))
            conn.execute("DELETE FROM actor_presence_habits WHERE actor_id=?", (brother,))
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (place("Greenwood"), brother))
        assert brother in [p["id"] for p in server.scene()["present"]]
        assert speak(brother)["status"] == "applied"

        # travel to a person arrives with them, even where their presence would be a long shot
        go(target_actor_id=far)
        assert at(me) == place("Point Pleasant")
        assert speak(far)["status"] == "applied"
        assert far in [p["id"] for p in server.scene()["present"]]

        # a companion stays with him wherever he goes
        pal = person("Wendell Pryor", "Point Pleasant")
        go(target_actor_id=pal)
        go(target_location_id=place("Greenwood"), details={"with": [pal]})
        assert at(pal) == place("Greenwood")
        assert speak(pal)["status"] == "applied"
        assert pal in [p["id"] for p in server.scene()["present"]]
        go(target_location_id=home)
        assert speak(pal)["status"] != "applied", "left behind, he is not at the protagonist's home"
        # someone who is not with him cannot be taken along
        got = server.act(cid(), "travel", "Take him.", target_location_id=place("Greenwood"), details={"with": [far]})
        assert got["status"] == "refused", got

        # a business in a thin place, owned by someone from the surrounding settlement; travel to it meets him there
        owner = person("Bruno Pagnotta", "South Hill")
        shop = server.author(cid(), "business", {"name": "Pagnotta Machine", "trade": "machine shop", "place": "Point Pleasant",
                                                 "owner_actor_id": owner})
        assert shop["status"] == "created", shop
        go(details={"business": "Pagnotta Machine"})
        assert at(me) == place("Point Pleasant")
        assert speak(owner)["status"] == "applied", "the owner is at his shop"

        # a place refusal names places that would be accepted
        got = server.author(cid(), "business", {"name": "Nowhere Garage", "trade": "garage", "place": "Nowhereville", "owner_actor_id": owner})
        assert got["status"] == "refused" and got["accepted_places"], got
        assert all(place(n) for n in got["accepted_places"]), got
        got = server.author(cid(), "business", {"name": "Second Shop", "trade": "garage", "place": got["accepted_places"][0],
                                                "owner_actor_id": owner})
        assert got["status"] == "created", got
    print("PASS p2_places_test")


if __name__ == "__main__":
    main()
