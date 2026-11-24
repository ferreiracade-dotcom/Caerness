"""BZ1.6: ventures with stages, backers, parties, approvals and weighed outcomes.

Run: PYTHONPATH=. python tests/bz1_ventures_test.py"""
from __future__ import annotations

import sys
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world


def _day_of(conn, iso):
    from engine import world_calendar
    from engine.world_package import package_for
    return (date.fromisoformat(iso) - world_calendar._start(package_for(conn))).days


def _fund(conn, who, amount):
    from engine import ledger
    ledger.receive(conn, ("person", int(who)), amount, purpose="test funding")


def _cash(conn, who):
    from engine import ledger
    return ledger.balance(conn, ("person", int(who)))


def _start(w, day, **kw):
    from engine import ventures
    args = dict(kind="open_business", title="A new bar", backer_ref=f"person:{w.soldier}", location_id=None,
                budget_usd=10000.0, day=day)
    args.update(kw)
    return ventures.start_venture(w.conn, **args)


def _run(conn, start, steps, step=30):
    from engine import ventures
    for k in range(1, steps + 1):
        ventures.process_due_ventures(conn, start + step * k)


def test_open_business_completes_with_place():
    from engine import ventures
    w = _open_world()
    c = w.conn
    d0 = _day_of(c, "1977-04-01")
    _fund(c, w.soldier, 20000.0)
    pay = {"kind": "place", "place": {"name": "The New Bar", "place_kind": "bar_room", "location_id": w.ground,
                                      "owner_ref": f"person:{w.soldier}"}}
    pid = _start(w, d0, payoff=pay)
    _run(c, d0, 10)
    v = ventures.venture(c, pid)
    assert v["outcome"] == "completed", (v["outcome"], v["outcome_reason"], v["why"])
    assert abs(v["spent_usd"] - 10000.0) < 1.0, v["spent_usd"]
    assert c.execute("SELECT COUNT(*) FROM place_details d JOIN buildings b ON b.id=d.building_id WHERE b.name='The New Bar'").fetchone()[0] == 1
    assert c.execute("SELECT status FROM civilian_projects WHERE id=?", (pid,)).fetchone()[0] == "completed"
    assert c.execute("SELECT COUNT(*) FROM driver_readings WHERE subject_kind='venture' AND subject_id=?", (pid,)).fetchone()[0] == 1


def test_backer_runs_dry_stalls_then_fails():
    from engine import ventures
    w = _open_world()
    c = w.conn
    d0 = _day_of(c, "1977-04-01")
    _fund(c, w.soldier, 1000.0)
    pid = _start(w, d0)
    stalls = []
    for k in range(1, 14):
        ventures.process_due_ventures(c, d0 + 30 * k)
        assert _cash(c, w.soldier) >= -1e-9
        stalls.append(int(c.execute("SELECT stalled_days FROM venture_details WHERE project_id=?", (pid,)).fetchone()[0]))
    v = ventures.venture(c, pid)
    assert max(stalls) > 0 and v["outcome"] == "failed" and v["outcome_reason"] == "backer short of money", (v["outcome"], v["outcome_reason"], stalls)
    assert c.execute("SELECT status FROM civilian_projects WHERE id=?", (pid,)).fetchone()[0] == "failed"


def test_bad_drivers_fail_with_named_factor():
    from engine import business, ventures
    w = _open_world()
    c = w.conn
    d0 = _day_of(c, "1977-04-01")
    _fund(c, w.soldier, 20000.0)
    pid = _start(w, d0)
    old = business._demand_score
    business._demand_score = lambda weights, ctx: 0.0
    try:
        _run(c, d0, 10)
    finally:
        business._demand_score = old
    v = ventures.venture(c, pid)
    assert v["outcome"] == "failed" and "demand" in v["outcome_reason"], (v["outcome"], v["outcome_reason"])


def test_pending_approval_does_not_block_but_is_said():
    from engine import ventures
    w = _open_world()
    c = w.conn
    d0 = _day_of(c, "1977-04-01")
    _fund(c, w.soldier, 20000.0)
    pid = _start(w, d0)
    assert c.execute("SELECT status FROM venture_approvals WHERE project_id=? AND approval_kind='building_permit'", (pid,)).fetchone()[0] == "pending"
    _run(c, d0, 4)
    v = ventures.venture(c, pid)
    assert v["stage_key"] != "fit_out" or v["outcome"] is not None, v["stage_key"]
    assert any("building_permit pending: politics not built" in line for line in v["why"]), v["why"]


