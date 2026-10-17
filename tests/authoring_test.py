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
                              AND a.status='active' AND p.demographic_sex='male' AND p.life_status='living' AND a.id<>? AND p.birth_day BETWEEN (SELECT current_day FROM world_state)-55*365 AND (SELECT current_day FROM world_state)-25*365 ORDER BY a.id LIMIT 1""", (me,)).fetchone()
        bro_age = (_count(conn, "SELECT current_day FROM world_state WHERE id=1") - conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (bro["id"],)).fetchone()[0]) // 365
        s = author(conn, me, "person", {"sex": "male", "age": max(18, min(85, bro_age)), "ties": [{"actor_id": bro["id"], "as": "sibling"}]}, "k1")
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
        assert a["current_location_id"] == place and a["home_location_id"] == place and r["from"] == origin, (dict(a), r, origin)
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


def _outsider_combo(conn, place):
    from engine.person_ecology import find_background_candidate
    for work in WORK:
        for sex in ("male", "female"):
            for stage in ("Third", "Breach"):
                kw = dict(location_id=place, occupation_domains=(work,), demographic_sex=sex, required_stage=stage, require_open_core=True, strict_stage=True)
                if find_background_candidate(conn, allow_elsewhere=False, **kw) is None:
                    row = find_background_candidate(conn, **kw)
                    if row is not None and int(row["current_location_id"]) != place and row["current_stage"] == stage:
                        return work, sex, stage, row
    raise AssertionError("no outsider-only combination")


def _day_of(conn):
    return _count(conn, "SELECT current_day FROM world_state WHERE id=1")


def run_presence():
    from engine.authoring import author
    from engine.presence import actor_is_present_candidate

    # an outsider has moved: present at the new place, not at the origin
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "f1.db")
        work, sex, stage, row = _outsider_combo(conn, place)
        r = author(conn, me, "person", {"sex": sex, "work": work, "stage": stage, "from_elsewhere": True}, "f1")
        d0 = _day_of(conn)
        here = sum(actor_is_present_candidate(conn, r["actor_id"], place, day=d0 + i) for i in range(10))
        there = sum(actor_is_present_candidate(conn, r["actor_id"], int(row["current_location_id"]), day=d0 + i) for i in range(10))
        assert here >= 9 and there == 0, ("outsider presence", here, there)
        assert conn.execute("SELECT home_location_id FROM actors WHERE id=?", (r["actor_id"],)).fetchone()[0] == place
        conn.close()

    # locals are reliably there on the authoring day
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "f2.db")
        ids = [author(conn, me, "person", {"sex": "male" if i % 2 else "female", "age": 25 + i}, f"l{i}")["actor_id"] for i in range(10)]
        d0 = _day_of(conn)
        assert all(actor_is_present_candidate(conn, a, place, day=d0) for a in ids), "authored people not present on the authoring day"
        assert sum(actor_is_present_candidate(conn, a, place, day=d0 + i) for a in ids for i in range(1, 6)) >= 47
        conn.close()


def run_bodies():
    from engine.authoring import author

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "f3.db", pop=6000)
        own = author(conn, me, "person", {"sex": "female", "age": 45}, "o")["actor_id"]
        boss = author(conn, me, "person", {"sex": "male", "age": 40}, "b")["actor_id"]
        head = author(conn, me, "person", {"sex": "female", "age": 52}, "h")["actor_id"]
        biz = author(conn, me, "business", {"name": "Tarn Rope", "trade": "rope and tackle", "enterprise_kind": "workshop", "owner_actor_id": own}, "bz")
        gang = author(conn, me, "organisation", {"name": "The Ferry Lads", "type": "gang", "leader_actor_id": boss}, "gg")
        guild = author(conn, me, "organisation", {"name": "Weavers Guild", "type": "guild", "leader_actor_id": head}, "gd")
        e, o, i = biz["enterprise_id"], gang["outfit_id"], guild["institution_actor_id"]
        assert _count(conn, "SELECT COUNT(*) FROM enterprise_business_profiles WHERE enterprise_id=?", e) == 1
        assert _count(conn, "SELECT COUNT(*) FROM enterprise_ecology_state WHERE enterprise_id=?", e) == 1
        assert _count(conn, "SELECT COUNT(*) FROM underworld_membership_profiles WHERE organization_id=?", o) == 1
        assert _count(conn, "SELECT COUNT(*) FROM underworld_heat WHERE organization_id=?", o) == 1
        assert conn.execute("SELECT member_count_estimate FROM underworld_organizations WHERE id=?", (o,)).fetchone()[0] == 1
        assert _count(conn, "SELECT COUNT(*) FROM organization_agency_profiles WHERE institution_actor_id=?", i) == 1
        assert _count(conn, "SELECT COUNT(*) FROM organization_lifecycle_profiles WHERE institution_actor_id=?", i) == 1
        conn.commit()
        from connector.timeflow import advance
        d0 = _day_of(conn)
        for k in range(2):
            advance(conn, f"adv{k}", 30, "test")
        assert _day_of(conn) > d0
        assert conn.execute("SELECT last_resolved_day FROM enterprise_business_profiles WHERE enterprise_id=?", (e,)).fetchone()[0] > d0, "economy never touched the authored business"
        conn.close()


def run_caps():
    from engine.authoring import AuthoringRefused, author
    from engine.presence import actor_is_present_candidate, add_presence_habit

    # somebody must live there, and so must the owner
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "f4.db", pop=6000)
        own = author(conn, me, "person", {"sex": "female", "age": 45}, "o")["actor_id"]
        away = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND home_location_id<>? AND current_location_id<>? AND id<>? ORDER BY id LIMIT 1",
                                (place, place, me)).fetchone()[0])
        for kind, det in (("business", {"name": "Away Shop", "trade": "x", "enterprise_kind": "shop", "owner_actor_id": away}),
                          ("organisation", {"name": "Away Crew", "type": "gang", "leader_actor_id": away}),
                          ("organisation", {"name": "Away Guild", "type": "guild", "leader_actor_id": away})):
            _refused(lambda: author(conn, me, kind, det, "away" + det["name"]), "live")
        conn.execute("UPDATE background_population_sources SET population_estimate=0 WHERE location_id=?", (place,))
        for kind, det in (("business", {"name": "Ghost Shop", "trade": "x", "enterprise_kind": "shop", "owner_actor_id": own}),
                          ("organisation", {"name": "Ghost Crew", "type": "gang", "leader_actor_id": own}),
                          ("organisation", {"name": "Ghost Guild", "type": "guild", "leader_actor_id": own})):
            _refused(lambda: author(conn, me, kind, det, "gh" + det["name"]), "nobody lives")
        conn.close()


def run_rarity():
    from engine.authoring import AuthoringRefused, author
    from engine.presence import actor_is_present_candidate, add_presence_habit

    # rarity: authored people reflect the settlement
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "f5.db")
        base = conn.execute("SELECT AVG(open_core) FROM background_person_profiles WHERE current_location_id=?", (place,)).fetchone()[0]
        got = [author(conn, me, "person", {"sex": "male" if i % 2 else "female"}, f"p{i}")["actor_id"] for i in range(20)]
        share = sum(conn.execute("SELECT core_state FROM cultivation_profiles WHERE actor_id=?", (a,)).fetchone()[0] == "Open-Core" for a in got) / 20
        assert share <= float(base) + 0.25, ("open-core share", share, base)
        early = sum(conn.execute("SELECT core_state FROM cultivation_profiles WHERE actor_id=?", (a,)).fetchone()[0] == "Open-Core" for a in got[:10]) / 10
        assert early <= float(base) + 0.25, ("early open-core share", early, base)
        conn.close()


def run_errors():
    from engine.authoring import AuthoringRefused, author
    from engine.presence import actor_is_present_candidate, add_presence_habit

    # a bug is a bug, not a refusal; nothing persists
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        import engine.civilian as civ
        conn, me, place = _open(tmp, "f6.db", pop=6000)
        own = author(conn, me, "person", {"sex": "female", "age": 45}, "o")["actor_id"]
        n = _count(conn, "SELECT COUNT(*) FROM civilian_enterprises")
        real = civ.create_enterprise
        civ.create_enterprise = lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
        try:
            author(conn, me, "business", {"name": "Bug", "trade": "x", "enterprise_kind": "shop", "owner_actor_id": own}, "bug")
            raise AssertionError("bug swallowed")
        except AuthoringRefused:
            raise AssertionError("a bug became a refusal")
        except ValueError as e:
            assert "boom" in str(e)
        finally:
            civ.create_enterprise = real
        assert _count(conn, "SELECT COUNT(*) FROM civilian_enterprises") == n
        conn.close()


def run_minor():
    from engine.authoring import AuthoringRefused, author
    from engine.presence import actor_is_present_candidate, add_presence_habit

    # minor: one-word names, sibling ages, rumour hearers by presence
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "f7.db")
        _refused(lambda: author(conn, me, "person", {"sex": "female", "name": "Fennick"}, "w1"), "family name")
        bro = conn.execute("""SELECT a.id,p.birth_day FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id WHERE a.actor_type='character' AND a.status='active'
                              AND p.demographic_sex='male' AND p.life_status='living' AND p.birth_day IS NOT NULL AND a.id<>? ORDER BY a.id LIMIT 1""", (me,)).fetchone()
        bage = (_day_of(conn) - bro["birth_day"]) // 365
        n = _count(conn, "SELECT COUNT(*) FROM actors")
        want = bage + 30 if bage + 30 <= 90 else bage - 30
        assert want >= 13, (bage, want)
        _refused(lambda: author(conn, me, "person", {"sex": "male", "age": want, "ties": [{"actor_id": bro["id"], "as": "sibling"}]}, "w2"), "25 years")
        assert _count(conn, "SELECT COUNT(*) FROM actors") == n
        far = conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND current_location_id IS NOT NULL AND current_location_id<>? AND id<>? LIMIT 1", (place, me)).fetchone()[0]
        add_presence_habit(conn, far, place, habit_kind="work", weight=1.0, confidence=1.0)
        assert actor_is_present_candidate(conn, far, place)
        rum = author(conn, me, "rumour", {"text": "A visitor talks.", "heard_by": [far]}, "w3")
        assert rum["status"] == "created", rum
        conn.close()


def run_spouse():
    from engine.authoring import author

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, place = _open(tmp, "sp.db")
        day = _day_of(conn)
        base = """SELECT a.id FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id WHERE a.actor_type='character' AND a.status='active'
                  AND p.demographic_sex='male' AND p.life_status='living' AND p.birth_day BETWEEN ?-60*365 AND ?-25*365 AND a.id<>?
                  AND NOT EXISTS (SELECT 1 FROM household_unions u WHERE u.status='active' AND a.id IN (u.actor_a_id,u.actor_b_id)) %s ORDER BY a.id LIMIT 1"""
        from engine.civilian import create_household
        free = "AND NOT EXISTS (SELECT 1 FROM household_members m WHERE m.actor_id=a.id AND m.status='active')"
        head = conn.execute(base % free, (day, day, me)).fetchone()
        loner = conn.execute(base % (free + " AND a.id<>%d" % head["id"]), (day, day, me)).fetchone()
        create_household(conn, "Test household", head_actor_id=head["id"], location_id=place)  # a bachelor who heads a household
        assert head and loner, (head, loner)

        def check(husband, wife_id, key):
            u = conn.execute("SELECT * FROM household_unions WHERE status='active' AND ? IN (actor_a_id,actor_b_id) AND ? IN (actor_a_id,actor_b_id)", (husband, wife_id)).fetchone()
            births = [conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (x,)).fetchone()[0] for x in (husband, wife_id)]
            assert day - 30 * 365 <= u["started_day"] < day, u["started_day"]
            assert u["started_day"] >= max(births) + 18 * 365, (u["started_day"], births)
            ks = conn.execute("SELECT started_day FROM kinship_links WHERE kin_kind='spouse' AND actor_a_id IN (?,?) AND actor_b_id IN (?,?)", (husband, wife_id, husband, wife_id)).fetchall()
            assert ks and all(r[0] == u["started_day"] for r in ks), (ks, u["started_day"])
            assert _count(conn, "SELECT COUNT(*) FROM life_events WHERE event_kind='union' AND day=? AND actor_id IN (?,?)", day, husband, wife_id) == 0
            ev = conn.execute("SELECT day FROM life_events WHERE event_kind='union' AND actor_id IN (?,?) AND related_actor_id IN (?,?)", (husband, wife_id, husband, wife_id)).fetchall()
            assert ev and all(r[0] == u["started_day"] for r in ev), (ev, u["started_day"])
            return u

        # a wife joins the household her husband heads
        hh = conn.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active' AND role='head'", (head["id"],)).fetchone()[0]
        w = author(conn, me, "person", {"sex": "female", "age": 30, "ties": [{"actor_id": head["id"], "as": "spouse"}]}, "sp1")
        assert conn.execute("SELECT status FROM household_members WHERE household_id=? AND actor_id=?", (hh, w["actor_id"])).fetchone()[0] == "active"
        assert conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (w["actor_id"],)).fetchone()[0] == hh
        check(head["id"], w["actor_id"], "sp1")

        # a husband with no household: both in one new household, he heads it, dated with the marriage
        w2 = author(conn, me, "person", {"sex": "female", "age": 30, "ties": [{"actor_id": loner["id"], "as": "spouse"}]}, "sp2")
        u = check(loner["id"], w2["actor_id"], "sp2")
        rows = conn.execute("SELECT actor_id,role,household_id FROM household_members WHERE status='active' AND actor_id IN (?,?)", (loner["id"], w2["actor_id"])).fetchall()
        assert len(rows) == 2 and len({r[2] for r in rows}) == 1, [tuple(r) for r in rows]
        assert [r[1] for r in rows if r[0] == loner["id"]] == ["head"]
        assert conn.execute("SELECT created_day FROM households WHERE id=?", (rows[0][2],)).fetchone()[0] == u["started_day"]
        conn.close()


def run_ground():
    """An authored gang anywhere holds a vacant zone, or challenges the weakest-held one."""
    from engine.authoring import author
    from engine.spectacle import activate_spectacle_substrate
    from engine.underworld_ecology import seed_all_settlements

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        conn, me, _ = _open(tmp, "g.db")
        activate_spectacle_substrate(conn)
        seed_all_settlements(conn)  # the world as schema 110 leaves it (idempotent if already migrated)
        toll = int(conn.execute("SELECT id FROM locations WHERE name='Toll’s Reach'").fetchone()[0])
        zones = [r[0] for r in conn.execute("SELECT id FROM underworld_zones WHERE city_location_id=? AND status='active' ORDER BY id", (toll,))]
        assert len(zones) >= 4, zones

        def claims(zid, kind):
            return [r[0] for r in conn.execute("SELECT organization_id FROM underworld_zone_claims WHERE zone_id=? AND claim_kind=? AND status='active'", (zid, kind))]

        def leader(i):
            row = conn.execute("""SELECT a.id FROM actors a WHERE a.actor_type='character' AND a.status='active' AND a.current_location_id=? AND a.home_location_id=?
                                  AND a.id<>? AND NOT EXISTS (SELECT 1 FROM underworld_personnel p WHERE p.actor_id=a.id AND p.status='active')
                                  ORDER BY a.id LIMIT 1 OFFSET ?""", (toll, toll, me, i)).fetchone()
            assert row, "no free local in Toll's Reach"
            return int(row[0])

        vacant = [z for z in zones if not claims(z, "controller")]
        assert vacant, "seeding should leave open ground"
        g = author(conn, me, "organisation", {"name": "The Quay Lads", "type": "gang", "location_id": toll, "leader_actor_id": leader(0)}, "gr1")
        held = [z for z in zones if g["outfit_id"] in claims(z, "controller")]
        assert len(held) == 1 and held[0] in vacant, (held, vacant)
        # no vacant ground left: it challenges the weakest-held zone
        for z in [z for z in zones if not claims(z, "controller")]:
            from engine.underworld_rebuild import set_zone_controller
            other = int(conn.execute("SELECT id FROM underworld_organizations WHERE organization_type='gang' AND primary_location_id=? AND id<>? AND status='active' LIMIT 1", (toll, g["outfit_id"])).fetchone()[0])
            set_zone_controller(conn, z, other, strength=60)
        weakest = conn.execute("""SELECT c.zone_id FROM underworld_zone_claims c JOIN underworld_zones z ON z.id=c.zone_id
                                  WHERE z.city_location_id=? AND c.claim_kind='controller' AND c.status='active' ORDER BY c.strength,c.id LIMIT 1""", (toll,)).fetchone()[0]
        g2 = author(conn, me, "organisation", {"name": "The Sea Wall Boys", "type": "crew", "location_id": toll, "leader_actor_id": leader(1)}, "gr2")
        assert g2["outfit_id"] in claims(weakest, "challenger"), (weakest, claims(weakest, "challenger"))
        assert g2["outfit_id"] not in [o for z in zones for o in claims(z, "controller")]
        conn.close()


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, fn in (("run", run), ("run_orgs", run_orgs), ("presence", run_presence), ("bodies", run_bodies), ("caps", run_caps), ("rarity", run_rarity), ("errors", run_errors), ("minor", run_minor), ("spouse", run_spouse), ("ground", run_ground)):
        if only in (None, name):
            fn()
    print("authoring_test: ok")
