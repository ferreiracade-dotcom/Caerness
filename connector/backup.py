"""Consistent, rotating campaign backups through SQLite's online backup API (never a file copy: WAL)."""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LABELS = ("daily", "preadvance", "manual", "preimport")
_STAMP = "%Y%m%dT%H%M%SZ"
_NAME = re.compile(r"^(?P<stem>.+)-(?P<ts>\d{8}T\d{6}Z)-(?P<label>[a-z]+)\.db$")


class SnapshotIntegrityError(RuntimeError):
    """A fresh snapshot failed PRAGMA integrity_check: the source itself may be damaged."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _integrity_ok(path: Path) -> bool:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def copy_consistent(src: Path, dst: Path) -> None:
    """Back up src into the new file dst with the online backup API, then verify the copy.

    The source is opened read-only where SQLite allows it, so it is never modified. On any failure
    dst is removed.
    """
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        raise FileNotFoundError(f"no such database: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            source = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
            source.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        except sqlite3.OperationalError:  # e.g. a WAL database with no -shm yet
            source = sqlite3.connect(src)
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        if not _integrity_ok(dst):
            raise SnapshotIntegrityError(f"snapshot of {src.name} failed its integrity check")
    except BaseException:
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(dst) + suffix).unlink(missing_ok=True)
        raise


def snapshot(src: Path, dest_dir: Path, label: str, now: datetime | None = None) -> Path:
    if label not in LABELS:
        raise ValueError(f"label must be one of {LABELS}")
    src, dest_dir = Path(src), Path(dest_dir)
    when = (now or _utcnow()).astimezone(timezone.utc).replace(microsecond=0)
    while True:
        dst = dest_dir / f"{src.stem}-{when.strftime(_STAMP)}-{label}.db"
        if not dst.exists():
            break
        when += timedelta(seconds=1)  # two snapshots inside one second
    copy_consistent(src, dst)
    return dst


def _parse(dest_dir: Path, stem: str) -> list[tuple[datetime, str, Path]]:
    found = []
    for p in Path(dest_dir).glob(f"{stem}-*.db"):
        m = _NAME.match(p.name)
        if m and m["stem"] == stem and m["label"] in LABELS:
            found.append((datetime.strptime(m["ts"], _STAMP).replace(tzinfo=timezone.utc), m["label"], p))
    return sorted(found, key=lambda t: t[0], reverse=True)  # newest first


def prune(dest_dir: Path, stem: str, keep_daily: int = 7, keep_weekly: int = 4, keep_preadvance: int = 5,
          keep_preimport: int = 3, now: datetime | None = None) -> list[Path]:
    """Delete snapshots beyond the retention policy; return the deleted paths.

    daily: the newest keep_daily, plus the oldest daily of each of the newest keep_weekly ISO weeks
    older than that window. preadvance / preimport: the newest N. manual: kept. The newest snapshot of
    every label always survives.
    """
    entries = _parse(dest_dir, stem)
    doomed: list[Path] = []

    dailies = [e for e in entries if e[1] == "daily"]
    older = dailies[max(1, keep_daily):]
    weeks: dict[tuple[int, int], tuple[datetime, str, Path]] = {}
    for entry in older:  # newest first, so the last write per week is the oldest daily of it
        iso = entry[0].isocalendar()
        weeks[(iso[0], iso[1])] = entry
    keepers = {e[2] for e in sorted(weeks.values(), key=lambda t: t[0], reverse=True)[:max(0, keep_weekly)]}
    doomed += [e[2] for e in older if e[2] not in keepers]

    for label, keep in (("preadvance", keep_preadvance), ("preimport", keep_preimport)):
        doomed += [e[2] for e in [e for e in entries if e[1] == label][max(1, keep):]]

    for p in doomed:
        p.unlink(missing_ok=True)
    return doomed


def pre_advance_snapshot(campaign_path: Path, backup_dir: Path | None, min_interval_s: int = 3600) -> Path | None:
    if backup_dir is None:
        return None
    campaign_path = Path(campaign_path)
    latest = [e for e in _parse(Path(backup_dir), campaign_path.stem) if e[1] == "preadvance"]
    if latest and (_utcnow() - latest[0][0]).total_seconds() < min_interval_s:
        return None
    path = snapshot(campaign_path, Path(backup_dir), "preadvance")
    prune(Path(backup_dir), campaign_path.stem)
    return path


def main(argv: list[str] | None = None) -> int:
    from connector.campaign import _NAME as CAMPAIGN_NAME, campaign_dir
    from connector.settings import Settings

    ap = argparse.ArgumentParser(description="Snapshot a campaign (or every campaign) and rotate old snapshots")
    ap.add_argument("--campaign")
    ap.add_argument("--all", action="store_true", help="every *.db in the campaign directory")
    ap.add_argument("--label", default="daily", choices=LABELS)
    args = ap.parse_args(argv)
    settings = Settings.from_env()
    try:
        if bool(args.campaign) == bool(args.all):
            raise ValueError("give exactly one of --campaign NAME or --all")
        if settings.backup_dir is None:
            raise ValueError("CAERNESS_BACKUP_DIR is not set")
        names = sorted(p.stem for p in campaign_dir().glob("*.db")) if args.all else [args.campaign]
        if not names:
            raise ValueError("no campaigns to back up")
        failed = 0
        for name in names:
            try:
                if not CAMPAIGN_NAME.match(name):
                    raise ValueError("invalid campaign name")
                path = snapshot(campaign_dir() / f"{name}.db", settings.backup_dir, args.label)
                prune(settings.backup_dir, name)
                print(f"snapshot: {path}")
            except Exception as e:
                failed += 1
                print(f"backup failed for {name}: {e}", file=sys.stderr)
        return 1 if failed else 0
    except Exception as e:
        print(f"backup failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
