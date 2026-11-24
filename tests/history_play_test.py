"""R1 play check: a technology, a firm and a law proposed through author; a figure killed; a venture in a foreseen firm's field;
time advanced across the real dates. Outcomes, divergences and lookups are read back; an unrelated fact stays on time.

Run: PYTHONPATH=. python tests/history_play_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, set_day, world
from engine import held_things, history, household_life


def test_a_run_of_real_history_through_the_door():
    from connector import store
    from connector.views import lookup
    w = world()
    c = w.conn
    store.ensure_connector_schema(c)
    # the GM looks up and proposes: a firm in a field, a law, an unrelated technology, all ahead of the game date
    firm = fact(w, "Orchard Computer", "firm", "1976-04-01", needs=[{"text": "its founder", "ref": f"actor:{w.soldier}"}])
    law = fact(w, "the Pier Safety Act", "law", "1976-06-01", source="memory")
    tech = fact(w, "the slim cassette deck", "technology", "1976-02-01")
    assert firm["foreseen"] and law["foreseen"] and law["provisional"] and tech["foreseen"]
    # the run touches it: the founder is killed; another man founds a shop in the same field
    household_life.mark_actor_deceased(c, w.soldier, reason="shot")
    from tests.intake_test import _fund
    _fund(c, w.capo, 50000)
    door(w, "a software shop", {"what": "Ferry Street computer software shop", "money": {"start": 200}})
    # time passes across the dates
    for iso in ("1976-02-08", "1976-04-08", "1976-06-08"):
        set_day(w, history.day_of(c, iso))
        held_things.process_due(c, history.day_of(c, iso))
    row = lambda e: c.execute("SELECT status,outcome FROM history_entries WHERE key=?", (e["entry"],)).fetchone()
    assert row(tech)["outcome"] == "on_time" and row(tech)["status"] == "in_force"  # nothing touched it
    assert row(law)["outcome"] == "on_time"  # a provisional law holds on its date too
    assert row(firm)["status"] == "never" and row(firm)["outcome"] == "never"  # its founder is dead and nothing stood in
    div = lookup(c, "diverged")["divergences"]
    assert any(d["entry"] == firm["entry"] for d in div) and any(d["subject"] == f"actor:{w.soldier}" for d in div), div
    hist = lookup(c, "history")
    assert hist["to_verify"] == 1 and {e["key"] for e in hist["entries"]} >= {firm["entry"], law["entry"], tech["entry"]}
    # a fact the run killed is not re-proposed
    again = fact(w, "Orchard Computer", "firm", "1976-04-01")
    assert again["replayed"] and again["outcome"] == "never"


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
