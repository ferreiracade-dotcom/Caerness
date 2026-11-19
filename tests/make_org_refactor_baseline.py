"""Regenerate tests/fixtures/org_refactor_baseline.json: one-period money sums of the Saint Jude opening.

Run (written before the org refactor, so it names the OLD money table; C1 renames it to org_money):
    PYTHONPATH=. python tests/make_org_refactor_baseline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine import org_money

TABLE = "org_money"


def main() -> dict:
    path = build_saintjude(Path(tempfile.mkdtemp()))
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect(path)
    from engine.design import run_seed
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) + 28
    org_money.post_period(conn, day, 28)
    sums = {k: float(conn.execute(f"SELECT COALESCE(SUM(amount),0) FROM {TABLE} WHERE kind=? AND day=?", (k, day)).fetchone()[0])
            for k in ("pad", "take", "kickup")}
    sums["note"] = (f"package saintjude, run seed {run_seed(conn)}, day {day} (opening day + 28), days 28; "
                    f"SUM(amount) of {TABLE} by kind for that one period; made by tests/make_org_refactor_baseline.py")
    return sums


if __name__ == "__main__":
    out = main()
    dest = ROOT / "tests" / "fixtures" / "org_refactor_baseline.json"
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(out)
