"""Campaign files: each campaign is a copy of the packaged opening world."""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGED_DB = ROOT / "data" / "caerness.db"
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def campaign_dir() -> Path:
    configured = os.environ.get("CAERNESS_CAMPAIGN_DIR")
    base = Path(configured) if configured else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Caerness" / "campaigns"
    base.mkdir(parents=True, exist_ok=True)
    return base


def open_campaign(name: str) -> Path:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError("campaign name must match [A-Za-z0-9_-]{1,40}")
    path = campaign_dir() / f"{name}.db"
    if not path.exists():
        # Copy beside the target, then rename: a crash or a second server starting at the same
        # moment never sees a half-copied campaign under the real name.
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            shutil.copy2(PACKAGED_DB, tmp)
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
    return path


def connect_campaign() -> sqlite3.Connection:
    from engine.db import connect

    conn = connect()
    conn.execute("PRAGMA busy_timeout=30000")
    return conn
