"""Choices a made man weighs (task B10): where a racket lands, asking first, the killing and its aftermath.

Run: PYTHONPATH=. python tests/outfit_choices_test.py   (builds a scratch Saint Jude opening)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, drives, forced_roll, open_world, rel, run_review


def _cash(w, actor, amount=20000.0):
    from engine import ledger
    ledger.receive(w.conn, ("person", actor), amount, purpose="test purse")


def _neutral(w):
    w.conn.execute("UPDATE org_arrangements SET status='ended'")
    drives(w.conn, w.soldier, ambition=0.5, risk_tolerance=0.5)


def _effects(row):
    return json.loads(row["effects_json"])


def _siblings(w):
    """The places beside his ground that he may start in (his ground is the first of his places)."""
    from engine import orgs, outfit_motives as om
    return om._places(w.conn, orgs.seat_of(w.conn, w.soldier, w.org))[1:]


def _crowd(w, loc, n=300):
    c = w.conn
    holding = int(c.execute("SELECT id FROM org_holdings LIMIT 1").fetchone()[0])
    for _ in range(n):
        c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,started_day) VALUES (?,?,?,?,?,?,0)",
                  (holding, w.unit, w.capo, "a crowd", loc, 10.0))


def _racket_world(vacancy: bool):
    """A soldier with cash whose own ground is crowded; the places beside it are thin, and one has a lost line when `vacancy`."""
    w = open_world()
    c = w.conn
    _neutral(w)
    _cash(w, w.soldier)
    _crowd(w, w.ground)
    sib = _siblings(w)
    w.vacant = sib[0]
    if vacancy:
        bookmaking = int(c.execute("SELECT id FROM org_holdings WHERE pool_key='bookmaking' LIMIT 1").fetchone()[0])
        c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,status,started_day,ended_day) "
                  "VALUES (?,?,?,?,?,?,'closed',0,?)", (bookmaking, w.unit, w.capo, "a book", w.vacant, 300.0, DAY - 5))
    return w


def _started(w):
    return w.conn.execute(
        "SELECT l.*,h.pool_key,h.source FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE l.started_day=? AND h.source='started'", (DAY,)).fetchall()


def test_racket_lands_where_the_opportunity_is():
    sizes = []
    for vacancy in (True, False):
        w = _racket_world(vacancy)
        before = w.conn.execute("SELECT COALESCE(SUM(amount),0) FROM resources WHERE actor_id=? AND resource_type='cash'", (w.soldier,)).fetchone()[0]
        with forced_roll("start_racket"):
            row = run_review(w.conn, w.soldier)
        assert row["action_type"] == "org_action" and _effects(row)["org_action_kind"] == "start_racket", dict(row)
        lines = _started(w)
        assert len(lines) == 1 and int(lines[0]["holder_actor_id"]) == w.soldier
        line = lines[0]
        assert line["location_id"] != w.ground, "the crowded ground is not where he starts"
        if vacancy:
            assert line["location_id"] == w.vacant and line["pool_key"] == "bookmaking", dict(line)
        after = w.conn.execute("SELECT COALESCE(SUM(amount),0) FROM resources WHERE actor_id=? AND resource_type='cash'", (w.soldier,)).fetchone()[0]
        assert after < before, "he paid the start cost"
        sizes.append(float(line["weekly_take"]))
    assert sizes[0] > sizes[1], sizes  # the line follows the opportunity


def test_cautious_man_asks_first():
    w = open_world()
    c = w.conn
    drives(c, w.soldier, risk_tolerance=0.1, aggression=0.5, loyalty=0.5, ambition=0.5)
    rel(c, w.soldier, w.boss, trust=80, loyalty=80)
    rel(c, w.soldier, w.capo, resentment=90)
    with forced_roll("remove_superior"):
        row = run_review(c, w.soldier)
    assert row["action_type"] == "org_action" and _effects(row)["org_action_kind"] == "seek_permission", dict(row)
    item = c.execute("SELECT * FROM org_agenda WHERE actor_id=? AND kind='grant_or_refuse' AND status='open'", (w.boss,)).fetchone()
    assert item is not None and item["subject_id"] == w.soldier
    from engine import org_choices, orgs
    assert orgs.is_living(c, w.capo)
    kinds = {x.action_kind for x in org_choices.org_provider(c, w.boss, "STRATEGIC", DAY + 10, {})}
    assert {"grant_leave", "refuse_leave", "warn_capo"} <= kinds, kinds
    # a bold man with real fear of the capo acts alone
    b = open_world()
    drives(b.conn, b.soldier, risk_tolerance=0.95, aggression=0.9)
    rel(b.conn, b.soldier, b.capo, resentment=90)
    from engine import orgs as o2
    o2.add_agenda(b.conn, b.boss, "hit", DAY + 3, subject_kind="actor", subject_id=b.soldier, metadata={"known_to": [b.soldier]})
    with forced_roll("remove_superior"):
        row = run_review(b.conn, b.soldier)
    assert _effects(row)["org_action_kind"] == "remove_superior" and not o2.is_living(b.conn, b.capo), dict(row)


def _kill_alone(w):
    from engine import org_choices
    return org_choices.execute(w.conn, w.soldier, "remove_superior",
                               {"org": w.org, "target": w.capo, "unit_id": w.unit, "sanctioned": False}, DAY)


def _open(c, actor, kind):
    return c.execute("SELECT * FROM org_agenda WHERE actor_id=? AND kind=? AND status='open'", (actor, kind)).fetchall()


def test_unsanctioned_killing_brings_a_hunt_sanctioned_does_not():
    from engine import org_choices, orgs
    # unsanctioned, the boss did not want it: a hunt, and both histories are flagged
    w = open_world()
    c = w.conn
    _kill_alone(w)
    assert not orgs.is_living(c, w.capo)
    hunts = _open(c, w.boss, "discipline_hunt")
    assert len(hunts) == 1 and hunts[0]["subject_id"] == w.soldier
    assert c.execute("SELECT history_due FROM org_seats WHERE actor_id=? AND org_actor_id=?", (w.soldier, w.org)).fetchone()[0] == 1
    assert c.execute("SELECT history_due FROM org_seats WHERE actor_id=? AND org_actor_id=?", (w.capo, w.org)).fetchone()[0] == 1
    fatal = c.execute("SELECT metadata_json FROM harm_incidents WHERE actor_id=? AND fatal=1", (w.capo,)).fetchone()
    assert json.loads(fatal[0])["offender_actor_id"] == w.soldier
    # the boss wanted it: no hunt, and the killer gains standing
    d = open_world()
    rel(d.conn, d.boss, d.capo, resentment=80, respect=10)
    s0 = d.conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=?", (d.soldier, d.org)).fetchone()[0]
    _kill_alone(d)
    assert not _open(d.conn, d.boss, "discipline_hunt")
    assert d.conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=?", (d.soldier, d.org)).fetchone()[0] > s0
    # sanctioned: he asked, the boss granted, he carried it out: no hunt
    s = open_world()
    k = s.conn
    org_choices.execute(k, s.soldier, "seek_permission", {"org": s.org, "target": s.capo, "unit_id": s.unit}, DAY)
    ask = _open(k, s.boss, "grant_or_refuse")[0]
    org_choices.execute(k, s.boss, "grant_leave", {"agenda_id": ask["id"], "applicant": s.soldier, "target": s.capo, "org": s.org}, DAY + 3)
    hit = _open(k, s.soldier, "hit")[0]
    assert hit["subject_id"] == s.capo and json.loads(hit["metadata_json"])["sanctioned"] is True
    offers = [x for x in org_choices.org_provider(k, s.soldier, "STRATEGIC", DAY + 5, {}) if x.action_kind == "hit"]
    assert offers
    org_choices.execute(k, s.soldier, "hit", {"agenda_id": hit["id"], "target": s.capo, "sanctioned": True}, DAY + 5)
    assert not orgs.is_living(k, s.capo) and not _open(k, s.boss, "discipline_hunt")


def test_capo_killing_refills_seat_and_reparents_crew():
    from engine import orgs
    from engine.org_lifecycle import fill_unit_leader
    w = open_world()
    c = w.conn
    assert fill_unit_leader(c, w.unit, DAY) is None, "a living leader's unit has no vacancy"
    mates = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE unit_id=? AND role_key='soldier' AND status='active' ORDER BY actor_id", (w.unit,))]
    under_capo = {int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active'", (w.capo,))}
    held = [int(r[0]) for r in c.execute("SELECT id FROM org_lines WHERE holder_actor_id=? AND unit_id=? AND status='active'", (w.capo, w.unit))]
    # a sanctioned killing, so the boss's list holds only the seat
    from engine import org_choices
    org_choices.execute(c, mates[0], "seek_permission", {"org": w.org, "target": w.capo, "unit_id": w.unit}, DAY)
    ask = _open(c, w.boss, "grant_or_refuse")[0]
    org_choices.execute(c, w.boss, "grant_leave", {"agenda_id": ask["id"], "applicant": mates[0], "target": w.capo, "org": w.org}, DAY)
    org_choices.execute(c, mates[0], "hit", {"target": w.capo, "sanctioned": True, "agenda_id": _open(c, mates[0], "hit")[0]["id"]}, DAY + 1)
    fill = _open(c, w.boss, "fill_capo_seat")
    assert len(fill) == 1 and fill[0]["subject_id"] == w.unit
    row = run_review(c, w.boss, DAY + 10)
    assert _effects(row)["org_action_kind"] == "fill_capo_seat", dict(row)
    new = int(c.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (w.unit,)).fetchone()[0])
    assert new != w.capo and orgs.is_living(c, new) and new in mates
    seat = orgs.seat_of(c, new, w.org)
    assert seat["role_key"] == "capo" and seat["superior_actor_id"] == w.boss and seat["level"] == 4
    assert orgs.unit_leader_of(c, mates[1] if mates[1] != new else mates[2], w.org) == new
    for a in under_capo - {new, mates[0]}:
        assert orgs.superior_of(c, a, w.org) == new, a
    for line in held:
        assert c.execute("SELECT holder_actor_id,unit_id FROM org_lines WHERE id=?", (line,)).fetchone()[:] == (new, w.unit)
    assert not _open(c, w.boss, "fill_capo_seat")
    role = c.execute("SELECT role_text FROM institution_memberships WHERE member_actor_id=? AND institution_actor_id=?", (new, w.org)).fetchone()[0]
    assert role.startswith("Capo"), role


def _kickup_from(c, actor):
    return float(c.execute("SELECT COALESCE(SUM(amount),0) FROM org_money WHERE kind='kickup' AND from_actor_id=?", (actor,)).fetchone()[0])


def _start_big_line(hidden: bool):
    from engine import org_choices, org_money
    w = _racket_world(True)
    c = w.conn
    cand = org_choices.org_provider  # noqa: F841 (the provider is exercised in the other tests)
    from engine import outfit_choices as oc
    offer = oc.start_candidates(c, w.soldier, w.org, DAY)[0]
    with forced_roll("hidden") if hidden else forced_roll():
        org_choices.execute(c, w.soldier, "start_racket", offer["payload"], DAY)
    line = _started(w)[0]
    assert bool(line["hidden"]) is hidden, dict(line)
    c.execute("UPDATE org_lines SET weekly_take=?, started_day=0 WHERE id=?", (50000.0, line["id"]))
    org_money.post_period(c, DAY, 28)
    taken = float(c.execute("SELECT COALESCE(SUM(amount),0) FROM org_money WHERE kind='take' AND to_actor_id=?", (w.soldier,)).fetchone()[0])
    return _kickup_from(c, w.soldier), taken


def test_hidden_racket_kicks_up_nothing():
    open_kick, open_take = _start_big_line(False)
    hid_kick, hid_take = _start_big_line(True)
    assert abs(open_take - hid_take) < 1e-6, "the line brings the same take either way"
    assert open_kick > hid_kick + 1000.0, (open_kick, hid_kick)  # the open line kicks up its share
    base_w = _racket_world(True)
    from engine import org_money
    org_money.post_period(base_w.conn, DAY, 28)
    # nothing is kicked up on the hidden take (the associates' pay out of the patron's whole take can only lower the rest)
    assert hid_kick <= _kickup_from(base_w.conn, base_w.soldier) + 1e-6, "a hidden line adds nothing to what he kicks up"


def test_associate_starts_a_small_line_under_his_soldier():
    from engine import org_choices
    from engine import outfit_choices as oc
    w = open_world()
    c = w.conn
    assoc = int(c.execute("SELECT actor_id FROM org_seats WHERE role_key='associate' AND superior_actor_id=? AND status='active' LIMIT 1",
                          (w.soldier,)).fetchone()[0])
    _cash(w, assoc, 5000.0)
    offers = oc.start_candidates(c, assoc, w.org, DAY)
    assert offers, "an associate with the money weighs a small line"
    org_choices.execute(c, assoc, "start_racket", offers[0]["payload"], DAY)
    line = _started(w)[0]
    assert line["holder_actor_id"] == w.soldier and line["weekly_take"] < 150.0, dict(line)


def test_provider_silent_for_non_members():
    from engine import org_choices
    w = open_world()
    c = w.conn
    outsider = int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND id NOT IN (SELECT actor_id FROM org_seats) ORDER BY id LIMIT 1").fetchone()[0])
    with forced_roll("start_racket", "remove_superior"):
        assert org_choices.org_provider(c, outsider, "STRATEGIC", DAY, {}) == []
        assert not org_choices._reason(c, outsider, DAY)


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
