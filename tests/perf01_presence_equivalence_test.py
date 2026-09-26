"""PERF-01: presence snapshots from indexed lookups give exactly the same answer as the original
OR-over-left-joins query, for every place, on the opening and after a month of travel and habits."""
from __future__ import annotations
import os, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reference_snapshot(conn, location_id, day):
    """The pre-PERF-01 implementation of presence_probability_snapshot (no exact-scene arguments)."""
    from engine.presence import _clamp, _location_is_large
    rows = conn.execute(
        """SELECT DISTINCT a.id,a.status,a.home_location_id,a.current_location_id
           FROM actors a
           LEFT JOIN actor_presence_profiles p ON p.actor_id=a.id
           LEFT JOIN actor_presence_habits h ON h.actor_id=a.id AND h.location_id=?
                AND h.effective_from_day<=? AND (h.effective_to_day IS NULL OR h.effective_to_day>=?)
           LEFT JOIN travel_plans tp ON tp.subject_kind='actor' AND tp.subject_id=a.id
                AND tp.status IN ('active','stalled')
           WHERE a.actor_type='character' AND a.status='active'
             AND (h.id IS NOT NULL OR p.base_location_id=? OR a.current_location_id=? OR tp.current_location_id=?)
           ORDER BY a.id""",
        (location_id, day, day, location_id, location_id, location_id),
    ).fetchall()
    actor_by_id = {int(r["id"]): r for r in rows}
    if not actor_by_id:
        return {}
    ids = sorted(actor_by_id)
    marks = ",".join("?" for _ in ids)
    travel_by_actor = {}
    for row in conn.execute(f"""SELECT * FROM travel_plans WHERE subject_kind='actor' AND status IN ('active','stalled')
                                AND subject_id IN ({marks}) ORDER BY subject_id,id DESC""", tuple(ids)).fetchall():
        travel_by_actor.setdefault(int(row["subject_id"]), row)
    profiles = {int(r["actor_id"]): r for r in conn.execute(f"SELECT * FROM actor_presence_profiles WHERE actor_id IN ({marks})", tuple(ids))}
    habits_by_actor = {}
    for row in conn.execute("""SELECT * FROM actor_presence_habits WHERE location_id=? AND effective_from_day<=?
                               AND (effective_to_day IS NULL OR effective_to_day>=?) ORDER BY actor_id,weight DESC,id""",
                            (location_id, day, day)).fetchall():
        habits_by_actor.setdefault(int(row["actor_id"]), []).append(row)
    large = _location_is_large(conn, location_id)
    out = {}
    for aid in ids:
        actor = actor_by_id[aid]
        travel = travel_by_actor.get(aid)
        if travel is not None:
            if travel["current_route_id"] is not None and travel["segment_due_day"] is not None and day < int(travel["segment_due_day"]):
                continue
            if int(travel["current_location_id"]) == location_id:
                out[aid] = 1.0
            continue
        miss, has_basis = 1.0, False
        for row in habits_by_actor.get(aid, ()):
            w = _clamp(float(row["weight"]) * (0.55 + 0.45 * float(row["confidence"])))
            if str(row["habit_kind"]) == "legacy_anchor" and large:
                w = min(w, 0.12)
            miss *= (1.0 - w); has_basis = True
        probability = 1.0 - miss
        profile = profiles.get(aid)
        if not has_basis and profile is not None and profile["base_location_id"] is not None and int(profile["base_location_id"]) == location_id:
            probability = 0.22 if large else 0.52; has_basis = True
        if not has_basis and actor["current_location_id"] is not None and int(actor["current_location_id"]) == location_id:
            probability = 0.10 if large else 0.28
        probability = round(_clamp(probability), 4)
        if probability > 0.0:
            out[aid] = probability
    return out


def run():
    db = Path(tempfile.gettempdir()) / f"caerness_perf01_presence_{os.getpid()}.db"
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    shutil.copy2(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ["CAERNESS_BACKUP_DIR"] = str(db.parent / "perf01_backups")
    from engine.db import init_db, connect
    from engine.presence import presence_probability_snapshot
    from engine.simulation import advance_connection, current_day
    init_db(); c = connect()
    checked = 0
    for advance in (0, 30):
        if advance:
            advance_connection(c, advance); c.commit()
        day = current_day(c)
        for (loc,) in c.execute("SELECT id FROM locations ORDER BY id").fetchall():
            ref = _reference_snapshot(c, int(loc), day)
            new = presence_probability_snapshot(c, int(loc), day=day)
            assert new == ref, (day, loc, sorted(set(new.items()) ^ set(ref.items()))[:5])
            checked += 1
    assert checked > 100
    c.close()
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    print("PERF-01 presence equivalence PASS", {"snapshots": checked})


if __name__ == "__main__":
    run()
