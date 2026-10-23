"""World packages: a manifest (worlds/<id>/world.json) naming a world's bible, seed, calendar and systems.

A campaign is bound to a package by engine_meta.world_package_id. An absent row means "caerness",
so every pre-package database keeps loading as Caerness.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = "caerness"
META_KEY = "world_package_id"
SYSTEM_KEYS = ("cultivation", "elixir", "hollow", "groundbinding", "caerness_underworld",
               "caerness_religions", "caerness_trade", "merchant_houses")


class WorldPackageError(ValueError):
    pass


@dataclass(frozen=True)
class WorldPackage:
    id: str
    display_name: str
    root: Path
    calendar: dict
    bible_path: Path
    bible_sha256: str | None
    seed_path: Path
    seed_namespace: str
    rulebook_section: Path | None
    creation_section: Path | None
    systems: dict[str, bool]
    data: dict[str, Path] = field(default_factory=dict)
    name_pools: dict = field(default_factory=dict)
    name_groups: dict = field(default_factory=dict)
    mortality: dict = field(default_factory=lambda: {"model": "gompertz_premodern"})
    background: dict = field(default_factory=lambda: {"stage_distribution": True})
    opening_family: dict = field(default_factory=lambda: {"marry_adults_on_day0": True})


def worlds_dir() -> Path:
    env = os.environ.get("CAERNESS_WORLDS_DIR")
    return Path(env) if env else ROOT / "worlds"


def list_packages() -> list[str]:
    base = worlds_dir()
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir() if (d / "world.json").is_file())


def _need(pkg_id: str, root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if not path.exists():
        raise WorldPackageError(f"package '{pkg_id}': file '{rel}' missing")
    return path


def load_package(pkg_id: str) -> WorldPackage:
    root = worlds_dir() / pkg_id
    manifest = root / "world.json"
    if not manifest.is_file():
        raise WorldPackageError(f"package '{pkg_id}': file 'world.json' missing")
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
    except ValueError as e:
        raise WorldPackageError(f"package '{pkg_id}': file 'world.json' invalid: {e}") from e
    for key in ("id", "display_name", "calendar", "bible_path", "seed_path", "seed_namespace"):
        if key not in m:
            raise WorldPackageError(f"package '{pkg_id}': field '{key}' missing in world.json")
    if m["id"] != pkg_id:
        raise WorldPackageError(f"package '{pkg_id}': world.json id is '{m['id']}'")
    if (m["calendar"] or {}).get("kind") not in ("sv", "gregorian"):
        raise WorldPackageError(f"package '{pkg_id}': calendar.kind must be 'sv' or 'gregorian'")
    systems = {k: bool((m.get("systems") or {}).get(k, False)) for k in SYSTEM_KEYS}
    optional = lambda k: _need(pkg_id, root, m[k]) if m.get(k) else None
    data = {name: _need(pkg_id, root, rel) for name, rel in (m.get("data") or {}).items()}
    name_groups = {}
    if "names" in data:  # ethnic groups: a person's given and family names are drawn from the same group
        try:
            name_groups = dict(json.loads(data["names"].read_text(encoding="utf-8")).get("groups") or {})
        except ValueError as e:
            raise WorldPackageError(f"package '{pkg_id}': file '{m['data']['names']}' invalid: {e}") from e
    return WorldPackage(
        id=pkg_id,
        display_name=str(m["display_name"]),
        root=root,
        calendar=dict(m["calendar"]),
        bible_path=_need(pkg_id, root, m["bible_path"]),
        bible_sha256=m.get("bible_sha256") or None,
        seed_path=_need(pkg_id, root, m["seed_path"]),
        seed_namespace=str(m["seed_namespace"]),
        rulebook_section=optional("rulebook_section"),
        creation_section=optional("creation_section"),
        systems=systems,
        data=data,
        name_pools=dict(m.get("name_pools") or {}),
        name_groups=name_groups,
        mortality=dict(m.get("mortality") or {"model": "gompertz_premodern"}),
        background={"stage_distribution": True, **(m.get("background") or {})},
        opening_family={"marry_adults_on_day0": True, **(m.get("opening_family") or {})},
    )


def current_package(conn) -> WorldPackage:
    try:
        row = conn.execute("SELECT value FROM engine_meta WHERE key=?", (META_KEY,)).fetchone()
    except Exception:
        row = None
    return load_package(str(row[0]) if row and row[0] else DEFAULT_PACKAGE)


def set_campaign_package(conn, pkg_id: str) -> None:
    load_package(pkg_id)  # validates before binding
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES (?,?)", (META_KEY, pkg_id))
    conn.commit()


def configured_package_id() -> str:
    return os.environ.get("CAERNESS_WORLD_PACKAGE") or DEFAULT_PACKAGE


_SWITCH_CACHE: dict[tuple, "WorldPackage"] = {}


def package_for(conn) -> "WorldPackage":
    """current_package(conn), memoised on the manifest's identity and mtime (cheap enough for per-person hot paths)."""
    try:
        row = conn.execute("SELECT value FROM engine_meta WHERE key=?", (META_KEY,)).fetchone()
    except Exception:
        row = None
    pkg_id = str(row[0]) if row and row[0] else DEFAULT_PACKAGE
    manifest = worlds_dir() / pkg_id / "world.json"
    try:
        key = (str(manifest), manifest.stat().st_mtime_ns)
    except OSError:
        key = (str(manifest), 0)
    pkg = _SWITCH_CACHE.get(key)
    if pkg is None:
        pkg = _SWITCH_CACHE[key] = load_package(pkg_id)
    return pkg


def system_enabled(conn, key: str) -> bool:
    """True when the campaign's world package switches the system `key` on."""
    return bool(package_for(conn).systems.get(key, False))


_TIMELINE_CACHE: dict[tuple, dict[str, dict]] = {}


def _timeline(pkg: "WorldPackage") -> dict[str, dict]:
    """The package's dated timeline (data "timeline"), indexed by lower-cased name and alias; empty when it has none."""
    path = pkg.data.get("timeline")
    if path is None:
        return {}
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        key = (str(path), 0)
    index = _TIMELINE_CACHE.get(key)
    if index is None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw.get("entries", []) if isinstance(raw, dict) else raw
        index = {}
        for e in entries:
            for label in [e["name"], *(e.get("aliases") or [])]:
                index[str(label).strip().lower()] = e
        _TIMELINE_CACHE[key] = index
    return index


def timeline_status(pkg: "WorldPackage", name: str, date) -> str:
    """Where a named thing stands on `date` (an ISO string or a datetime.date) in the package's timeline.

    "unknown" when the package does not list the name; otherwise "not_yet" before it exists, then "exists", "available"
    and "common" as each stage's date is reached. A stage with no date (null) is never reached, so a thing without a
    "common" date stays "available". Names match case-insensitively and by alias."""
    entry = _timeline(pkg).get(str(name).strip().lower())
    if entry is None:
        return "unknown"
    day = (date.isoformat() if hasattr(date, "isoformat") else str(date))[:10]
    status = "not_yet"
    for stage in ("exists", "available", "common"):
        stage_date = entry.get(stage)
        if stage_date is not None and day >= stage_date:
            status = stage
    return status
