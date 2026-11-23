"""Prison (J1): facilities as places, the men inside them, and the groups they belong to.

Sphere-free. A facility is a package-data institution (`prison.json` "facilities"): level, security, who it takes, a headcount and
character figures that drift. Each facility has inside groups (`facility_groups`), each an org-core organisation of the data's society
kind whose seats exist only for notable inmates; everyone else is a headcount. The case chain (`crime_response`: report, case, arrest,
bail, disposition, `sentences`, `custody`) is unchanged and stays the only writer of `custody`; this layer sits beside it, places a man
(`inmate_stays`), and from J1.2 owns his release. Every figure is a Design proposal in the package data, never a cap.
"""
from __future__ import annotations

import json
import sqlite3

from . import org_motives
from .world_package import package_for, prison_rules, system_enabled

DDL = """
CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    institution_actor_id INTEGER NOT NULL REFERENCES actors(id),
    location_id INTEGER,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    security TEXT NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 0,
    headcount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    character_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS facility_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    group_key TEXT NOT NULL,
    org_actor_id INTEGER NOT NULL REFERENCES actors(id),
    headcount INTEGER NOT NULL DEFAULT 0,
    character_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(facility_id, group_key)
);
CREATE TABLE IF NOT EXISTS inmate_stays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id),
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    group_id INTEGER,
    sentence_id INTEGER,
    case_id INTEGER,
    since_day INTEGER NOT NULL,
    until_day INTEGER,
    status TEXT NOT NULL DEFAULT 'inside',
    protective INTEGER NOT NULL DEFAULT 0,
    block_key TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_inmate_stays_actor ON inmate_stays(actor_id, status);
CREATE INDEX IF NOT EXISTS idx_inmate_stays_facility ON inmate_stays(facility_id, status);
CREATE TABLE IF NOT EXISTS prison_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stay_id INTEGER NOT NULL REFERENCES inmate_stays(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    outside_actor_id INTEGER,
    quality REAL NOT NULL DEFAULT 0.5,
    watched REAL NOT NULL DEFAULT 0.5,
    cost_weekly REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    since_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_prison_channels_stay ON prison_channels(stay_id, status);
CREATE TABLE IF NOT EXISTS prison_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    stay_id INTEGER NOT NULL,
    channel_id INTEGER,
    kind TEXT NOT NULL,
    from_actor_id INTEGER,
    to_actor_id INTEGER,
    summary TEXT NOT NULL DEFAULT '',
    intercepted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_prison_contacts_stay ON prison_contacts(stay_id, day);
CREATE TABLE IF NOT EXISTS prison_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day INTEGER NOT NULL,
    facility_id INTEGER NOT NULL,
    actor_id INTEGER,
    other_actor_id INTEGER,
    kind TEXT NOT NULL,
    severity REAL NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_prison_events_actor ON prison_events(actor_id, day);
CREATE TABLE IF NOT EXISTS law_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    sentence_id INTEGER NOT NULL,
    actor_id INTEGER NOT NULL,
    filed_day INTEGER NOT NULL,
    hearing_day INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    outcome TEXT,
    factors_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_law_reviews_due ON law_reviews(status, hearing_day);
CREATE TABLE IF NOT EXISTS inmate_ties (
    actor_a_id INTEGER NOT NULL,
    actor_b_id INTEGER NOT NULL,
    facility_id INTEGER NOT NULL,
    since_day INTEGER NOT NULL,
    kind TEXT NOT NULL,
    strength REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (actor_a_id, actor_b_id, facility_id)
);
"""

_READY: dict = {"key": None}


def ensure_tables(conn: sqlite3.Connection) -> None:
    """The J1 tables (also in the schema once Task 9 lands; a no-op once they exist)."""
    key = org_motives.db_key(conn)
    if _READY["key"] != key:
        for stmt in DDL.split(";"):  # not executescript: that commits, and a time skip is running inside a savepoint
            if stmt.strip():
                conn.execute(stmt)
        _READY["key"] = key


def rules(conn: sqlite3.Connection) -> dict:
    return prison_rules(package_for(conn))


