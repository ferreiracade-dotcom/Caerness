"""R1 task 4: the run writes divergences when it touches real history, and only then.

Run: PYTHONPATH=. python tests/history_divergence_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, world
from engine import facts, history, household_life


def _div(c, subject):
    return c.execute("SELECT COUNT(*) FROM divergences WHERE subject=?", (subject,)).fetchone()[0]


def test_a_death_that_touches_a_named_cause_is_a_divergence_and_an_unrelated_one_is_not():
    w = world()
    c = w.conn
    fact(w, "the founder's firm opens", "firm", "1974-01-01", needs=[{"text": "founder", "ref": f"actor:{w.soldier}"}])
    household_life.mark_actor_deceased(c, w.soldier, reason="shot")
    assert _div(c, f"actor:{w.soldier}") == 1
    other = int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND status!='deceased' AND id NOT IN (?,?,?) ORDER BY id LIMIT 1",
                          (w.soldier, w.capo, w.boss)).fetchone()[0])
    household_life.mark_actor_deceased(c, other, reason="old age")
    assert _div(c, f"actor:{other}") == 0
    assert c.execute("SELECT COUNT(*) FROM divergences").fetchone()[0] == 1


def test_the_protagonist_founding_in_a_field_diverges_a_later_real_firm_the_same_way():
    w = world()
    c = w.conn
    from tests.intake_test import _fund
    _fund(c, w.capo, 5000)
    door(w, "a software shop", {"what": "Capo's microcomputer software shop", "money": {"start": 100}, "agenda": "sell programs"})
    r = fact(w, "a personal computer software maker is founded", "firm", "1974-09-01")
    assert r["outcome"] == "changed" and "already holds this field" in " ".join(r["links"]) + " ".join(r["reasons"]), r
    assert c.execute("SELECT COUNT(*) FROM divergences WHERE subject LIKE 'thing:%' AND entry_key=?", (r["entry"],)).fetchone()[0] == 1
    again = fact(w, "a shoe maker is founded", "firm", "1974-09-01")
    assert again["outcome"] == "on_time"


def test_overriding_a_fixed_history_fact_needs_a_cause_and_records_the_divergence():
    w = world()
    c = w.conn
    r = fact(w, "the Quarry Act", "law", "1973-06-01")
    try:
        facts.override(c, r["entry"], "the act failed", None, "o1")
        assert False
    except facts.FactRefused:
        pass
    out = facts.override(c, r["entry"], "the act failed in committee", "the protagonist's lobbyists split the committee", "o2")
    assert out.get("diverged") and _div(c, r["entry"]) == 1
    assert c.execute("SELECT status FROM history_entries WHERE key=?", (r["entry"],)).fetchone()[0] == "superseded"


def test_a_source_in_the_cause_verifies_a_provisional_entry_and_is_not_a_divergence():
    w = world()
    c = w.conn
    r = fact(w, "the Harbor Statute", "law", "1972-03-01", source="memory")
    assert r["provisional"] is True
    out = facts.override(c, r["entry"], "the Harbor Statute, 1972", "source https://example.test/statute \"enacted 1 March 1972\"", "o3")
    assert out.get("verified")
    e = c.execute("SELECT provisional,verify FROM history_entries WHERE key=?", (r["entry"],)).fetchone()
    assert e["provisional"] == 0 and e["verify"] == "verified" and _div(c, r["entry"]) == 0


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
