"""Prison J1.5: the outside carries on while a man is inside, for NPCs and the protagonist alike.

Run: PYTHONPATH=. python tests/j1_outside_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.j1_admission_test import _convict, _run, _stay  # noqa: E402
from tests.outfit_choice_fixture import DAY, open_world  # noqa: E402

from engine import ledger, org_informing, org_lifecycle, org_motives, orgs, prison, prison_channels as pc  # noqa: E402
from engine.player import set_player  # noqa: E402


def _world(protagonist=False):
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    if protagonist:
        set_player(c, w.soldier)
    _convict(c, w.soldier, 1000)
    _run(c)
    return w, c


def _p_lose_seat(c, a, org, since) -> float:
    """The chance the weekly decision gives his seat away, found by bisecting the roll that decides it (the roll passes when it is under p)."""
    old = org_motives._roll
    lo, hi = 0.0, 1.0
    try:
        for _ in range(24):
            mid = (lo + hi) / 2
            org_motives._roll = lambda conn, actor, day, stream, m=mid: m if stream == "held_seat" else 0.99
            c.execute("UPDATE org_seats SET status='active', left_day=NULL WHERE actor_id=? AND org_actor_id=?", (a, org))
            org_lifecycle._held_decisions(c, {a: since}, DAY)
            if orgs.seat_of(c, a, org)["status"] == "held":
                lo = mid
            else:
                hi = mid
    finally:
        org_motives._roll = old
        c.execute("UPDATE org_seats SET status='active', left_day=NULL WHERE actor_id=? AND org_actor_id=?", (a, org))
    return lo


def _give_household(c, a):
    """A household with his wife in it (the opening gave him none): its id."""
    wife = int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND id<>? ORDER BY id DESC LIMIT 1", (a,)).fetchone()[0])
    hh = int(c.execute("INSERT INTO households(name,head_actor_id,status,wealth,liquidity,created_day,updated_day) VALUES ('J1 test',?, 'active',0,0,0,0)", (a,)).lastrowid)
    c.execute("INSERT INTO household_members(household_id,actor_id,role,joined_day,status) VALUES (?,?,?,0,'active')", (hh, a, "head"))
    c.execute("INSERT INTO household_members(household_id,actor_id,role,joined_day,status) VALUES (?,?,?,0,'active')", (hh, wife, "spouse"))
    return hh


def test_strong_channel_keeps_the_seat_longer():
    for protagonist in (False, True):
        w, c = _world(protagonist)
        a, org = w.soldier, w.org
        since = DAY - 400
        p_none = _p_lose_seat(c, a, org, since)
        assert p_none > 0.0
        st = _stay(c, a)
        pc.open_channel(c, int(st["id"]), "bought_guard", None, DAY)
        c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
        grip = pc.channel_grip(c, a)
        assert grip > 0.3
        p_chan = _p_lose_seat(c, a, org, since)
        dec = org_lifecycle._lc(c, org)["held_decision"]
        cw = org_lifecycle._num(c, dec, "channel_weight", 0.0)
        assert cw > 0
        assert p_chan < p_none
        assert abs(p_chan / p_none - (1.0 - cw * grip)) < 1e-3, (p_chan, p_none, cw, grip)  # the grip takes its weighed share off the pressure


def test_no_prison_data_no_change():
    w, c = _world()
    a, org = w.soldier, w.org
    st = _stay(c, a)
    pc.open_channel(c, int(st["id"]), "bought_guard", None, DAY)
    p_with = _p_lose_seat(c, a, org, DAY - 400)
    orig = pc.rules
    pc.rules = lambda conn: {}  # a package with no prison data: no grip, no change
    try:
        p_without = _p_lose_seat(c, a, org, DAY - 400)
        assert pc.channel_grip(c, a) == 0.0
    finally:
        pc.rules = orig
    p_none = None
    c.execute("UPDATE prison_channels SET status='closed'")
    p_none = _p_lose_seat(c, a, org, DAY - 400)
    assert abs(p_without - p_none) < 1e-9 and p_with < p_none


def test_two_seats_both_weighed_inside_seat_not():
    for protagonist in (False, True):
        w, c = _world(protagonist)
        a = w.soldier
        st = _stay(c, a)
        inside_org = c.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (st["group_id"],)).fetchone()[0]
        assert orgs.seat_of(c, a, inside_org)["status"] == "active"
        old = org_motives._roll
        org_motives._roll = lambda conn, actor, day, stream: 0.0  # every decision passes
        try:
            org_lifecycle._held_decisions(c, {a: DAY - 800}, DAY)
        finally:
            org_motives._roll = old
        assert orgs.seat_of(c, a, w.org)["status"] == "held"  # the outside seat is weighed and given away
        assert orgs.seat_of(c, a, inside_org)["status"] == "active"  # the inside seat has no such decision


def test_released_man_takes_back_what_is_free():
    w, c = _world()
    a = w.soldier
    old = org_motives._roll
    org_motives._roll = lambda conn, actor, day, stream: 0.0
    try:
        org_lifecycle._held_decisions(c, {a: DAY - 800}, DAY)
    finally:
        org_motives._roll = old
    assert orgs.seat_of(c, a, w.org)["status"] == "held"
    st = _stay(c, a)
    prison.leave(c, int(st["id"]), DAY + 400, "released")
    c.execute("UPDATE custody SET kind='released', until_day=? WHERE actor_id=? AND kind='held'", (DAY + 400, a))
    c.execute("UPDATE sentences SET status='served' WHERE actor_id=? AND status='serving'", (a,))
    org_lifecycle._held_and_released(c, DAY + 401)
    assert orgs.seat_of(c, a, w.org)["status"] == "active"


def test_standing_outside_decays_without_a_channel_and_holds_with_one():
    w, c = _world()
    a, org = w.soldier, w.org
    c.execute("UPDATE org_seats SET standing=0.5 WHERE actor_id=? AND org_actor_id=?", (a, org))
    prison.carry_on(c, DAY + 7)
    quiet = orgs.seat_of(c, a, org)["standing"]
    assert quiet < 0.5
    c.execute("UPDATE org_seats SET standing=0.5 WHERE actor_id=? AND org_actor_id=?", (a, org))
    pc.open_channel(c, int(_stay(c, a)["id"]), "bought_guard", None, DAY + 7)
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY + 7,))
    prison.carry_on(c, DAY + 7)
    held = orgs.seat_of(c, a, org)["standing"]
    assert quiet < held < 0.5


def test_envelope_shrinks_with_time_and_a_family_going_without_pushes_toward_talking():
    w, c = _world()
    a, org = w.soldier, w.org
    hh = _give_household(c, a)
    assert prison._household(c, a) == hh
    c.execute("UPDATE org_seats SET standing=0.8 WHERE actor_id=? AND org_actor_id=?", (a, org))
    head = orgs.head_of(c, org)
    c.execute("DELETE FROM underworld_leader_wealth WHERE actor_id=?", (head,))
    c.execute("DELETE FROM resources WHERE actor_id=? AND resource_type='cash'", (head,))
    c.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,?,?)", (head, "cash", 1_000_000))
    c.execute("UPDATE households SET liquidity=0 WHERE id=?", (hh,))
    need0 = prison.family_need(c, a, DAY)
    assert need0 > 0.99  # his household has nothing
    st = _stay(c, a)
    early = c.execute("SELECT liquidity FROM households WHERE id=?", (hh,)).fetchone()[0]
    prison.carry_on(c, int(st["since_day"]) + 7)
    first = c.execute("SELECT liquidity FROM households WHERE id=?", (hh,)).fetchone()[0] - early
    assert first > 0
    c.execute("UPDATE households SET liquidity=0 WHERE id=?", (hh,))
    c.execute("UPDATE org_seats SET standing=0.8 WHERE actor_id=? AND org_actor_id=?", (a, org))
    prison.carry_on(c, int(st["since_day"]) + 7 * 120)  # much later
    later = c.execute("SELECT liquidity FROM households WHERE id=?", (hh,)).fetchone()[0]
    assert 0 <= later < first  # the longer he is held, the thinner the envelope
    # a family with savings is not going without
    c.execute("UPDATE households SET liquidity=100000 WHERE id=?", (hh,))
    assert prison.family_need(c, a, DAY) < 0.01
    c.execute("UPDATE households SET liquidity=0 WHERE id=?", (hh,))
    f = org_informing._man_factors(c, a, org, DAY)
    assert f["family_need"] > 0.99  # read by the weighing of whether he talks


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
