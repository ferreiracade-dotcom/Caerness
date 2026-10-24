"""Rackets as money in the Saint Jude outfits: holdings, crew slices, lines, the monthly flow (mob minimum, task 7).

Run: CAERNESS_DB_PATH=<tmp>.db PYTHONPATH=. python tests/saintjude_outfit_money_test.py
test_family_net_over_a_year_matches_9_3 is an EXPECTED FAILURE until Task 8 adds the Pad (the net is gross minus the
Pad); the runner below reports it as "xfail" and the file still passes. When Task 8 makes it pass the runner says
"XPASS" and fails, so the marker must then be removed (delete the name from EXPECTED_FAILURES)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine import ledger, outfit_money, outfits
from engine.design import figure
from engine.household_life import mark_actor_deceased
from engine.outfit_opening import outfit_actor
from engine.world_package import outfit_rules, package_for

FAMILIES = ("sabatini", "pellegrino", "vannucci", "ferrante")
EXPECTED_FAILURES = {"test_family_net_over_a_year_matches_9_3"}  # Task 8 (the Pad) makes this pass


def _open():
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect(path)
    return conn, outfit_rules(package_for(conn))["outfits"]


def _oid(conn, spec) -> int:
    return outfit_actor(conn, spec["institution"])


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _alloc(conn):
    return outfit_money.design_allocation(conn)


def _member_ids(conn, oid=None):
    sql = "SELECT actor_id FROM outfit_ranks" + (" WHERE outfit_actor_id=?" if oid else "")
    return [int(r[0]) for r in conn.execute(sql, (oid,) if oid else ())]


def _cash(conn, ids) -> float:
    return sum(ledger.balance(conn, ("person", i)) for i in ids)


def _drawn_gross_m(conn, fam: str) -> float:
    """The family's gross from this run's drawn pool figures, computed here independently of the engine."""
    alloc = _alloc(conn)
    total = 0.0
    for pool, p in outfit_money.design_pools(conn).items():
        share = float(p["shares"].get(fam, 0) or 0)
        if p.get("kind") == "cost" or share <= 0:
            continue
        if p.get("tie"):
            total += figure(conn, p["tie"]["figure"], default=p["default_m"]) * share / 100.0
        else:
            total += alloc["drugs_1975"]["expected_take_m"][fam]
    return total


def test_holdings_sum_to_family_gross():
    """Figures are drawn per run (cards, theft, row tax and others move), so a run's gross differs from 9.3 by the
    draws: holdings must equal the run's drawn pools, and the pools at their defaults must give the 9.3 gross."""
    conn, outfits_ = _open()
    alloc = _alloc(conn)
    tol = alloc["gross_tolerance_m"]
    for fam in FAMILIES:
        g = conn.execute("SELECT SUM(yearly_take) FROM outfit_holdings WHERE outfit_actor_id=? AND source='opening'",
                         (_oid(conn, outfits_[fam]),)).fetchone()[0]
        assert abs(g / 1e6 - _drawn_gross_m(conn, fam)) < 1e-6, (fam, g / 1e6)
        at_default = sum(p["default_m"] * float(p["shares"].get(fam, 0) or 0) / 100.0 if not p.get("tie") else p["default_m"] * float(p["shares"].get(fam, 0) or 0) / 100.0
                         for p in outfit_money.design_pools(conn).values() if p.get("kind") != "cost" and p.get("tie"))
        at_default += alloc["drugs_1975"]["expected_take_m"][fam]
        assert abs(at_default - alloc["family_gross_net_9_3"][fam]["gross_m"]) <= tol, (fam, at_default)
        assert not conn.execute("SELECT 1 FROM outfit_holdings WHERE outfit_actor_id=? AND pool_key='pad'", (_oid(conn, outfits_[fam]),)).fetchone()


def test_crew_slices_and_lines_add_up():
    conn, outfits_ = _open()
    for h in conn.execute("SELECT id,yearly_take FROM outfit_holdings WHERE source='opening'").fetchall():
        lines = conn.execute("SELECT weekly_take FROM outfit_lines WHERE holding_id=?", (h["id"],)).fetchall()
        if lines:
            assert abs(sum(l[0] * 52 for l in lines) - h["yearly_take"]) < 1.0, dict(h)
    for fam in FAMILIES:
        oid = _oid(conn, outfits_[fam])
        for r in conn.execute("SELECT actor_id FROM outfit_ranks WHERE outfit_actor_id=? AND rank_key IN ('capo','soldier')", (oid,)):
            lines = conn.execute("SELECT description,location_id FROM outfit_lines WHERE holder_actor_id=?", (r[0],)).fetchall()
            assert lines, (fam, r[0])
            assert all(l["description"] and " in " in l["description"] and l["location_id"] for l in lines), [dict(l) for l in lines]
    ex = conn.execute("SELECT description FROM outfit_lines l JOIN outfit_holdings h ON h.id=l.holding_id WHERE h.pool_key='loansharking' LIMIT 1").fetchone()
    assert ex and ex[0].startswith("a loan book in ")


