"""Long-run measurement: advance a copy of an opening for N days and record speed and storage as it goes.

Usage: python tools/run_years.py --days 1095 --out runs/perf3y [--db data/caerness.db] [--every 90]

Writes <out>/sim.db (the advanced world) and <out>/progress.jsonl, one line per checkpoint:
day, seconds for that stretch, seconds per simulated day, database MB, and the row counts of the tables
that grow with history.  The source DB is only copied.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROWING = ["knowledge", "claim_evidence", "actor_beliefs", "belief_revisions", "rumour_exposures",
           "information_links", "rumour_transmissions", "relationship_history", "decisions", "events"]


def db_mb(conn: sqlite3.Connection) -> float:
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    free = conn.execute("PRAGMA freelist_count").fetchone()[0]
    size = conn.execute("PRAGMA page_size").fetchone()[0]
    return round((pages - free) * size / 1048576, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "caerness.db"))
    ap.add_argument("--days", type=int, default=1095)
    ap.add_argument("--every", type=int, default=90)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    db = out / "sim.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    shutil.copy2(a.db, db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ["CAERNESS_BACKUP_DIR"] = str(out / "backups")
    sys.path.insert(0, str(ROOT))
    from engine.db import connect, init_db
    from engine.simulation import advance_connection, current_day
    init_db()
    conn = connect()
    log = (out / "progress.jsonl").open("w", encoding="utf-8")
    start = current_day(conn)
    while current_day(conn) < start + a.days:
        step = min(a.every, start + a.days - current_day(conn))
        t0 = time.perf_counter()
        advance_connection(conn, step)
        conn.commit()
        secs = time.perf_counter() - t0
        rec = {"day": current_day(conn), "secs": round(secs, 1), "secs_per_day": round(secs / step, 3), "db_mb": db_mb(conn),
               "living": conn.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND status='active'").fetchone()[0],
               **{t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in GROWING}}
        log.write(json.dumps(rec) + "\n"); log.flush()
        print(json.dumps(rec), flush=True)
    rec = {"integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
           "foreign_key_violations": len(conn.execute("PRAGMA foreign_key_check").fetchall())}
    log.write(json.dumps(rec) + "\n"); log.close()
    print("DONE", json.dumps(rec), flush=True)
    conn.close()


if __name__ == "__main__":
    main()
