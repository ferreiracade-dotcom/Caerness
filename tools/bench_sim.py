"""Full-engine phone benchmark: how long the Narrative Engine takes to advance the packaged opening.

Usage:
  python tools/bench_sim.py [--db data/caerness.db] [--out benchmarks/results/<label>_engine.json]
                            [--label pc] [--segments 1,7,90]

Each segment runs in its own subprocess on a fresh copy of the opening, so segments are independent and
peak memory is per segment.  The source DB is only ever copied, never opened.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def peak_rss_mb() -> float | None:
    try:
        import resource
    except ImportError:  # Windows
        return None
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(v / (1048576 if sys.platform == "darwin" else 1024), 1)


def device_info() -> dict:
    import numpy
    return {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "numpy": numpy.__version__, "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count()}


def child(db: Path, days: int) -> None:
    os.environ["CAERNESS_DB_PATH"] = str(db)
    os.environ["CAERNESS_BACKUP_DIR"] = str(db.parent / "backups")
    sys.path.insert(0, str(ROOT))
    from engine.db import connect, init_db
    from engine.simulation import advance_connection, current_day
    init_db()
    conn = connect()
    start = current_day(conn)
    t0 = time.perf_counter()
    advance_connection(conn, days)
    conn.commit()
    wall = time.perf_counter() - t0
    reached = current_day(conn)
    conn.close()
    print(json.dumps({"days": days, "wall_secs": round(wall, 3), "secs_per_day": round(wall / days, 3),
                      "day_reached": reached - start, "peak_rss_mb": peak_rss_mb()}))


def run_segment(src: Path, days: int, work: Path) -> dict:
    db = work / f"bench_{days}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    shutil.copy2(src, db)
    r = subprocess.run([sys.executable, __file__, "--child", str(db), str(days)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"segment {days} failed:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(Path(sys.argv[2]), int(sys.argv[3]))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "caerness.db"))
    ap.add_argument("--label", default="device")
    ap.add_argument("--out", default=None)
    ap.add_argument("--segments", default="1,7,90")
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / "benchmarks" / "results" / f"{a.label}_engine.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {"label": a.label, "device": device_info(), "segments": []}
    with tempfile.TemporaryDirectory(prefix="caerness_bench_") as tmp:
        for days in [int(x) for x in a.segments.split(",") if x.strip()]:
            seg = run_segment(Path(a.db), days, Path(tmp))
            result["segments"].append(seg)
            print(json.dumps(seg), flush=True)
    out.write_text(json.dumps(result, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
