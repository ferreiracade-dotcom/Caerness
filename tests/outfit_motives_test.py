"""Motives read from a man's world (task B10): each reader sees its own situation, reasons add up, the ground sets the odds.

Run: PYTHONPATH=. python tests/outfit_motives_test.py   (builds a scratch Saint Jude opening)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, drives, open_world, rel


def _pressure(w, choice="remove_superior"):
    from engine import org_motives
    return org_motives.pressure(w.conn, w.soldier, DAY, choice)


def _money(c, w, kind, frm, to, amount):
    c.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,amount,org_actor_id) VALUES (?,?,?,?,?,?)",
              (DAY - 10, kind, frm, to, amount, w.org))


def test_each_motive_reads_its_situation():
    from engine import orgs
    w = open_world()
    c = w.conn
    base = _pressure(w)[1]
    assert base["squeezed"] == 0 and base["fear"] == 0 and base["boss_wants_it"] == 0, base
    # squeeze: the capo takes 30% of the soldier's net (the ladder share is 18.3%)
    _money(c, w, "take", None, w.soldier, 1000.0)
    _money(c, w, "kickup", w.soldier, w.capo, 300.0)
    assert _pressure(w)[1]["squeezed"] > 0.5
    # a seat to a junior man: his capo is far junior to him in years inducted
    c.execute("UPDATE org_seats SET inducted_day=? WHERE actor_id=? AND org_actor_id=?", (DAY - 15 * 365, w.soldier, w.org))
    c.execute("UPDATE org_seats SET inducted_day=? WHERE actor_id=? AND org_actor_id=?", (DAY - 365, w.capo, w.org))
    assert _pressure(w)[1]["passed_over"] > 0.5
    # an open hit naming the soldier, known to him
    orgs.add_agenda(c, w.boss, "hit", DAY + 3, subject_kind="actor", subject_id=w.soldier, metadata={"known_to": [w.soldier]})
    assert _pressure(w)[1]["fear"] > 0.5
    # the capo held on a homicide charge: fear (who talks) and a weak capo
    w2 = open_world()
    p0 = _pressure(w2)[1]
    assert p0["fear"] == 0 and p0["capo_weak"] == 0, p0
    w2.conn.execute("INSERT INTO custody(actor_id,kind,charge,since_day) VALUES (?,?,?,?)", (w2.capo, "held", "homicide", DAY - 1))
    parts = _pressure(w2)[1]
    assert parts["fear"] > 0 and parts["capo_weak"] > 0, parts
    # the boss's resentment of the capo far above his respect
    rel(c, w.boss, w.capo, resentment=80, respect=10)
    assert _pressure(w)[1]["boss_wants_it"] > 0.5
    # revenge: the capo harmed a close friend of his
    friend = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='associate' AND actor_id<>? LIMIT 1",
                           (w.org, w.soldier)).fetchone()[0])
    rel(c, w.soldier, friend, affection=80)
    from engine.harm import record_harm
    record_harm(c, friend, source_kind="test", source_ref_id=1, severity=60.0, intent_class="hostile",
                metadata={"offender_actor_id": w.capo}, outcome_override="persistent")
    assert _pressure(w)[1]["revenge"] > 0.5
    # grievance reads his resentment of the capo
    rel(c, w.soldier, w.capo, resentment=70)
    assert 0.6 < _pressure(w)[1]["grievance"] < 0.8


def test_reasons_add_up():
    w = open_world()
    c = w.conn
    drives(c, w.soldier, ambition=0.0)
    rel(c, w.soldier, w.capo, resentment=60)
    one = _pressure(w)[0]
    _money(c, w, "take", None, w.soldier, 1000.0)
    _money(c, w, "kickup", w.soldier, w.capo, 300.0)
    two = _pressure(w)[0]
    assert 0 < one < two < 1, (one, two)


def _neutral_racket_man(w):
    """The same man in every comparison: no Pad on his ground, no open case, a rich line so he feels no need."""
    c = w.conn
    c.execute("UPDATE org_arrangements SET status='ended'")
    drives(c, w.soldier, ambition=0.5, risk_tolerance=0.5)
    c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,started_day) "
              "SELECT holding_id,unit_id,?,'a rich line',NULL,9000,0 FROM org_lines WHERE unit_id=? LIMIT 1", (w.soldier, w.unit))


def _chance(w):
    from engine import org_motives
    return org_motives.weekly_chance(w.conn, w.soldier, DAY, "start_racket")


def test_racket_chance_follows_the_ground():
    from engine import org_motives
    from engine import outfit_motives as om
    w = open_world()
    c = w.conn
    _neutral_racket_man(w)
    ids = om._subtree(c, w.ground)
    marks = ",".join("?" * len(ids))
    holding = int(c.execute("SELECT id FROM org_holdings LIMIT 1").fetchone()[0])
    # thin: nothing works the people there
    c.execute(f"UPDATE org_lines SET location_id=NULL WHERE location_id IN ({marks})", ids)
    thin = _chance(w)
    assert org_motives.pressure(c, w.soldier, DAY, "start_racket")[1]["thin_ground"] > 0.9
    # thick: the ground is crowded with lines
    for _ in range(300):
        c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,started_day) VALUES (?,?,?,?,?,?,0)",
                  (holding, w.unit, w.capo, "a crowd", w.ground, 10.0))
    thick = _chance(w)
    assert thin > 3 * thick, (thin, thick)
    # a vacancy on his ground raises it
    lid = int(c.execute("SELECT id FROM org_lines WHERE location_id=? AND description='a crowd' LIMIT 1", (w.ground,)).fetchone()[0])
    c.execute("UPDATE org_lines SET status='closed', ended_day=? WHERE id=?", (DAY - 5, lid))
    assert _chance(w) > thick
    # his precinct on his family's Pad and no case: the chance rises; an open case naming him lowers it again
    c.execute("UPDATE org_arrangements SET status='active'")
    padded = _chance(w)
    assert padded > thick
    c.execute("INSERT INTO crime_reports(day,crime_kind,offender_actor_id,status) VALUES (?,?,?,'open')", (DAY - 3, "extortion", w.soldier))
    assert _chance(w) < padded


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad.append(t.__name__)
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, repr(e)[:300])
        else:
            print("ok", t.__name__)
    print(f"{len(TESTS) - len(bad)} passed" + (f", {len(bad)} FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)
