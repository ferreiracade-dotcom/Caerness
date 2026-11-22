"""P1 Task 3: voter groups as information-1b audiences; turnout and delivery driven by figures.

Run: PYTHONPATH=. python tests/p1_electorate_test.py"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

WARD1 = "office:council:ward-1"


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def _gid(c, key):
    return int(c.execute("SELECT id FROM voter_groups WHERE group_key=?", (key,)).fetchone()[0])


def _race(c, candidates: dict[int, list[str]], day=100, key=WARD1) -> int:
    oid = int(c.execute("SELECT id FROM offices WHERE office_key=?", (key,)).fetchone()[0])
    rid = int(c.execute("INSERT INTO races(office_id,election_day,stage) VALUES (?,?,?)", (oid, day + 200, "campaign")).lastrowid)
    for a, ag in candidates.items():
        c.execute("INSERT INTO race_candidates(race_id,actor_id,filed_day,agenda_json) VALUES (?,?,?,?)", (rid, a, day, json.dumps(ag)))
    return rid


def test_groups_from_data():
    w = _open_world()
    c = w.conn
    pol = json.loads((ROOT / "worlds" / "saintjude" / "politics.json").read_text(encoding="utf-8"))
    n = c.execute("SELECT COUNT(*),SUM(size),COUNT(audience_id) FROM voter_groups").fetchone()
    assert n[0] == len(pol["voter_groups"]["groups"]) == 30 and n[1] == 775500 and n[2] == 30, tuple(n)
    assert c.execute("SELECT COUNT(*) FROM voter_groups WHERE location_id IS NULL").fetchone()[0] == 0


def test_group_is_an_i1b_audience():
    from engine import civic_seams, claims, electorate
    w = _open_world()
    c = w.conn
    gid = _gid(c, "ward-1:irish-catholic-working")
    aud = civic_seams.group_audience(c, gid)
    assert aud["key"] == "electorate" and aud["ref"] == gid
    day = int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    before = civic_seams.group_regard(c, gid, w.boss, day)
    civic_seams.tell_group(c, gid, w.boss, "He took the contract money.", source="press", confidence=0.9, valence=-0.8, day=day)
    assert civic_seams.group_regard(c, gid, w.boss, day) < before
    # membership: a man living in the group's district with no age words belongs to it
    loc = int(c.execute("SELECT location_id FROM voter_groups WHERE id=?", (gid,)).fetchone()[0])
    c.execute("UPDATE actors SET home_location_id=? WHERE id=?", (loc, w.soldier))
    assert claims.is_member(c, w.soldier, aud)
    assert not claims.is_member(c, w.soldier, civic_seams.group_audience(c, _gid(c, "ward-14:protestant-wealthy")))
    # a candidate in a ward is held in view by that ward's groups, and the rule yields them
    _race(c, {w.soldier: ["jobs"]})
    keys = {a["ref"] for a in claims.audiences_of(c, w.soldier) if a["key"] == "electorate"}
    assert gid in keys and _gid(c, "ward-14:protestant-wealthy") not in keys


def test_no_impression_store_in_p1():
    w = _open_world()
    c = w.conn
    cols = {r[1] for r in c.execute("PRAGMA table_info(voter_groups)")}
    assert not {"regard", "impression", "opinion", "support"} & cols, cols
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not [n for n in names if "impression" in n and "voter" in n]


def test_existing_audience_rules_unchanged():
    from engine import claims
    w = _open_world()
    c = w.conn
    assert set(claims._RULES) == {"voter_group"}
    kinds = {a["key"] for a in claims.audiences_of(c, w.soldier)}
    assert "electorate" not in kinds  # a man who stands nowhere is in no electorate's view


def test_delivery_falls_with_jobs():
    from engine import electorate
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    gid = _gid(c, "ward-1:irish-catholic-working")
    kind = json.loads((ROOT / "worlds" / "saintjude" / "politics.json").read_text(encoding="utf-8"))["patronage_line_kind"]
    unit = int(c.execute("SELECT id FROM org_units WHERE org_actor_id=? ORDER BY id LIMIT 1", (machine,)).fetchone()[0])
    bare = electorate.delivery(c, gid, "org", machine)
    for i in range(40):
        c.execute("INSERT INTO org_lines(unit_id,description,weekly_take,status,started_day) VALUES (?,?,0,'active',0)", (unit, f"{kind} {i}"))
    full = electorate.delivery(c, gid, "org", machine)
    assert full > bare > 0, (full, bare)
    c.execute("UPDATE org_lines SET status='ended' WHERE description LIKE ?", (kind + "%",))
    assert abs(electorate.delivery(c, gid, "org", machine) - bare) < 1e-9
    # a group no one holds delivers nothing
    assert electorate.delivery(c, gid, "org", _org(c, "taxpayers")) == 0.0


def test_turnout_rises_with_grievance_at_stake():
    from engine import electorate
    w = _open_world()
    c = w.conn
    gid = _gid(c, "ward-1:irish-catholic-working")  # grievances: jobs, taxes
    quiet = _race(c, {w.soldier: ["parks"]})
    loud = _race(c, {w.capo: ["jobs", "taxes"]}, key="office:council:ward-2")
    day = 200 + 100  # a summer day: no winter term in either
    a, b = electorate.turnout(c, gid, quiet, day), electorate.turnout(c, gid, loud, day)
    assert b > a > 0, (a, b)
    assert 0.0 < electorate.turnout(c, gid, loud, day) < 1.0
    assert electorate.turnout(c, gid, loud, 0 + 20) < electorate.turnout(c, gid, loud, day)  # January


def test_protagonist_held_alike():
    from engine import claims, civic_field, electorate, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    _race(c, {w.capo: ["jobs"], w.soldier: ["jobs"]})
    mine = sorted(a["ref"] for a in claims.audiences_of(c, w.capo) if a["key"] == "electorate")
    his = sorted(a["ref"] for a in claims.audiences_of(c, w.soldier) if a["key"] == "electorate")
    assert mine == his and mine
    # a delivery stake in his own hand brings out a group exactly as an NPC's would
    gid = _gid(c, "ward-1:irish-catholic-working")
    machine = _org(c, "county_party")
    sid = int(c.execute("SELECT id FROM field_holdings WHERE holder_id=? AND stake_kind='delivery' AND stake_ref='ward-1:irish-catholic-working' AND ended_day IS NULL", (machine,)).fetchone()[0])
    civic_field.transfer(c, sid, "actor", w.capo, day=5, cause_kind="gift")
    assert electorate.delivery(c, gid, "actor", w.capo) > 0
    assert electorate.drive(c, gid) > 0


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
