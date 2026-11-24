"""S1: household-life scans on the coarse clock still catch a stage boundary on its day, plan births on their day, and look for new contacts weekly."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CAERNESS_TEST_MODE", "1")
os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def _open(tmp):
    path = build_saintjude(Path(tmp))
    os.environ["CAERNESS_DB_PATH"] = str(path)
    return connect(path)


def test_boundary_day_and_weekly_stamp():
    from engine import household_life as hl, tiers
    tmp = tempfile.mkdtemp()
    try:
        conn = _open(tmp)
        D = 3000
        rising = tiers.rising_actor_ids(conn, D)
        rows = [r[0] for r in conn.execute("SELECT actor_id FROM actor_life_profiles WHERE life_status='living'") if r[0] not in rising][:2]
        a, b = rows
        # a turns 18 today, reviewed three days ago; b is reviewed three days ago and crosses nothing
        conn.execute("UPDATE actor_life_profiles SET life_stage='youth',birth_day=?,last_review_day=? WHERE actor_id=?", (D - 18 * 365, D - 3, a))
        conn.execute("UPDATE actor_life_profiles SET life_stage='adult',birth_day=?,last_review_day=? WHERE actor_id=?", (D - 30 * 365, D - 3, b))
        hl._review_profiles(conn, D, None)
        la = conn.execute("SELECT life_stage,last_review_day FROM actor_life_profiles WHERE actor_id=?", (a,)).fetchone()
        lb = conn.execute("SELECT life_stage,last_review_day FROM actor_life_profiles WHERE actor_id=?", (b,)).fetchone()
        assert (la[0], la[1]) == ("adult", D), tuple(la)
        assert lb[1] == D - 3, "a quiet man with nothing to cross waits for his weekly stamp"
        hl._review_profiles(conn, D + 4, None)
        assert conn.execute("SELECT last_review_day FROM actor_life_profiles WHERE actor_id=?", (b,)).fetchone()[0] == D + 4
        conn.close()
    finally:
        import gc
        gc.collect()
        shutil.rmtree(tmp, ignore_errors=True)


def test_planned_births_read_only_due_unions_and_social_scan_is_weekly():
    from engine import household_life as hl
    tmp = tempfile.mkdtemp()
    try:
        conn = _open(tmp)
        day = 4000
        want = set()
        for u in conn.execute("SELECT * FROM household_unions WHERE status='active'").fetchall():
            plan = json.loads(u["family_plan_json"] or "{}")
            if plan.get("auto_children") and day >= int(plan.get("earliest_next_child_day", int(u["started_day"]) + int(plan.get("spacing_days", 730)))):
                want.add(int(u["id"]))
        got = {int(r[0]) for r in conn.execute(
            """SELECT id FROM household_unions WHERE status='active'
               AND COALESCE(json_extract(family_plan_json,'$.auto_children'),0) NOT IN (0,'',0.0)
               AND COALESCE(json_extract(family_plan_json,'$.earliest_next_child_day'),
                            started_day + COALESCE(json_extract(family_plan_json,'$.spacing_days'), 730)) <= ?""", (day,))}
        assert got == want
        hl._resolve_social_contacts(conn, 100)
        assert conn.execute("SELECT value FROM runtime_flags WHERE key='social_scan_day'").fetchone()[0] == "100"
        hl._resolve_social_contacts(conn, 103)
        assert conn.execute("SELECT value FROM runtime_flags WHERE key='social_scan_day'").fetchone()[0] == "100"
        hl._resolve_social_contacts(conn, 107)
        assert conn.execute("SELECT value FROM runtime_flags WHERE key='social_scan_day'").fetchone()[0] == "107"
        assert hl.next_household_life_due_day(conn, 107, 130) <= 114
        conn.close()
    finally:
        import gc
        gc.collect()
        shutil.rmtree(tmp, ignore_errors=True)


def test_household_money_integrates_the_same_days():
    """Daily and weekly runs reach the same liquidity on the day both have integrated (income, wages and upkeep all scale with elapsed days)."""
    from engine import civilian, tiers
    out, stamps, quiet = {}, {}, []
    for mode in ("off", "on"):
        os.environ["CAERNESS_TIERS"] = "on"
        tmp = tempfile.mkdtemp()
        try:
            conn = _open(tmp)
            if mode == "off":
                rising = tiers.rising_actor_ids(conn, 0)
                quiet = [int(r[0]) for r in conn.execute("SELECT id FROM households WHERE status='active' AND head_actor_id IS NOT NULL ORDER BY id")
                         if conn.execute("SELECT head_actor_id FROM households WHERE id=?", (int(r[0]),)).fetchone()[0] not in rising][:200]
            start = int(conn.execute("SELECT MIN(updated_day) FROM households").fetchone()[0])
            os.environ["CAERNESS_TIERS"] = mode
            for day in range(start + 1, start + 36):
                civilian._resolve_households(conn, day)
            out[mode] = {h: conn.execute("SELECT liquidity,wealth,updated_day FROM households WHERE id=?", (h,)).fetchone() for h in quiet}
            conn.close()
        finally:
            import gc
            gc.collect()
            shutil.rmtree(tmp, ignore_errors=True)
            os.environ.pop("CAERNESS_TIERS", None)
    assert len(quiet) >= 20
    same_day = [h for h in quiet if out["on"][h][2] == out["off"][h][2]]
    assert len(same_day) >= 0.8 * len(quiet), "after 35 days a quiet household was brought up to date on the 35th day as well"
    for h in same_day:
        a, b = out["off"][h], out["on"][h]
        assert abs((a[0] + a[1]) - (b[0] + b[1])) <= 1e-6 * max(1.0, abs(a[0] + a[1])) + 1e-6, (h, tuple(a), tuple(b))


if __name__ == "__main__":
    test_boundary_day_and_weekly_stamp()
    test_planned_births_read_only_due_unions_and_social_scan_is_weekly()
    test_household_money_integrates_the_same_days()
    print("ok s1_household_test")
