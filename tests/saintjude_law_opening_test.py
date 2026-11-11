"""Law, the Pad and connected people at the Saint Jude opening (mob minimum, task 8).

Run: PYTHONPATH=. python tests/saintjude_law_opening_test.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine import law_opening, ledger, outfit_money
from engine.design import figure
from engine.world_package import law_rules, outfit_rules, package_for

FAMILIES = ("sabatini", "pellegrino", "vannucci", "ferrante")
_CONN = []


def _open():
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect(path)
    pkg = package_for(conn)
    return conn, law_rules(pkg), outfit_rules(pkg)


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _profile(conn, actor_id):
    return conn.execute("SELECT * FROM simulation_profiles WHERE actor_id=?", (actor_id,)).fetchone()


def _is_level4(conn, actor_id) -> bool:
    p = _profile(conn, actor_id)
    return p is not None and p["cadence_days"] == 1 and p["quiet_routine"] == 1 and p["tier"] == "ACTIVE"


def _holder(conn, key):
    r = conn.execute("SELECT holder_actor_id FROM world_facts WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def _inst(conn, name):
    return int(conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='institution'", (name,)).fetchone()[0])


def _pad_total_m(conn) -> float:
    return figure(conn, "pad_total_m")


def test_jurisdictions_and_agencies_loaded():
    conn, law, _ = _open()
    keys = {r[0] for r in conn.execute("SELECT jurisdiction_key FROM law_jurisdictions")}
    assert {"city", "killbuck_county", "marsh_county", "state", "federal"} <= keys, keys
    assert conn.execute("SELECT COUNT(*) FROM law_rules").fetchone()[0] >= 4
    prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE name='FBI Saint Jude Field Office'").fetchone()
    assert prof is not None and json.loads(prof["metadata_json"])["pad_reaches"] is False
    assert conn.execute("SELECT COUNT(*) FROM law_enforcement_profiles").fetchone()[0] == len(law["agencies"])
    sjpd = conn.execute("SELECT * FROM law_enforcement_profiles WHERE profile_key='sjpd'").fetchone()
    assert json.loads(sjpd["metadata_json"])["pad_reaches"] is True
    # one agency row per agency with an institution; the State AG has none
    ag = conn.execute("SELECT * FROM law_enforcement_profiles WHERE profile_key='state_ag'").fetchone()
    assert ag is not None and ag["institution_actor_id"] is None
    # routing
    pid = law_opening.agency_for(conn, conn.execute("SELECT id FROM locations WHERE name='Kerrytown'").fetchone()[0], "assault")
    assert conn.execute("SELECT name FROM law_enforcement_profiles WHERE id=?", (pid,)).fetchone()[0] == "11th Precinct"
    pid = law_opening.agency_for(conn, conn.execute("SELECT id FROM locations WHERE name='Kerrytown'").fetchone()[0], "racket")
    assert conn.execute("SELECT name FROM law_enforcement_profiles WHERE id=?", (pid,)).fetchone()[0] == "Organized Crime Control Division"
    pid = law_opening.agency_for(conn, None, "racket", federal=True)
    assert conn.execute("SELECT name FROM law_enforcement_profiles WHERE id=?", (pid,)).fetchone()[0] == "Organized Crime and Racketeering Strike Force"
    pid = law_opening.agency_for(conn, None, "homicide", federal=True)
    assert conn.execute("SELECT name FROM law_enforcement_profiles WHERE id=?", (pid,)).fetchone()[0] == "FBI Saint Jude Field Office"


def test_level4_offices_filled_once():
    conn, law, outf = _open()
    holders = []
    for key in law["level4_offices"]:
        h = _holder(conn, key)
        assert h is not None, key
        assert _is_level4(conn, h), key
        holders.append(h)
    assert len(set(holders)) == len(holders)
    # every role holds a seat
    for role in law["level4_roles"]:
        lead = role["role_text"].replace(",", " ").split()[0]  # a seeded holder keeps his own wording ("Captain, commander of ...")
        rows = conn.execute("""SELECT DISTINCT m.member_actor_id FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id
                               WHERE i.name=? AND (m.role_text=? OR m.role_text LIKE ?) AND m.status='active'""",
                            (role["institution"], role["role_text"], lead + "%")).fetchall()
        assert len(rows) >= 1, role
        for (aid,) in rows:
            assert _is_level4(conn, aid), role
    aldermen = conn.execute("""SELECT COUNT(DISTINCT member_actor_id) FROM institution_memberships
                               WHERE role_text IN ('Alderman of a ward on mob ground','Member of the City Council')""").fetchone()[0]
    assert aldermen == round(figure(conn, "mob_wards")), aldermen  # the seeded councilman is one of them
    # a captain for every precinct that contains a family crew's ground
    grounds = {r[0] for r in conn.execute("SELECT DISTINCT ground_location_id FROM outfit_crews WHERE ground_location_id IS NOT NULL")}
    assert grounds
    covered = set()
    for g in grounds:
        p = law_opening.precinct_for_location(conn, g)
        if p is not None:  # a ground no precinct covers (the freight corridor) is the department's own
            covered.add(p)
    assert len(covered) >= 6, covered
    for inst_id in covered:
        name = conn.execute("SELECT name FROM actors WHERE id=?", (inst_id,)).fetchone()[0]
        role = f"Captain, {name}"
        n = conn.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND role_text LIKE 'Captain%' AND status='active'",
                         (inst_id,)).fetchone()[0]
        assert n >= 1, name
    # the seeded captain of the 14th is the one who commands it
    mc = conn.execute("SELECT id FROM actors WHERE name='Dennis McCaffrey'").fetchone()[0]
    assert _is_level4(conn, mc)
    # created locals have a president and no outfit rank
    for role in law["level4_roles"]:
        if role.get("created_by_builder"):
            assert conn.execute("SELECT 1 FROM actors WHERE name=? AND actor_type='institution'", (role["institution"],)).fetchone(), role
    assert not conn.execute("SELECT 1 FROM outfit_ranks r JOIN institution_memberships m ON m.member_actor_id=r.actor_id "
                            "WHERE m.role_text='Chief of Detectives'").fetchone()


def test_pad_officers_and_envelopes_balance():
    conn, law, outf = _open()
    env = conn.execute("SELECT * FROM pad_envelopes WHERE status='active'").fetchall()
    officers = {e["officer_actor_id"] for e in env}
    assert len(officers) == len(env) == round(figure(conn, "pad_officers")), (len(officers), len(env))
    total_m = sum(e["weekly_usd"] for e in env) * 52 / 1e6
    assert abs(total_m - _pad_total_m(conn)) <= 0.05, (total_m, _pad_total_m(conn))
    alloc = outfit_money.design_allocation(conn)["pad_by_family_m"]
    scale = _pad_total_m(conn) / sum(alloc.values())  # at the default total the scale is 1: the 9.3A split
    names = {fam: law_opening.outfit_actor(conn, outf["outfits"][fam]["institution"]) for fam in FAMILIES}
    for fam in FAMILIES:
        paid = sum(e["weekly_usd"] for e in env if e["payer_outfit_actor_id"] == names[fam]) * 52 / 1e6
        assert abs(paid - alloc[fam] * scale) <= 0.02, (fam, paid, alloc[fam] * scale)
    pat = max(figure(conn, "pad_patrolman_weekly_usd"), 0)
    # position keys are "<precinct institution id>:<tier>:<n>" and unique
    keys = [e["position_key"] for e in env]
    assert len(set(keys)) == len(keys)
    for k in keys:
        pid, tier, n = k.split(":")
        assert conn.execute("SELECT 1 FROM actors WHERE id=? AND name LIKE '%Precinct'", (int(pid),)).fetchone(), k
        assert tier in ("captain", "sergeant", "patrolman") and int(n) >= 1
    # every precinct captain on family ground has an envelope larger than any patrolman's
    biggest_patrolman = max(e["weekly_usd"] for e in env if e["position_key"].split(":")[1] == "patrolman")
    grounds = {r[0] for r in conn.execute("SELECT DISTINCT ground_location_id FROM outfit_crews WHERE ground_location_id IS NOT NULL")}
    precincts = {law_opening.precinct_for_location(conn, g) for g in grounds} - {None}
    for pid in precincts:
        capt = [e for e in env if e["position_key"].startswith(f"{pid}:captain:")]
        assert capt, pid
        cap_actor = conn.execute("SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND role_text LIKE 'Captain%' "
                                 "AND status='active' ORDER BY id LIMIT 1", (pid,)).fetchone()[0]
        mine = [e for e in env if e["officer_actor_id"] == cap_actor]
        assert mine and mine[0]["weekly_usd"] > biggest_patrolman, pid
    # sex: 99 percent male, tier-3 officers at level 3 weekly
    male = conn.execute("""SELECT SUM(lp.demographic_sex='male'),COUNT(*) FROM pad_envelopes e JOIN actor_life_profiles lp ON lp.actor_id=e.officer_actor_id""").fetchone()
    assert male[0] / male[1] >= 0.98, male[:]
    for e in env:
        p = _profile(conn, e["officer_actor_id"])
        if p["cadence_days"] == 1:  # only a precinct captain is a level-4 officer; the rest are weekly
            assert conn.execute("SELECT 1 FROM institution_memberships WHERE member_actor_id=? AND role_text LIKE 'Captain%'", (e["officer_actor_id"],)).fetchone()
        else:
            assert p["cadence_days"] == 7 and p["quiet_routine"] == 1 and p["tier"] == "STRATEGIC", dict(p)
    # bagmen are sergeants in the Pad
    bag = {e["bagman_actor_id"] for e in env if e["bagman_actor_id"] is not None}
    assert bag and bag <= officers
    # police are pulled up from the background, never invented
    n_unlinked = conn.execute("""SELECT COUNT(*) FROM pad_envelopes e WHERE NOT EXISTS (SELECT 1 FROM background_population_identity_links l WHERE l.actor_id=e.officer_actor_id)""").fetchone()[0]
    assert n_unlinked <= len(precincts)  # only seeded captains may be unlinked


def test_connected_people_are_level_4():
    conn, law, outf = _open()
    total = 0
    holders: set[int] = set()
    for c in outf["connected"]:
        rows = conn.execute("""SELECT m.member_actor_id FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id
                               WHERE i.name=? AND m.role_text=? AND m.status='active'""", (c["institution"], c["role_text"])).fetchall() if c["institution"] else \
            conn.execute("SELECT id FROM actors WHERE subtype=? AND status='active'", (c["role_text"],)).fetchall()
        assert len(rows) >= c["count"], (c, len(rows))
        for (aid,) in rows[: c["count"]]:
            assert _is_level4(conn, aid), c
            holders.add(aid)
            if c["tied_to"]:
                boss = law_opening.head_of(conn, c["tied_to"], outf["outfits"][c["tied_to"]])
                assert conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (aid, boss)).fetchone(), c
        total += c["count"]
    assert not conn.execute("SELECT 1 FROM outfit_ranks r JOIN institution_memberships m ON m.member_actor_id=r.actor_id JOIN actors i ON i.id=m.institution_actor_id "
                            "WHERE i.name='Docks Chinatown Associations'").fetchone()
    chin = conn.execute("""SELECT COUNT(DISTINCT m.member_actor_id) FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id
                           WHERE i.name='Docks Chinatown Associations' AND m.status='active'""").fetchone()[0]
    assert chin >= 3
    law_side = set()
    for key in law["level4_offices"]:
        law_side.add(_holder(conn, key))
    for role in law["level4_roles"]:
        lead = role["role_text"].replace(",", " ").split()[0]
        for (aid,) in conn.execute("""SELECT m.member_actor_id FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id
                                      WHERE i.name=? AND (m.role_text=? OR m.role_text LIKE ?)""", (role["institution"], role["role_text"], lead + "%")):
            law_side.add(aid)
    both = law_side | holders
    assert 50 <= len(both) <= 80, len(both)


def test_pad_is_paid_in_the_flow():
    conn, law, outf = _open()
    env = conn.execute("SELECT * FROM pad_envelopes WHERE status='active'").fetchall()
    day = _day(conn) + 28
    ids = [r[0] for r in conn.execute("SELECT actor_id FROM outfit_ranks")]
    out = outfit_money.post_period(conn, day, 28)
    want = sum(e["weekly_usd"] for e in env) * 4
    assert abs(out["pad"] - want) < 0.5, (out["pad"], want)
    q = ",".join("?" * len(ids))
    family_paid = conn.execute(f"SELECT SUM(amount) FROM outfit_money WHERE day=? AND kind='pad' AND from_actor_id IN ({q})", (day, *ids)).fetchone()[0]
    assert abs(family_paid - want) < 0.5, (family_paid, want)
    for e in env:
        got = conn.execute("SELECT SUM(amount) FROM outfit_money WHERE day=? AND kind='pad' AND to_actor_id=?", (day, e["officer_actor_id"])).fetchone()[0]
        bag = e["bagman_actor_id"]
        if bag is not None and bag == e["officer_actor_id"]:
            continue  # a bagman keeps his own envelope out of what he collects; his row is the collection
        assert got and got > 0, e["position_key"]
    # one row per payer/payee/kind per period
    rows = conn.execute("SELECT kind,from_actor_id,to_actor_id FROM outfit_money WHERE day=?", (day,)).fetchall()
    seen = [(r[0], r[1], r[2]) for r in rows]
    assert len(seen) == len(set(seen))
    # an officer ends with his envelope in cash
    e = next(e for e in env if e["bagman_actor_id"] != e["officer_actor_id"] and e["bagman_actor_id"] is not None)
    assert ledger.balance(conn, ("person", e["officer_actor_id"])) >= e["weekly_usd"] * 4 - 0.01


def test_engine_has_no_saint_jude_words():
    for name in ("law_opening.py", "outfit_money.py"):
        text = (ROOT / "engine" / name).read_text(encoding="utf-8")
        for w in ("Sabatini", "Pellegrino", "Ferrante", "Vannucci", "Brigades", "Kerrytown", "Mercer"):
            assert w not in text, (name, w)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad.append(t.__name__)
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, repr(e)[:300])
        else:
            print("ok", t.__name__)
    print(f"{len(TESTS) - len(bad)} passed" + (f", {len(bad)} FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)
