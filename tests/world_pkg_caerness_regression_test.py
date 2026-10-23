"""Lock the Caerness opening: two fresh builds must match each other and the committed fingerprint.

Fingerprint = per-table sha256 of all rows (sorted), see tools/build_opening.py.
Volatile exclusions (documented in tools/build_opening.py):
  VOLATILE_TABLES  - tables that are audit/connector scratch, not world state.
  columns named *_at (and VOLATILE_COLUMNS) - wall-clock timestamps.
Regenerate the fixture only on purpose: python tools/build_opening.py --write-fixture
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "caerness_opening_fingerprint.json"
SEED = ROOT / "game" / "seeds" / "Caerness_Initial_World_State_Seed_v1_4.json"


def run():
    from tools.build_opening import build_opening, fingerprint

    with tempfile.TemporaryDirectory() as tmp:
        prints = []
        for n in (1, 2):
            db = Path(tmp) / f"open{n}.db"
            os.environ["CAERNESS_DB_PATH"] = str(db)
            t0 = time.time()
            build_opening(db, SEED)
            print(f"build {n}: {time.time() - t0:.1f}s")
            prints.append(fingerprint(db))
    diff = sorted(t for t in set(prints[0]) | set(prints[1]) if prints[0].get(t) != prints[1].get(t))
    assert not diff, f"two fresh builds differ (nondeterministic): {diff}"
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = sorted(t for t in set(expected) | set(prints[0]) if expected.get(t) != prints[0].get(t))
    assert not bad, f"opening differs from fixture in tables: {bad}"
    print(f"world_pkg_caerness_regression_test passed ({len(expected)} tables)")


if __name__ == "__main__":
    run()
