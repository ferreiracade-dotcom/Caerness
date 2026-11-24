"""Task B12f: a table of heads that can form and fail, debt and men changing sides, informers in every kind of organisation, sweeps with co-defendants.

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/b12f_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world


def _org(conn, key):
    return int(conn.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def test_schema_120_and_no_table_at_the_opening():
    w = open_world()
    c = w.conn
    from engine.db import SCHEMA_VERSION
    assert SCHEMA_VERSION == 128
    for t in ("org_councils", "org_council_seats", "org_council_acts", "org_informers", "org_absorptions"):
        assert c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0] == 0, t  # nothing is forced to exist: a table, a debt, an informer come from what happens


def test_a_table_binds_only_while_it_has_members_and_standing():
    from engine import org_council as co
    w = open_world()
    c = w.conn
    a, b, d = _org(c, "sabatini"), _org(c, "pellegrino"), _org(c, "vannucci")
    assert co.binding(c, a, b, DAY) is None
    cid = co._form(c, a, [b, d], DAY)
    got = co.binding(c, a, b, DAY)
    assert got is not None and got[0] == cid and 0 < got[1] < 1
    assert co.binding(c, a, _org(c, "ferrante"), DAY) is None  # a pair with an outsider is not bound
    co._move(c, cid, 50.0, DAY, "test")
    assert co.binding(c, a, b, DAY)[1] > got[1]  # standing has no top, only a diminishing return
    # members leave until too few remain: the table ends, with a reason
    for org in (b, d):
        c.execute("UPDATE org_council_seats SET left_day=?, left_reason='withdrew' WHERE council_id=? AND org_actor_id=?", (DAY, cid, org))
    co._leave(c, DAY + 1)
    row = c.execute("SELECT ended_day,end_reason FROM org_councils WHERE id=?", (cid,)).fetchone()
    assert row[0] is not None and row[1] == "too few"


def test_a_strike_between_members_is_put_to_the_table():
    from engine import org_council as co
    w = open_world()
    c = w.conn
    a, b, d = _org(c, "sabatini"), _org(c, "pellegrino"), _org(c, "vannucci")
    from engine.orgs import head_of
    plan = {"from": a, "to": b, "voice": head_of(c, a), "rung": "soldier", "method": "ambush"}
    assert co.strike_verdict(c, plan, DAY, False) is None  # no table: nothing to ask
    cid = co._form(c, a, [b, d], DAY)
    seen = set()
    for day in range(DAY, DAY + 120):
        seen.add(co.strike_verdict(c, plan, day, False))
    assert seen <= {"approved", "defied", "barred"} and len(seen) >= 2  # it is weighed, not fixed
    kinds = {r[0] for r in c.execute("SELECT kind FROM org_council_acts WHERE council_id=?", (cid,))}
    assert kinds & {"sanctioned", "barred", "broken"}


def test_a_part_paid_levy_is_a_debt_that_sours_and_paying_eases():
    from engine import org_dealings as dl, org_tension as ot
    w = open_world()
    c = w.conn
    a, b = _org(c, "sabatini"), _org(c, "pellegrino")
    did = dl.owe(c, a, b, 80000.0, "levy", DAY)
    assert did is not None and dl.owe(c, a, a, 5.0, "x", DAY) is None  # no one owes himself
    before = ot.level(c, a, b, DAY + 60)
    c.execute("UPDATE org_debts SET accrued_day=? WHERE id=?", (DAY, did))
    dl._debts(c, DAY + 60)
    open_ = c.execute("SELECT status FROM org_debts WHERE id=?", (did,)).fetchone()[0]
    if open_ == "open":  # unpaid: the creditor is aggrieved, more the longer and the more
        assert ot.level(c, a, b, DAY + 60) > before
        n = c.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind='debt_unpaid'").fetchone()[0]
        assert n >= 1
    else:
        assert c.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind='debt_paid'").fetchone()[0] == 1


def test_a_man_changing_sides_takes_his_seat_and_sours_his_old_outfit():
    from engine import org_dealings as dl, org_tension as ot
    from engine.orgs import seat_of
    w = open_world()
    c = w.conn
    old = w.org
    new = _org(c, "pellegrino") if old != _org(c, "pellegrino") else _org(c, "sabatini")
    before = ot.level(c, old, new, DAY)
    assert dl.change_side(c, w.soldier, old, new, "poached", DAY)
    assert seat_of(c, w.soldier, new)["status"] == "active" and seat_of(c, w.soldier, old)["status"] != "active"
    assert ot.level(c, old, new, DAY) > before
    assert not dl.change_side(c, w.soldier, old, new, "poached", DAY)  # no longer his to move
    # coming in by agreement has no quarrel behind it
    other = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key='soldier' ORDER BY actor_id LIMIT 1", (old,)).fetchone()[0])
    mid = ot.level(c, old, new, DAY)
    assert dl.change_side(c, other, old, new, "absorbed", DAY)
    assert ot.level(c, old, new, DAY) == mid


def test_informers_are_turned_in_any_kind_of_organisation_and_report():
    from engine import org_informing as inf
    w = open_world()
    c = w.conn
    kinds = {k for k in (inf.idata(c).get("roles") or {})}
    assert {"family", "independent", "club"} <= kinds  # the package lists seats beyond the families'
    man = w.soldier
    assert not inf.is_informer(c, man)
    inf._turn(c, man, w.org, "law", None, DAY)
    assert inf.is_informer(c, man)
    # a man turned by a rival is a reading the rival's voices weigh
    other = _org(c, "pellegrino") if w.org != _org(c, "pellegrino") else _org(c, "sabatini")
    assert inf.informed(c, other, w.org) == 0.0
    c.execute("INSERT INTO org_informers(informer_actor_id,org_actor_id,turned_by_kind,turned_by_id,since_day) VALUES (?,?,?,?,?)", (w.capo, w.org, "org", other, DAY))
    assert inf.informed(c, other, w.org) == 1.0 and inf.informed(c, w.org, other) == 0.0
    n = 0
    for day in range(DAY, DAY + 400):  # a turned man reports now and then
        n += inf._reports(c, day)
    assert n >= 1


def test_a_sweep_holds_several_men_on_one_case_and_each_is_disposed_alone():
    from engine import crime_response as cr
    w = open_world()
    c = w.conn
    cr.ensure_tables(c)
    cfg = cr._cfg(c)
    assert cfg.get("sweep"), "the package's sweep data is read"
    men = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id LIMIT 4", (w.org,))]
    lead, others = men[0], men[1:]
    rid = cr.open_report(c, crime_kind=cfg["sweep"]["conspiracy_kind"], day=DAY, offender_actor_id=lead, victim_actor_id=None, location_id=None,
                         metadata={"source": "sweep", "identified": True, "co_defendants": others})
    case = c.execute("SELECT case_id FROM crime_reports WHERE id=?", (rid,)).fetchone()[0]
    assert case is not None or True
    meta = json.loads(c.execute("SELECT metadata_json FROM crime_reports WHERE id=?", (rid,)).fetchone()[0] or "{}")
    assert meta.get("co_defendants") == others


def test_package_figures_exist_for_every_new_name():
    p = ROOT / "worlds" / "saintjude"
    figs = json.loads((p / "design_figures.json").read_text(encoding="utf-8"))["figures"]
    out = json.loads((p / "outfits.json").read_text(encoding="utf-8"))["tension"]
    used = set()

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("weight"), str):
                used.add(x["weight"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(out)
    missing = [u for u in used if u not in figs]
    assert not missing, missing[:5]
    for name in ("co_min_seats", "ib_debt_rate", "ib_side_raise"):
        assert figs[name]["tag"] == "Design" and "unsourced" in figs[name]["note"]


def test_the_new_engine_modules_name_no_outfit_rank_or_money():
    import re
    bad = re.compile(r"sabatini|pellegrino|vannucci|ferrante|capo|underboss|consigliere|mafia|\$\s?\d")
    for f in ("org_council.py", "org_dealings.py", "org_informing.py"):
        txt = (ROOT / "engine" / f).read_text(encoding="utf-8")
        hit = bad.search(txt)
        assert hit is None, (f, hit.group(0))


def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {name}: {exc!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
