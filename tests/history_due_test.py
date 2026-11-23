"""R1 task 8: effects at the run date, foreseen facts re-judged on their date, the "what was due" prompt.

Run: PYTHONPATH=. python tests/history_due_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, set_day, world
from engine import held_things, history


def _at(w, iso):
    d = history.day_of(w.conn, iso)
    set_day(w, d)
    return d


def test_nothing_waiting_means_no_weekly_pass_is_scheduled_for_history():
    w = world()
    assert history.next_due(w.conn) is False
    fact(w, "an old act", "law", "1972-01-01")
    assert history.next_due(w.conn) is False
    fact(w, "a coming firm", "firm", "1976-03-01")
    assert history.next_due(w.conn) is True


def test_a_foreseen_fact_with_nothing_touching_it_comes_in_force_on_its_date_with_its_effects():
    w = world()
    c = w.conn
    r = fact(w, "the pocket synthesizer", "technology", "1975-06-01")
    assert r["foreseen"]
    held_things.process_due(c, _at(w, "1975-05-20"))
    assert c.execute("SELECT status FROM history_entries WHERE key=?", (r["entry"],)).fetchone()[0] == "foreseen"
    held_things.process_due(c, _at(w, "1975-06-08"))
    e = c.execute("SELECT * FROM history_entries WHERE key=?", (r["entry"],)).fetchone()
    assert e["status"] == "in_force" and e["outcome"] == "on_time" and e["judged_day"] is not None
    assert c.execute("SELECT exists_date FROM tech_level WHERE thing='the pocket synthesizer'").fetchone()[0] == "1975-06-01"
    assert c.execute("SELECT start_date FROM world_facts WHERE key=?", (r["entry"],)).fetchone()[0] == "1975-06-01"
    assert history.next_due(c) is False


def test_the_run_changed_before_the_date_so_it_is_rejudged_later_then_comes_in_force():
    w = world()
    c = w.conn
    ref = f"org:{w.org}"
    r = fact(w, "the Harbor Works opens", "firm_event", "1976-03-01", needs=[{"text": "the supplier", "ref": ref, "central": False}])
    history.record_divergence(c, ref, "", "act 9", "the supplier was bankrupted")  # between the foresight and the date
    held_things.process_due(c, _at(w, "1976-03-08"))
    e = c.execute("SELECT * FROM history_entries WHERE key=?", (r["entry"],)).fetchone()
    assert e["outcome"] == "later" and e["status"] == "foreseen" and e["run_date"] > "1976-03-01", dict(e)
    held_things.process_due(c, _at(w, e["run_date"][:10]) + 7)
    assert c.execute("SELECT status FROM history_entries WHERE key=?", (r["entry"],)).fetchone()[0] == "in_force"
    assert c.execute("SELECT COUNT(*) FROM divergences WHERE entry_key=?", (r["entry"],)).fetchone()[0] >= 1


def test_a_fact_judged_never_on_its_date_is_recorded_and_not_in_force():
    w = world()
    c = w.conn
    c.execute("UPDATE actors SET status='deceased' WHERE id=?", (w.soldier,))
    r = fact(w, "the founder's firm", "firm", "1976-03-01", needs=[{"text": "founder", "ref": f"actor:{w.soldier}"}])
    held_things.process_due(c, _at(w, "1976-03-08"))
    e = c.execute("SELECT status,outcome,run_date FROM history_entries WHERE key=?", (r["entry"],)).fetchone()
    assert e["status"] == "never" and e["outcome"] == "never" and e["run_date"] is None


def test_the_due_prompt_lists_package_defaults_and_foreseen_facts_and_asks_only_its_classes():
    w = world()
    c = w.conn
    due = history.due_prompt(c, 0, history.day_of(c, "1980-06-01"))
    names = {d["name"] for d in due}
    assert "New Jersey income tax" in names and "Contraband Cigarette Trafficking Act" in names and "numeric display pager" in names, names
    assert "Church Committee" not in names  # an institution: not a class the package asks about
    fact(w, "New Jersey income tax", "law", "1976-07-31")
    again = {d["name"]: d for d in history.due_prompt(c, 0, history.day_of(c, "1980-06-01"))}
    assert again["New Jersey income tax"]["hint"].startswith("foreseen")
    assert history.due_prompt(c, 0, 1) == []


def test_advance_carries_history_due_through_the_connector():
    from connector import store, timeflow
    from engine.player import set_player
    w = world()
    c = w.conn
    store.ensure_connector_schema(c)
    set_player(c, w.capo)
    c.commit()
    out = timeflow.advance(c, "adv-1", 14, "wait")
    assert "history_due" not in out  # nothing from the package falls in two weeks of January 1975 in a prompted class... or it is a list
    assert isinstance(out.get("history_due", []), list)


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
