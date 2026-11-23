"""P1b: corruption and fraud start on their own.

Run: PYTHONPATH=. python tests/p1b_graft_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

ZONING = "office:zoning:board"
COUNCIL = "office:council:body"
MAYOR = "office:city-hall:mayor"


def _trial(c, seed, fn):
    c.execute("SAVEPOINT trial")
    try:
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed,))
        return fn()
    finally:
        c.execute("ROLLBACK TO trial")
        c.execute("RELEASE trial")


def _official(c):
    from engine import offices
    return [a for _, _, a in offices.members(c, ZONING)][0]


def test_weighing_follows_need_risk_and_temperament():
    from engine import civic_graft
    w = _open_world()
    c = w.conn
    off = _official(c)
    base = civic_graft.weigh(c, w.soldier, 1.0, off, 10)["p"]
    assert civic_graft.weigh(c, w.soldier, 3.0, off, 10)["p"] > base
    c.execute("INSERT OR REPLACE INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,0.5,0.1,0.5,0.9,0.5,0.1)", (w.soldier,))
    timid = civic_graft.weigh(c, w.soldier, 1.0, off, 10)["p"]
    c.execute("INSERT OR REPLACE INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,0.5,0.9,0.5,0.1,0.5,0.9)", (w.soldier,))
    bold = civic_graft.weigh(c, w.soldier, 1.0, off, 10)["p"]
    assert bold > timid
    assert 0.0 < timid < bold < 1.0  # neither a rule nor a ceiling


def test_a_need_before_a_board_sometimes_becomes_a_payment_and_not_always():
    from engine import civic_graft, civic_votes, offices
    w = _open_world()
    c = w.conn
    iid = civic_votes.open_item(c, ZONING, "zoning_variance", {"sponsor": w.soldier, "title": "a variance"}, vote_day=60, day=10)
    c.execute("INSERT OR REPLACE INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,0.5,0.9,0.5,0.1,0.5,0.9)", (w.soldier,))
    got = []
    for s in range(1, 200):
        def go():
            c.execute("UPDATE civic_items SET subject_json=? WHERE id=?", ('{"sponsor": %d, "title": "a variance"}' % w.soldier, iid))
            return civic_graft.consider_item(c, iid, 10)
        got.append(_trial(c, s, go) is not None)
    assert any(got) and not all(got), sum(got)


def test_nobody_pays_on_the_protagonists_behalf_but_he_is_told_of_an_offer():
    from engine import civic_graft, civic_votes, offices, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.soldier)
    iid = civic_votes.open_item(c, ZONING, "zoning_variance", {"sponsor": w.soldier, "title": "his variance"}, vote_day=60, day=10)
    c.execute("INSERT OR REPLACE INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,0.5,0.9,0.5,0.1,0.5,0.9)", (w.soldier,))
    for s in range(1, 60):
        def go():
            c.execute("UPDATE civic_items SET subject_json=? WHERE id=?", ('{"sponsor": %d, "title": "his variance"}' % w.soldier, iid))
            return civic_graft.consider_item(c, iid, 10)
        assert _trial(c, s, go) is None  # his payments are his own act
    # the rule is the same for him as for anyone in his place
    off = _official(c)
    mine = civic_graft.weigh(c, w.soldier, 1.0, off, 10)["p"]
    c.execute("INSERT OR REPLACE INTO actor_drives SELECT ?,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism FROM actor_drives WHERE actor_id=?", (w.capo, w.soldier))
    assert abs(civic_graft.weigh(c, w.capo, 1.0, off, 10)["p"] - mine) < 1e-9
    # as an official he is offered, and told
    player.set_player(c, off)
    told = 0
    for s in range(1, 120):
        def go():
            c.execute("UPDATE civic_items SET subject_json=? WHERE id=?", ('{"sponsor": %d, "title": "a bill"}' % w.capo, iid))
            c.execute("INSERT OR REPLACE INTO actor_drives SELECT ?,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism FROM actor_drives WHERE actor_id=?", (w.capo, w.soldier))
            civic_graft.consider_item(c, iid, 10)
            n = c.execute("SELECT COUNT(*) FROM delivery_ledger WHERE viewer_actor_id=? AND kind='offer'", (off,)).fetchone()[0]
            assert c.execute("SELECT COUNT(*) FROM org_arrangements WHERE official_actor_id=? AND position_key LIKE 'political:%'", (off,)).fetchone()[0] == 0
            return n
        told += _trial(c, s, go)
    assert told > 0


def test_a_close_race_sometimes_tempts_a_candidate():
    from engine import civic_graft, races
    w = _open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=150 WHERE id=1")
    races.schedule(c, 150)
    rid = int(c.execute("SELECT r.id FROM races r JOIN offices o ON o.id=r.office_id WHERE o.office_key=? ORDER BY r.election_day LIMIT 1", (MAYOR,)).fetchone()[0])
    for who in (w.capo, w.boss):
        try:
            races.file(c, who, rid, 150)
        except ValueError:
            pass
    el = int(races.race(c, rid)["election_day"])
    n_cands = len(races.candidates(c, rid))
    assert n_cands >= 1
    for who in (w.soldier,):
        try:
            races.file(c, who, rid, 150)
        except ValueError:
            pass
    got = []
    for s in range(1, 150):
        def go():
            for a in races.candidates(c, rid):
                c.execute("INSERT OR REPLACE INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,0.5,0.9,0.5,0.1,0.5,0.9)", (a,))
            return civic_graft.fraud_pass(c, el - 7)
        got.append(_trial(c, s, go))
    assert len(races.candidates(c, rid)) >= 2, races.candidates(c, rid)
    assert any(got) and not all(got), sum(map(bool, got))


if __name__ == "__main__":
    failed = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f()
                print("PASS", n)
            except Exception:
                failed += 1
                print("FAIL", n)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
