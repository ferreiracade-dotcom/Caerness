"""P1 Task 0: the seam adapter reaches the intake, ventures, agreements ledger, push and approvals.

Run: PYTHONPATH=. python tests/p1_seams_test.py"""
from __future__ import annotations

import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world


def test_each_seam_reaches_its_prerequisite():
    from engine import civic_seams as S, ventures
    w = _open_world()
    c = w.conn
    day = int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    # a venture the BZ1 reader sees
    vid = S.open_venture(c, "bid_contract", w.soldier, stages_key="bid_contract", due_day=day + 30, meta={"title": "a bid", "budget_usd": 100.0})
    assert ventures.venture(c, vid)["venture_kind"] == "bid_contract"
    S.advance_venture(c, vid, "bid", day + 1, outcome={"outcome": "completed", "reason": None})
    assert ventures.venture(c, vid)["outcome"] == "completed"
    # an entry, then its breach path
    eid = S.ledger_entry(c, w.soldier, w.capo, kind="favour", terms={"note": "a vote", "breach_word": "grudge"}, due_day=day + 10, day=day)
    assert [r["id"] for r in S.ledger_open(c, w.soldier, kind="favour")] == [eid]
    S.ledger_breach(c, eid, w.soldier, day + 11, "voted the other way")
    assert c.execute("SELECT status FROM agreement_terms WHERE id=?", (eid,)).fetchone()[0] == "breached"
    assert c.execute("SELECT COUNT(*) FROM agreement_breaches WHERE term_id=?", (eid,)).fetchone()[0] == 1
    assert S.ledger_open(c, w.soldier, kind="favour") == []
    # a held outcome at B depth
    hid = S.hold_outcome(c, what="won the mayoralty", people=[w.boss], dates={"start_day": day}, consequences=["takes office in January"], day=day)
    h = c.execute("SELECT * FROM held_things WHERE id=?", (hid,)).fetchone()
    assert h["depth"] == "B" and h["shape"] == "dated_fact" and h["gap_key"] is None, dict(h)
    # a push: once per key
    S.push(c, w.soldier, "election_night", "the count is in", day, {"race": 1})
    S.push(c, w.soldier, "election_night", "the count is in", day, {"race": 1})
    assert c.execute("SELECT COUNT(*) FROM delivery_ledger WHERE viewer_actor_id=? AND kind='election_night'", (w.soldier,)).fetchone()[0] == 1
    # the protagonist is a person like any other
    from engine import player
    player.set_player(c, w.capo)
    S.push(c, w.capo, "election_night", "the count is in", day, {"race": 1})
    S.ledger_entry(c, w.capo, w.soldier, kind="favour", terms={"note": "a job"}, due_day=None, day=day)
    assert len(S.ledger_open(c, w.capo, kind="favour")) == 1


def test_missing_prerequisite_names_itself():
    import engine
    from engine import civic_seams as S
    w = _open_world()
    saved = sys.modules.get("engine.intake")
    attr = getattr(engine, "intake", None)
    sys.modules["engine.intake"] = None
    if hasattr(engine, "intake"):
        delattr(engine, "intake")
    try:
        try:
            S.hold_outcome(w.conn, what="x", people=[w.soldier], dates={}, consequences=[], day=1)
        except RuntimeError as e:
            assert "history intake core" in str(e)
        else:
            raise AssertionError("expected a RuntimeError")
    finally:
        sys.modules["engine.intake"] = saved
        if attr is not None:
            engine.intake = attr


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