def test_other_outfits_hold_lines_for_their_pools():
    conn, outfits_ = _open()
    for key, pool in (("brigades", "brigades_docks"), ("horsemen", "horsemen_crank"), ("combine", "combine_own_lines"), ("bolita", "bolita_net")):
        oid = _oid(conn, outfits_[key])
        assert conn.execute("SELECT COUNT(*) FROM outfit_holdings WHERE outfit_actor_id=? AND pool_key=?", (oid, pool)).fetchone()[0] == 1, key
        assert conn.execute("SELECT COUNT(*) FROM outfit_lines l JOIN outfit_holdings h ON h.id=l.holding_id WHERE h.outfit_actor_id=?", (oid,)).fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM outfit_holdings WHERE outfit_actor_id=?", (_oid(conn, outfits_["russians"]),)).fetchone()[0] == 0


def test_money_is_conserved_in_a_period():
    conn, outfits_ = _open()
    ids = _member_ids(conn)
    before = _cash(conn, ids)
    day = _day(conn) + 28
    out = outfit_money.post_period(conn, day, 28)
    assert out["take"] > 0 and out["kickup"] > 0 and out["associate_earning"] > 0 and out["executive_share"] > 0
    assert abs((_cash(conn, ids) - before) - out["take"]) < 0.01
    rows = conn.execute("SELECT kind,from_actor_id,to_actor_id,amount FROM outfit_money WHERE day=?", (day,)).fetchall()
    sums = {k: sum(r["amount"] for r in rows if r["kind"] == k) for k in ("take", "associate_earning", "kickup", "executive_share")}
    for k in sums:
        assert abs(sums[k] - out[k]) < 0.01, k
    into, out_of = {}, {}
    for r in rows:
        if r["kind"] == "kickup":
            into[r["to_actor_id"]] = into.get(r["to_actor_id"], 0.0) + r["amount"]
            out_of[r["from_actor_id"]] = out_of.get(r["from_actor_id"], 0.0) + r["amount"]
    assert abs(sum(into.values()) - sum(out_of.values())) < 0.01
    # one row per man per kind per period for what he sends up
    seen = [(r["kind"], r["from_actor_id"], r["to_actor_id"]) for r in rows]
    assert len(seen) == len(set(seen))


def test_ladder_shares_apply():
    conn, outfits_ = _open()
    oid = _oid(conn, outfits_["sabatini"])
    pair = conn.execute(
        """SELECT a.actor_id AS assoc, a.superior_actor_id AS sold FROM outfit_ranks a JOIN outfit_ranks s ON s.actor_id=a.superior_actor_id
           WHERE a.outfit_actor_id=? AND a.rank_key='associate' AND s.rank_key='soldier' ORDER BY a.actor_id LIMIT 1""", (oid,)).fetchone()
    day = _day(conn) + 28
    outfit_money.post_period(conn, day, 28)
    earn = conn.execute("SELECT SUM(amount) FROM outfit_money WHERE day=? AND kind='associate_earning' AND to_actor_id=?", (day, pair["assoc"])).fetchone()[0]
    kick = conn.execute("SELECT SUM(amount) FROM outfit_money WHERE day=? AND kind='kickup' AND from_actor_id=? AND to_actor_id=?",
                        (day, pair["assoc"], pair["sold"])).fetchone()[0]
    assert earn and abs(kick - earn * figure(conn, "ladder_associate_to_soldier")) < 0.01
    # the soldier's kickup to his capo is the Ladder share of what he kept
    capo = conn.execute("SELECT superior_actor_id FROM outfit_ranks WHERE actor_id=?", (pair["sold"],)).fetchone()[0]
    up = conn.execute("SELECT amount FROM outfit_money WHERE day=? AND kind='kickup' AND from_actor_id=? AND to_actor_id=?", (day, pair["sold"], capo)).fetchone()
    taken = conn.execute("SELECT SUM(amount) FROM outfit_money WHERE day=? AND kind='take' AND to_actor_id=?", (day, pair["sold"])).fetchone()[0]
    paid = conn.execute("SELECT SUM(amount) FROM outfit_money WHERE day=? AND kind='associate_earning' AND from_actor_id=?", (day, pair["sold"])).fetchone()[0] or 0.0
    back = conn.execute("SELECT SUM(amount) FROM outfit_money WHERE day=? AND kind='kickup' AND to_actor_id=? AND from_actor_id IN (SELECT actor_id FROM outfit_ranks WHERE rank_key='associate')",
                        (day, pair["sold"])).fetchone()[0] or 0.0
    assert up and abs(up[0] - figure(conn, "ladder_soldier_to_capo") * (taken - paid + back)) < 0.01


