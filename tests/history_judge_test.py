"""R1 task 3: do the causes still hold here? History holds unless the run touches it, directly or through a chain.

Run: PYTHONPATH=. python tests/history_judge_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, world
from engine import history


def test_no_needs_no_divergence_is_on_time_every_time():
    w = world()
    for i in range(50):
        r = fact(w, f"quiet fact number {i}", "law", "1972-01-01")
        assert r["outcome"] == "on_time" and r["reasons"] == [] and r["run_date"] == "1972-01-01", r


def test_a_dead_founder_changes_or_ends_it_by_whether_a_substitute_exists():
    w = world()
    c = w.conn
    c.execute("UPDATE actors SET status='deceased' WHERE id=?", (w.soldier,))
    ref = f"actor:{w.soldier}"
    never = fact(w, "founder firm alpha", "firm", "1974-04-01", needs=[{"text": "the founder", "ref": ref}])
    assert never["outcome"] == "never" and never["run_date"] is None and "dead" in " ".join(never["reasons"]), never
    changed = fact(w, "founder firm beta", "firm", "1974-04-01", needs=[{"text": "the founder", "ref": ref, "substitute": True}])
    assert changed["outcome"] == "changed" and changed["run_date"] >= "1974-04-01", changed
    sup = fact(w, "founder firm gamma", "firm", "1974-04-01", needs=[{"text": "a minor backer", "ref": ref, "central": False}])
    assert sup["outcome"] == "later", sup
    assert c.execute("SELECT status FROM history_entries WHERE key=?", (never["entry"],)).fetchone()[0] == "never"
    assert c.execute("SELECT COUNT(*) FROM divergences WHERE entry_key=?", (never["entry"],)).fetchone()[0] == 1
    again = fact(w, "founder firm alpha", "firm", "1974-04-01")
    assert again["replayed"] and again["outcome"] == "never"
    assert c.execute("SELECT COUNT(*) FROM history_entries WHERE key=?", (never["entry"],)).fetchone()[0] == 1


def test_a_direct_divergence_on_a_supporting_cause_delays_it():
    w = world()
    ref = f"org:{w.org}"
    history.record_divergence(w.conn, ref, "", "act 1", "the supplier was bankrupted")
    r = fact(w, "a chip plant opens", "firm_event", "1974-02-01", needs=[{"text": "the supplier", "ref": ref, "central": False}])
    assert r["outcome"] == "later" and r["run_date"] > "1974-02-01" and "supplier" in " ".join(r["reasons"]), r


def test_a_chain_of_named_causes_reaches_a_later_fact():
    w = world()
    history.record_divergence(w.conn, f"actor:{w.boss}", "", "act 2", "the financier was ruined")
    e1 = fact(w, "the fund closes its round", "firm_event", "1974-03-01", needs=[{"text": "the financier", "ref": f"actor:{w.boss}", "central": False}])
    assert e1["outcome"] == "later"
    key1 = e1["entry"]
    e2 = fact(w, "the start-up ships", "firm", "1974-06-01", needs=[{"text": "the round", "ref": key1, "central": False}])
    assert e2["outcome"] in ("later", "changed"), e2
    joined = " ".join(e2["links"])
    assert "fund closes its round" in joined and "financier" in joined, e2
    assert e2["run_date"] >= e1["run_date"] or e2["run_date"] > "1974-06-01"


def test_an_earlier_enabler_brings_it_earlier_by_a_lead_time_never_below_it():
    w = world()
    w.conn.execute("INSERT INTO tech_level(thing,exists_date,available_date) VALUES ('fast chip','1973-01-01','1973-01-01')")
    r = fact(w, "the pocket machine", "technology", "1974-12-01", needs=[{"text": "a fast chip", "ref": "tech:fast chip", "real_date": "1974-06-01"}])
    assert r["outcome"] == "earlier", r
    assert "1973-01-01" < r["run_date"] < "1974-12-01", r


def test_niche_taken_by_the_run_changes_a_real_firms_fact_and_unrelated_runs_do_not():
    w = world()
    history.record_divergence(w.conn, f"org:{w.org}", "microcomputer kit", "act 3", "he sells kits")
    hit = fact(w, "a personal computer maker is founded", "firm", "1974-07-01")
    assert hit["outcome"] == "changed" and "taken" in " ".join(hit["reasons"]), hit
    miss = fact(w, "a shoe company is founded", "firm", "1974-07-01")
    assert miss["outcome"] == "on_time", miss


def test_the_judgement_is_repeatable():
    w = world()
    history.record_divergence(w.conn, f"org:{w.org}", "", "act 4", "x")
    entry = {"key": "history:probe", "what": "probe", "real_date": "1974-01-01", "about": [],
             "needs": [{"text": "n", "ref": f"org:{w.org}", "central": False}]}
    a = history.judge(w.conn, entry, 0)
    b = history.judge(w.conn, entry, 0)
    assert a == b and a["outcome"] == "later"


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
