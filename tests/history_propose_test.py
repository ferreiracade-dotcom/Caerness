"""R1 task 2: a real fact proposed through the intake is recorded with its source, provisional marks and foreseen state.

Run: PYTHONPATH=. python tests/history_propose_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, set_day, world
from engine.authoring import AuthoringRefused


def test_a_sourced_law_in_the_past_is_in_force_and_a_fixed_world_fact():
    w = world()
    r = fact(w, "the Quarry Act", "law", "1973-06-01")
    assert r["status"] == "created" and r["kind"] == "history" and r["outcome"] == "on_time", r
    e = w.conn.execute("SELECT * FROM history_entries WHERE key='history:the-quarry-act'").fetchone()
    assert e["status"] == "in_force" and e["run_date"] == "1973-06-01" and e["provisional"] == 0 and e["verify"] == "verified"
    f = w.conn.execute("SELECT tag,start_date FROM world_facts WHERE key='history:the-quarry-act'").fetchone()
    assert f["tag"] == "Fixed" and f["start_date"] == "1973-06-01"
    assert w.conn.execute("SELECT COUNT(*) FROM held_things WHERE backing_table='history_entries'").fetchone()[0] == 1


def test_memory_major_is_provisional_minor_is_not():
    w = world()
    a = fact(w, "the Harbor Statute", "law", "1972-03-01", source="memory")
    b = fact(w, "the price of a pack of cigarettes", "price", "1974-05", source="memory")
    assert a["provisional"] is True and b["provisional"] is False
    assert w.conn.execute("SELECT verify FROM history_entries WHERE key='history:the-harbor-statute'").fetchone()[0] == "to verify"


def test_a_date_ahead_is_foreseen_with_no_effects_and_no_knowledge():
    w = world()
    before = w.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] if w.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='knowledge'").fetchone() else 0
    r = fact(w, "a garage firm lists its shares", "firm_event", "1980-12-12", knows=[w.capo])
    assert r["foreseen"] is True and r["outcome"] == "default"
    e = w.conn.execute("SELECT status,judged_day FROM history_entries WHERE key=?", (r["entry"],)).fetchone()
    assert e["status"] == "foreseen" and e["judged_day"] is None
    assert w.conn.execute("SELECT start_date FROM world_facts WHERE key=?", (r["entry"],)).fetchone()[0] is None
    after = w.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] if w.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='knowledge'").fetchone() else 0
    assert after == before


def test_missing_fields_are_input_gaps_and_the_same_call_replays():
    w = world()
    for bad, word in (({"what": "x", "class": "law", "real_date": "1973"}, "source"), ({"what": "x", "real_date": "1973", "source": "memory"}, "class")):
        try:
            door(w, "law", bad)
            assert False, "should refuse"
        except AuthoringRefused as e:
            assert e.reason_kind == "input_gap" and word in str(e), str(e)
    r1 = fact(w, "the Dock Act", "law", "1971-01-01")
    r2 = door(w, "law", {"what": "the Dock Act", "class": "law", "real_date": "1971-01-01", "source": "memory"}, "h-replay")
    assert r2["replayed"] and r2["entry"] == r1["entry"]
    assert w.conn.execute("SELECT COUNT(*) FROM history_entries WHERE key=?", (r1["entry"],)).fetchone()[0] == 1


tests = None
if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
