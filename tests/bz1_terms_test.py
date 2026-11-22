"""BZ1.5: agreement terms that fall due, and their breach paths.

Run: PYTHONPATH=. python tests/bz1_terms_test.py"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world


def _fund(conn, who, amount):
    from engine import ledger
    ledger.receive(conn, ("person", int(who)), amount, purpose="test funding")


def _cash(conn, who):
    from engine import ledger
    return ledger.balance(conn, ("person", int(who)))


def _term(conn, a, b, **kw):
    from engine import agreement_terms as at
    args = dict(ref_kind="test", ref_id=None, debtor_ref=f"person:{a}", creditor_ref=f"person:{b}", amount_usd=50.0,
                first_due_day=7, every_days=7, grace_days=14, breach_word="street", purpose="a weekly payment", day=0)
    args.update(kw)
    return at.add_term(conn, **args)


def _state(conn, tid):
    r = conn.execute("SELECT missed_count,owed_usd,status,next_due_day FROM agreement_terms WHERE id=?", (tid,)).fetchone()
    br = [tuple(x) for x in conn.execute("SELECT day,path,owed_usd FROM agreement_breaches WHERE term_id=? ORDER BY id", (tid,))]
    return tuple(r), br


def test_recurring_term_pays():
    from engine import agreement_terms as at
    w = _open_world()
    c = w.conn
    _fund(c, w.soldier, 1000.0)
    before = _cash(c, w.capo)
    tid = _term(c, w.soldier, w.capo)
    at.process_due_terms(c, 28)
    assert abs(_cash(c, w.capo) - before - 200.0) < 0.01 and abs(_cash(c, w.soldier) - 800.0) < 0.01
    assert c.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='other' AND metadata_json LIKE '%a weekly payment%'").fetchone()[0] == 4
    assert c.execute("SELECT status FROM agreement_terms WHERE id=?", (tid,)).fetchone()[0] == "active"


def test_shortfall_accrues_then_breaches():
    from engine import agreement_terms as at
    w = _open_world()
    c = w.conn
    assert _cash(c, w.soldier) < 1.0
    tid = _term(c, w.soldier, w.capo)
    at.process_due_terms(c, 14)
    row, br = _state(c, tid)
    assert row[0] == 2 and abs(row[1] - 100.0) < 0.01 and row[2] == "active" and br == []
    at.process_due_terms(c, 40)
    row, br = _state(c, tid)
    assert row[2] == "breached" and len(br) == 1, (row, br)
    assert abs(br[0][2] - row[1]) < 0.01 and abs(row[1] - 50.0 * row[0]) < 0.01


def test_breach_paths():
    from engine import agreement_terms as at, org_tension
    from engine.relationships import ensure_relationship
    w = _open_world()
    c = w.conn
    other = int(c.execute("SELECT org_actor_id FROM org_profiles WHERE org_actor_id<>? ORDER BY org_actor_id LIMIT 1", (w.org,)).fetchone()[0])
    day = 50
    # tension: two organisations, through each one's institution actor
    t = _term(c, w.boss, w.boss, debtor_ref=f"institution:{w.org}", creditor_ref=f"institution:{other}", breach_word="between_orgs")
    c.execute("UPDATE agreement_terms SET owed_usd=4000 WHERE id=?", (t,))
    before = org_tension.level(c, other, w.org, day)
    bid = at.breach(c, t, day)
    assert org_tension.level(c, other, w.org, day) > before
    assert json.loads(c.execute("SELECT effect_json FROM agreement_breaches WHERE id=?", (bid,)).fetchone()[0])["tension_delta"] > 0
    # debt between organisations
    t = _term(c, w.boss, w.boss, debtor_ref=f"institution:{w.org}", creditor_ref=f"institution:{other}", breach_word="street")
    c.execute("UPDATE agreement_terms SET owed_usd=300 WHERE id=?", (t,))
    n = c.execute("SELECT COUNT(*) FROM org_debts").fetchone()[0]
    at.breach(c, t, day)
    assert c.execute("SELECT COUNT(*) FROM org_debts").fetchone()[0] == n + 1
    # street debt between persons: resentment rises
    t = _term(c, w.soldier, w.capo, breach_word="street")
    c.execute("UPDATE agreement_terms SET owed_usd=300 WHERE id=?", (t,))
    ensure_relationship(c, w.capo, w.soldier, 0)
    r0 = c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (w.capo, w.soldier)).fetchone()[0]
    bid = at.breach(c, t, day)
    r1 = c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (w.capo, w.soldier)).fetchone()[0]
    assert r1 > r0 and "no org" in c.execute("SELECT effect_json FROM agreement_breaches WHERE id=?", (bid,)).fetchone()[0]
    # grudge
    t = _term(c, w.soldier, w.capo, breach_word="grudge")
    c.execute("UPDATE agreement_terms SET owed_usd=300 WHERE id=?", (t,))
    at.breach(c, t, day)
    r2 = c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (w.capo, w.soldier)).fetchone()[0]
    assert r2 > r1
    # claim: nothing reads it yet
    t = _term(c, w.soldier, w.capo, breach_word="sue")
    c.execute("UPDATE agreement_terms SET owed_usd=300 WHERE id=?", (t,))
    bid = at.breach(c, t, day)
    assert "unread" in c.execute("SELECT effect_json FROM agreement_breaches WHERE id=?", (bid,)).fetchone()[0]


def test_skip_equals_steps():
    from engine import agreement_terms as at
    results = []
    for mode in ("steps", "skip"):
        w = _open_world()
        c = w.conn
        _fund(c, w.soldier, 120.0)  # pays two weeks, then runs short
        tid = _term(c, w.soldier, w.capo, grace_days=30)
        if mode == "steps":
            for d in range(30, 361, 30):
                at.process_due_terms(c, d)
        else:
            at.process_due_terms(c, 360)
        results.append(_state(c, tid))
    assert results[0] == results[1], results
    assert results[0][0][2] == "breached" and len(results[0][1]) == 1


def test_orphaned_when_party_gone():
    from engine import agreement_terms as at
    w = _open_world()
    c = w.conn
    _fund(c, w.soldier, 500.0)
    tid = _term(c, w.soldier, w.capo)
    c.execute("UPDATE actors SET status='dead' WHERE id=?", (w.capo,))
    c.execute("UPDATE actor_life_profiles SET life_status='deceased', current_household_id=NULL WHERE actor_id=?", (w.capo,))
    at.process_due_terms(c, 30)
    row, br = _state(c, tid)
    assert row[2] == "orphaned" and br[-1][1] == "orphaned"
    assert "creditor" in c.execute("SELECT effect_json FROM agreement_breaches WHERE term_id=?", (tid,)).fetchone()[0]


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
