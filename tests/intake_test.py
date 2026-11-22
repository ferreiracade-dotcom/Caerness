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
