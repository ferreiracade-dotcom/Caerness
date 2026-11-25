"""P2: only real holdings are held. People, talk and a day's errands never become the protagonist's ventures, and
"drew notice" is not something he hears.

Run: PYTHONPATH=. python tests/p2_held_things_test.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world  # noqa: E402


def _held(c, **where):
    q = " AND ".join(f"{k}=?" for k in where) or "1"
    return c.execute(f"SELECT * FROM held_things WHERE {q}", tuple(where.values())).fetchall()


def _me(w):
    from engine.player import set_player
    set_player(w.conn, w.capo)
    return w.conn


def test_an_authored_person_or_rumour_is_not_a_holding():
    from engine import authoring
    w = open_world()
    c = _me(w)
    p = authoring.author(c, w.capo, "person", {"sex": "male", "age": 40, "place": w.ground}, "p-1")
    assert p.get("actor_id") and not _held(c, call_id="p-1"), p
    r = authoring.author(c, w.capo, "rumour", {"text": "the bakery is for sale", "place": w.ground}, "p-2")
    assert r.get("rumour_id") and not _held(c, call_id="p-2"), r


def test_another_mans_organisation_is_held_by_him_not_the_protagonist():
    from engine import authoring
    w = open_world()
    c = _me(w)
    other = authoring.author(c, w.capo, "person", {"sex": "male", "age": 40, "place": w.ground}, "o-1")["actor_id"]
    out = authoring.author(c, w.capo, "organisation", {"name": "The Orchard Street Club", "members": 2, "leader_actor_id": other,
                                                       "place": w.ground}, "o-2")
    assert [r["owner_actor_id"] for r in _held(c, call_id="o-2")] == [other], out


def test_a_days_errand_that_settles_leaves_nothing_held():
    from engine import free_operation
    w = open_world()
    c = _me(w)
    before = len(_held(c))
    out = free_operation.run(c, w.capo, "quietly ask around the parts trade whether anyone needs engine work", {"time": "a week"}, "e-1")
    assert out.get("commitment_id"), out
    c.execute("UPDATE world_state SET current_day=current_day+8 WHERE id=1")
    done = free_operation.settle_due(c, w.capo)
    assert done and "held_thing_id" not in done[0] and "stands as" not in done[0]["result"], done
    assert len(_held(c)) == before


def test_old_rows_that_are_not_holdings_never_happen_to_him():
    from engine import held_things
    w = open_world()
    c = _me(w)
    for name, shape, income in (("Frank Amato", "person", 0), ("an evening out", "thing", 0)):
        c.execute("""INSERT INTO held_things(name,kind_text,shape,owner_actor_id,income_weekly,start_day,created_day,updated_day,status)
                     VALUES (?,?,?,?,?,?,?,?,'active')""", (name, name, shape, w.capo, income, DAY, DAY, DAY))
    logged = []
    for k in range(1, 120):
        held_things.process_due(c, DAY + 7 * k, event_logger=lambda **e: logged.append(e))
    assert not logged, logged[:3]
    assert not c.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE '%drew notice%'", (w.capo,)).fetchone()


def test_his_earning_holding_changes_but_he_is_never_told_it_drew_notice():
    from engine import authoring, held_things
    w = open_world()
    c = _me(w)
    authoring.author(c, w.capo, "a chop shop", {"what": "the Route 1 chop shop", "legality": "illegal", "money": {"income": "400 a week"}}, "h-1")
    logged = []
    for k in range(1, 200):
        held_things.process_due(c, DAY + 7 * k, event_logger=lambda **e: logged.append(e["title"]))
    assert any("grew" in t or "shrank" in t for t in logged), logged[:5]
    assert not any("drew notice" in t for t in logged), logged
    assert not c.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND belief_text LIKE '%drew notice%'", (w.capo,)).fetchone()


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc(limit=4)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
