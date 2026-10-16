from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def utc(y, m, d, hh=4, mm=30, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


def stamp(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def rows(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()


def fingerprint(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns


def run():
    from connector import backup

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "camp" / "ansel.db"
        src.parent.mkdir()
        writer = sqlite3.connect(src)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE t(x)")
        writer.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(10)])
        writer.commit()
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(10, 25)])  # only in the WAL
        writer.commit()

        # A plain file copy would lose the WAL rows; the backup API must not.
        naive = tmp / "naive.db"
        shutil.copy(src, naive)
        assert rows(naive) == 10
        before = fingerprint(src)

        dest = tmp / "backups"
        snap = backup.snapshot(src, dest, "manual", now=utc(2026, 10, 16, 12, 0, 5))
        assert snap.name == "ansel-20261016T120005Z-manual.db", snap.name
        assert rows(snap) == 25

        try:
            backup.snapshot(src, dest, "weird")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown label accepted")

        # A copy that fails its integrity check is deleted and reported.
        orig = backup._integrity_ok
        backup._integrity_ok = lambda p: False
        try:
            before_files = sorted(dest.iterdir())
            try:
                backup.snapshot(src, dest, "daily", now=utc(2026, 10, 16, 13, 0, 0))
            except RuntimeError:
                pass
            else:
                raise AssertionError("failed integrity check not reported")
            assert sorted(dest.iterdir()) == before_files
        finally:
            backup._integrity_ok = orig

        # prune: newest 7 dailies, one per older ISO week, newest of each label, others rotated.
        pdir = tmp / "prune"
        pdir.mkdir()

        def fake(label, dt):
            p = pdir / f"ansel-{stamp(dt)}-{label}.db"
            p.write_bytes(b"x")
            return p

        daily_days = [(9, 23), (9, 30), (10, 1), (10, 5), (10, 7), (10, 9), (10, 12), (10, 13), (10, 14), (10, 16)]
        dailies = {md: fake("daily", utc(2026, *md)) for md in daily_days}
        pre = [fake("preadvance", utc(2026, 10, 1 + i, 9)) for i in range(7)]
        imp = [fake("preimport", utc(2026, 10, 1 + i, 10)) for i in range(4)]
        man = [fake("manual", utc(2026, 10, 1 + i, 11)) for i in range(2)]
        other_stem = pdir / f"other-{stamp(utc(2026, 9, 1))}-daily.db"
        other_stem.write_bytes(b"x")
        stray = pdir / "notes.txt"
        stray.write_text("keep")

        deleted = backup.prune(pdir, "ansel", now=utc(2026, 10, 16, 5))
        expected = {dailies[(10, 1)], pre[0], pre[1], imp[0]}
        assert set(deleted) == expected, sorted(p.name for p in set(deleted) ^ expected)
        for p in expected:
            assert not p.exists()
        for p in [dailies[(9, 23)], dailies[(9, 30)], *man, other_stem, stray]:
            assert p.exists(), p
        assert dailies[(10, 16)].exists() and pre[-1].exists() and imp[-1].exists()

        # pre_advance_snapshot: no-op without a directory; throttled; source untouched.
        pdest = tmp / "pre"
        assert backup.pre_advance_snapshot(src, None) is None
        first = backup.pre_advance_snapshot(src, pdest)
        assert first is not None and first.name.endswith("-preadvance.db") and rows(first) == 25
        assert backup.pre_advance_snapshot(src, pdest) is None
        again = backup.pre_advance_snapshot(src, pdest, min_interval_s=0)
        assert again is not None and again != first
        assert len(list(pdest.glob("*-preadvance.db"))) == 2

        assert fingerprint(src) == before, "snapshot code modified the source database"
        writer.close()
    print("connector_backup_test passed")


if __name__ == "__main__":
    run()
