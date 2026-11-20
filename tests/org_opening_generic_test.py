"""The opening builder is data-driven (task D1): an organisation with invented role words is built from data alone.

Run: CAERNESS_DB_PATH=<scratch>.db PYTHONPATH=. python tests/org_opening_generic_test.py   (builds a scratch Saint Jude opening
and adds a made-up guild to it; the guild's roles exist only in this test's data)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine import outfit_opening as oo
from engine.world_package import org_rules, outfit_rules, package_for

FIG = {"guild_members": 20, "guild_dependents": 0.5, "guild_leader_min": 2, "guild_per_leader": 8, "guild_clerks": 3, "guild_wardens": 2}

KIND = {
    "sphere": "test", "head": "warden", "unit_leader": "bailiff", "labels": {},
    "opening": {
        "layout": "units", "executives": ["warden", "clerk"], "member_role": "sergeant", "dependent_role": "runner",
        "unit_label": "{surname} ward", "own_group_share": 0.7, "inducted_after_age": 20,
        "leader_minimum_figure": "guild_leader_min", "members_per_leader_figure": "guild_per_leader",
        "in_roles": ["bailiff"],
        "roles": {
            "warden": {"ages": [45, 70], "sex": "male", "level": 4, "inducted": True},
            "clerk": {"ages": [40, 70], "sex": "male", "level": 4, "inducted": True},
            "bailiff": {"ages": [35, 60], "sex": "male", "level": 4, "inducted": True},
            "sergeant": {"ages": [25, 60], "sex": "male", "level": 3, "inducted": True},
            "runner": {"ages": [17, 40], "male_share_key": "runner", "level": 3, "standing": {"mean": 0.3, "sd": 0.2}},
        },
    },
}
RANKS = {
    "sphere": "test", "head": "reeve", "unit_leader": None, "labels": {},
    "opening": {"layout": "ranks", "male_share_key": "ranks",
                "roles": {"reeve": {"ages": [40, 65]}, "hayward": {"ages": [25, 50], "superior": {"role": "reeve", "pick": "first"}}}},
}


def _open():
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect(path)
    oo.figure = lambda c, key, default=None: FIG[key]  # made-up figures for the made-up guild
    return conn


def _institution(conn, name):
    loc = conn.execute("SELECT id FROM locations LIMIT 1").fetchone()[0]
    return conn.execute("INSERT INTO actors(name,actor_type,status,home_location_id,current_location_id) VALUES (?, 'institution','active',?,?)",
                        (name, loc, loc)).lastrowid


def test_units_layout_from_invented_words():
    conn = _open()
    _institution(conn, "Hollow Guild")
    ground = conn.execute("SELECT name FROM locations ORDER BY id LIMIT 2").fetchall()
    spec = {"institution": "Hollow Guild", "shape": "guild", "members_figure": "guild_members", "dependents_figure": "guild_dependents",
            "name_group": "italian", "ground": [r[0] for r in ground]}
    rules = {"male_share": {"runner": 1.0}, "seed_role_to_rank": {}}
    res = oo.build_org(conn, "hollow", spec, rules, 0, kind=KIND)
    oid = oo.outfit_actor(conn, "Hollow Guild")
    by = dict(conn.execute("SELECT role_key,COUNT(*) FROM org_seats WHERE org_actor_id=? GROUP BY role_key", (oid,)).fetchall())
    assert by["warden"] == 1 and by["clerk"] == 1, by
    assert by["bailiff"] == res["units"] == 3, (by, res["units"])  # ceil(20 / 8) = 3 > the minimum of 2
    assert by["sergeant"] == 20 - 2 - 3, by
    assert by["runner"] == 10, by
    assert set(by) == {"warden", "clerk", "bailiff", "sergeant", "runner"}
    assert res["counts"] == by
    labels = [r[0] for r in conn.execute("SELECT label FROM org_units WHERE org_actor_id=?", (oid,))]
    assert all(label.endswith(" ward") for label in labels), labels
    head = conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='warden'", (oid,)).fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND role_key='clerk' AND superior_actor_id=?", (oid, head)).fetchone()[0] == 1
    sub = conn.execute("SELECT a.subtype FROM org_seats s JOIN actors a ON a.id=s.actor_id WHERE s.org_actor_id=? AND s.role_key='bailiff' LIMIT 1", (oid,)).fetchone()[0]
    assert sub == "Bailiff in the Hollow Guild", sub


def test_ranks_layout_from_invented_words():
    conn = _open()
    _institution(conn, "Moot of the Reeves")
    spec = {"institution": "Moot of the Reeves", "shape": "moot", "name_group": "italian", "ground": [],
            "ranks": {"reeve": {"count": 1, "level": 4}, "hayward": {"count": 4, "level": 3}}}
    rules = {"male_share": {"ranks": 1.0}, "seed_role_to_rank": {}}
    res = oo.build_org(conn, "moot", spec, rules, 0, kind=RANKS)
    oid = oo.outfit_actor(conn, "Moot of the Reeves")
    reeve = conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='reeve'", (oid,)).fetchone()[0]
    assert res["counts"] == {"reeve": 1, "hayward": 4} and res["units"] is None
    assert conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND role_key='hayward' AND superior_actor_id=?", (oid, reeve)).fetchone()[0] == 4


def test_package_declares_an_opening_layout_for_every_outfit_kind():
    conn = _open()
    pkg = package_for(conn)
    kinds = org_rules(pkg)["kinds"]
    for key, spec in outfit_rules(pkg)["outfits"].items():
        assert (kinds[spec["shape"]].get("opening") or {}).get("layout") in ("units", "ranks"), key


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
