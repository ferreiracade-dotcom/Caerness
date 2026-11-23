"""Prison J1.1: facilities and inside societies exist, once, from package data.

Run: PYTHONPATH=. python tests/j1_facilities_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world  # noqa: E402

from engine import prison  # noqa: E402


def test_facilities_materialise_once():
    w = open_world()
    c = w.conn
    first = prison.ensure_facilities(c)
    again = prison.ensure_facilities(c)
    assert first == again and first, first
    cfg = prison.rules(c)
    assert set(first) == set(cfg["facilities"]), set(first) ^ set(cfg["facilities"])
    assert c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == len(cfg["facilities"])
    for key, spec in cfg["facilities"].items():
        row = c.execute("SELECT * FROM facilities WHERE key=?", (key,)).fetchone()
        inst = c.execute("SELECT actor_type FROM actors WHERE id=?", (row["institution_actor_id"],)).fetchone()
        assert inst["actor_type"] == "institution"
        groups = c.execute("SELECT * FROM facility_groups WHERE facility_id=?", (row["id"],)).fetchall()
        assert sorted(g["group_key"] for g in groups) == sorted(spec["groups"]), key
        for g in groups:
            prof = c.execute("SELECT org_kind,sphere FROM org_profiles WHERE org_actor_id=?", (g["org_actor_id"],)).fetchone()
            assert prof["org_kind"] == cfg["society"]["kind"], dict(prof)
        # the groups' headcounts add up to about the facility's headcount (rounding only)
        assert abs(sum(g["headcount"] for g in groups) - row["headcount"]) <= len(groups), key
    assert c.execute("SELECT COUNT(*) FROM org_seats s JOIN facility_groups f ON f.org_actor_id=s.org_actor_id").fetchone()[0] == 0


def test_society_kind_is_known_to_the_org_core():
    from engine import orgs
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    org = c.execute("SELECT org_actor_id FROM facility_groups LIMIT 1").fetchone()[0]
    rules = orgs.kind_rules(c, org)
    assert rules.get("head") and "held_decision" not in (rules.get("lifecycle") or {}), rules


def test_missing_fallback_is_loud():
    from engine import world_package
    w = open_world()
    c = w.conn
    real = prison.rules
    prison.rules = lambda conn: {k: v for k, v in real(conn).items() if k != "fallback_facility"}
    try:
        try:
            prison.ensure_facilities(c)
        except KeyError:
            return
        raise AssertionError("no error for a package with no fallback facility")
    finally:
        prison.rules = real


def test_enabled_needs_data_and_the_outfits_switch():
    w = open_world()
    assert prison.enabled(w.conn)


def main() -> None:
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            ran += 1
            print("ok", name)
    print(f"{ran} tests passed")


if __name__ == "__main__":
    main()
