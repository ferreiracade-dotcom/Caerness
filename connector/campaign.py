"""Campaign files: each campaign is a copy of the packaged opening world."""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from pathlib import Path

from engine.world_package import DEFAULT_PACKAGE, configured_package_id, current_package, list_packages, load_package, set_campaign_package

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
        pkg_id = package or configured_package_id()  # CAERNESS_WORLD_PACKAGE picks a new campaign's world; unset is Caerness
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


LAST_FILE = "last_campaign"


def campaign_name_for(world: str) -> str:
    """The live campaign's name for a world: the default world keeps `main`, every other world is named by its package id."""
    return "main" if world == DEFAULT_PACKAGE else world


def last_played() -> str | None:
    """The world id last switched to (text file beside the campaigns), or None."""
    try:
        text = (campaign_dir() / LAST_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def remember_last(name: str) -> None:
    (campaign_dir() / LAST_FILE).write_text(name.strip() + "\n", encoding="utf-8")


def list_worlds() -> list[dict]:
    """Every installed world package: its id, display name (from the package), campaign name, and whether that campaign exists."""
    out = []
    for pkg_id in list_packages():
        try:
            display = load_package(pkg_id).display_name
        except Exception:  # a broken package is listed by id; opening it reports the real error
            display = pkg_id
        name = campaign_name_for(pkg_id)
        out.append({"world": pkg_id, "display_name": display, "campaign": name, "exists": (campaign_dir() / f"{name}.db").is_file()})
    return out


def switch_to(world: str) -> Path:
    """Open (creating from the packaged opening if new) the world's campaign, make it current, and remember it.

    An unknown or broken world raises before CAERNESS_DB_PATH changes. The package caches in engine.world_package
    are keyed by manifest path and mtime (never by package id alone), so nothing needs clearing on a switch.
    """
    if not isinstance(world, str) or world not in list_packages():
        raise ValueError(f"unknown world '{world}'; known: {', '.join(list_packages()) or 'none'}")
    load_package(world)
    previous = os.environ.get("CAERNESS_DB_PATH")
    try:
        path = open_campaign(campaign_name_for(world), package=world)
    except Exception:
        if previous is None:
            os.environ.pop("CAERNESS_DB_PATH", None)
        else:
            os.environ["CAERNESS_DB_PATH"] = previous
        raise
    remember_last(world)
    return path


def open_startup(default_campaign: str) -> Path:
    """Start-up: the world last played if there is one, else the configured campaign (a new Caerness campaign as before)."""
    world = last_played()
    if world and world != DEFAULT_PACKAGE and world in list_packages():
        try:
            return open_campaign(campaign_name_for(world), package=world)
        except Exception:
            pass  # fall back to the configured campaign rather than refuse to start
    return open_campaign(default_campaign)
