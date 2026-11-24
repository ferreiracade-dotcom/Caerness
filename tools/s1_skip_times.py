"""S1: wall time of a 1-day, 1-week, 1-month and 1-year skip from the Saint Jude opening, and the file growth.

  python tools/s1_skip_times.py [--db data/saintjude.db] [--seed 3] [--segments 1,7,30,365] [--out runs/s1/x.json]

Each segment runs in a child process on a fresh copy of the opening (the source is only copied). Runs one segment at a time."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def child(db: Path, days: int, seed: int) -> None:
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ["CAERNESS_BACKUP_DIR"] = str(db.parent / "backups")
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    sys.path.insert(0, str(ROOT))
    from engine.db import connect, init_db
    from engine.simulation import advance_connection
    init_db()
    conn = connect()
    conn.execute("UPDATE world_state SET rng_seed=?", (seed,))
    conn.commit()
    t0 = time.perf_counter()
    advance_connection(conn, days)
    conn.commit()
    wall = time.perf_counter() - t0
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    print(json.dumps({"days": days, "wall_secs": round(wall, 2), "size_mb": round(db.stat().st_size / 1048576, 1)}))


def main() -> None:
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        child(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "saintjude.db"))
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--segments", default="1,7,30,365")
    ap.add_argument("--out", default=None)
    ap.add_argument("--keep", default=None, help="copy the last segment's database here (for profiling)")
    a = ap.parse_args()
    start_mb = Path(a.db).stat().st_size / 1048576
    res = {"seed": a.seed, "start_mb": round(start_mb, 1), "segments": []}
    with tempfile.TemporaryDirectory(prefix="s1_skip_", dir=str(ROOT / "runs")) as tmp:
        for days in [int(x) for x in a.segments.split(",")]:
            db = Path(tmp) / f"seg_{days}.db"
            shutil.copy2(a.db, db)
            r = subprocess.run([sys.executable, __file__, "--child", str(db), str(days), str(a.seed)], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(r.stderr[-3000:])
            seg = json.loads(r.stdout.strip().splitlines()[-1])
            seg["growth_mb"] = round(seg["size_mb"] - start_mb, 1)
            res["segments"].append(seg)
            print(json.dumps(seg), flush=True)
            if a.keep and days == int(a.segments.split(",")[-1]):
                shutil.copy2(db, a.keep)
            for s in ("", "-wal", "-shm"):
                Path(str(db) + s).unlink(missing_ok=True)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
