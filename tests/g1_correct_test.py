"""G1: the game master corrects the record on the player's word. Undoing an offscreen marriage restores every row it
changed; a person's work, place, age, sex, ties, household and cash are set; each correction is kept with the player's
words; only real impossibilities are refused."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}}, "accept": True}
WORDS = "No. Dominic never married her. Take it back."
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"g{_n[0]:03d}"


def rows(conn, sql: str, args=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args)]


def state(conn, a: int, b: int) -> dict:
    """Everything a marriage touches, without the bookkeeping columns (row ids of relationships, updated days)."""
    pair = (a, b, a, b)
    homes = [r[0] for r in conn.execute("SELECT DISTINCT household_id FROM household_members WHERE actor_id IN (?,?)", (a, b))]
    marks = ",".join("?" * len(homes)) or "NULL"
    return {
        "unions": rows(conn, "SELECT * FROM household_unions WHERE actor_a_id IN (?,?) OR actor_b_id IN (?,?) ORDER BY id", pair),
        "kin": rows(conn, "SELECT * FROM kinship_links WHERE actor_a_id IN (?,?) OR actor_b_id IN (?,?) ORDER BY id", pair),
        "households": rows(conn, f"SELECT id,name,head_actor_id,location_id,status FROM households WHERE id IN ({marks}) ORDER BY id", homes),
        "members": rows(conn, f"SELECT household_id,actor_id,role,authority,dependency,joined_day,left_day,status FROM household_members "
                              f"WHERE household_id IN ({marks}) OR actor_id IN (?,?) ORDER BY household_id,actor_id", (*homes, a, b)),
        "profiles": rows(conn, "SELECT actor_id,current_household_id FROM actor_life_profiles WHERE actor_id IN (?,?) ORDER BY actor_id", (a, b)),
        "relationships": [r for r in rows(conn, "SELECT actor_a_id,actor_b_id,stance,familiarity,trust,affection,respect,fear,loyalty,"
                                               "resentment,obligation,professional_confidence FROM relationships WHERE "
                                               "(actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?) ORDER BY actor_a_id",
                                         (a, b, b, a)) if any(v for k, v in r.items() if not k.startswith("actor_"))],
    }


def marry(conn, her: int, me: int, day: int) -> dict:
    """What the engine writes when a proposal is accepted offscreen (domain_actions propose_union)."""
    from engine.household_life import create_union
    from engine.interactions import _link, _log_event
    from engine.relationships import record_relationship_effect

    iid = conn.execute("INSERT INTO interactions(created_day,proposer_actor_id,recipient_actor_id,interaction_type,status,response_due_day,"
                       "resolved_day) VALUES (?,?,?,'offer','accepted',?,?)", (day, her, me, day, day)).lastrowid
    uid = create_union(conn, her, me, create_new_household_name="Household of Lucia and Dominic")
    conn.execute("UPDATE household_unions SET metadata_json=? WHERE id=?",
                 (json.dumps({"authority": "ENGINE_DERIVED", "accepted_interaction_id": iid}), uid))
    record_relationship_effect(conn, me, her, day, source_kind="interaction", source_id=iid, summary="married", trust_delta=7.0, affection_delta=9.0)
    record_relationship_effect(conn, her, me, day, source_kind="interaction", source_id=iid, summary="married", trust_delta=5.0)
    ev = _log_event(conn, day, "interaction:offer:accepted", "Union accepted", "Lucia Fernandes and Dominic Basile married.", 3, her, (me,))
    _link(conn, day, "interaction", iid, "event", ev, "produced")
    conn.execute("INSERT OR IGNORE INTO knowledge(knower_actor_id,fact_key,belief_text,truth_event_id,learned_day) VALUES (?,?,?,?,?)",
                 (me, f"event:{ev}", "Lucia Fernandes and Dominic Basile married.", ev, day))
    life = conn.execute("SELECT id FROM life_events WHERE event_kind='union' AND actor_id=? ORDER BY id DESC LIMIT 1", (her,)).fetchone()[0]
    conn.commit()
    return {"interaction": iid, "union": uid, "event": ev, "life_event": life}


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        for name in ("CAERNESS_BACKUP_DIR", "CAERNESS_WORLDS_DIR", "CAERNESS_SHELVED_WORLDS"):
            os.environ.pop(name, None)
        from connector import campaign, server
        from engine import money_records
        from engine.civilian import create_household
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("g1", package="saintjude")
        made = server.author(cid(), "protagonist", PROTAGONIST)
        assert made["status"] == "created", made
        me = made["actor_id"]
        got = server.author(cid(), "person", {"name": "Lucia Ferrandina", "sex": "female", "age": 22, "place": "South Hill", "from_elsewhere": True})
        her = got["actor_id"]

        with connect() as conn:
            # she keeps her own flat, so the marriage dissolves a household and the undo has to bring it back
            conn.execute("UPDATE household_members SET status='former',left_day=0 WHERE actor_id=?", (her,))
            flat = create_household(conn, "Ferrandina flat", head_actor_id=her)
            conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (flat, her))
            married_on = conn.execute("SELECT current_day FROM world_state").fetchone()[0] + 30
            conn.execute("UPDATE world_state SET current_day=?", (married_on,))
            conn.commit()
            before = state(conn, me, her)
            wed = marry(conn, her, me, married_on)
            assert state(conn, me, her) != before
            assert conn.execute("SELECT status FROM households WHERE id=?", (flat,)).fetchone()[0] == "dissolved"
            conn.execute("UPDATE world_state SET current_day=?", (married_on + 5,))
            conn.commit()
            wedded = state(conn, me, her)

        # looking first changes nothing
        look = server.correct(cid(), "preview", details={"actors": ["me", her], "day": married_on})
        assert look["status"] == "preview" and look["would_reverse"], look
        assert any("union" in line for line in look["would_reverse"]), look
        with connect() as conn:
            assert state(conn, me, her) == wedded

        # the player's words are required
        for words in ("", "   "):
            out = server.correct(cid(), "undo_event", words, {"actors": ["me", her], "day": married_on})
            assert "player_said" in out.get("error", ""), out
        with connect() as conn:
            assert state(conn, me, her) == wedded
            assert not conn.execute("SELECT 1 FROM corrections").fetchone()

        call = cid()
        undone = server.correct(call, "undo_event", WORDS, {"actors": ["me", her], "day": married_on})
        assert undone["status"] == "corrected" and undone["reversed"], undone
        with connect() as conn:
            after = state(conn, me, her)
            assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
            assert conn.execute("SELECT status FROM interactions WHERE id=?", (wed["interaction"],)).fetchone()[0] == "cancelled"
            assert conn.execute("SELECT title FROM events WHERE id=?", (wed["event"],)).fetchone()[0].startswith("[never happened]")
            assert not conn.execute("SELECT 1 FROM knowledge WHERE truth_event_id=?", (wed["event"],)).fetchone()
            life = conn.execute("SELECT event_kind,summary,day FROM life_events WHERE id=?", (wed["life_event"],)).fetchone()
            assert life["event_kind"] == "other" and life["summary"].startswith("[never happened]") and life["day"] == married_on, dict(life)
            row = conn.execute("SELECT * FROM corrections").fetchone()
            assert row["player_said"] == WORDS and row["day"] == married_on + 5 and row["op"] == "undo_event", dict(row)
            assert json.loads(row["changes_json"]), dict(row)
        again = server.correct(call, "undo_event", WORDS, {"actors": ["me", her], "day": married_on})
        assert again.get("replayed"), again
        empty = server.correct(cid(), "undo_event", WORDS, {"actors": ["me", her], "day": married_on})
        assert "nothing" in empty.get("error", ""), empty

        back = server.resume()
        shown = back["recent_corrections"]
        assert shown[-1]["player_said"] == WORDS and shown[-1]["day"] == married_on + 5, shown

        # the same undo, found from the life event the game master was shown
        with connect() as conn:
            second = marry(conn, her, me, married_on + 5)
        out = server.correct(cid(), "undo_event", WORDS, {"life_event_id": second["life_event"]})
        assert out["status"] == "corrected", out
        with connect() as conn:
            assert state(conn, me, her) == before

        # ---- setting a person straight
        with connect() as conn:
            places = [r["id"] for r in conn.execute("SELECT id FROM locations ORDER BY id LIMIT 40")]
            shop = conn.execute("SELECT id,name FROM civilian_enterprises WHERE status='active' ORDER BY id LIMIT 1").fetchone()
        here = places[-1]
        said = "Yes, fix all that."
        out = server.correct(cid(), "person", said, {"person": "me", "work": "welder", "business": f"business:{shop['id']}", "role": "welder",
                                                     "location": here, "home": here, "age": 26, "sex": "male"})
        assert out["status"] == "corrected", out
        with connect() as conn:
            day = conn.execute("SELECT current_day FROM world_state").fetchone()[0]
            a = conn.execute("SELECT * FROM actors WHERE id=?", (me,)).fetchone()
            assert a["current_location_id"] == here and a["home_location_id"] == here and a["subtype"] == "welder", dict(a)
            assert conn.execute("SELECT current_location_id FROM player_state").fetchone()[0] == here
            lp = conn.execute("SELECT birth_day,life_stage FROM actor_life_profiles WHERE actor_id=?", (me,)).fetchone()
            assert (day - lp["birth_day"]) // 365 == 26 and lp["life_stage"] == "adult", dict(lp)
            staff = conn.execute("SELECT role,status FROM enterprise_staff WHERE actor_id=? AND enterprise_id=?", (me, shop["id"])).fetchone()
            assert staff["status"] == "active" and staff["role"] == "welder", dict(staff)
            assert conn.execute("SELECT COUNT(*) FROM enterprise_staff WHERE actor_id=? AND status='active'", (me,)).fetchone()[0] == 1
            kept = conn.execute("SELECT changes_json FROM corrections ORDER BY id DESC LIMIT 1").fetchone()[0]
            changes = {c["field"]: c for c in json.loads(kept)}
            assert changes["location"]["new"] == here and changes["location"]["old"] != here, changes

        assert server.correct(cid(), "relationship", said, {"from": "me", "to": her, "values": {"trust": 40, "affection": -10}})["status"] == "corrected"
        assert server.correct(cid(), "cash", said, {"holder": "me", "amount": 2500})["status"] == "corrected"
        assert server.correct(cid(), "kinship", said, {"a": "me", "b": her, "change": "add", "kind": "spouse"})["status"] == "corrected"
        with connect() as conn:
            rel = conn.execute("SELECT trust,affection FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (me, her)).fetchone()
            assert (rel["trust"], rel["affection"]) == (40, -10), dict(rel)
            assert money_records.cash(conn, f"person:{me}") == 2500
            assert conn.execute("SELECT COUNT(*) FROM kinship_links WHERE kin_kind='spouse' AND ended_day IS NULL AND actor_a_id IN (?,?)", (me, her)).fetchone()[0] == 2
            assert conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND actor_a_id IN (?,?)", (me, her)).fetchone()
        assert server.correct(cid(), "kinship", said, {"a": "me", "b": her, "change": "end", "kind": "spouse"})["status"] == "corrected"
        with connect() as conn:
            assert not conn.execute("SELECT 1 FROM kinship_links WHERE kin_kind='spouse' AND ended_day IS NULL AND actor_a_id IN (?,?)", (me, her)).fetchone()
            assert not conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND actor_a_id IN (?,?)", (me, her)).fetchone()

        assert server.correct(cid(), "household", said, {"person": her, "household": f"household:{flat}", "change": "leave"})["status"] == "corrected"
        out = server.correct(cid(), "household", said, {"person": "me", "household": flat, "change": "join"})
        assert out["status"] == "corrected", out
        with connect() as conn:
            active = rows(conn, "SELECT household_id FROM household_members WHERE actor_id=? AND status='active'", (me,))
            assert active == [{"household_id": flat}], active
            assert conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (me,)).fetchone()[0] == flat
            home = conn.execute("SELECT status,head_actor_id FROM households WHERE id=?", (flat,)).fetchone()
            assert home["status"] == "active" and home["head_actor_id"] == me, dict(home)

        # ---- real impossibilities are refused, and nothing is half done
        with connect() as conn:
            from engine.household_life import mark_actor_deceased
            dead = got_dead = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND id NOT IN (?,?) ORDER BY id DESC LIMIT 1", (me, her)).fetchone()[0]
            mark_actor_deceased(conn, got_dead, reason="test")
            death = conn.execute("SELECT id,day FROM life_events WHERE event_kind='death' AND actor_id=?", (dead,)).fetchone()
            old_event = conn.execute("SELECT id,day FROM events ORDER BY id LIMIT 1").fetchone()
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        for op, details in (
                ("undo_event", {"life_event_id": death["id"]}),
                ("undo_event", {"reverse": [{"table": "actors", "id": dead, "action": "set", "values": {"status": "active"}}]}),
                ("undo_event", {"reverse": [{"table": "actor_life_profiles", "where": {"actor_id": dead}, "action": "set", "values": {"life_status": "living"}}]}),
                ("undo_event", {"reverse": [{"table": "events", "id": old_event["id"], "action": "set", "values": {"day": old_event["day"] + 3}}]}),
                ("undo_event", {"reverse": [{"table": "actors", "id": her, "action": "delete"}]}),
                ("undo_event", {"reverse": [{"table": "world_state", "id": 1, "action": "set", "values": {"current_day": 1}}]}),
                ("undo_event", {"reverse": [{"table": "corrections", "id": 1, "action": "delete"}]}),
                # a good row followed by a bad one: neither is applied
                ("undo_event", {"reverse": [{"table": "actors", "id": her, "action": "set", "values": {"notes": "half done"}},
                                            {"table": "no_such_table", "id": 1, "action": "delete"}]}),
                ("person", {"person": her, "age": -4}),
        ):
            out = server.correct(cid(), op, said, details)
            assert out.get("error"), (op, details, out)
        with connect() as conn:
            assert conn.execute("SELECT status FROM actors WHERE id=?", (dead,)).fetchone()[0] == "deceased"
            assert conn.execute("SELECT notes FROM actors WHERE id=?", (her,)).fetchone()[0] != "half done"
            assert conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0] == count

        # rows the game master lists himself are reversed and recorded
        out = server.correct(cid(), "undo_event", said, {"reverse": [{"table": "actors", "id": her, "action": "set", "values": {"notes": "set by hand"}}]})
        assert out["status"] == "corrected", out

        # a Fixed canon fact about the person needs a cause, and is named
        with connect() as conn:
            conn.execute("INSERT INTO world_facts(key,subject,text,tag) VALUES ('claim:ferrandina','The Ferrandina bakery',"
                         "'Lucia Ferrandina has run the bakery on Orchard Street since 1970.','Fixed')")
            conn.commit()
        out = server.correct(cid(), "person", said, {"person": her, "work": "typist"})
        assert "claim:ferrandina" in out.get("error", "") and "cause" in out["error"], out
        out = server.correct(cid(), "person", said, {"person": her, "work": "typist", "cause": "the bakery burned and she took an office job"})
        assert out["status"] == "corrected", out

        with connect() as conn:
            assert conn.execute("SELECT subtype FROM actors WHERE id=?", (her,)).fetchone()[0] == "typist"
    print("PASS g1_correct_test")


if __name__ == "__main__":
    main()