def test_family_net_over_a_year_matches_9_3():
    conn, outfits_ = _open()
    alloc = _alloc(conn)["family_gross_net_9_3"]
    day = _day(conn)
    for i in range(13):
        outfit_money.post_period(conn, day + 28 * (i + 1), 28)
    for fam in FAMILIES:
        oid = _oid(conn, outfits_[fam])
        ids = tuple(_member_ids(conn, oid))
        q = ",".join("?" * len(ids))
        take = conn.execute(f"SELECT SUM(amount) FROM outfit_money WHERE kind='take' AND to_actor_id IN ({q})", ids).fetchone()[0]
        pad = conn.execute(f"SELECT COALESCE(SUM(amount),0) FROM outfit_money WHERE kind='pad' AND from_actor_id IN ({q})", ids).fetchone()[0]
        # 9.3: net = gross - pad. This run's gross is drawn, so the target is the run's gross less 9.3A's pad for the family.
        want = _drawn_gross_m(conn, fam) - alloc[fam]["pad_m"]
        assert abs(take / 1e6 - _drawn_gross_m(conn, fam)) < 0.01, (fam, take / 1e6)  # a year of takes is the year's gross
        assert abs(take / 1e6 - pad / 1e6 - want) <= 0.15, (fam, take / 1e6, pad / 1e6, want)


def test_dead_holder_line_goes_to_capo():
    conn, outfits_ = _open()
    oid = _oid(conn, outfits_["pellegrino"])
    row = conn.execute(
        """SELECT l.id,l.holder_actor_id,r.superior_actor_id AS capo FROM outfit_lines l JOIN outfit_ranks r ON r.actor_id=l.holder_actor_id
           WHERE r.outfit_actor_id=? AND r.rank_key='soldier' ORDER BY l.id LIMIT 1""", (oid,)).fetchone()
    soldier, capo, line = int(row["holder_actor_id"]), int(row["capo"]), int(row["id"])
    assert outfit_money.line_holder(conn, line) == soldier
    day = _day(conn) + 28
    mark_actor_deceased(conn, soldier)
    conn.execute("UPDATE outfit_ranks SET status='dead', left_day=? WHERE actor_id=?", (day - 1, soldier))  # task 12 will do this on death
    assert outfit_money.line_holder(conn, line) == capo
    # a held man's line goes up too, and a capo who is also gone sends it to the boss
    boss = int(outfits.boss_of(conn, oid))
    conn.execute("UPDATE outfit_ranks SET status='held' WHERE actor_id=?", (capo,))
    assert outfit_money.line_holder(conn, line) == boss
    conn.execute("UPDATE outfit_ranks SET status='active' WHERE actor_id=?", (capo,))
    outfit_money.post_period(conn, day, 28)
    assert not conn.execute("SELECT 1 FROM outfit_money WHERE day>=? AND to_actor_id=?", (day - 1, soldier)).fetchone()
    assert not conn.execute("SELECT 1 FROM outfit_money WHERE day>=? AND from_actor_id=?", (day - 1, soldier)).fetchone()
    assert conn.execute("SELECT 1 FROM outfit_money WHERE day=? AND kind='take' AND to_actor_id=?", (day, capo)).fetchone()


def test_process_posts_every_28_days_from_the_opening():
    from engine.simulation import advance_connection
    conn, _ = _open()
    start = _day(conn)
    assert outfit_money.next_due_day(conn, start, start + 100) == start + 28
    advance_connection(conn, 57)
    days = sorted({r[0] for r in conn.execute("SELECT DISTINCT day FROM outfit_money WHERE kind='take'")})
    assert days == [start + 28, start + 56], days


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    passed = xfailed = 0
    bad: list[str] = []
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            if t.__name__ in EXPECTED_FAILURES:
                xfailed += 1
                print("xfail", t.__name__, "(expected until Task 8):", str(e)[:120])
            else:
                bad.append(t.__name__)
                print("FAIL", t.__name__, repr(e)[:300])
        else:
            if t.__name__ in EXPECTED_FAILURES:
                bad.append(t.__name__)
                print("XPASS", t.__name__, "- Task 8 landed: remove it from EXPECTED_FAILURES")
            else:
                passed += 1
                print("ok", t.__name__)
    print(f"{passed} passed, {xfailed} expected failure(s)" + (f", {len(bad)} FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)
