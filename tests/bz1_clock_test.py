"""BZ1.7: the shared layer runs on the clock, drivers sit on existing businesses, the GM can ask why.

Run: PYTHONPATH=. python tests/bz1_clock_test.py"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

# Recorded on HEAD before BZ1.7 (d546067): a Caerness copy advanced 60 days through advance_connection.
CAERNESS_60_DAYS = {"accounts": (435, 4473.6553), "cycles": (186, 2382.8341)}


def _fund(conn, who, amount):
    from engine import ledger
    ledger.receive(conn, ("person", int(who)), amount, purpose="test funding")


def _today(conn):
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def test_advance_runs_terms_places_ventures():
    from engine import agreement_terms, places, simulation, ventures
    w = _open_world()
    c = w.conn
    d0 = _today(c)
    _fund(c, w.soldier, 40000.0)
    bid = places.make_place(c, name="Rented Garage", place_kind="garage", location_id=w.ground, owner_ref=f"person:{w.soldier}",
                            day=d0, landlord_ref=f"person:{w.capo}", rent_usd_30=120.0)
    pid = ventures.start_venture(c, kind="open_business", title="A new bar", backer_ref=f"person:{w.soldier}",
                                 location_id=None, budget_usd=9000.0, day=d0)
    tid = agreement_terms.add_term(c, ref_kind="test", ref_id=None, debtor_ref=f"person:{w.soldier}", creditor_ref=f"person:{w.boss}",
                                   amount_usd=25.0, first_due_day=d0 + 7, every_days=7, grace_days=14, breach_word="street",
                                   purpose="weekly clock term", day=d0)
    c.commit()
    simulation.advance_connection(c, 90)
    rent = c.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='other' AND metadata_json LIKE '%rent for Rented Garage%'").fetchone()[0]
    weekly = c.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='other' AND metadata_json LIKE '%weekly clock term%'").fetchone()[0]
    assert rent >= 2 and weekly >= 10, (rent, weekly)
    assert int(c.execute("SELECT next_due_day FROM place_details WHERE building_id=?", (bid,)).fetchone()[0]) > d0 + 60
    v = ventures.venture(c, pid)
    refused = any(a["status"] == "refused" for a in v["approvals"])  # politics now answers the permit: a refusal fails the venture
    assert (refused and v["outcome"] == "failed") or (v["spent_usd"] > 0 and (v["stage_key"] != "fit_out" or v["outcome"] is not None)), (v["stage_key"], v["spent_usd"])
    assert c.execute("SELECT status FROM agreement_terms WHERE id=?", (tid,)).fetchone()[0] in ("active", "breached")


def test_idle_layer_adds_no_wakeups():
    from engine import agreement_terms, civilian, places, ventures
    w = _open_world()
    c = w.conn
    d = _today(c)
    real = civilian.next_civilian_due_day(c, d, d + 400)
    saved = (agreement_terms.next_terms_due_day, places.next_places_due_day, ventures.next_ventures_due_day)
    try:
        agreement_terms.next_terms_due_day = places.next_places_due_day = ventures.next_ventures_due_day = lambda *a: None
        patched = civilian.next_civilian_due_day(c, d, d + 400)
    finally:
        agreement_terms.next_terms_due_day, places.next_places_due_day, ventures.next_ventures_due_day = saved
    assert real == patched


def test_existing_bar_has_why():
    from engine import business, civilian
    w = _open_world()
    c = w.conn
    d = _today(c)
    eid = civilian.create_enterprise(c, "Why Bar", "service", location_id=w.ground, capital=1000, cash=1000)
    business.configure_enterprise_business(c, eid, "bar")
    out = business.resolve_business_cycle(c, eid, d + 30)
    assert not out.get("skipped"), out
    prof = business.business_profile(c, eid)
    assert len(prof["why"]) == 8 and all("(" in line for line in prof["why"]), prof["why"]


def test_caerness_cycle_untouched():
    from engine import simulation
    from engine.db import connect, init_db
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "c.db"
    shutil.copy2(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    init_db()
    conn = connect()
    simulation.advance_connection(conn, 60)
    conn.commit()
    a = conn.execute("SELECT COUNT(*), ROUND(COALESCE(SUM(amount),0),4) FROM enterprise_accounts").fetchone()
    b = conn.execute("SELECT COUNT(*), ROUND(COALESCE(SUM(gross_revenue),0),4) FROM business_cycles").fetchone()
    assert (a[0], a[1]) == CAERNESS_60_DAYS["accounts"] and (b[0], b[1]) == CAERNESS_60_DAYS["cycles"], (tuple(a), tuple(b))
    for t in ("place_details", "venture_details", "agreement_terms", "driver_readings"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
    conn.close()


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
