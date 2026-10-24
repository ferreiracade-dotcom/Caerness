"""The other gangs as people at the Saint Jude opening (Saint Jude mob minimum, task 6)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine.design import figure
from engine.world_package import outfit_rules, package_for


def _open():
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect(path)
    return conn, outfit_rules(package_for(conn))["outfits"]


def _oid(conn, o) -> int:
    return int(conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='institution'", (o["institution"],)).fetchone()[0])


def _members(conn, o):
    return conn.execute("SELECT r.*, l.demographic_sex AS sex FROM outfit_ranks r JOIN actor_life_profiles l ON l.actor_id=r.actor_id "
                        "WHERE r.outfit_actor_id=?", (_oid(conn, o),)).fetchall()


def _rank_of(conn, name: str):
    r = conn.execute("SELECT r.rank_key FROM outfit_ranks r JOIN actors a ON a.id=r.actor_id WHERE a.name=?", (name,)).fetchone()
    return r[0] if r else None


def test_counts_per_rank_match_figures():
    conn, outfits = _open()
    for key, o in outfits.items():
        if o["shape"] == "family":
            continue
        rows = _members(conn, o)
        for rank, r in o["ranks"].items():
            want = r.get("count") or round(figure(conn, r["figure"]))
            assert sum(1 for m in rows if m["rank_key"] == rank) == want, (key, rank)
        assert len(rows) == sum(1 for _ in rows)


def test_seeded_gang_people_keep_their_places():
    conn, _ = _open()
    assert _rank_of(conn, "Declan Gallagher") == "elder" and _rank_of(conn, "Roy Pike") == "president"
    assert _rank_of(conn, "Walter Pettiford") == "banker"
    assert _rank_of(conn, "Brendan O'Malley") == "middle" and _rank_of(conn, "Liam Gallagher") == "young"


def test_brigades_have_no_chain_of_command():
    conn, outfits = _open()
    rows = _members(conn, outfits["brigades"])
    assert rows and all(r["superior_actor_id"] is None for r in rows)
    older = {r["actor_id"] for r in rows if r["rank_key"] in ("elder", "middle")}
    young = [r for r in rows if r["rank_key"] == "young"]
    assert young
    for y in young:
        got = {x[0] for x in conn.execute("SELECT actor_b_id FROM relationships WHERE actor_a_id=?", (y["actor_id"],))}
        assert got & older, y["actor_id"]


def test_chains_for_banks_club_and_handful():
    conn, outfits = _open()
    for key, top, below in (("combine", "banker", ("controller",)), ("bolita", "banker", ("runner",)),
                            ("russians", "senior", ("man",))):
        rows = _members(conn, outfits[key])
        tops = {r["actor_id"] for r in rows if r["rank_key"] == top}
        assert tops
        for r in rows:
            if r["rank_key"] in below:
                assert r["superior_actor_id"] in tops, (key, dict(r))
                assert conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?",
                                    (r["actor_id"], r["superior_actor_id"])).fetchone()
    rows = _members(conn, outfits["horsemen"])
    by = {r["actor_id"]: r["rank_key"] for r in rows}
    for r in rows:
        sup = by.get(r["superior_actor_id"])
        want = {"president": None, "officer": "president", "member": "officer", "prospect": "officer"}[r["rank_key"]]
        assert sup == want, dict(r)


def test_sex_shares():
    conn, outfits = _open()
    for key in ("brigades", "horsemen", "russians"):
        assert all(r["sex"] == "male" for r in _members(conn, outfits[key])), key
    rows = _members(conn, outfits["combine"]) + _members(conn, outfits["bolita"])
    assert sum(1 for r in rows if r["sex"] == "male") / len(rows) >= 0.98


def test_levels_follow_ranks():
    conn, outfits = _open()
    for key, o in outfits.items():
        if o["shape"] == "family":
            continue
        for r in _members(conn, o):
            assert r["level"] == o["ranks"][r["rank_key"]]["level"], (key, dict(r))


def test_no_chinatown_or_cuban_outfit_rows():
    conn, _ = _open()
    oid = conn.execute("SELECT id FROM actors WHERE name='Docks Chinatown Associations'").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM outfit_ranks WHERE outfit_actor_id=?", (oid,)).fetchone()[0] == 0
    assert not conn.execute("SELECT 1 FROM outfit_ranks r JOIN actors a ON a.id=r.outfit_actor_id WHERE a.name LIKE '%Cuban%'").fetchone()


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print("ok", t.__name__)
    print(f"{len(TESTS)} passed")
