"""BZ1.4: places with owners, straws, landlords, upkeep and condition.

Run: PYTHONPATH=. python tests/bz1_places_test.py"""
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


def _fund(conn, who, amount):
    from engine import ledger
    ledger.receive(conn, ("person", int(who)), amount, purpose="test funding")


def _cash(conn, who):
    from engine import ledger
    return ledger.balance(conn, ("person", int(who)))


def _make(w, **kw):
    from engine import places
    args = dict(name="Test Garage", place_kind="garage", location_id=w.ground, owner_ref=f"person:{w.soldier}", day=0)
    args.update(kw)
    return places.make_place(w.conn, **args)


def test_make_place_writes_both_rows():
    from engine import places
    w = _open_world()
    c = w.conn
    bid = _make(w, landlord_ref=f"person:{w.capo}", rent_usd_30=120.0)
    p = places.place(c, bid)
    assert p["place_kind"] == "garage" and p["building_kind"] == "workshop" and p["upkeep_usd_30"] == 250.0
    assert p["who_pays_upkeep"] == f"person:{w.soldier}" and p["legal_owner"] == f"person:{w.soldier}"
    t = c.execute("SELECT * FROM agreement_terms WHERE id=?", (p["rent_term_id"],)).fetchone()
    assert t["amount_usd"] == 120.0 and t["creditor_ref"] == f"person:{w.capo}" and t["ref_kind"] == "place"


def test_upkeep_paid_from_owner():
    from engine import places
    w = _open_world()
    c = w.conn
    _fund(c, w.soldier, 1000.0)
    bid = _make(w)
    places.process_due_places(c, 30)
    assert abs(_cash(c, w.soldier) - 750.0) < 0.01
    assert float(c.execute("SELECT condition FROM buildings WHERE id=?", (bid,)).fetchone()[0]) == 100.0


def test_unpaid_upkeep_decays_and_labels():
    from engine import places
    w = _open_world()
    c = w.conn
    assert _cash(c, w.soldier) < 1.0
    bid = _make(w)
    seen = []
    for k in range(1, 30):
        places.process_due_places(c, 30 * k)
        seen.append(c.execute("SELECT status FROM buildings WHERE id=?", (bid,)).fetchone()[0])
    cond = float(c.execute("SELECT condition FROM buildings WHERE id=?", (bid,)).fetchone()[0])
    assert cond < 100.0 and seen[0] == "active"
    assert "strained" in seen and "derelict" in seen and seen.index("strained") < seen.index("derelict")
    assert seen[-1] == "destroyed" or cond < 15.0


def test_straw_owner_pays_when_owner_gone():
    from engine import places
    w = _open_world()
    c = w.conn
    _fund(c, w.capo, 1000.0)
    bid = _make(w, legal_owner_ref=f"person:{w.capo}")
    c.execute("UPDATE actors SET status='dead' WHERE id=?", (w.soldier,))
    c.execute("UPDATE actor_life_profiles SET life_status='deceased', current_household_id=NULL WHERE actor_id=?", (w.soldier,))
    places.process_due_places(c, 30)
    assert abs(_cash(c, w.capo) - 750.0) < 0.01
    # no legal owner either: it decays unpaid and says so
    b2 = _make(w, name="Orphan Lot", place_kind="lot")
    places.process_due_places(c, 60)
    meta = c.execute("SELECT metadata_json FROM buildings WHERE id=?", (b2,)).fetchone()[0]
    assert "no owner" in meta


def test_damage_to_destroyed():
    from engine import places
    w = _open_world()
    c = w.conn
    bid = _make(w)
    assert places.damage_place(c, bid, 30.0, "a fire", 5) == 70.0
    assert places.damage_place(c, bid, 500.0, "a fire", 6) == 0.0
    assert c.execute("SELECT status FROM buildings WHERE id=?", (bid,)).fetchone()[0] == "destroyed"


def test_long_skip_settles_each_period():
    from engine import places
    out = []
    for mode in ("steps", "skip"):
        w = _open_world()
        c = w.conn
        _fund(c, w.soldier, 1300.0)  # five periods of upkeep, then it runs short
        bid = _make(w)
        if mode == "steps":
            for k in range(1, 13):
                places.process_due_places(c, 30 * k)
        else:
            places.process_due_places(c, 360)
        out.append((float(c.execute("SELECT condition FROM buildings WHERE id=?", (bid,)).fetchone()[0]), round(_cash(c, w.soldier), 4)))
    assert out[0] == out[1] and out[0][0] < 100.0, out


def test_transfer_keeps_a_straw_when_not_legal():
    from engine import places
    w = _open_world()
    c = w.conn
    bid = _make(w, legal_owner_ref=f"person:{w.capo}")
    places.transfer_place(c, bid, f"person:{w.boss}", 10, legal=False)
    p = places.place(c, bid)
    assert p["owner_ref"] == f"person:{w.boss}" and p["legal_owner_ref"] == f"person:{w.capo}"
    places.transfer_place(c, bid, f"person:{w.soldier}", 11)
    p = places.place(c, bid)
    assert p["owner_ref"] == f"person:{w.soldier}" and p["legal_owner"] == f"person:{w.soldier}"


def test_no_business_data_noop():
    from engine import places
    from engine.db import connect, init_db
    path = Path(tempfile.mkdtemp()) / "c.db"
    shutil.copy2(ROOT / "data" / "caerness.db", path)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
    init_db()
    conn = connect()
    assert places.process_due_places(conn, 500) == {}
    assert conn.execute("SELECT COUNT(*) FROM place_details").fetchone()[0] == 0
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
