"""L1: the lived opening builds in under a minute and stays inside a size bound (an uncached build, in a throwaway folder)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BUILD_SECONDS = 60.0
DB_MB = 50.0


def test_build_time_and_size():
    os.environ["CAERNESS_NO_OPENING_CACHE"] = "1"
    from tools.build_opening import build_opening
    tmp = Path(tempfile.mkdtemp())
    names = ("CAERNESS_DB_PATH", "CAERNESS_WORLD_PACKAGE")
    prior = {n: os.environ.get(n) for n in names}
    try:
        db = tmp / "b.db"
        t0 = time.time()
        build_opening(db, package="saintjude")
        secs = time.time() - t0
        mb = db.stat().st_size / 1048576
        print(f"build {secs:.1f}s, {mb:.1f} MB")
        assert secs < BUILD_SECONDS, secs
        assert mb < DB_MB, mb
    finally:
        os.environ.pop("CAERNESS_NO_OPENING_CACHE", None)
        for n, v in prior.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_build_time_and_size()
    print("ok test_build_time_and_size")
