"""R1 task 7: technology enablers, distance ahead, and foreknowledge judged on what the character could know.

Run: PYTHONPATH=. python tests/history_tech_test.py
"""
from __future__ import annotations

import sys

from tests.history_fixture import door, fact, run_all, world
from engine import authoring, foreknowledge, history


def test_a_missing_enabler_is_a_named_contradiction_and_building_it_is_allowed():
    w = world()
    history.add_tech(w.conn, "cellular network", "1983-12-31")
    try:
        door(w, "an invention", {"what": "a pocket handset sold to executives", "needs_tech": ["cellular network"]})
        assert False
    except authoring.AuthoringRefused as e:
        assert "cellular network" in str(e) and "does not exist" in str(e) and e.reason_kind == "contradiction", str(e)
    ok = door(w, "an invention", {"what": "a cellular network built from rooftop sites", "needs_tech": ["cellular network"], "builds": ["cellular network"]})
    assert ok["status"] == "created"


def test_distance_ahead_scales_cost_time_and_failure_with_no_ceiling():
    from tests.intake_test import _fund
    w = world()
    _fund(w.conn, w.capo, 10 ** 7)
    near = door(w, "an invention", {"what": "a fax machine reseller", "money": {"start": 1000}})
    far = door(w, "an invention", {"what": "a cellular phone for executives", "money": {"start": 1000}, "ready_in_days": 30})
    assert "basis" not in near
    d = far["basis"]["tech_distance"]
    assert d["years_ahead"] > 8 and d["cost_factor"] > 4 and 0 < d["failure_odds"] < 1, d
    assert far["status"] in ("created", "scaled_down")
    spent = w.conn.execute("SELECT start_cost FROM held_things WHERE id=?", (far["held_thing_id"],)).fetchone()[0]
    assert spent > 4000, spent  # dearer, not refused


def _firm(w):
    return fact(w, "Orchard Computer", "firm", "1980-12-12")


def test_a_bet_on_a_foreseen_firm_is_a_long_shot_without_competence_and_informed_with_it():
    w = world()
    c = w.conn
    from tests.intake_test import _fund
    _fund(c, w.capo, 10 ** 6)
    _firm(w)
    bad = door(w, "a stake", {"what": "a stake in Orchard Computer", "money": {"start": 500, "income": 200}})
    f = bad["basis"]["foresight"]
    assert f["judged_as"] == "long_shot" and f["knows"] == "none", f
    assert c.execute("SELECT income_weekly FROM held_things WHERE id=?", (bad["held_thing_id"],)).fetchone()[0] == 0
    # he positions himself: a man he commands knows computers
    c.execute("INSERT OR IGNORE INTO competence_domains(domain_key,name) VALUES ('computing','Computer')")
    dom = c.execute("SELECT id FROM competence_domains WHERE domain_key='computing'").fetchone()[0]
    c.execute("INSERT INTO actor_competence(actor_id,domain_id,score) VALUES (?,?,80)", (w.soldier, dom))
    k = foreknowledge.character_knows(c, w.capo, "Orchard Computer")
    assert k["level"] == "informed" and any("works for him" in s for s in k["sources"]), k
    good = door(w, "a stake", {"what": "a second stake in Orchard Computer", "about": ["Orchard Computer"], "money": {"start": 500, "income": 200}})
    assert good["basis"]["foresight"]["judged_as"] == "informed"
    assert c.execute("SELECT income_weekly FROM held_things WHERE id=?", (good["held_thing_id"],)).fetchone()[0] > 0


def test_the_same_judgement_acts_on_an_npc_owner():
    w = world()
    _firm(w)
    r = door(w, "a stake", {"what": "a stake in Orchard Computer", "owner_actor_id": w.boss, "money": {"income": 300}})
    assert r["basis"]["foresight"]["judged_as"] == "long_shot"


if __name__ == "__main__":
    sys.exit(0 if run_all(globals()) else 1)
