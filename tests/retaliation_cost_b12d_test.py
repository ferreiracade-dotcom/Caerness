"""Task B12d: retaliation weighs what a war costs (men and earnings lost, being the weaker side, law heat, a thin purse, a cautious head,
a third head who can broker a sit-down, redress), as package data, with no cap on anything.

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/retaliation_cost_b12d_test.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world
from tests.lethality_b12c_test import _killing


def _offers(w, head, item, day=DAY + 2):
    from engine import org_choices
    return {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](w.conn, head, item, day)}


def _more_killings(w, other, n, day=DAY - 5):
    """n earlier killings of `other`'s men by this outfit's men."""
    from engine import org_happenings as oh
    c = w.conn
    for i in range(n):
        v = c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id LIMIT 1 OFFSET ?", (other, i + 1)).fetchone()
        oh._record(c, day, "killing", w.soldier, victim=int(v[0]), matters=1, raised=other, status="retaliated", killer_org=w.org, role="soldier")


def test_men_already_lost_weigh_against_retaliating_and_toward_peace():
    a, b = open_world(), open_world()
    ia, ha, _, oa = _killing(a)
    ib, hb, _, ob = _killing(b)
    _more_killings(b, ob, 4)
    ua, ub = _offers(a, ha, ia), _offers(b, hb, ib)
    assert ub["retaliate"]["utility"] < ua["retaliate"]["utility"], (ua["retaliate"]["utility"], ub["retaliate"]["utility"])
    assert ub["sit_down_peace"]["utility"] > ua["sit_down_peace"]["utility"]
    assert ub["accept_killing"]["utility"] > ua["accept_killing"]["utility"]


def test_law_heat_in_the_city_weighs_against_retaliating():
    a, b = open_world(), open_world()
    ia, ha, _, oa = _killing(a)
    ib, hb, _, ob = _killing(b)
    from engine import org_happenings as oh
    for i in range(8):  # killings elsewhere in the city, between other men
        oh._record(b.conn, DAY - 3, "killing", b.soldier, victim=int(ib["subject_id"]), matters=1, raised=-1 - i, status="done", killer_org=-99)
    ua, ub = _offers(a, ha, ia), _offers(b, hb, ib)
    assert ub["retaliate"]["utility"] < ua["retaliate"]["utility"]


def test_a_cautious_head_weighs_the_cost_more_than_a_hot_one():
    a, b = open_world(), open_world()
    ia, ha, _, _ = _killing(a)
    ib, hb, _, _ = _killing(b)
    a.conn.execute("UPDATE actor_drives SET aggression=0.05 WHERE actor_id=?", (ha,))
    b.conn.execute("UPDATE actor_drives SET aggression=0.95 WHERE actor_id=?", (hb,))
    ua, ub = _offers(a, ha, ia), _offers(b, hb, ib)
    assert ua["retaliate"]["utility"] < ub["retaliate"]["utility"]
    assert ua["sit_down_peace"]["utility"] > ub["sit_down_peace"]["utility"]


def test_a_third_head_both_respect_makes_a_sit_down_likelier():
    a, b = open_world(), open_world()
    ia, ha, _, oa = _killing(a)
    ib, hb, _, ob = _killing(b)
    from engine import org_happenings as oh
    third = oh._third_heads(b.conn, b.org, ob)
    assert third, "the opening has other outfits of the same kind"
    t = third[0][0]
    for h in (hb, int(b.conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='boss'", (b.org,)).fetchone()[0])):
        b.conn.execute("""INSERT OR REPLACE INTO relationships(actor_a_id,actor_b_id,respect,trust,familiarity) VALUES (?,?,90,90,50)""", (h, t))
    ua, ub = _offers(a, ha, ia), _offers(b, hb, ib)
    assert ub["sit_down_peace"]["utility"] > ua["sit_down_peace"]["utility"]


def test_without_any_cost_the_old_weights_are_unchanged():
    """No recent killings, no heat, nobody to broker: a counter-term at zero takes nothing off an answer (blend with no against terms)."""
    from engine import org_happenings as oh
    w = open_world()
    assert abs(oh._blend(w.conn, [{"name": "x", "weight": 0.5}, {"name": "c", "weight": 0.9, "against": True}], {"x": 1.0, "c": 0.0}) - 0.5) < 1e-9
    assert abs(oh._blend(w.conn, [{"name": "x", "weight": 0.5}, {"name": "c", "weight": 0.9, "against": True}], {"x": 1.0, "c": 1.0}) - 0.05) < 1e-9


def test_a_sit_down_can_settle_a_killing_and_ease_both_heads():
    from engine import org_choices, org_happenings as oh
    w = open_world()
    item, head, vic, other = _killing(w)
    payload = _offers(w, head, item)["sit_down_peace"]["payload"]
    real, oh._rng = oh._rng, lambda *a, **k: random.Random(0) if False else type("R", (), {"random": lambda self: 0.0})()
    try:
        org_choices.execute(w.conn, head, "sit_down_peace", payload, DAY + 2)
    finally:
        oh._rng = real
    assert w.conn.execute("SELECT status FROM org_incidents WHERE id=?", (payload["incident"],)).fetchone()[0] == "settled"
    assert not w.conn.execute("SELECT 1 FROM org_agenda WHERE kind='hit' AND status='open'").fetchone(), "settled: no hunt follows"


def test_a_refused_sit_down_puts_it_back_marked_and_raises_retaliation():
    from engine import org_choices, org_happenings as oh
    w = open_world()
    item, head, vic, other = _killing(w)
    before = _offers(w, head, item)
    payload = before["sit_down_peace"]["payload"]
    real, oh._rng = oh._rng, lambda *a, **k: type("R", (), {"random": lambda self: 0.999999})()
    try:
        org_choices.execute(w.conn, head, "sit_down_peace", payload, DAY + 2)
    finally:
        oh._rng = real
    again = w.conn.execute("SELECT * FROM org_agenda WHERE kind='respond_killing' AND actor_id=? AND status='open' ORDER BY id DESC", (head,)).fetchone()
    assert again is not None
    after = _offers(w, head, again, DAY + 6)
    assert after["retaliate"]["utility"] > before["retaliate"]["utility"]
    assert after["sit_down_peace"]["utility"] < before["sit_down_peace"]["utility"]


def test_refused_redress_for_a_killing_comes_back_to_the_asker():
    from engine import org_choices
    w = open_world()
    item, head, vic, other = _killing(w)
    payload = _offers(w, head, item)["demand_redress"]["payload"]
    org_choices.execute(w.conn, head, "demand_redress", payload, DAY + 2)
    pay = w.conn.execute("SELECT * FROM org_agenda WHERE kind='pay_or_refuse' AND status='open' ORDER BY id DESC").fetchone()
    assert pay is not None
    import json
    meta = json.loads(pay["metadata_json"])
    org_choices.execute(w.conn, int(pay["actor_id"]), "refuse", {**meta, "incident_id": int(meta["incident"]), "agenda_id": int(pay["id"])}, DAY + 4)
    again = w.conn.execute("SELECT * FROM org_agenda WHERE kind='respond_killing' AND actor_id=? AND status='open' ORDER BY id DESC", (head,)).fetchone()
    assert again is not None and json.loads(again["metadata_json"]).get("redress_refused") is True


def test_retaliation_is_still_offered_and_nothing_caps_it():
    """No count, cooldown or ceiling: even with the feud at its costliest the answer is offered with a utility above its floor."""
    w = open_world()
    item, head, vic, other = _killing(w)
    _more_killings(w, other, 12)
    u = _offers(w, head, item)
    assert "retaliate" in u and u["retaliate"]["utility"] >= 8.0


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            bad.append(t.__name__)
            print("FAIL", t.__name__, repr(e)[:300])
    sys.exit(1 if bad else 0)
