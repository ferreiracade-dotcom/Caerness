"""Task B12g: who may be taken in (descent and identity from the package), deals that leave an organisation its own, a sweep's co-defendants reaching a
disposition and a sentence each.

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/b12g_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, forced_roll, open_world as _open_world


def _org(conn, key):
    return int(conn.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def test_a_family_holds_only_the_identities_the_package_lists():
    from engine import org_dealings as dl
    w = _open_world()
    c = w.conn
    fam = _org(c, "sabatini")
    assert dl.can_hold(c, fam, _org(c, "decavalcante"))  # another Italian family: weighed, not barred
    assert dl.can_hold(c, fam, _org(c, "hired_men"))  # a small crew with no descent of its own
    for key in ("brigades", "horsemen", "combine", "bolita", "russians", "greek_merchants"):
        assert not dl.can_hold(c, fam, _org(c, key)), key  # a group with an identity of its own is dealt with, taxed or fought, not taken in
    assert not dl.can_hold(c, _org(c, "brigades"), _org(c, "horsemen"))  # kinds that hold nothing hold nothing


def test_taking_in_a_family_of_the_same_descent_weighs_the_leave_of_a_table_and_blood():
    from engine import org_council as co, org_dealings as dl
    w = _open_world()
    c = w.conn
    a, b, d = _org(c, "sabatini"), _org(c, "pellegrino"), _org(c, "vannucci")
    f = dl.pair_factors(c, a, b, DAY)
    assert f["kin_group"] == 1.0 and f["family_unleft"] == 1.0 and f["other_blood"] == 1.0 and f["same_blood"] == 0.0
    co._form(c, a, [b, d], DAY)  # a table that holds both is the leave
    g = dl.pair_factors(c, a, b, DAY + 1)  # the next day (the day's readings are kept)
    assert g["family_unleft"] < 1.0
    assert dl.pair_factors(c, a, _org(c, "brigades"), DAY)["kin_group"] == 0.0


def test_a_client_deal_is_paid_and_blocks_the_blows_it_replaces_and_ends_by_a_head_weighing_it():
    from engine import ledger, org_dealings as dl, org_tension as ot
    from engine.orgs import head_of
    w = _open_world()
    c = w.conn
    F, T = _org(c, "sabatini"), _org(c, "bolita")
    assert dl.feasible_client(c, head_of(c, F), F, T, DAY)
    assert dl.pair_factors(c, F, T, DAY)["dealt"] == 0.0
    did = dl._make_deal(c, "client", F, T, DAY, head_of(c, F))
    assert dl.pair_factors(c, F, T, DAY)["dealt"] == 1.0 and dl.pair_factors(c, T, F, DAY)["dealt"] == 1.0
    assert not dl.feasible_client(c, head_of(c, F), F, T, DAY)  # one deal at a time
    hc, hp = head_of(c, T), head_of(c, F)
    before = ledger.balance(c, ("person", int(hp)))
    c.execute("UPDATE org_deals SET paid_day=? WHERE id=?", (DAY, did))
    dl._deals(c, DAY + 28)
    assert ledger.balance(c, ("person", int(hp))) >= before  # the share goes to the patron's head (what the client could pay)
    assert c.execute("SELECT paid_day FROM org_deals WHERE id=?", (did,)).fetchone()[0] == DAY + 28
    ended = False
    for day in range(DAY + 29, DAY + 29 + 3000, 7):  # a head weighs ending it each week: never certain, never forbidden
        dl._deals(c, day)
        if c.execute("SELECT status FROM org_deals WHERE id=?", (did,)).fetchone()[0] == "ended":
            ended = True
            break
    if ended:
        assert c.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind='deal_broken'").fetchone()[0] == 1
    assert ot.enabled(c)


def test_a_sweeps_co_defendants_reach_a_disposition_each_and_a_conviction_a_sentence():
    from engine import crime_response as cr
    w = _open_world()
    c = w.conn
    cr.ensure_tables(c)
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    men = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key='soldier' ORDER BY actor_id LIMIT 4", (w.org,))]
    assert len(men) == 4
    lead, others = men[0], men[1:]
    rid = cr.open_report(c, crime_kind="homicide", day=DAY, offender_actor_id=lead, victim_actor_id=None, location_id=w.ground,
                         metadata={"identified": True, "public": True, "co_defendants": others})
    with forced_roll("pad_publicity", "identify"):
        for day in range(DAY + 1, DAY + 4):
            c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
            cr.process_due(c, day)
    rep = c.execute("SELECT * FROM crime_reports WHERE id=?", (rid,)).fetchone()
    assert rep["status"] == "arrest", rep["status"]
    case = c.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()
    meta = json.loads(case["metadata_json"])
    assert sorted(meta["held_with"]) == sorted(others)  # all held on the one case
    for m in men:
        assert c.execute("SELECT 1 FROM custody WHERE actor_id=? AND case_id=? AND kind IN ('held','bailed')", (m, case["id"])).fetchone() is not None
    due = int(meta["disposition_day"])
    day = DAY + 4
    while day <= due + 3:
        c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
        cr.process_due(c, day)
        day += 1
    rows = c.execute("SELECT actor_id,kind FROM case_dispositions WHERE case_id=? ORDER BY actor_id", (case["id"],)).fetchall()
    assert sorted(int(r[0]) for r in rows) == sorted(men), rows  # each man has his own disposition
    convicted = [int(r[0]) for r in rows if r[1] in ("plea", "verdict_guilty")]
    for m in convicted:
        s = c.execute("SELECT * FROM sentences WHERE actor_id=? AND case_id=?", (m, case["id"])).fetchone()
        assert s is not None and s["term_days"] > 0 and s["crime_kind"] == "homicide"
    for m in set(men) - set(convicted):
        assert c.execute("SELECT 1 FROM sentences WHERE actor_id=? AND case_id=?", (m, case["id"])).fetchone() is None
    assert convicted, "at least one of four is convicted on these draws (a plain count of the case, not a quota)"


def test_no_leftover_defects_kind_in_the_package():
    p = ROOT / "worlds" / "saintjude"
    assert "hap_defects" not in (p / "outfits.json").read_text(encoding="utf-8")
    assert "hap_w_defects" not in (p / "design_figures.json").read_text(encoding="utf-8")


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
