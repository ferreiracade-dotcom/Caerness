"""P1b (slow): five simulated years, no prompting, seeds 3/7/11: some standing payments start, some come to light, and at least one
conviction or one fraud happens across the seeds. Reuses the P1 measures run and its output (runs/p1_measures/).

Run: PYTHONPATH=. python tests/p1b_five_years_test.py"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.p1_measures_test as M


def test_graft_happens_unprompted():
    M.OUT.mkdir(parents=True, exist_ok=True)
    rows = [M._one(s) for s in M.SEEDS]
    (M.OUT / "measures_p1b.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for r in rows:
        print(json.dumps(r))
    assert sum(r["payments_started"] for r in rows) > 0, rows
    assert sum(r["bribery_reports"] for r in rows) > 0, rows
    assert sum(r["terms_ended_convicted"] + r["fraud_acts"] for r in rows) > 0, rows
    assert all(r["civic_seconds"] < 600 for r in rows), rows


if __name__ == "__main__":
    try:
        test_graft_happens_unprompted()
        print("PASS test_graft_happens_unprompted")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
