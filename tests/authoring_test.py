"""author: invented people, businesses, outfits, bodies and rumours become real only through the engine's own paths."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WORK = ("artisan", "artist", "clerk", "criminal", "hospitality", "labor", "merchant", "physician", "soldier", "teacher", "transport")


def _open(tmp, name, pop=None):
    db = Path(tmp) / name
    shutil.copy2(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    from engine.db import connect, init_db
    from engine.player import set_player
    from connector import store

    init_db()
    conn = connect()
    conn.execute("PRAGMA busy_timeout=30000")
    store.ensure_connector_schema(conn)
    me = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0])
    set_player(conn, me)
    place = int(conn.execute("SELECT current_location_id FROM actors WHERE id=?", (me,)).fetchone()[0])
    if pop is not None:  # a small town, so the caps bite
        conn.execute("UPDATE background_population_sources SET population_estimate=? WHERE location_id=?", (pop, place))
    conn.commit()
    return conn, me, place


def _count(conn, sql, *a):
    return int(conn.execute(sql, a).fetchone()[0])


def _refused(fn, needle):
    from engine.authoring import AuthoringRefused
    try:
        fn()
    except AuthoringRefused as e:
        assert needle.lower() in str(e).lower(), (needle, str(e))
        return str(e)
    raise AssertionError(f"not refused (wanted {needle!r})")


def _pop(conn):
    return _count(conn, "SELECT SUM(population_estimate) FROM background_population_sources")


def run():
    from engine.authoring import author
    from engine.person_ecology import FIRST_FEMALE, FIRST_MALE, find_background_candidate

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "p.db")
        pop0 = _pop(conn)
        actors0 = _count(conn, "SELECT COUNT(*) FROM actors")
        r = author(conn, me, "person", {"sex": "male", "age": 30, "work": "labor"}, "a1")
        assert r["status"] == "created" and r["kind"] == "person" and r["sex"] == "male" and r["from"] is None, r
        aid = r["actor_id"]
        a = conn.execute("SELECT * FROM actors WHERE id=?", (aid,)).fetchone()
        assert a["current_location_id"] == place and a["name"].split()[0] in FIRST_MALE and a["name"] == r["name"]
        assert a["subtype"] == "authored_labor" and "Authored in play" in a["notes"], dict(a)
        assert conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0] == "male"
        assert 26 <= r["age"] <= 34 and r["work"] == "labor", r
        assert conn.execute("SELECT status FROM background_person_profiles WHERE actor_id=?", (aid,)).fetchone()[0] == "resolved"
        assert _pop(conn) == pop0 and _count(conn, "SELECT COUNT(*) FROM actors") == actors0 + 1  # population-preserving
        assert conn.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?", (aid,)).fetchone()[0] == "STRATEGIC"
        assert _count(conn, "SELECT COUNT(*) FROM underworld_personnel WHERE actor_id=?", aid) == 0
        assert _count(conn, "SELECT COUNT(*) FROM relationships WHERE actor_a_id=? OR actor_b_id=?", aid, aid) == 0

        # names follow sex and are never reused
        _refused(lambda: author(conn, me, "person", {"sex": "male", "name": "Mira Holt"}, "n1"), "Mira")
        taken = conn.execute("SELECT name FROM actors WHERE actor_type='character' ORDER BY id LIMIT 1").fetchone()[0]
        _refused(lambda: author(conn, me, "person", {"sex": "male" if taken.split()[0] not in FIRST_FEMALE else "female", "name": taken}, "n2"), "already")
        ok = author(conn, me, "person", {"sex": "female", "name": "Fennick Vael"}, "n3")
        assert ok["name"] == "Fennick Vael" and ok["sex"] == "female", ok
        _refused(lambda: author(conn, me, "person", {"sex": "male", "work": "wizard"}, "w1"), "artisan")
        _refused(lambda: author(conn, me, "person", {"sex": "other"}, "w2"), "sex")
        _refused(lambda: author(conn, me, "person", {"sex": "male", "age": 5}, "w3"), "age")

        # rarity: not conjured, no rows left behind
        n = _count(conn, "SELECT COUNT(*) FROM actors")
        _refused(lambda: author(conn, me, "person", {"sex": "male", "stage": "Sixth"}, "r1"), "population")
        assert _count(conn, "SELECT COUNT(*) FROM actors") == n

        # kin ties
        bro = conn.execute("""SELECT a.id,a.name FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id WHERE a.actor_type='character'
                              AND a.status='active' AND p.demographic_sex='male' AND p.life_status='living' AND a.id<>? ORDER BY a.id LIMIT 1""", (me,)).fetchone()
        s = author(conn, me, "person", {"sex": "male", "age": 35, "ties": [{"actor_id": bro["id"], "as": "sibling"}]}, "k1")
        assert s["name"].split(" ", 1)[1] == bro["name"].split(" ", 1)[1], (s, dict(bro))
        assert _count(conn, "SELECT COUNT(*) FROM kinship_links WHERE kin_kind='sibling' AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))",
                      s["actor_id"], bro["id"], bro["id"], s["actor_id"]) == 2
        # a tie to the protagonist cannot make kin; 'knows' is bare acquaintance only
        _refused(lambda: author(conn, me, "person", {"sex": "male", "ties": [{"actor_id": me, "as": "sibling"}]}, "k2"), "protagonist")
        kn = author(conn, me, "person", {"sex": "female", "ties": [{"actor_id": me, "as": "knows"}]}, "k3")
        rel = conn.execute("SELECT familiarity,trust,affection,loyalty FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (kn["actor_id"], me)).fetchone()
        assert rel["familiarity"] > 0 and rel["trust"] == 0 and rel["loyalty"] == 0 and rel["affection"] == 0, dict(rel)
        assert _count(conn, "SELECT COUNT(*) FROM relationships WHERE actor_a_id=? AND actor_b_id=?", me, kn["actor_id"]) == 1
        # a parent only a few years older is refused, and the actor goes with it
        child = conn.execute("""SELECT p.actor_id,p.birth_day FROM actor_life_profiles p JOIN actors a ON a.id=p.actor_id WHERE a.actor_type='character'
                                AND a.status='active' AND p.life_status='living' AND p.birth_day IS NOT NULL AND a.id<>?
                                AND p.birth_day BETWEEN (SELECT current_day FROM world_state)-60*365 AND (SELECT current_day FROM world_state)-25*365
                                ORDER BY a.id LIMIT 1""", (me,)).fetchone()
        day = _count(conn, "SELECT current_day FROM world_state WHERE id=1")
        cage = (day - child["birth_day"]) // 365
        n, k = _count(conn, "SELECT COUNT(*) FROM actors"), _count(conn, "SELECT COUNT(*) FROM kinship_links")
        _refused(lambda: author(conn, me, "person", {"sex": "male", "age": cage + 5, "ties": [{"actor_id": child["actor_id"], "as": "parent"}]}, "k4"), "older")
        assert _count(conn, "SELECT COUNT(*) FROM actors") == n and _count(conn, "SELECT COUNT(*) FROM kinship_links") == k
        # a union: opposite sex, adults, wife takes his family name; same sex refused
        sp = author(conn, me, "person", {"sex": "female", "age": 30, "ties": [{"actor_id": s["actor_id"], "as": "spouse"}]}, "k5")
        assert sp["name"].split(" ", 1)[1] == s["name"].split(" ", 1)[1]
        assert _count(conn, "SELECT COUNT(*) FROM household_unions WHERE status='active' AND ? IN (actor_a_id,actor_b_id) AND ? IN (actor_a_id,actor_b_id)", sp["actor_id"], s["actor_id"]) == 1
        _refused(lambda: author(conn, me, "person", {"sex": "male", "age": 30, "ties": [{"actor_id": s["actor_id"], "as": "spouse"}]}, "k6"), "union")
        _refused(lambda: author(conn, me, "person", {"sex": "female", "age": 30, "ties": [{"actor_id": s["actor_id"], "as": "spouse"}]}, "k7"), "union")

        # wants and notes
        from connector import store
        gn = store.add_note(conn, "general", None, "A one-eyed ferryman owes the Rooks.", "g1")["note_id"]
        an = store.add_note(conn, "actor", bro["id"], "Likes dogs.", "g2")["note_id"]
        _refused(lambda: author(conn, me, "person", {"sex": "male", "from_notes": [an]}, "g3"), "note")
        _refused(lambda: author(conn, me, "person", {"sex": "male", "from_notes": [99999]}, "g4"), "note")
        w = author(conn, me, "person", {"sex": "male", "age": 50, "wants": "To buy his boat back.", "from_notes": [gn]}, "g5")
        assert conn.execute("SELECT subject_kind,subject_id FROM gm_notes WHERE id=?", (gn,)).fetchone()[:] == ("actor", w["actor_id"])
        assert conn.execute("SELECT description,priority,status FROM goals WHERE actor_id=?", (w["actor_id"],)).fetchone()[:] == ("To buy his boat back.", 50, "active")
        _refused(lambda: author(conn, me, "person", {"sex": "male", "wants": "x" * 201}, "g6"), "200")
        assert conn.execute("SELECT subject_kind FROM gm_notes WHERE id=?", (an,)).fetchone()[0] == "actor"
        conn.close()

    # from_elsewhere: an outsider only on request, and then moved here
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "e.db")
        found = None
        for work in WORK:
            for sex in ("male", "female"):
                for stage in ("Third", "Breach"):
                    kw = dict(location_id=place, occupation_domains=(work,), demographic_sex=sex, required_stage=stage, require_open_core=True, strict_stage=True)
                    if find_background_candidate(conn, allow_elsewhere=False, **kw) is None:
                        row = find_background_candidate(conn, **kw)
                        if row is not None and int(row["current_location_id"]) != place and row["current_stage"] == stage:
                            found = (work, sex, stage, row)
                            break
                if found: break
            if found: break
        assert found, "no outsider-only combination in the opening world"
        work, sex, stage, row = found
        n = _count(conn, "SELECT COUNT(*) FROM actors")
        _refused(lambda: author(conn, me, "person", {"sex": sex, "work": work, "stage": stage}, "x1"), "population")
        assert _count(conn, "SELECT COUNT(*) FROM actors") == n
        r = author(conn, me, "person", {"sex": sex, "work": work, "stage": stage, "from_elsewhere": True}, "x2")
        a = conn.execute("SELECT current_location_id,home_location_id FROM actors WHERE id=?", (r["actor_id"],)).fetchone()
        origin = conn.execute("SELECT name FROM locations WHERE id=?", (row["current_location_id"],)).fetchone()[0]
        assert a["current_location_id"] == place and a["home_location_id"] != place and r["from"] == origin, (dict(a), r, origin)
        conn.close()


def run_orgs():
    from engine.authoring import author

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "o.db", pop=400)
        owner = author(conn, me, "person", {"sex": "female", "age": 45}, "o0")
        b = author(conn, me, "business", {"name": "Tarn & Daughters", "trade": "rope and tackle", "enterprise_kind": "workshop", "owner_actor_id": owner["actor_id"]}, "b1")
        assert b["status"] == "created" and b["kind"] == "business" and isinstance(b["means"], str), b
        e = conn.execute("SELECT * FROM civilian_enterprises WHERE id=?", (b["enterprise_id"],)).fetchone()
        assert e["location_id"] == place and e["owner_actor_id"] == owner["actor_id"] and e["capital"] == e["cash"] > 0, dict(e)
        assert conn.execute("SELECT role,authority FROM enterprise_staff WHERE enterprise_id=? AND actor_id=?", (e["id"], owner["actor_id"])).fetchone()[:] == ("owner", 100)
        _refused(lambda: author(conn, me, "business", {"name": "Forged", "trade": "x", "enterprise_kind": "shop", "owner_actor_id": me}, "b2"), "protagonist")
        _refused(lambda: author(conn, me, "business", {"name": "Tarn & Daughters", "trade": "x", "enterprise_kind": "shop", "owner_actor_id": owner["actor_id"]}, "b3"), "already")
        n = _count(conn, "SELECT COUNT(*) FROM civilian_enterprises")
        _refused(lambda: author(conn, me, "business", {"name": "Odd", "trade": "x", "enterprise_kind": "casino", "owner_actor_id": owner["actor_id"]}, "b4"), "kind")
        # his people cannot own authored businesses: staff of a business he owns
        from engine.civilian import create_enterprise
        from engine.merchant import add_enterprise_staff
        far_loc = int(conn.execute("SELECT id FROM locations WHERE id<>? ORDER BY id LIMIT 1", (place,)).fetchone()[0])
        mine = create_enterprise(conn, "My Counting House", "shop", owner_actor_id=me, location_id=far_loc, capital=5, cash=5)
        hand = author(conn, me, "person", {"sex": "male", "age": 28}, "b0")
        add_enterprise_staff(conn, mine, hand["actor_id"], role="factor", authority=40)
        n = _count(conn, "SELECT COUNT(*) FROM civilian_enterprises")
        _refused(lambda: author(conn, me, "business", {"name": "Hers", "trade": "x", "enterprise_kind": "shop", "owner_actor_id": hand["actor_id"]}, "b5"), "his people")
        _refused(lambda: author(conn, me, "organisation", {"name": "Hands", "type": "gang", "leader_actor_id": hand["actor_id"]}, "b6"), "his people")
        assert _count(conn, "SELECT COUNT(*) FROM civilian_enterprises") == n
        # the town only has room for so many
        i = 0
        while True:
            try:
                author(conn, me, "business", {"name": f"Stall {i}", "trade": "odds", "enterprise_kind": "shop", "owner_actor_id": owner["actor_id"]}, f"cap{i}")
            except Exception as ex:
                assert "no room" in str(ex), ex
                break
            i += 1
            assert i < 10
        assert _count(conn, "SELECT COUNT(*) FROM civilian_enterprises WHERE location_id=? AND status='active'", place) == 3

        # outfits
        boss = author(conn, me, "person", {"sex": "male", "age": 40}, "o1")
        g = author(conn, me, "organisation", {"name": "The Ferry Lads", "type": "gang", "leader_actor_id": boss["actor_id"]}, "g1")
        assert g["status"] == "created" and g["kind"] == "organisation" and "outfit_id" in g, g
        o = conn.execute("SELECT * FROM underworld_organizations WHERE id=?", (g["outfit_id"],)).fetchone()
        assert o["primary_location_id"] == place and not o["treasury"] and o["current_leader_actor_id"] == boss["actor_id"], dict(o)
        assert conn.execute("SELECT role_kind FROM underworld_personnel WHERE actor_id=?", (boss["actor_id"],)).fetchone()[0] == "boss"
        _refused(lambda: author(conn, me, "organisation", {"name": "Mafia Lite", "type": "sect", "leader_actor_id": boss["actor_id"]}, "g2"), "canon-scale")
        _refused(lambda: author(conn, me, "organisation", {"name": "Mafia Lite", "type": "mafia_family", "leader_actor_id": boss["actor_id"]}, "g3"), "canon-scale")
        b2 = author(conn, me, "person", {"sex": "male", "age": 38}, "o2")
        _refused(lambda: author(conn, me, "organisation", {"name": "Second Crew", "type": "crew", "leader_actor_id": b2["actor_id"]}, "g4"), "no room")
        _refused(lambda: author(conn, me, "organisation", {"name": "Mine", "type": "gang", "leader_actor_id": me}, "g5"), "protagonist")
        _refused(lambda: author(conn, me, "organisation", {"name": "Again", "type": "club", "leader_actor_id": boss["actor_id"]}, "g6"), "already")
        # his outfit's people cannot front an authored body either
        # local bodies
        head = author(conn, me, "person", {"sex": "female", "age": 52}, "i0")
        c = author(conn, me, "organisation", {"name": "Stillwater Weavers' Guild", "type": "guild", "leader_actor_id": head["actor_id"]}, "i1")
        assert c["status"] == "created" and "institution_actor_id" in c, c
        ia = conn.execute("SELECT * FROM actors WHERE id=?", (c["institution_actor_id"],)).fetchone()
        assert ia["actor_type"] == "institution" and ia["subtype"] == "guild" and ia["current_location_id"] == place
        m = conn.execute("SELECT member_actor_id,role_text,status FROM institution_memberships WHERE institution_actor_id=?", (ia["id"],)).fetchone()
        assert m[:] == (head["actor_id"], "head", "active"), tuple(m)
        h2 = author(conn, me, "person", {"sex": "male", "age": 50}, "i2")
        _refused(lambda: author(conn, me, "organisation", {"name": "Second Guild", "type": "guild", "leader_actor_id": h2["actor_id"]}, "i3"), "no room")
        assert conn.execute("SELECT 1 FROM underworld_organizations WHERE name='Second Guild'").fetchone() is None

        # rumours
        here = author(conn, me, "person", {"sex": "male", "age": 33}, "m0")
        rum = author(conn, me, "rumour", {"text": "The ferryman is selling a map.", "heard_by": [here["actor_id"]]}, "m1")
        assert rum["status"] == "created" and rum["kind"] == "rumour", rum
        rr = conn.execute("SELECT * FROM rumours WHERE id=?", (rum["rumour_id"],)).fetchone()
        assert rr["truth_event_id"] is None and rr["origin_location_id"] == place and rr["status"] == "circulating"
        assert _count(conn, "SELECT COUNT(*) FROM rumour_exposures WHERE rumour_id=? AND actor_id=?", rr["id"], here["actor_id"]) == 1
        assert _count(conn, "SELECT COUNT(*) FROM rumour_locations WHERE rumour_id=? AND location_id=?", rr["id"], place) == 1
        far = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL AND current_location_id<>? LIMIT 1", (place,)).fetchone()[0]
        nr = _count(conn, "SELECT COUNT(*) FROM rumours")
        _refused(lambda: author(conn, me, "rumour", {"text": "Elsewhere news.", "heard_by": [far]}, "m2"), "present")
        _refused(lambda: author(conn, me, "rumour", {"text": "x" * 301}, "m3"), "300")
        assert _count(conn, "SELECT COUNT(*) FROM rumours") == nr
        _refused(lambda: author(conn, me, "gizmo", {}, "z1"), "kind")
        conn.close()


if __name__ == "__main__":
    run()
    run_orgs()
    print("authoring_test: ok")
