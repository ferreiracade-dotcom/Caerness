"""Build the single zip to copy onto the phone (Termux home) for running and benchmarking Caerness.

Usage: python tools/package_phone.py [--out dist/caerness_phone.zip]
The packaged opening is copied with the SQLite backup API so pending WAL content is included and the
zip holds one consistent file.  The source DB is opened read-only.
"""
from __future__ import annotations

import argparse
import sqlite3
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["run.py", "DESIGN.md", "ANDROID_ONEPLUS12.md"]
DIRS = ["engine", "mobile", "canon", "tools"]


def _wanted(p: Path) -> bool:
    return "__pycache__" not in p.parts and p.suffix != ".pyc" and p.is_file()


def build(out: Path) -> dict:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with tempfile.TemporaryDirectory(prefix="caerness_pkgdb_") as tmp:
        db_copy = Path(tmp) / "caerness.db"
        src = sqlite3.connect(f"file:{ROOT / 'data' / 'caerness.db'}?mode=ro", uri=True)
        dst = sqlite3.connect(db_copy)
        src.backup(dst)
        dst.close(); src.close()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in FILES:
                z.write(ROOT / f, f); count += 1
            for d in DIRS:
                for p in sorted((ROOT / d).rglob("*")):
                    if _wanted(p):
                        z.write(p, p.relative_to(ROOT).as_posix()); count += 1
            z.write(db_copy, "data/caerness.db"); count += 1
    return {"path": str(out), "files": count, "bytes": out.stat().st_size}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist" / "caerness_phone.zip"))
    info = build(Path(ap.parse_args().out))
    print(info)


if __name__ == "__main__":
    main()
