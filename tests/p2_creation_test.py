"""P2: an accepted draft keeps what was shown even when accept adds to it; people the player names are made with the
stated relationship and put to work where said; savings are real dollars or the stated sum; a full name a stranger already
carries gets a middle initial instead of a refusal."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"},
                          "siblings": [{"sex": "male", "age": 21}, {"sex": "male", "age": 18}]},
               "family_business": {"name": "Basile & Sons Auto Repair", "type": "garage", "owner": "father", "works": ["self", "siblings"]}}
PEOPLE = [{"name": "Frank Amato", "relation": "best friend", "since": "since boyhood", "age": 24},
          {"name": "Gennaro Pace", "relation": "older mechanic at the garage", "work": "mechanic", "works": True},
          {"relation": "older mechanic at the garage", "work": "mechanic", "works": True}]
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"c{_n[0]:03d}"


def family(out) -> dict:
    return {x["field"]: x["value"] for x in out["as_stated"] + out["filled"]
            if x["field"] in ("father", "mother") or x["field"].startswith("sibling")}


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine import money_records
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("creation", package="saintjude")

        draft = server.author(cid(), "protagonist", {**PROTAGONIST, "accept": False})
        assert draft["status"] == "draft", draft
        added = server.author(cid(), "protagonist", {**PROTAGONIST, "people": PEOPLE, "accept": False})
        assert added["status"] == "draft", added
        assert family(added) == family(draft), (family(draft), family(added))
        shown = [x["value"] for x in added["as_stated"] if x["field"] == "person"]
        assert len(shown) == 3 and shown[0].startswith("Frank Amato, best friend, 24"), shown

        made = server.author(cid(), "protagonist", {**PROTAGONIST, "people": PEOPLE, "accept": True,
                                                    "concept": "a garage man's eldest son"})
        assert made["status"] == "created", made
        assert family(made) == family(draft), (family(draft), family(made))
        assert [x["value"] for x in made["as_stated"] if x["field"] == "person"] == shown, made["as_stated"]
        me = made["actor_id"]
        with connect() as conn:
            def one(sql, *args):
                return conn.execute(sql, args).fetchone()

            day = one("SELECT current_day FROM world_state WHERE id=1")[0]
            frank = one("SELECT id FROM actors WHERE name='Frank Amato'")[0]
            for a, b in ((me, frank), (frank, me)):
                r = one("SELECT familiarity,affection,trust,started_day FROM relationships WHERE actor_a_id=? AND actor_b_id=?", a, b)
                assert r and r[0] >= 80 and r[1] >= 55 and r[2] >= 55, (a, b, tuple(r) if r else r)
                assert r[3] <= day - 13 * 365, ("since boyhood", r[3], day)
            shop = one("SELECT id FROM civilian_enterprises WHERE name='Basile & Sons Auto Repair'")[0]
            hands = [shown[1].split(",")[0], shown[2].split(",")[0]]
            for name in hands:
                r = one("""SELECT a.id,p.birth_day FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                           JOIN enterprise_staff s ON s.actor_id=a.id AND s.enterprise_id=? AND s.status='active' WHERE a.name=?""", shop, name)
                assert r, (name, "not on the garage's staff")
                assert (day - r[1]) // 365 >= 38, (name, "an older man", (day - r[1]) // 365)
            cash = money_records.cash(conn, f"person:{me}")
            assert 100 <= cash <= 5000, cash
        got = server.lookup("Frank Amato")
        assert got["standing"]["knows"] == "knows you", got
        assert any("best friend" in k["text"] and "since boyhood" in k["text"] for k in got["known"]), got

        # authoring: a name a stranger carries is set apart; a man he knows is not made twice
        first = server.author(cid(), "person", {"name": "Rocco Vitale", "sex": "male", "age": 26, "place": "South Hill", "from_elsewhere": True})
        assert first["status"] == "created" and first["name"].startswith("Rocco "), first
        again = server.author(cid(), "person", {"name": "Rocco Vitale", "sex": "male", "age": 26, "place": "South Hill", "from_elsewhere": True})
        assert again["status"] == "refused" and str(first["actor_id"]) in again["reason"], again
        again = server.author(cid(), "person", {"name": "Frank Amato", "sex": "male", "age": 40, "place": "South Hill", "from_elsewhere": True})
        assert again["status"] == "refused" and str(frank) in again["reason"], again
        with connect() as conn:
            stranger = conn.execute("""SELECT a.id,a.name FROM actors a WHERE a.actor_type='character' AND a.status='active' AND a.name LIKE '% %'
                AND a.name NOT LIKE '%.%' AND a.id NOT IN (SELECT actor_a_id FROM relationships WHERE actor_b_id=?)
                AND a.id NOT IN (SELECT actor_b_id FROM relationships WHERE actor_a_id=?)
                AND a.id NOT IN (SELECT entity_id FROM authored_entities WHERE entity_table='actors')
                AND a.id NOT IN (SELECT entity_id FROM source_identity_map) ORDER BY a.id LIMIT 1""", (me, me)).fetchone()
        if stranger is None:  # the fixture holds no such person: make one outside the connector
            with connect() as conn:
                conn.execute("INSERT INTO actors(name,actor_type) VALUES ('Aldo Ferrante','character')")
                conn.commit()
                stranger = conn.execute("SELECT id,name FROM actors WHERE name='Aldo Ferrante'").fetchone()
        twin = server.author(cid(), "person", {"name": stranger["name"], "sex": None, "age": 30, "place": "South Hill", "from_elsewhere": True})
        assert twin["status"] == "created" and twin["name"] != stranger["name"] and twin["name"].split()[0] == stranger["name"].split()[0], twin
        assert str(stranger["id"]) in twin["named"], twin

        # a stated sum is what he has; a taken full name is set apart, not refused
        campaign.open_campaign("creation2", package="saintjude")
        with connect() as conn:
            conn.execute("INSERT INTO actors(name,actor_type) VALUES ('Dominic Basile','character')")
            conn.commit()
        out = server.author(cid(), "protagonist", {**PROTAGONIST, "holdings": [{"kind": "savings", "amount": 500}], "accept": True})
        assert out["status"] == "created", out
        with connect() as conn:
            name = conn.execute("SELECT name FROM actors WHERE id=?", (out["actor_id"],)).fetchone()[0]
            assert name != "Dominic Basile" and name.startswith("Dominic ") and name.endswith(" Basile"), name
            assert money_records.cash(conn, f"person:{out['actor_id']}") == 500, money_records.cash(conn, f"person:{out['actor_id']}")
    print("PASS p2_creation_test")


if __name__ == "__main__":
    main()
