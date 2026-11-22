"""P1 Task 2: the field's actors and their holdings; the Machine is only package data.

Run: PYTHONPATH=. python tests/p1_field_test.py"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def test_machine_is_only_data():
    from engine import civic_field
    w = _open_world()
    c = w.conn
    pol = json.loads((ROOT / "worlds" / "saintjude" / "politics.json").read_text(encoding="utf-8"))
    names = [s["institution"] for s in pol["polity_orgs"].values()] + list(pol["polity_orgs"])
    for f in (ROOT / "engine").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for n in names:
            assert n not in text, f"{n!r} named in {f.name}"
    machine = _org(c, "county_party")
    held = {(r["stake_kind"], r["stake_ref"]) for r in civic_field.holdings_of(c, "org", machine)}
    want = {(h["stake_kind"], h["stake_ref"]) for h in pol["holdings_1975"] if h["holder"].get("org") == "county_party" and h["stake_kind"] != "delivery"}
    assert want <= held, want - held
    assert civic_field.strength(c, "org", machine) > civic_field.strength(c, "org", _org(c, "reform_clubs")) > 0


def test_any_stake_can_move():
    from engine import civic_field, offices
    w = _open_world()
    c = w.conn
    machine, club = _org(c, "county_party"), _org(c, "reform_clubs")
    sid = int(c.execute("SELECT id FROM field_holdings WHERE holder_id=? AND stake_ref='office:party:ward-leader-5' AND ended_day IS NULL", (machine,)).fetchone()[0])
    before = offices.holder(c, "office:party:ward-leader-5")
    new = civic_field.transfer(c, sid, "org", club, day=50, cause_kind="defeat", cause_id=7)
    old = c.execute("SELECT * FROM field_holdings WHERE id=?", (sid,)).fetchone()
    assert old["ended_day"] == 50 and old["cause_kind"] == "defeat"
    nw = c.execute("SELECT * FROM field_holdings WHERE id=?", (new,)).fetchone()
    assert nw["holder_id"] == club and nw["cause_id"] == 7 and nw["since_day"] == 50
    assert civic_field.holder_of(c, "party_office", "office:party:ward-leader-5") == ("org", club)
    assert offices.holder(c, "office:party:ward-leader-5") not in (None, before)


def test_politics_runs_with_an_org_holding_nothing():
    from engine import civic_field
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    for r in civic_field.holdings_of(c, "org", machine):
        civic_field.weaken(c, int(r["id"]), 99.0, day=10, cause_kind="test")
    assert civic_field.strength(c, "org", machine) == 0.0
    assert civic_field.holdings_of(c, "org", machine) == []
    assert civic_field.seed_field(c, 11)["unresolved"] == 0  # reseeding the opening data is idempotent about the holder's state


def test_protagonist_can_hold_stakes():
    from engine import civic_field, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    machine = _org(c, "county_party")
    sid = int(c.execute("SELECT id FROM field_holdings WHERE holder_id=? AND stake_kind='patronage' AND ended_day IS NULL", (machine,)).fetchone()[0])
    new = civic_field.transfer(c, sid, "actor", w.capo, day=20, cause_kind="gift")
    assert civic_field.holder_of(c, "patronage", c.execute("SELECT stake_ref FROM field_holdings WHERE id=?", (new,)).fetchone()[0]) == ("actor", w.capo)
    assert civic_field.strength(c, "actor", w.capo) > 0
    npc = civic_field.transfer(c, int(c.execute("SELECT id FROM field_holdings WHERE holder_id=? AND stake_kind='patronage' AND ended_day IS NULL", (machine,)).fetchone()[0]),
                               "actor", w.soldier, day=20, cause_kind="gift")
    assert c.execute("SELECT holder_kind FROM field_holdings WHERE id=?", (npc,)).fetchone()[0] == "actor"


if __name__ == "__main__":
    failed = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f()
                print("PASS", n)
            except Exception:
                failed += 1
                print("FAIL", n)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
