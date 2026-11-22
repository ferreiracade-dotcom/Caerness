"""Shared fixture for Saint Jude tests: build the packaged opening once per process, copy it per call.

    from tests.sj_fixture import build_saintjude, connect
    db = build_saintjude(Path(tmp)); conn = connect(db)

The build (tools.build_opening.build_opening(db, package="saintjude")) takes a few seconds; its time is
printed once so later tasks can note the opening time.
"""
from __future__ import annotations

import atexit
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_CACHE: dict[str, Path] = {}
_CACHE_DIR: list[tempfile.TemporaryDirectory] = []
_COPIES = [0]


def _cached_build() -> Path:
    if "db" not in _CACHE:
        from tools.build_opening import build_opening
        holder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        _CACHE_DIR.append(holder)  # kept alive for the process
        db = Path(holder.name) / "saintjude_opening.db"
        names = ("CAERNESS_DB_PATH", "CAERNESS_WORLD_PACKAGE")  # build_opening sets both
        prior = {n: os.environ.get(n) for n in names}
        t0 = time.time()
        try:
            build_opening(db, package="saintjude")
        finally:
            for n, v in prior.items():
                if v is None:
                    os.environ.pop(n, None)
                else:
                    os.environ[n] = v
        print(f"sj_fixture: Saint Jude opening built in {time.time() - t0:.1f}s")
        _CACHE["db"] = db
    return _CACHE["db"]


def build_saintjude(tmp: Path) -> Path:
    """A fresh copy of the Saint Jude opening under `tmp` (built once per process)."""
    src = _cached_build()
    _COPIES[0] += 1
    out = Path(tmp) / f"saintjude_{_COPIES[0]}.db"
    shutil.copyfile(src, out)
    _remove_at_exit(Path(tmp))
    return out


_TO_REMOVE: set[Path] = set()


def _remove_at_exit(d: Path) -> None:
    """Callers pass a mkdtemp() dir and never remove it; remove it when the process ends (only under the temp root)."""
    d = d.resolve()
    if d.is_relative_to(Path(tempfile.gettempdir()).resolve()) and d not in _TO_REMOVE:
        _TO_REMOVE.add(d)
        atexit.register(shutil.rmtree, d, ignore_errors=True)


def connect(path: Path) -> sqlite3.Connection:
    """A connection to a fixture database with sqlite3.Row rows."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size = -262144")  # as engine.db.connect: a late-run save is far bigger than the default page cache
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn
