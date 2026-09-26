"""package_phone: one zip with everything the phone needs, a consistent DB, and no build litter."""
from __future__ import annotations
import os, sqlite3, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from package_phone import build


def run():
    tmp = Path(tempfile.mkdtemp(prefix="caerness_pkg_"))
    info = build(tmp / "caerness_phone.zip")
    assert info["files"] > 50 and info["bytes"] > 1_000_000, info
    z = zipfile.ZipFile(info["path"])
    names = set(z.namelist())
    for required in ("run.py", "engine/db.py", "engine/simulation.py", "mobile/index.html", "data/caerness.db",
                     "tools/bench_sim.py", "tools/bench_simulants.py", "tools/derive_budgets.py", "ANDROID_ONEPLUS12.md"):
        assert required in names, required
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc") or n.endswith("-wal") or n.endswith("-shm")]
    assert not [n for n in names if n.startswith("tests/")]
    z.extract("data/caerness.db", tmp)
    c = sqlite3.connect(tmp / "data" / "caerness.db")
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) == 0
    c.close()
    print("package_phone PASS", info)


if __name__ == "__main__":
    run()
