"""The four Italian families as people at the Saint Jude opening (Saint Jude mob minimum, task 5)."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine.design import figure
from engine.world_package import package_for

FAMILIES = ("sabatini", "pellegrino", "ferrante", "vannucci")
FAMILY_ONLY = "r.outfit_actor_id IN (SELECT id FROM actors WHERE name LIKE '%% Family')"  # the gangs are task 6
MADE = ("boss", "underboss", "consigliere", "capo", "soldier")


def _open():
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect(path)
    return conn, package_for(conn)


def _outfit(conn, fam: str) -> int:
    inst = f"{fam.capitalize()} Family"
    return int(conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='institution'", (inst,)).fetchone()[0])


def _count(conn, fam: str, *ranks: str) -> int:
    q = ",".join("?" for _ in ranks)
    return int(conn.execute(f"SELECT COUNT(*) FROM outfit_ranks WHERE outfit_actor_id=? AND rank_key IN ({q}) AND status='active'",
                            (_outfit(conn, fam), *ranks)).fetchone()[0])


def _rank_of(conn, name: str):
    r = conn.execute("SELECT r.rank_key FROM outfit_ranks r JOIN actors a ON a.id=r.actor_id WHERE a.name=?", (name,)).fetchone()
    return r[0] if r else None


def test_made_men_and_associates_match_drawn_figures():
    conn, _ = _open()
    for fam in FAMILIES:
        made = _count(conn, fam, *MADE)
        assert made == round(figure(conn, f"made_men_{fam}")), (fam, made)
        want = round(made * figure(conn, f"associates_per_man_{fam}"))
        assert abs(_count(conn, fam, "associate") - want) <= 1, (fam, _count(conn, fam, "associate"), want)


def test_capo_rule():
    conn, _ = _open()
    for fam in FAMILIES:
        made = _count(conn, fam, *MADE)
        expect = max(int(figure(conn, "capo_minimum_per_family")), math.ceil(made / figure(conn, "capo_one_per_men")))
        assert _count(conn, fam, "capo") == expect, (fam, _count(conn, fam, "capo"), expect)


def test_structure_is_complete():
    conn, _ = _open()
    for fam in FAMILIES:
        o = _outfit(conn, fam)
        rows = conn.execute("SELECT r.*, s.rank_key AS srank, s.outfit_actor_id AS sout, s.crew_id AS screw FROM outfit_ranks r "
                            "LEFT JOIN outfit_ranks s ON s.actor_id=r.superior_actor_id WHERE r.outfit_actor_id=?", (o,)).fetchall()
        boss = [r for r in rows if r["rank_key"] == "boss"]
        assert len(boss) == 1
        for r in rows:
            if r["rank_key"] in ("soldier", "capo"):
                assert r["crew_id"] is not None, dict(r)
            if r["rank_key"] == "capo":
                assert r["srank"] == "boss", dict(r)
            if r["rank_key"] == "soldier":
                assert r["srank"] == "capo" and r["screw"] == r["crew_id"], dict(r)
            if r["rank_key"] == "associate":
                assert r["srank"] in ("soldier", "capo") and r["sout"] == o and r["screw"] == r["crew_id"], dict(r)
        crews = conn.execute("SELECT * FROM outfit_crews WHERE outfit_actor_id=?", (o,)).fetchall()
        assert crews
        for c in crews:
            leaders = [r for r in rows if r["crew_id"] == c["id"] and r["rank_key"] == "capo"]
            assert len(leaders) == 1 and leaders[0]["actor_id"] == c["leader_actor_id"]
            assert c["ground_location_id"] is not None


def test_seeded_examples_hold_their_seats():
    conn, _ = _open()
    assert _rank_of(conn, "Carmine Sabatini") == "boss" and _rank_of(conn, "Lorenzo DeLuca") == "capo"
    assert _rank_of(conn, "Johnny Drago") == "associate" and _rank_of(conn, "Carlo Spatafore") == "soldier"
    for fam in FAMILIES:
        for rank in ("boss", "underboss", "consigliere"):
            assert _count(conn, fam, rank) == 1, (fam, rank)


def test_levels_and_rhythm():
    conn, _ = _open()
    rows = conn.execute("SELECT r.rank_key,r.level,s.cadence_days,s.quiet_routine,s.tier FROM outfit_ranks r "
                        "JOIN simulation_profiles s ON s.actor_id=r.actor_id WHERE %s" % FAMILY_ONLY).fetchall()
    assert rows and len(rows) == conn.execute("SELECT COUNT(*) FROM outfit_ranks r WHERE %s" % FAMILY_ONLY).fetchone()[0]
    for r in rows:
        if r["rank_key"] in ("boss", "underboss", "consigliere", "capo"):
            assert (r["level"], r["cadence_days"], r["quiet_routine"], r["tier"]) == (4, 1, 1, "ACTIVE"), dict(r)
        else:
            assert (r["level"], r["cadence_days"], r["quiet_routine"], r["tier"]) == (3, 7, 1, "STRATEGIC"), dict(r)


def test_all_made_men_are_male_and_italian():
    conn, pkg = _open()
    italian = set(pkg.name_groups["italian"]["family"])
    made = conn.execute("SELECT a.id,a.name,l.demographic_sex FROM outfit_ranks r JOIN actors a ON a.id=r.actor_id "
                        "JOIN actor_life_profiles l ON l.actor_id=a.id WHERE r.rank_key<>'associate' AND %s" % FAMILY_ONLY).fetchall()
    assert made
    pulled = {r[0] for r in conn.execute("SELECT actor_id FROM person_resolution_provenance WHERE resolution_reason='outfit_opening'")}
    assert len(pulled) > 100
    for m in made:  # seeded Example men keep their own names; everyone pulled up is from the italian group
        assert m["demographic_sex"] == "male", dict(m)
        if m["id"] in pulled:
            assert m["name"].split()[-1] in italian, dict(m)
    assoc = conn.execute("SELECT l.demographic_sex FROM outfit_ranks r JOIN actor_life_profiles l ON l.actor_id=r.actor_id "
                         "WHERE r.rank_key='associate' AND %s" % FAMILY_ONLY).fetchall()
    assert sum(1 for a in assoc if a[0] == "male") / len(assoc) >= 0.99


def test_feelings_toward_superior_exist():
    conn, _ = _open()
    rows = conn.execute("SELECT actor_id,superior_actor_id FROM outfit_ranks r WHERE superior_actor_id IS NOT NULL AND %s" % FAMILY_ONLY).fetchall()
    assert rows
    for r in rows:
        assert conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
                            (r["actor_id"], r["superior_actor_id"])).fetchone(), dict(r)
    assert conn.execute("SELECT COUNT(*) FROM outfit_ranks r WHERE superior_actor_id IS NULL AND rank_key<>'boss' AND %s" % FAMILY_ONLY).fetchone()[0] == 0


def _fingerprint(db: Path) -> str:
    conn = connect(db)
    h = hashlib.sha256()
    for sql in ("SELECT * FROM outfit_crews ORDER BY id", "SELECT * FROM outfit_ranks ORDER BY actor_id",
                "SELECT a.name,r.* FROM relationships r JOIN actors a ON a.id=r.actor_a_id "
                "WHERE r.actor_a_id IN (SELECT actor_id FROM outfit_ranks) ORDER BY r.id",
                "SELECT a.name,d.* FROM actor_drives d JOIN actors a ON a.id=d.actor_id "
                "WHERE d.actor_id IN (SELECT actor_id FROM outfit_ranks) ORDER BY d.actor_id"):
        for row in conn.execute(sql).fetchall():
            h.update(json.dumps(list(row), default=repr).encode())
    return h.hexdigest()


def test_opening_is_deterministic():
    from tools.build_opening import build_opening
    tmp = Path(tempfile.mkdtemp())
    prints = []
    prior = {n: os.environ.get(n) for n in ("CAERNESS_DB_PATH", "CAERNESS_WORLD_PACKAGE")}
    try:
        for i in (1, 2):
            db = tmp / f"o{i}.db"
            build_opening(db, package="saintjude")
            prints.append(_fingerprint(db))
    finally:
        for n, v in prior.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v
    assert prints[0] == prints[1]
    conn = connect(tmp / "o1.db")
    assert conn.execute("SELECT COUNT(*) FROM outfit_ranks").fetchone()[0] > 500


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print("ok", t.__name__)
    print(f"{len(TESTS)} passed")
