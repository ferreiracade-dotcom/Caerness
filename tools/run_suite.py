"""Isolated regression suite: every tests/*_test.py and tests/v*_test.py in its own process and scratch DB.

Usage: python tools/run_suite.py --out runs/suite [--timeout 1500] [--only name1,name2]

tenyear02_opening_activation_gate_test runs against a copy of the packaged opening (it checks that opening).
Writes <out>/progress.jsonl and <out>/<test>.log; prints a TOTAL line.  Tests rewrite
game/campaign_01/model_requests/*.md; restore with `git restore game/campaign_01/model_requests/`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGED_OPENING_TESTS = {"tenyear02_opening_activation_gate_test"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    out = Path(a.out); (out / "db").mkdir(parents=True, exist_ok=True)
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    tests = sorted(p for p in (ROOT / "tests").glob("*.py") if p.stem.endswith("_test") and (not only or p.stem in only))
    totals: dict[str, int] = {}
    progress = (out / "progress.jsonl").open("w", encoding="utf-8")
    for p in tests:
        db = out / "db" / f"{p.stem}.db"
        for suffix in ("", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
        if p.stem in PACKAGED_OPENING_TESTS:
            shutil.copy2(ROOT / "data" / "caerness.db", db)
        env = dict(os.environ, CAERNESS_TEST_MODE="1", CAERNESS_DB_PATH=str(db), CAERNESS_BACKUP_DIR=str(out / "backups" / p.stem),
                   PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT))
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, str(p)], cwd=ROOT, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=a.timeout)
            status = "PASS" if r.returncode == 0 else "FAIL"
            log = r.stdout + r.stderr
        except subprocess.TimeoutExpired as e:
            status = "TIMEOUT"
            log = (e.stdout or "") if isinstance(e.stdout, str) else ""
        (out / f"{p.stem}.log").write_text(log, encoding="utf-8")
        totals[status] = totals.get(status, 0) + 1
        line = {"test": p.stem, "status": status, "secs": round(time.time() - t0, 1)}
        progress.write(json.dumps(line) + "\n"); progress.flush()
        print(json.dumps(line), flush=True)
        for suffix in ("", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
    progress.write("TOTAL " + json.dumps(totals) + "\n"); progress.close()
    print("TOTAL", totals, flush=True)


if __name__ == "__main__":
    main()