def enabled(conn: sqlite3.Connection) -> bool:
    """The package has prison data and its organisation layer is on."""
    return bool(rules(conn)) and system_enabled(conn, "outfits")


def _figure(spec, default: float | None = None) -> float:
    """A figure as written, or `{"value": n, ...}` with its reasoning."""
    if isinstance(spec, dict):
        spec = spec.get("value")
    if spec is None:
        if default is None:
            raise KeyError("a figure the prison data should give is missing")
        return float(default)
    return float(spec)


# ---- facilities and their groups ----

def _institution(conn: sqlite3.Connection, name: str, subtype: str) -> int:
    row = conn.execute("SELECT id FROM actors WHERE name=? AND actor_type='institution'", (name,)).fetchone()
    if row is not None:
        return int(row[0])
    return int(conn.execute("INSERT INTO actors(name,actor_type,subtype,status) VALUES (?, 'institution', ?, 'active')", (name, subtype)).lastrowid)


def _location(conn: sqlite3.Connection, name: str, kind: str) -> int:
    row = conn.execute("SELECT id FROM locations WHERE name=?", (name,)).fetchone()
    if row is not None:
        return int(row[0])
    return int(conn.execute("INSERT INTO locations(name,kind,notes) VALUES (?,?,?)", (name, kind, "J1: a prison facility")).lastrowid)


def ensure_facilities(conn: sqlite3.Connection) -> dict[str, int]:
    """Create the package's facilities and their inside groups once (idempotent). A facility is an institution actor with a location;
    each group is an organisation of the data's society kind with no seats yet. Returns facility key -> facility id. A package with
    facilities but no fallback facility is a loud error: a man with no room anywhere must not silently go nowhere."""
    ensure_tables(conn)
    cfg = rules(conn)
    facilities = cfg.get("facilities") or {}
    if not facilities:
        return {}
    fb = cfg.get("fallback_facility")
    if fb not in facilities:
        raise KeyError("prison data names no fallback facility among its facilities")
    soc = cfg.get("society") or {}
    kind = soc.get("kind")
    if not kind:
        raise KeyError("prison data names no society kind")
    groups_cfg = cfg.get("groups") or {}
    out: dict[str, int] = {}
    for key, spec in facilities.items():
        row = conn.execute("SELECT id FROM facilities WHERE key=?", (key,)).fetchone()
        if row is not None:
            out[key] = int(row[0])
            continue
        inst = _institution(conn, spec["name"], "prison")
        loc = _location(conn, spec["name"], "prison")
        conn.execute("UPDATE actors SET current_location_id=COALESCE(current_location_id,?) WHERE id=?", (loc, inst))
        fid = int(conn.execute(
            """INSERT INTO facilities(key,institution_actor_id,location_id,name,level,security,capacity,headcount,character_json,metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (key, inst, loc, spec["name"], spec["level"], spec["security"], int(spec.get("capacity") or 0), int(spec.get("headcount") or 0),
             json.dumps(spec.get("character") or {}, sort_keys=True), json.dumps({"off_map": bool(spec.get("off_map"))}, sort_keys=True))).lastrowid)
        shares = {g: _figure((groups_cfg.get(g) or {}).get("share"), 0.0) for g in spec.get("groups") or []}
        total = sum(shares.values()) or 1.0
        for g in spec.get("groups") or []:
            gname = str((groups_cfg.get(g) or {}).get("name") or g)
            org = _institution(conn, str(soc.get("name_template") or "{group} at {facility}").format(group=gname, facility=spec["name"]), "inmate_society")
            conn.execute("INSERT OR IGNORE INTO org_profiles(org_actor_id,org_kind,sphere,package_key) VALUES (?,?,?,?)",
                         (org, kind, "prison", f"prison:{key}:{g}"))
            conn.execute("INSERT INTO facility_groups(facility_id,group_key,org_actor_id,headcount,character_json) VALUES (?,?,?,?,?)",
                         (fid, g, org, int(round(int(spec.get("headcount") or 0) * shares[g] / total)), "{}"))
        out[key] = fid
    return out
