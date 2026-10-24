"""Campaign files: each campaign is a copy of the packaged opening world."""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from pathlib import Path

from engine.world_package import DEFAULT_PACKAGE, current_package, load_package, set_campaign_package

ROOT = Path(__file__).resolve().parent.parent
PACKAGED_DB = ROOT / "data" / "caerness.db"
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def campaign_dir() -> Path:
    configured = os.environ.get("CAERNESS_CAMPAIGN_DIR")
    base = Path(configured) if configured else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Caerness" / "campaigns"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _packaged_db(pkg_id: str) -> Path:
    return PACKAGED_DB if pkg_id == DEFAULT_PACKAGE else ROOT / "data" / f"{pkg_id}.db"


def _bible_needs_index(bible: Path, has_canon: int) -> bool:
    """True when the campaign has no World Bible index, or the one it has was built from an older file.

    The indexed file's sha256 is canon_sources.content_hash (written by index_canon). An existing index
    with no row for this bible path (nothing recorded to compare) is left alone, so a Caerness campaign
    whose bible is unchanged is never re-indexed.
    """
    if not has_canon:
        return True
    import hashlib

    from engine.canon import ROOT as CANON_ROOT
    from engine.db import connect

    resolved = bible.resolve()
    try:
        key = str(resolved.relative_to(CANON_ROOT))
    except ValueError:
        key = str(resolved)
    with connect() as conn:
        row = conn.execute("SELECT content_hash FROM canon_sources WHERE source_path=?", (key,)).fetchone()
    if row is None:
        return False
    return row["content_hash"] != hashlib.sha256(resolved.read_bytes()).hexdigest()


def open_campaign(name: str, package: str | None = None) -> Path:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError("campaign name must match [A-Za-z0-9_-]{1,40}")
    path = campaign_dir() / f"{name}.db"
    created = False
    if not path.exists():
        pkg_id = package or DEFAULT_PACKAGE
        load_package(pkg_id)  # unknown or broken package raises before anything is written
        source = _packaged_db(pkg_id)
        if not source.is_file():
            raise FileNotFoundError(f"packaged opening for world package '{pkg_id}' not found: {source}")
        created = True
        # Copy beside the target, then rename: a crash or a second server starting at the same
        # moment never sees a half-copied campaign under the real name.
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            shutil.copy2(source, tmp)
            if not path.exists():
                os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    from engine.db import connect, init_db
    from connector.store import ensure_connector_schema

    init_db()
    with connect() as conn:
        ensure_connector_schema(conn)
        if created:
            set_campaign_package(conn, pkg_id)
        has_canon = conn.execute("SELECT COUNT(*) FROM canon_chunks").fetchone()[0]
        bible = current_package(conn).bible_path
    if bible.exists() and _bible_needs_index(bible, has_canon):
        from engine.canon import index_canon

        index_canon(bible)  # replaces that source's chunks; the stored content hash is the new file's
    return path


def connect_campaign() -> sqlite3.Connection:
    from engine.db import connect

    conn = connect()
    conn.execute("PRAGMA busy_timeout=30000")
    return conn
