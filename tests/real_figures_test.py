"""R1 task 5: documented real figures replace the offstage refusal; the engine vetoes contradictions only.

Run: PYTHONPATH=. python tests/real_figures_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, world
from engine import authoring, household_life, real_figures


def _gov(w, **more):
    d = {"name": "Brendan Byrne", "source": "https://example.test/governor \"Byrne, governor\"", "public_roles": ["governor"], "record": [],
         "age": 50, "work": "politician"}
    d.update(more)
    return door(w, "real person", d)


def test_an_invented_person_wearing_a_real_name_is_refused_with_the_lookup_path():
    w = world()
    try:
        door(w, "person", {"name": "Brendan Byrne", "work": "clerk", "age": 40})
        assert False
    except authoring.AuthoringRefused as e:
        assert "real person" in str(e) and "author(kind='real person'" in str(e), str(e)


def test_a_documented_figure_is_created_once_and_the_name_is_then_taken():
    w = world()
    c = w.conn
    r = _gov(w)
    assert r["kind"] == "real_figure" and r["real_figure"] == "figure:brendan-byrne", r
    fig = c.execute("SELECT * FROM real_figures WHERE name_norm='brendan byrne'").fetchone()
    assert fig and fig["actor_id"] == r["actor_id"] and fig["provisional"] == 0
    assert c.execute("SELECT tag FROM world_facts WHERE key='figure:brendan-byrne'").fetchone()[0] == "Fixed"
    again = _gov(w)
    assert again.get("replayed") and c.execute("SELECT COUNT(*) FROM real_figures").fetchone()[0] == 1
    try:
        door(w, "person", {"name": "Brendan Byrne", "work": "clerk", "age": 40})
        assert False
    except authoring.AuthoringRefused as e:
        assert "already" in str(e)


def test_memory_sourced_public_office_is_provisional():
    w = world()
    r = _gov(w, source="memory")
    assert r["provisional"] is True


def test_a_public_act_passes_and_unlawful_work_off_his_record_is_refused():
    w = world()
    r = _gov(w)
    aid = r["actor_id"]
    ok = door(w, "a speech", {"what": "a speech on the port bill", "people": [aid], "legality": "legal", "agenda": "win the port vote"})
    assert ok["status"] == "created"
    try:
        door(w, "a racket", {"what": "a numbers bank", "people": [aid], "legality": "illegal", "agenda": "take the numbers"})
        assert False
    except authoring.AuthoringRefused as e:
        assert "invented man" in str(e), str(e)


def test_a_figure_with_a_record_may_be_tied_to_wrongdoing_of_that_kind():
    w = world()
    r = door(w, "real person", {"name": "Anthony Provenzano", "source": "https://example.test/u \"racketeering conviction\"", "public_roles": ["union official"],
                                "record": ["racketeering", "union fraud"], "age": 57, "work": "union official"})
    ok = door(w, "a racketeering scheme", {"what": "a union racketeering scheme", "people": [r["actor_id"]], "legality": "illegal", "agenda": "skim the pension fund"})
    assert ok["status"] == "created"


def test_the_same_check_acts_on_any_flagged_actor_and_not_on_the_protagonist():
    w = world()
    c = w.conn
    # no player-only branch: a plain actor is untouched, and flagging any actor as real subjects him to the check
    real_figures.check_acts(c, [w.capo], "illegal", "a racket")
    c.execute("INSERT INTO real_figures(name,name_norm,actor_id,record_json,status) VALUES ('Test Man','test man',?,'[]','alive')", (w.capo,))
    try:
        real_figures.check_acts(c, [w.capo], "illegal", "a racket")
        assert False
    except authoring.AuthoringRefused:
        pass


def test_a_figure_the_run_killed_cannot_be_proposed_as_living_and_the_death_is_a_divergence():
    w = world()
    c = w.conn
    r = _gov(w)
    household_life.mark_actor_deceased(c, r["actor_id"], reason="shot")
    assert c.execute("SELECT COUNT(*) FROM divergences WHERE subject=?", (f"actor:{r['actor_id']}",)).fetchone()[0] == 1
    try:
        _gov(w)
        assert False
    except authoring.AuthoringRefused as e:
        assert "dead in this run" in str(e)


def test_a_figure_dead_on_the_start_date_is_refused_as_active():
    w = world()
    try:
        door(w, "real person", {"name": "Vito Genovese", "source": "memory", "status": "dead", "public_roles": []})
        assert False
    except authoring.AuthoringRefused as e:
        assert "dead" in str(e)


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
