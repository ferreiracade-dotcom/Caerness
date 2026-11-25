"""Task B13b: fixes after B12e and B13 (package memo, protection of a head, schema 119, a pressure resolved twice, a patron who is gone).

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/b13b_fixes_test.py
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_FAILURES: set[str] = set()


def _fresh():
    from engine.db import connect, init_db
    os.environ["CAERNESS_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "b13b.db")
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    init_db()
    return connect()


def test_schema_119_has_the_law_tables():
    from engine.db import SCHEMA_VERSION
    conn = _fresh()
    assert SCHEMA_VERSION == 131
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
    for t in ("public_attention", "case_dispositions", "sentences"):
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None, t
    conn.close()


def test_package_for_is_read_once_per_skip_and_fresh_outside_one():
    from engine import world_package as wp
    conn = _fresh()
    calls = []
    real = wp.worlds_dir
    wp.worlds_dir = lambda: (calls.append(1), real())[1]
    try:
        with wp.package_pass():
            a = wp.package_for(conn)
            b = wp.package_for(conn)
            assert a is b and len(calls) == 1
        wp.package_for(conn)
        wp.package_for(conn)
        assert len(calls) == 3, "outside a skip every call checks the manifest, so a swapped package is read fresh"
    finally:
        wp.worlds_dir = real
    conn.close()


def test_a_pressure_resolved_twice_does_not_collide():
    from engine.organization_agency import resolve_pressures
    conn = _fresh()
    iid = int(conn.execute("INSERT INTO actors(name,actor_type) VALUES ('Test Board','institution')").lastrowid)
    for rnd in range(3):
        conn.execute("INSERT INTO organization_pressures(institution_actor_id,pressure_key,domain,status) VALUES (?,?,?,'active')", (iid, "authority_vacancy:head", "authority"))
        ids = resolve_pressures(conn, "institution_actor_id=? AND pressure_key=?", (iid, "authority_vacancy:head"), day=10 + rnd)
        assert len(ids) == 1
    rows = conn.execute("SELECT pressure_key,status FROM organization_pressures WHERE institution_actor_id=? ORDER BY id", (iid,)).fetchall()
    assert [r[1] for r in rows] == ["resolved"] * 3 and len({r[0] for r in rows}) == 3, [tuple(r) for r in rows]
    conn.close()


def test_succession_resolving_a_vacancy_again_does_not_crash():
    """The old UPDATE ... SET status='resolved' hit UNIQUE(institution, key, status) when the same vacancy came round a second time."""
    conn = _fresh()
    iid = int(conn.execute("INSERT INTO actors(name,actor_type) VALUES ('Test Lodge','institution')").lastrowid)
    for _ in range(2):
        conn.execute("INSERT INTO organization_pressures(institution_actor_id,pressure_key,domain,status) VALUES (?,?,?,'active')", (iid, "authority_vacancy:x", "authority"))
        from engine.organization_agency import resolve_pressures
        resolve_pressures(conn, "institution_actor_id=? AND pressure_key=?", (iid, "authority_vacancy:x"), day=5)
    assert conn.execute("SELECT COUNT(*) FROM organization_pressures WHERE institution_actor_id=?", (iid,)).fetchone()[0] == 2
    conn.close()


def _world():
    from tests.outfit_choice_fixture import open_world
    return open_world()


def test_protection_grows_with_the_men_under_a_man_and_is_none_for_a_soldier():
    from engine import org_tension as ot
    w = _world()
    g_boss, l_boss = ot.protection(w.conn, w.boss)
    g_capo, _ = ot.protection(w.conn, w.capo)
    lone = int(w.conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND actor_id NOT IN (SELECT superior_actor_id FROM org_seats WHERE superior_actor_id IS NOT NULL) LIMIT 1", (w.org,)).fetchone()[0])
    g_sol, l_sol = ot.protection(w.conn, lone)
    assert g_sol == 0.0 and l_sol == 0.0
    assert 0.0 < g_capo < g_boss < 1.0, (g_capo, g_boss)
    assert 0.0 <= l_boss <= 1.0


def test_a_guarded_head_is_a_less_likely_pick_among_the_men_on_a_rung():
    from engine import org_tension as ot, orgs
    w = _world()
    c = w.conn
    other = int(c.execute("SELECT org_actor_id FROM org_profiles WHERE org_kind='family' AND org_actor_id<>? ORDER BY org_actor_id LIMIT 1", (w.org,)).fetchone()[0])
    head = orgs.head_of(c, other)
    vs = [head] + [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND actor_id<>? ORDER BY actor_id LIMIT 9", (other, head))]
    assert len(vs) == 10
    day = 200
    picks = sum(1 for i in range(400) if ot._pick_victim(c, vs, random.Random(i), other, w.org, w.soldier, day) == head)
    assert picks < 400 / 10 * 0.8, f"a head of a whole family, picked by a soldier acting alone, should come up well under 1 in 10 (got {picks}/400)"


def test_a_man_whose_patron_is_gone_has_no_better_patron_to_compare():
    from engine import org_happenings as oh, orgs
    w = _world()
    c = w.conn
    c.execute("DELETE FROM org_seats WHERE actor_id=? AND org_actor_id=?", (w.capo, w.org))  # no seat for the patron in this organisation at all
    seat = orgs.seat_of(c, w.soldier, w.org)
    assert oh._better_patron(c, w.soldier, seat, w.org, 100) == (None, 0.0)


def run():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"FAIL {name}: {exc!r}")
            import traceback
            traceback.print_exc()
    unexpected = [n for n in failed if n not in EXPECTED_FAILURES]
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    return 1 if unexpected else 0


def test_factors_carry_every_term_the_package_names():
    """A comment once swallowed half the factor dict (heat, calm, always, the drives...): every term a package names must be present."""
    from engine import org_tension as ot
    w = _world()
    other = int(w.conn.execute("SELECT org_actor_id FROM org_profiles WHERE org_kind='family' AND org_actor_id<>? ORDER BY org_actor_id LIMIT 1", (w.org,)).fetchone()[0])
    f = ot.factors(w.conn, w.soldier, w.org, other, 200)
    for k in ("heat", "heat_back", "calm", "always", "aggression", "ambition", "caution", "patience", "pragmatism", "friendly", "grievance",
              "stronger", "their_head_weak", "own_head_weak", "ambition_open", "war_near", "shared_ground", "their_head_guarded", "their_head_loved", "unbacked"):
        assert k in f, k
    assert f["always"] == 1.0


def test_an_organised_offender_is_less_often_named_at_filing_than_an_outsider():
    from engine import crime_response as cr
    from engine import org_motives
    w = _world()
    c = w.conn
    pub = {"drivers": {"witnesses": 0.4}, "publicity": 40.0}
    outsider = int(c.execute("SELECT id FROM actors WHERE id NOT IN (SELECT actor_id FROM org_seats) ORDER BY id LIMIT 1").fetchone()[0])
    old = org_motives._roll
    try:
        hits = {}
        for who, a in (("organised", w.soldier), ("outsider", outsider)):
            n = 0
            for i in range(300):
                org_motives._roll = lambda conn, actor, day, stream, _i=i: (_i + 0.5) / 300.0
                n += 1 if cr._identified_at_filing(c, 1, 100, a, outsider if who == "organised" else w.soldier, pub) else 0
            hits[who] = n
    finally:
        org_motives._roll = old
    assert hits["outsider"] > hits["organised"], hits


if __name__ == "__main__":
    sys.exit(run())
