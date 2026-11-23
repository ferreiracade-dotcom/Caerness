"""R1 task 9: the GM's surface: lookup history / diverged / real:<name>, verification through note(kind="fact"), the rulebook line.

Run: PYTHONPATH=. python tests/history_connector_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from tests.history_fixture import door, fact, run_all, world
from connector import store
from connector.views import lookup
from engine import history

ROOT = Path(__file__).resolve().parent.parent


def _w():
    w = world()
    store.ensure_connector_schema(w.conn)
    w.conn.commit()
    return w


def test_lookup_history_lists_entries_provisional_first_and_counts_them():
    w = _w()
    fact(w, "the Dock Act", "law", "1971-01-01")
    fact(w, "the Harbor Statute", "law", "1972-03-01", source="memory")
    r = lookup(w.conn, "history")
    assert r["kind"] == "history" and r["to_verify"] == 1 and r["entries"][0]["provisional"] is True, r


def test_verification_through_note_fact_promotes_a_provisional_entry():
    w = _w()
    c = w.conn
    e = fact(w, "the Harbor Statute", "law", "1972-03-01", source="memory")["entry"]
    out = store.record(c, "fact", "the Harbor Statute, enacted 1 March 1972", "n1", field=e, cause="source https://example.test/statute \"enacted 1 March 1972\"")
    assert out.get("verified") is True, out
    assert lookup(c, "history")["to_verify"] == 0


def test_a_fixed_history_fact_changes_only_with_a_cause_through_note():
    w = _w()
    e = fact(w, "the Dock Act", "law", "1971-01-01")["entry"]
    try:
        store.record(w.conn, "fact", "repealed", "n2", field=e)
        assert False
    except ValueError as ex:
        assert "stated cause" in str(ex)


def test_lookup_diverged_and_real_figures():
    w = _w()
    c = w.conn
    history.record_divergence(c, "org:1", "", "act 5", "the supplier fell")
    d = lookup(c, "diverged")
    assert d["kind"] == "divergences" and d["divergences"][0]["text"] == "the supplier fell"
    miss = lookup(c, "real:Brendan Byrne")
    assert miss["found"] is False and miss["real_person_named_by_the_setting"] is True and "author(kind='real person'" in miss["hint"], miss
    door(w, "real person", {"name": "Brendan Byrne", "source": "https://example.test/g \"governor\"", "public_roles": ["governor"], "age": 50, "work": "politician"})
    hit = lookup(c, "real:Brendan Byrne")
    assert hit["found"] and hit["public_roles"] == ["governor"] and hit["alive"] is True, hit


def test_the_rulebook_tells_the_gm_how_real_history_enters():
    text = (ROOT / "worlds" / "saintjude" / "rulebook_section.md").read_text(encoding="utf-8")
    assert "Real history: it stays real offstage" in text and "history_due" in text and "does not pay" in text


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
