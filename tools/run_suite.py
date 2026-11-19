"""Isolated regression suite: every tests/*_test.py and tests/v*_test.py in its own process and scratch DB.

Usage: python tools/run_suite.py --out runs/suite [--timeout 1500] [--only name1,name2] [--quick] [--jobs N]

--quick skips the tests listed in tests/slow_tests.txt (each over a minute; about 60 of the full run's ~83 serial minutes).
Run --quick after each task; run the full suite once before shipping. --jobs runs that many tests at once (default 4);
each test already has its own process and scratch DB.

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGED_OPENING_TESTS = {"tenyear02_opening_activation_gate_test"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--only", default="")
    ap.add_argument("--quick", action="store_true", help="skip the tests listed in tests/slow_tests.txt")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out); (out / "db").mkdir(parents=True, exist_ok=True)
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    slow = set()
    if a.quick:
        slow = {ln.split("#")[0].strip() for ln in (ROOT / "tests" / "slow_tests.txt").read_text(encoding="utf-8").splitlines()} - {""}
    tests = sorted(p for p in (ROOT / "tests").glob("*.py")
                   if p.stem.endswith("_test") and (not only or p.stem in only) and p.stem not in slow)
    totals: dict[str, int] = {}
    progress = (out / "progress.jsonl").open("w", encoding="utf-8")

    def run_one(p: Path) -> dict:
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
        for suffix in ("", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
        return {"test": p.stem, "status": status, "secs": round(time.time() - t0, 1)}

    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        for line in pool.map(run_one, tests):
            totals[line["status"]] = totals.get(line["status"], 0) + 1
            progress.write(json.dumps(line) + "\n"); progress.flush()
            print(json.dumps(line), flush=True)
    progress.write("TOTAL " + json.dumps(totals) + "\n"); progress.close()
    print("TOTAL", totals, flush=True)


if __name__ == "__main__":
    main()
