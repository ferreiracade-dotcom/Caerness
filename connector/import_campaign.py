"""Validate and install an uploaded campaign file (laptop export -> VM).

Usage: python -m connector.import_campaign SRC --campaign NAME [--replace]
Stop the service first when using --replace.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connector import backup
from connector.campaign import _NAME, campaign_dir

SQLITE_MAGIC = b"SQLite format 3\x00"


def _check_raw(path: Path) -> None:
    """Refuse anything that is not a sound Caerness campaign with a protagonist."""
    from engine.db import SCHEMA_VERSION

    with path.open("rb") as fh:
        if fh.read(16) != SQLITE_MAGIC:
            raise ValueError("the file is not a SQLite database")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("the database failed its integrity check")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"actors", "world_state", "player_state"} <= tables:
                raise ValueError("the file is not a Caerness campaign (actors, world_state or player_state is missing)")
            if "engine_meta" in tables:
                row = conn.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()
                if row and str(row[0]).isdigit() and int(row[0]) > SCHEMA_VERSION:
                    raise ValueError(f"the campaign has schema {row[0]}, newer than this server's {SCHEMA_VERSION}")
            players = conn.execute(
                "SELECT COUNT(*) FROM player_state ps JOIN actors a ON a.id=ps.player_actor_id").fetchone()[0]
            if players != 1:
                raise ValueError("the campaign has no protagonist; set one before exporting")
        except sqlite3.DatabaseError as e:
            raise ValueError(f"the file cannot be read as a campaign: {e}") from e
    finally:
        conn.close()


def _bring_current(path: Path) -> None:
    """Migrate an older campaign to this server's schema (on the temp copy only)."""
    previous = os.environ.get("CAERNESS_DB_PATH")
    os.environ["CAERNESS_DB_PATH"] = str(path)
    try:
        from connector.store import ensure_connector_schema
        from engine.db import connect, init_db

        init_db()
        with connect() as conn:
            ensure_connector_schema(conn)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        if previous is None:
            os.environ.pop("CAERNESS_DB_PATH", None)
        else:
            os.environ["CAERNESS_DB_PATH"] = previous
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def install_campaign(src: Path, name: str, *, replace: bool = False, backup_dir: Path | None = None) -> Path:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError("campaign name must match [A-Za-z0-9_-]{1,40}")
    src = Path(src)
    if not src.is_file():
        raise ValueError(f"no such file: {src}")
    target = campaign_dir() / f"{name}.db"
    if target.exists() and not replace:
        raise FileExistsError(f"campaign '{name}' already exists; pass --replace to overwrite it "
                              "(the old file is snapshotted first)")
    tmp = target.with_name(f"{target.name}.{os.getpid()}.import.tmp")
    try:
        shutil.copyfile(src, tmp)  # work on a copy: the upload itself is never modified
        _check_raw(tmp)
        _bring_current(tmp)
        _check_raw(tmp)
        if target.exists():
            where = backup_dir or (campaign_dir() / "backups")
            backup.snapshot(target, where, "preimport")
            conn = sqlite3.connect(target)  # fold any WAL into the old file so no stale -wal meets the new one
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
            for suffix in ("-wal", "-shm"):
                Path(str(target) + suffix).unlink(missing_ok=True)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(tmp) + suffix).unlink(missing_ok=True)
    return target


def main(argv: list[str] | None = None) -> int:
    from connector.settings import Settings

    ap = argparse.ArgumentParser(description="Install an uploaded campaign file")
    ap.add_argument("src")
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args(argv)
    try:
        path = install_campaign(Path(args.src), args.campaign, replace=args.replace,
                                backup_dir=Settings.from_env().backup_dir)
    except (ValueError, FileExistsError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(f"installed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
