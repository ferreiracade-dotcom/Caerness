"""R1 task 6: dated rules read the run's dates; the package timeline is a default, not a wall.

Run: PYTHONPATH=. python tests/history_dated_rules_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, world
from engine import history, veto


def _refused(c, text):
    try:
        veto.check_world_text(c, text)
    except veto.Contradiction as e:
        return str(e)
    return None


def test_a_law_before_its_date_is_still_refused_and_a_technology_is_not():
    w = world()
    c = w.conn
    msg = _refused(c, "arrested under federal preventive detention")
    assert msg and "does not exist yet" in msg and "1984" in msg, msg
    assert _refused(c, "he carries a cellular phone") is None
    assert _refused(c, "a compact disc player") is None


def test_an_unlisted_name_passes_as_before():
    w = world()
    assert _refused(w.conn, "he owns a Walkman") is None


def test_a_law_the_run_judged_later_is_refused_until_the_later_date_and_never_is_refused_with_its_reason():
    w = world()
    c = w.conn
    history.record_divergence(c, f"org:{w.org}", "", "act", "the sponsor's bloc was broken")
    r = fact(w, "Atlantic City casino gambling referendum", "event", "1976-11-30",
             needs=[{"text": "the sponsor", "ref": f"org:{w.org}", "central": False}])
    assert r["foreseen"] is True  # still ahead of the game date
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (history.day_of(c, "1976-12-15"),))
    assert _refused(c, "voted on the Atlantic City casino gambling referendum") is not None
    c.execute("UPDATE history_entries SET outcome='never',status='never',run_date=NULL,reasons_json=? WHERE key=?",
              ('["the bloc held and voted it down"]', r["entry"]))
    msg = _refused(c, "voted on the Atlantic City casino gambling referendum")
    assert msg and "did not happen in this run" in msg and "voted it down" in msg, msg


def test_a_law_the_run_brought_earlier_is_in_force_before_its_real_date():
    w = world()
    c = w.conn
    c.execute("INSERT INTO history_entries(key,class,what,real_date,run_date,outcome,status,provisional) VALUES "
              "('history:federal-preventive-detention','law','federal preventive detention','1984-10-12','1974-06-01','earlier','in_force',0)")
    assert _refused(c, "arrested and held under federal preventive detention") is None


def test_proposing_a_future_law_as_a_real_fact_is_not_walled_by_its_own_name():
    w = world()
    r = fact(w, "federal preventive detention", "law", "1984-10-12")
    assert r["foreseen"] is True


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