def test_refused_approval_fails():
    from engine import ventures
    w = _open_world()
    c = w.conn
    d0 = _day_of(c, "1977-04-01")
    _fund(c, w.soldier, 20000.0)
    pid = _start(w, d0)
    aid = c.execute("SELECT id FROM venture_approvals WHERE project_id=?", (pid,)).fetchone()[0]
    ventures.decide_approval(c, aid, "refused", d0 + 5, by_actor_id=w.boss, reason="the board said no")
    _run(c, d0, 2)
    v = ventures.venture(c, pid)
    assert v["outcome"] == "failed" and "building_permit refused" in v["outcome_reason"]


def test_caerness_resolver_skips_ventures():
    from engine import civilian
    w = _open_world()
    c = w.conn
    d0 = _day_of(c, "1977-04-01")
    pid = _start(w, d0)
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (d0 + 20,))  # the clock is where the call says (the opening has families with births due)
    civilian.process_due_civilian(c, d0 + 20)  # before the first venture event, so only the Caerness resolver could touch it
    r = c.execute("SELECT progress,last_resolved_day,status FROM civilian_projects WHERE id=?", (pid,)).fetchone()
    assert r["progress"] == 0 and r["last_resolved_day"] == d0 and r["status"] == "active"


def test_parties_and_terms_and_dead_backer():
    from engine import ventures
    w = _open_world()
    c = w.conn
    d0 = _day_of(c, "1977-04-01")
    _fund(c, w.soldier, 20000.0)
    term = dict(ref_kind="venture", ref_id=None, debtor_ref=f"person:{w.soldier}", creditor_ref=f"person:{w.capo}", amount_usd=500.0,
                first_due_day=d0 + 30, every_days=30, grace_days=30, breach_word="street", purpose="the partner's cut")
    pid = _start(w, d0, parties=[{"role": "partner", "ref": f"person:{w.capo}", "term": term}])
    v = ventures.venture(c, pid)
    assert v["parties"][0]["role"] == "partner" and v["parties"][0]["term_id"]
    c.execute("UPDATE actors SET status='dead' WHERE id=?", (w.soldier,))
    c.execute("UPDATE actor_life_profiles SET life_status='deceased', current_household_id=NULL WHERE actor_id=?", (w.soldier,))
    ventures.process_due_ventures(c, d0 + 40)
    v = ventures.venture(c, pid)
    assert v["outcome"] == "failed" and v["outcome_reason"] == "backer gone"


def test_seed_reproducible():
    from engine import agreement_terms, ventures
    snaps = []
    for _ in range(2):
        w = _open_world()
        c = w.conn
        d0 = _day_of(c, "1977-04-01")
        _fund(c, w.soldier, 6000.0)
        term = dict(ref_kind="venture", ref_id=None, debtor_ref=f"person:{w.capo}", creditor_ref=f"person:{w.soldier}", amount_usd=300.0,
                    first_due_day=d0 + 7, every_days=7, grace_days=14, breach_word="street", purpose="a cut")
        pid = _start(w, d0, parties=[{"role": "partner", "ref": f"person:{w.capo}", "term": term}])
        for k in range(1, 16):
            day = d0 + 30 * k
            agreement_terms.process_due_terms(c, day)
            ventures.process_due_ventures(c, day)
        snaps.append(([tuple(r) for r in c.execute("SELECT * FROM venture_details ORDER BY project_id")],
                      [tuple(r) for r in c.execute("SELECT day,path,owed_usd,effect_json FROM agreement_breaches ORDER BY id")],
                      [tuple(r) for r in c.execute("SELECT * FROM driver_readings ORDER BY subject_id")]))
        assert pid
    assert snaps[0] == snaps[1] and snaps[0][0] and snaps[0][1], snaps[0]


tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
tests.sort(key=lambda f: f.__code__.co_firstlineno)


def _run_all():
    ok = 0
    for t in tests:
        try:
            t()
            ok += 1
        except Exception:
            print("FAIL", t.__name__)
            traceback.print_exc()
    print(f"{ok}/{len(tests)} passed")
    return ok == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
