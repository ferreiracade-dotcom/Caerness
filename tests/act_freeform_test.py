"""act rework: free-form operations, amounts, partial results, counters, memory paging. One packaged-world copy, sections in order."""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def t_amounts(conn, w):
    from engine import ledger, player_operations as po
    me, biz, outfit, hh = w["me"], w["business"], w["outfit"], w["household"]
    assert ledger.amount_of(37) == 37.0 and ledger.amount_of("37 silver") == 37.0 and ledger.amount_of("3 modest") == 9.0
    assert ledger.amount_of("half", 10) == 5.0 and ledger.amount_of("all of it", 7) == 7.0 and ledger.amount_of("25%", 8) == 2.0
    for bad in ("lots", "", -1, True):
        try:
            ledger.amount_of(bad)
        except ValueError:
            continue
        raise AssertionError(bad)

    # money to an institution, a polity, a household; and spent with no recipient
    inst = int(conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND id NOT IN (SELECT institution_actor_id FROM political_polities) LIMIT 1").fetchone()[0])
    pol = conn.execute("SELECT id,institution_actor_id FROM political_polities ORDER BY id LIMIT 1").fetchone()
    ledger.transfer(conn, ("business", biz), ("person", me), 1.0, flow_kind="other", purpose="t")
    conn.execute("UPDATE underworld_leader_wealth SET liquid_wealth=50 WHERE actor_id=?", (me,)) if conn.execute(
        "SELECT 1 FROM underworld_leader_wealth WHERE actor_id=?", (me,)).fetchone() else conn.execute(
        "UPDATE resources SET amount=50 WHERE actor_id=? AND resource_type='cash'", (me,))
    b0 = ledger.balance(conn, ("institution", inst))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"institution:{inst}", "amount": 12}, intent="A gift to the house.")
    assert r["status"] == "applied" and abs(ledger.balance(conn, ("institution", inst)) - b0 - 12) < 1e-9, r
    p0 = ledger.balance(conn, ("polity", pol["id"]))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"polity:{pol['id']}", "amount": "5 silver"}, intent="Tax paid.")
    assert r["status"] == "applied" and abs(ledger.balance(conn, ("polity", pol["id"])) - p0 - 5) < 1e-9, r
    assert abs(ledger.balance(conn, ("institution", pol["institution_actor_id"])) - p0 - 5) < 1e-9  # a polity's seat is its treasury
    h0 = ledger.balance(conn, ("household", hh))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"household:{hh}", "amount": "half"}, intent="Keep.")
    assert r["status"] == "applied" and ledger.balance(conn, ("household", hh)) > h0, r
    m0 = ledger.balance(conn, ("person", me))
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": "spend", "amount": 4, "purpose": "a feast"}, intent="A feast.")
    assert r["status"] == "applied" and abs(m0 - ledger.balance(conn, ("person", me)) - 4) < 1e-9, r
    # the sink needs rights: an institution he does not lead cannot be drawn on
    assert po.execute(conn, me, "pay", target_actor_id=None, details={"from": f"institution:{inst}", "to": "me", "amount": 1}, intent="x")["status"] == "refused"

    # an oversized sum pays what is there and says so
    r = po.execute(conn, me, "pay", target_actor_id=None, details={"to": f"institution:{inst}", "amount": 100000}, intent="All of it.")
    assert r["status"] == "partial" and r.get("short_of") and not re.search(r"\d", r["summary"]), r
    assert ledger.balance(conn, ("person", me)) < 1e-6


def t_hire_many(conn, w):
    import json
    from engine import ledger, player_operations as po
    me, outfit, hh = w["me"], w["outfit"], w["household"]
    conn.execute("UPDATE underworld_organizations SET treasury=5000 WHERE id=?", (outfit,))
    a0 = count(conn, "actors")
    r = po.execute(conn, me, "hire", target_actor_id=None, details={"count": 30, "into": f"outfit:{outfit}", "role": "member", "wage": 0.1, "_call_id": "h1"},
                   intent="I take on thirty men.")
    assert r["status"] == "applied" and r["hired"] == 30, r
    staffed = conn.execute("SELECT actor_id,metadata_json FROM underworld_personnel WHERE organization_id=? AND status='active' AND json_extract(metadata_json,'$.wage') IS NOT NULL", (outfit,)).fetchall()
    assert len(staffed) == 30 and json.loads(staffed[0][1])["wage"] == 0.1, len(staffed)  # the wage is stored, not dropped
    assert count(conn, "actors") >= a0  # revealed, never invented out of nothing: pool-bound
    # more asked than the place has: those there are, with the reason in words
    r = po.execute(conn, me, "hire", target_actor_id=None, details={"count": 5000, "into": f"outfit:{outfit}", "role": "member", "_call_id": "h2"},
                   intent="I take on five thousand men.")
    assert r["status"] == "partial" and 0 < r["hired"] < 5000 and "aren't that many" in r["summary"] and r["shortfall"], r
    # pay bounds the number: a poor household takes only what it can pay
    conn.execute("UPDATE households SET liquidity=0.25 WHERE id=?", (hh,))
    r = po.execute(conn, me, "hire", target_actor_id=None, details={"count": 20, "into": f"household:{hh}", "role": "servant", "wage": 0.1, "_call_id": "h3"},
                   intent="Servants.")
    assert r["hired"] <= 2 and "purse would not stand" in r["summary"], r
    # the wage binds the household's payroll
    from engine import payroll
    t = payroll.service_terms(conn, hh)
    assert t and abs(payroll.household_wage(t[-1]) - 0.1) < 1e-9


def t_crew_scale(conn, w):
    from engine import player_operations as po
    me, outfit, crew, by = w["me"], w["outfit"], w["crew"], w["bystander"]
    conn.execute("UPDATE underworld_crews SET size_estimate=60 WHERE id=?", (crew,))
    conn.execute("UPDATE underworld_organizations SET member_count_estimate=90 WHERE id=?", (outfit,))
    r = po.execute(conn, me, "attack", target_actor_id=by, details={"crew": f"crew:{crew}", "intent_kind": "beat", "men": 500, "_call_id": "c1"},
                   intent="I go for him with the whole crew.")
    assert r["status"] == "applied" and r["outcome"] == "won", r
    assert r.get("men_short") and r["men_lost"] >= 1, r  # a big force takes losses scaled to its size; and he has no more men to bring
    assert conn.execute("SELECT size_estimate FROM underworld_crews WHERE id=?", (crew,)).fetchone()[0] == 60 - r["men_lost"]


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "act.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from fixtures_protagonist import make_boss

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            w = make_boss(conn)
            for fn in (t_amounts, t_hire_many, t_crew_scale):
                fn(conn, w)
                print(fn.__name__, "ok")
    print("act_freeform_test passed")


if __name__ == "__main__":
    run()
