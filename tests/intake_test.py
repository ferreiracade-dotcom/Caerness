"""The intake core (I-1): held things, depth gaps, the shape registry, the weekly B tick.

Run: PYTHONPATH=. python tests/intake_test.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world as _open_world


def _fund(conn, actor, amount):
    """The fixture opening leaves purses empty; a test that spends gives its person coin first."""
    from engine import ledger
    ledger.receive(conn, ("person", int(actor)), amount, purpose="test funding")


def _caerness():
    """A Caerness copy (the live data/caerness.db is only read, never written) with a protagonist; returns (conn, me)."""
    tmp = tempfile.mkdtemp()
    db = Path(tmp) / "c.db"
    shutil.copy2(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    from engine.db import connect, init_db
    from engine.player import set_player
    init_db()
    conn = connect()
    me = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0])
    set_player(conn, me)
    conn.commit()
    return conn, me


def test_tables_exist_and_saintjude_has_intake_rules():
    from engine.world_package import intake_rules, package_for
    w = _open_world()
    c = w.conn
    for t in ("held_things", "depth_gaps"):
        assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone(), t
    r = intake_rules(package_for(c))
    assert set(r) >= {"shape_words", "readers", "tick"}
    assert r["tick"]["arrears_weeks_to_fail"] == 4


def test_caerness_has_no_intake_rules():
    from engine.world_package import intake_rules, package_for
    conn, _me = _caerness()
    assert intake_rules(package_for(conn)) == {}


def test_words_and_fields_pick_the_shape():
    from engine import intake
    w = _open_world()
    c = w.conn
    assert intake.shape_for(c, "a numbers bank", {"members": [w.soldier]}).name == "organisation"
    assert intake.shape_for(c, "the warehouse on Ferry Street", {}).name == "holding"
    assert intake.shape_for(c, "a ten percent deal", {}).name == "arrangement"
    assert intake.shape_for(c, "the Saint Rocco truce", {}).name == "custom"
    s = intake.shape_for(c, "something nobody has a word for", {})
    assert s.name == "thing" and s.floor_backed


def test_registering_a_maker_replaces_the_floor_shape():
    from engine import intake
    w = _open_world()
    c = w.conn
    intake.register_shape(intake.Shape("holding", (), (), lambda conn, me, p, cid: {"backing_table": "x", "backing_id": 1}, False))
    try:
        assert intake.shape_for(c, "a pier", {}).floor_backed is False
    finally:
        intake._reset_registry_for_tests()
    assert intake.shape_for(c, "a pier", {}).floor_backed is True


def test_money_words_parse_to_start_and_weekly():
    from engine import intake
    w = _open_world()
    c = w.conn
    p = intake.normalise(c, w.capo, "a bookmaking wire", {"what": "a wire", "money": {"start": 500, "income": "1,000 a month", "upkeep": "$200 a week"}})
    assert p.start_cost == 500 and abs(p.income_weekly - 1000 * 7 / 30) < 0.01 and p.upkeep_weekly == 200
    _fund(c, w.capo, 1000)
    q = intake.normalise(c, w.capo, "x", {"what": "x", "money": {"start": "half", "from": "me"}})
    assert q.start_cost > 0


def test_an_unknown_place_is_kept_as_words_not_refused():
    from engine import intake
    w = _open_world()
    p = intake.normalise(w.conn, w.capo, "a pier", {"what": "a pier", "place": "Nowhere Quay of the Moon"})
    assert p.location_id is None and p.place_text == "Nowhere Quay of the Moon"


def test_caerness_unclear_shape_still_input_gap():
    from engine import intake
    from engine.authoring import AuthoringRefused
    conn, _me = _caerness()
    try:
        intake.shape_for(conn, "an obscure arrangement", {})
        assert False
    except AuthoringRefused as e:
        assert e.reason_kind == "input_gap"


def test_a_floor_thing_is_held_with_people_money_place_and_a_gap():
    from engine import authoring, ledger
    w = _open_world()
    c = w.conn
    _fund(c, w.capo, 1000)
    before = ledger.balance(c, ("person", w.capo))
    out = authoring.author(c, w.capo, "a pigeon racing club for the bosses", {
        "what": "the Ferry Street pigeon club", "people": [w.capo, w.soldier], "place": w.ground,
        "money": {"start": 100, "upkeep": "20 a week"}, "agenda": "win the Shore race", "legality": "legal"}, "t3-1")
    row = c.execute("SELECT * FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert out["kind"] == "thing" and row["status"] == "active" and row["upkeep_weekly"] == 20 and row["location_id"] == w.ground
    assert ledger.balance(c, ("person", w.capo)) == before - 100
    g = c.execute("SELECT * FROM depth_gaps WHERE gap_key=?", (out["gap"],)).fetchone()
    assert g["count"] == 1 and g["status"] == "open"


def test_an_existing_shape_still_makes_its_entity_and_also_a_held_row():
    from engine import authoring
    w = _open_world()
    c = w.conn
    out = authoring.author(c, w.capo, "organisation", {"name": "The Ferry Street Social Club", "members": 2}, "t3-2")
    row = c.execute("SELECT * FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert row["shape"] == "organisation" and row["backing_table"] and row["backing_id"] and row["gap_key"] is None


def test_a_dead_owner_and_a_duplicate_are_refused_by_name():
    from engine import authoring
    w = _open_world()
    c = w.conn
    authoring.author(c, w.capo, "a card game", {"what": "the Tuesday card game", "people": [w.capo]}, "t3-3")
    try:
        authoring.author(c, w.capo, "a card game", {"what": "the Tuesday card game", "people": [w.capo]}, "t3-4")
        assert False
    except authoring.AuthoringRefused as e:
        assert "already held" in str(e)
    c.execute("UPDATE actors SET status='deceased' WHERE id=?", (w.soldier,))
    try:
        authoring.author(c, w.capo, "a card game", {"what": "another game", "people": [w.soldier]}, "t3-5")
        assert False
    except authoring.AuthoringRefused as e:
        assert "dead" in str(e)


def test_an_oversized_start_is_scaled_down_with_its_reason():
    from engine import authoring
    w = _open_world()
    c = w.conn
    _fund(c, w.soldier, 300)
    out = authoring.author(c, w.soldier, "a stake in a trucking fleet", {
        "what": "a stake in the Route 9 fleet", "money": {"start": 10_000_000, "income": "500 a week"}}, "t3-6")
    assert out["status"] == "scaled_down" and "part" in out["scaled"]
    assert c.execute("SELECT income_weekly FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()[0] < 500


def test_caerness_unclear_kind_is_still_an_input_gap():
    from engine import authoring
    conn, me = _caerness()
    try:
        authoring.author(conn, me, "an obscure arrangement", {}, "t3-7")
        assert False
    except authoring.AuthoringRefused as e:
        assert getattr(e, "reason_kind", "") == "input_gap"
    assert conn.execute("SELECT COUNT(*) FROM depth_gaps").fetchone()[0] == 0


def test_the_same_call_id_twice_holds_one_thing_and_one_gap_bump():
    from engine import authoring
    w = _open_world()
    c = w.conn
    a = authoring.author(c, w.capo, "a pigeon club", {"what": "the Shore pigeon club"}, "t3-8")
    b = authoring.author(c, w.capo, "a pigeon club", {"what": "the Shore pigeon club"}, "t3-8")
    assert b["held_thing_id"] == a["held_thing_id"]
    assert c.execute("SELECT COUNT(*) FROM held_things WHERE call_id='t3-8'").fetchone()[0] == 1
    assert c.execute("SELECT count FROM depth_gaps WHERE gap_key=?", (a["gap"],)).fetchone()[0] == 1


def test_unread_consequences_flag_a_gap_and_illegal_adds_heat_reader():
    from engine import authoring
    w = _open_world()
    c = w.conn
    out = authoring.author(c, w.capo, "organisation", {"name": "The Dock Social Club", "members": 2, "legality": "illegal",
                                                       "consequences": ["the cops will raid it", "the saints weep"]}, "t3-9")
    r = c.execute("SELECT readers_json,unmapped_json FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert "heat" in r["readers_json"] and "saints weep" in r["unmapped_json"] and out.get("gap")


def test_a_held_thing_earns_and_pays_each_week():
    from engine import authoring, held_things, ledger
    w = _open_world()
    c = w.conn
    authoring.author(c, w.capo, "a jukebox route", {"what": "the Ward 3 jukebox route", "money": {"income": "300 a week", "upkeep": "100 a week"}}, "t4-1")
    b = ledger.balance(c, ("person", w.capo))
    held_things.process_due(c, DAY + 7)
    assert abs(ledger.balance(c, ("person", w.capo)) - (b + 200)) < 0.01


def test_a_thing_that_cannot_pay_fails_then_ends_and_its_owner_is_told():
    from engine import authoring, held_things
    w = _open_world()
    c = w.conn
    out = authoring.author(c, w.soldier, "a racing pigeon loft", {"what": "the loft", "money": {"upkeep": "1,000,000 a week"}}, "t4-2")
    for k in range(1, 6):
        held_things.process_due(c, DAY + 7 * k)
    row = c.execute("SELECT status,ended_reason FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert row["status"] == "ended" and "pay its way" in row["ended_reason"]
    assert c.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE '%the loft is over%'", (w.soldier,)).fetchone()


def test_a_dead_owners_thing_passes_to_the_next_of_its_people():
    from engine import authoring, held_things
    w = _open_world()
    c = w.conn
    out = authoring.author(c, w.capo, "a social club", {"what": "the Vesuvio room", "people": [w.capo, w.soldier]}, "t4-3")
    c.execute("UPDATE actors SET status='deceased' WHERE id=?", (w.capo,))
    held_things.process_due(c, DAY + 7)
    assert c.execute("SELECT owner_actor_id FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()[0] == w.soldier


def test_a_thing_with_no_one_left_ends_with_its_reason_not_a_dead_mans_purse():
    from engine import authoring, held_things
    w = _open_world()
    c = w.conn
    out = authoring.author(c, w.soldier, "a loft", {"what": "the lonely loft", "money": {"income": "50 a week"}}, "t4-3b")
    c.execute("DELETE FROM org_seats WHERE actor_id=?", (w.soldier,))
    c.execute("UPDATE actors SET status='deceased' WHERE id=?", (w.soldier,))
    held_things.process_due(c, DAY + 7)
    row = c.execute("SELECT status,ended_reason FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()
    assert row["status"] == "ended" and "no one took it up" in row["ended_reason"]


def test_an_illegal_thing_draws_heat_on_its_owners_organisation():
    from engine import authoring, held_things, org_heat
    w = _open_world()
    c = w.conn
    authoring.author(c, w.capo, "a chop shop", {"what": "the Route 1 chop shop", "legality": "illegal", "money": {"income": "400 a week"}}, "t4-4")
    h0 = org_heat.read(c, w.org, DAY + 7)["investigative_heat"]
    held_things.process_due(c, DAY + 7)
    assert org_heat.read(c, w.org, DAY + 7)["investigative_heat"] > h0


def test_caerness_registers_no_held_things_work():
    from engine import held_things
    conn, _me = _caerness()
    assert held_things.next_due_day(conn, 0, 10_000) is None


def test_a_thing_can_belong_to_the_protagonist_and_fails_like_anyone_s():
    from engine import authoring, held_things
    from engine.player import set_player
    w = _open_world()
    c = w.conn
    set_player(c, w.soldier)
    out = authoring.author(c, w.soldier, "a racing pigeon loft", {"what": "his own loft", "money": {"upkeep": "900 a week"}}, "t4-6")
    for k in range(1, 6):
        held_things.process_due(c, DAY + 7 * k)
    assert c.execute("SELECT status FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()[0] == "ended"


def test_a_free_operation_that_settles_leaves_a_held_thing():
    from engine import free_operation
    from engine.player import set_player
    w = _open_world()
    c = w.conn
    set_player(c, w.capo)
    out = free_operation.run(c, w.capo, "set up a bookmaking wire in the back of the Ferry Street candy store", {"time": "a week"}, "t5-1")
    assert out.get("commitment_id"), out  # nothing models it, so it is a commitment
    c.execute("UPDATE world_state SET current_day=current_day+8 WHERE id=1")
    done = free_operation.settle_due(c, w.capo)
    hid = done[0]["held_thing_id"]
    assert c.execute("SELECT status FROM held_things WHERE id=?", (hid,)).fetchone()[0] == "active"
    assert "now stands as" in done[0]["result"]


def test_a_building_thing_goes_live_when_its_commitment_settles():
    from engine import authoring, free_operation
    from engine.player import set_player
    w = _open_world()
    c = w.conn
    set_player(c, w.capo)
    out = authoring.author(c, w.capo, "a new pier", {"what": "the Harbour pier", "ready_in_days": 10}, "t5-2")
    assert c.execute("SELECT status FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()[0] == "building"
    c.execute("UPDATE world_state SET current_day=current_day+11 WHERE id=1")
    done = free_operation.settle_due(c, w.capo)
    assert done and done[0]["held_thing_id"] == out["held_thing_id"]
    assert c.execute("SELECT status FROM held_things WHERE id=?", (out["held_thing_id"],)).fetchone()[0] == "active"


tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
tests.sort(key=lambda f: f.__code__.co_firstlineno)


def _run_all():
    ok = 0
    for t in tests:
        try:
            t()
            ok += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
    print(f"{ok}/{len(tests)} passed")
    return ok == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
