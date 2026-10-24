"""Build a Caerness opening in a scratch DB and fingerprint it.

Usage: CAERNESS_DB_PATH=<scratch.db> python tools/build_opening.py [--write-fixture]

build_opening mirrors run.py `current-canon-bootstrap` minus the coverage run.
fingerprint hashes every table's rows (sorted) so later changes can prove the opening is unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SEED = ROOT / "game" / "seeds" / "Caerness_Initial_World_State_Seed_v1_4.json"
FIXTURE = ROOT / "tests" / "fixtures" / "caerness_opening_fingerprint.json"

# Tables that are audit/connector scratch rather than world state.
VOLATILE = {"scene_packets"}
VOLATILE_PREFIXES = ("connector_",)
# Columns excluded from row hashes: wall-clock timestamps (all columns ending in _at) plus any listed here.
VOLATILE_COLUMNS: dict[str, set[str]] = {}


def build_opening(db_path: Path, seed_path: Path | None = None, package: str = "caerness") -> None:
    from engine.world_package import DEFAULT_PACKAGE, list_packages
    if package != DEFAULT_PACKAGE and package not in list_packages():
        raise ValueError(f"unknown package {package!r}")
    os.environ["CAERNESS_DB_PATH"] = str(db_path)
    # init_db names the world from the configured package, so the argument must win over a stale environment.
    os.environ["CAERNESS_WORLD_PACKAGE"] = package
    from engine.activation import activate_existing_loops
    from engine.current_seed import DEFAULT_CURRENT_SEED, import_current_seed
    from engine.db import connect, init_db

    init_db()
    with connect() as conn:
        if package != DEFAULT_PACKAGE:  # a Caerness database carries no package row, so its opening is unchanged
            from engine.world_package import set_campaign_package
            set_campaign_package(conn, package)
            import_current_seed(conn, str(seed_path) if seed_path else None)
        else:
            import_current_seed(conn, str(seed_path or DEFAULT_CURRENT_SEED))
        activate_existing_loops(conn)
        conn.commit()


def _skip_table(name: str) -> bool:
    return name.startswith("sqlite_") or name in VOLATILE or name.startswith(VOLATILE_PREFIXES)


def fingerprint(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        out: dict[str, str] = {}
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            if _skip_table(t):
                continue
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')
                    if not r[1].endswith("_at") and r[1] not in VOLATILE_COLUMNS.get(t, ())]
            if not cols:
                out[t] = hashlib.sha256(b"").hexdigest()
                continue
            q = ",".join(f'"{c}"' for c in cols)
            rows = sorted(json.dumps(list(r), default=repr, ensure_ascii=False) for r in conn.execute(f'SELECT {q} FROM "{t}"'))
            h = hashlib.sha256()
            h.update(json.dumps(cols).encode())
            for r in rows:
                h.update(r.encode("utf-8"))
                h.update(b"\n")
            out[t] = h.hexdigest()
        return out
    finally:
        conn.close()


def build_packaged(package: str, out: Path) -> None:
    """Write a package's opening world (e.g. data/saintjude.db) through a temp file, so a failed build leaves none."""
    tmp = out.with_name(out.name + ".building")
    for p in (tmp, Path(f"{tmp}-wal"), Path(f"{tmp}-shm")):
        p.unlink(missing_ok=True)
    build_opening(tmp, package=package)
    os.replace(tmp, out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    import tempfile
    if "--package" in sys.argv:
        package = sys.argv[sys.argv.index("--package") + 1]
        out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "data" / f"{package}.db"
        build_packaged(package, out)
        return
    write = "--write-fixture" in sys.argv
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "opening.db"
        build_opening(db, DEFAULT_SEED)
        fp = fingerprint(db)
    if write:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(fp, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {FIXTURE} ({len(fp)} tables)")
    else:
        print(json.dumps(fp, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
