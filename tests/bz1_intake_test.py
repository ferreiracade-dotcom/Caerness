"""BZ1.8: the intake's holding and arrangement shapes get real makers.

Run: PYTHONPATH=. python tests/bz1_intake_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world


def _fund(conn, who, amount):
    from engine import ledger
    ledger.receive(conn, ("person", int(who)), amount, purpose="test funding")


def _held(c, hid):
    return c.execute("SELECT * FROM held_things WHERE id=?", (hid,)).fetchone()


def test_author_building_is_held_place():
    from engine import authoring
    w = _open_world()
    c = w.conn
    _fund(c, w.soldier, 5000.0)
    out = authoring.author(c, w.soldier, "a garage on the waterfront", {
        "what": "Vince's garage", "place": w.ground, "money": {"start": 1000, "upkeep": 40}}, "bz8-1")
    h = _held(c, out["held_thing_id"])
    assert h["backing_table"] == "place_details" and h["gap_key"] is None, dict(h)
    d = c.execute("SELECT place_kind,owner_ref,upkeep_usd_30 FROM place_details WHERE building_id=?", (h["backing_id"],)).fetchone()
    assert d["place_kind"] == "garage" and d["owner_ref"] == f"person:{w.soldier}" and abs(d["upkeep_usd_30"] - 40 * 30 / 7) < 0.01


def test_author_deal_is_held_term():
    from engine import authoring, held_things
    w = _open_world()
    c = w.conn
    out = authoring.author(c, w.capo, "a deal", {
        "what": "the Friday envelope", "people": [w.soldier], "money": {"income": 100}, "consequences": ["he goes to the street"]}, "bz8-2")
    h = _held(c, out["held_thing_id"])
    assert h["backing_table"] == "agreement_terms", dict(h)
    t = c.execute("SELECT * FROM agreement_terms WHERE id=?", (h["backing_id"],)).fetchone()
    assert t["debtor_ref"] == f"person:{w.soldier}" and t["creditor_ref"] == f"person:{w.capo}" and t["amount_usd"] == 100.0
    assert t["breach_word"] == "street"
    before = c.execute("SELECT COUNT(*) FROM economic_flows").fetchone()[0]
    held_things.process_due(c, 7)  # the weekly tick must not also pay what the term pays
    assert c.execute("SELECT COUNT(*) FROM economic_flows").fetchone()[0] == before


def test_author_build_goes_through_venture():
    from engine import authoring, simulation
    w = _open_world()
    c = w.conn
    _fund(c, w.soldier, 20000.0)
    day0 = int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    cash = lambda: __import__("engine.ledger", fromlist=["x"]).balance(c, ("person", w.soldier))
    out = authoring.author(c, w.soldier, "a new storefront", {
        "what": "Corner Shop Refit", "place": w.ground, "ready_in_days": 120, "money": {"start": 8000}}, "bz8-3")
    h = _held(c, out["held_thing_id"])
    assert h["backing_table"] == "venture_details" and h["status"] == "building", dict(h)
    after_door = cash()
    c.commit()
    simulation.advance_connection(c, 400)
    h = _held(c, out["held_thing_id"])
    v = c.execute("SELECT outcome,outcome_reason,spent_usd FROM venture_details WHERE project_id=?", (h["backing_id"] if h["backing_table"] == "venture_details" else
                  c.execute("SELECT project_id FROM venture_details ORDER BY project_id DESC LIMIT 1").fetchone()[0],)).fetchone()
    assert v["outcome"] is not None, dict(v)
    assert abs(after_door - 12000.0) < 1.0  # charged once, at the door
    if v["outcome"] == "completed":
        assert h["backing_table"] == "place_details" and h["status"] in ("active", "failing", "ended"), dict(h)
    else:
        assert h["status"] == "ended" and h["ended_reason"], dict(h)


def test_claim_breach_bumps_gap():
    from engine import agreement_terms
    w = _open_world()
    c = w.conn
    tid = agreement_terms.add_term(c, ref_kind="test", ref_id=None, debtor_ref=f"person:{w.soldier}", creditor_ref=f"person:{w.capo}",
                                   amount_usd=50.0, first_due_day=7, every_days=7, grace_days=7, breach_word="sue", purpose="a debt", day=0)
    agreement_terms.process_due_terms(c, 60)
    row = c.execute("SELECT count,shape FROM depth_gaps WHERE gap_key='civil claim'").fetchone()
    assert row is not None and row["count"] >= 1 and row["shape"] == "arrangement", row and dict(row)


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
