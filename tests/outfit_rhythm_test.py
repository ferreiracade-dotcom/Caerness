"""Rhythm for outfit members: quiet routine weeks, agenda-driven daily review, Caerness unchanged (task 9)."""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine import outfits
from engine.simulation import advance_connection, current_day


def _open():
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    return connect(path)


def _member_ids(conn):
    return [int(r[0]) for r in conn.execute("SELECT actor_id FROM outfit_ranks WHERE status='active'")]


def _decision_rows(conn, ids):
    marks = ",".join("?" * len(ids))
    total = 0
    for table in ("decisions", "decision_evaluations", "decision_candidate_audit"):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        if "actor_id" in cols:
            total += conn.execute(f"SELECT COUNT(*) FROM {table} WHERE actor_id IN ({marks})", ids).fetchone()[0]
        else:
            total += conn.execute(f"SELECT COUNT(*) FROM {table} WHERE evaluation_id IN (SELECT id FROM decision_evaluations WHERE actor_id IN ({marks}))", ids).fetchone()[0]
    return total


def test_routine_week_writes_no_decision_rows():
    conn = _open()
    ids = _member_ids(conn)
    assert len(ids) > 1000
    before = _decision_rows(conn, ids)
    t0 = time.time()
    advance_connection(conn, 28)
    conn.commit()
    print(f"28-day outfit advance: {time.time() - t0:.1f}s")
    assert _decision_rows(conn, ids) - before == 0
    reviewed = conn.execute(
        "SELECT COUNT(*) FROM simulation_profiles WHERE actor_id IN (SELECT actor_id FROM outfit_ranks) AND last_review_day>0").fetchone()[0]
    assert reviewed > 0, "members are still reviewed on schedule (rescheduled, not frozen)"


def test_agenda_item_makes_a_weekly_man_daily_until_it_passes():
    conn = _open()
    soldier = int(conn.execute(
        "SELECT o.actor_id FROM outfit_ranks o JOIN simulation_profiles p ON p.actor_id=o.actor_id "
        "WHERE o.rank_key='soldier' AND p.cadence_days=7 ORDER BY o.actor_id LIMIT 1").fetchone()[0])
    today = current_day(conn)
    aid = outfits.add_agenda(conn, soldier, "collect_debt", due_day=today + 5)
    seen: list[int] = []
    for _ in range(25):
        advance_connection(conn, 1)
        d = current_day(conn)
        if conn.execute("SELECT last_review_day FROM simulation_profiles WHERE actor_id=?", (soldier,)).fetchone()[0] == d:
            seen.append(d)
    assert seen[:6] == list(range(today + 1, today + 7)), seen
    due_plus = today + 5 + 7
    after = [d for d in seen if d > due_plus]
    assert len(after) >= 2 and after[1] - after[0] == 7, seen
    assert outfits.has_reason_to_choose(conn, soldier, today + 5)
    outfits.resolve_agenda(conn, aid, today + 6)
    assert not outfits.has_reason_to_choose(conn, soldier, today + 6)


def test_reason_check_registration_is_idempotent():
    n = len(outfits._REASON_CHECKS)
    outfits.register_reason_check(outfits._open_agenda_due)
    assert len(outfits._REASON_CHECKS) == n


def _fingerprint(conn):
    h = hashlib.sha256()
    for t, cols in (("events", "day,event_type,title,summary,severity,source_actor_id"),
                    ("decisions", "day,actor_id,outcome_summary")):
        for row in conn.execute(f"SELECT {cols} FROM {t} ORDER BY id"):
            h.update(repr(tuple(row)).encode())
    return h.hexdigest()


def test_non_quiet_profiles_unchanged():
    import engine.simulation as sim
    src = ROOT / "data" / "caerness.db"
    if not src.exists():
        print("skip: data/caerness.db absent")
        return
    prints = []
    for disabled in (False, True):
        tmp = Path(tempfile.mkdtemp())
        db = tmp / "caerness.db"
        shutil.copyfile(src, db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        os.environ.pop("CAERNESS_WORLD_PACKAGE", None)
        from engine.db import init_db
        init_db()
        conn = connect(db)
        assert conn.execute("SELECT COUNT(*) FROM simulation_profiles WHERE quiet_routine=1").fetchone()[0] == 0
        orig = sim._quiet_routine
        if disabled:
            sim._quiet_routine = lambda profile: False
        try:
            t0 = time.time()
            advance_connection(conn, 30)
            conn.commit()
            print(f"caerness 30 days (quiet branch {'off' if disabled else 'on'}): {time.time() - t0:.1f}s")
        finally:
            sim._quiet_routine = orig
        prints.append(_fingerprint(conn))
        conn.close()
    assert prints[0] == prints[1]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
