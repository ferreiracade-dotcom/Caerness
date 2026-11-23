"""Prison (J1): facilities as places, the men inside them, and the groups they belong to.

Sphere-free. A facility is a package-data institution (`prison.json` "facilities"): level, security, who it takes, a headcount and
character figures that drift. Each facility has inside groups (`facility_groups`), each an org-core organisation of the data's society
kind whose seats exist only for notable inmates; everyone else is a headcount. The case chain (`crime_response`: report, case, arrest,
bail, disposition, `sentences`, `custody`) is unchanged and stays the only writer of `custody`; this layer sits beside it, places a man
(`inmate_stays`), and from J1.2 owns his release. Every figure is a Design proposal in the package data, never a cap.
"""
from __future__ import annotations

import json
import random
import sqlite3

from . import org_motives
from .design import run_seed
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


# ---- who goes where ----

def _rng(conn: sqlite3.Connection, stream: str, key) -> random.Random:
    return random.Random(f"{run_seed(conn)}:prison:{stream}:{key}")


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _sex(conn: sqlite3.Connection, actor_id: int) -> str:
    r = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (int(actor_id),)).fetchone()
    return "female" if r is not None and r[0] == "female" else "male"


def _cooperator(conn: sqlite3.Connection, actor_id: int) -> bool:
    """He has been found out as an informer, or is on the books of one who turned him."""
    return (conn.execute("SELECT 1 FROM org_incidents WHERE kind='informs' AND offender_actor_id=? LIMIT 1", (int(actor_id),)).fetchone() is not None
            or conn.execute("SELECT 1 FROM org_informers WHERE informer_actor_id=? LIMIT 1", (int(actor_id),)).fetchone() is not None)


def _outside_standing(conn: sqlite3.Connection, actor_id: int) -> float | None:
    """His best standing in an organisation outside the prison, None when he holds no seat outside."""
    r = conn.execute("""SELECT MAX(s.standing) FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
                        WHERE s.actor_id=? AND s.status IN ('active','held') AND p.sphere<>'prison'""", (int(actor_id),)).fetchone()
    return None if r is None or r[0] is None else float(r[0])


def _authority(conn: sqlite3.Connection, actor_id: int, sentence=None) -> str:
    """The authority kind of the agency whose case holds him (municipal when nothing says)."""
    prof = None
    if sentence is not None:
        try:
            prof = json.loads(sentence["metadata_json"] or "{}").get("agency_profile_id")
        except (ValueError, TypeError):
            prof = None
    if prof is None:
        r = conn.execute("SELECT agency_profile_id FROM custody WHERE actor_id=? AND agency_profile_id IS NOT NULL ORDER BY id DESC LIMIT 1", (int(actor_id),)).fetchone()
        prof = r[0] if r is not None else None
    if prof is None:
        return "municipal"
    r = conn.execute("SELECT authority_kind FROM law_enforcement_profiles WHERE id=?", (int(prof),)).fetchone()
    return str(r[0]) if r is not None else "municipal"


def assign_facility(conn: sqlite3.Connection, actor_id: int, *, term_days: int | None, authority: str, pretrial: bool, day: int) -> int:
    """The facility that takes him: the data's intake rules (authority, sex, term range, remand or not); several that fit are drawn
    by their `pull`; a woman is sent to a facility meant for women when one fits. When nothing fits, the declared fallback facility
    (or, if that does not take his sex, the first facility that does)."""
    cfg = rules(conn)
    sex = _sex(conn, actor_id)
    fac = cfg["facilities"]
    cands: list[str] = []
    for key, spec in fac.items():
        it = spec.get("intake") or {}
        takes = bool(it.get("remand")) if pretrial else bool(it.get("sentenced", True))  # `remand`: takes men awaiting trial; `sentenced` (default yes): takes sentenced men
        if not takes or authority not in (it.get("authority") or []):
            continue
        if it.get("sex", "any") not in ("any", sex):
            continue
        if not pretrial and term_days is not None and not (int(it.get("min_term_days", 0)) <= int(term_days) <= int(it.get("max_term_days", 10 ** 9))):
            continue
        cands.append(key)
    if sex == "female" and any((fac[k].get("intake") or {}).get("sex") == "female" for k in cands):
        cands = [k for k in cands if (fac[k].get("intake") or {}).get("sex") == "female"]
    if not cands:
        key = cfg["fallback_facility"]
        if (fac[key].get("intake") or {}).get("sex", "any") not in ("any", sex):
            key = next(k for k in sorted(fac) if (fac[k].get("intake") or {}).get("sex", "any") in ("any", sex))
    elif len(cands) == 1:
        key = cands[0]
    else:
        weights = [max(1e-9, _figure((fac[k].get("intake") or {}).get("pull"), 1.0)) for k in cands]
        key = _rng(conn, "facility", f"{actor_id}:{day}").choices(cands, weights=weights)[0]
    return int(conn.execute("SELECT id FROM facilities WHERE key=?", (key,)).fetchone()[0])


def assign_group(conn: sqlite3.Connection, actor_id: int, facility_id: int) -> int | None:
    """The inside group he belongs to (facility_groups.id): protective custody for a man who informed; the connected men for a man with a
    seat in an organisation of the life; the street crews for a man with violence on his record and no seat; otherwise one of the
    neighbourhood groups by a stable per-man draw, or the unaligned. A group the facility does not have is skipped."""
    cfg = rules(conn)
    gcfg = cfg.get("groups") or {}
    have = {r["group_key"]: int(r["id"]) for r in conn.execute("SELECT id,group_key FROM facility_groups WHERE facility_id=?", (int(facility_id),))}

    def basis(kind: str) -> list[str]:
        return [g for g in have if (gcfg.get(g) or {}).get("basis", {}).get("kind") == kind]

    if _cooperator(conn, actor_id):
        for g in basis("protective"):
            return have[g]
    if _outside_standing(conn, actor_id) is not None:
        for g in basis("connected"):
            return have[g]
    else:
        for g in basis("street"):
            need = int(_figure((gcfg[g].get("basis") or {}).get("min_harm"), 1.0))
            n = conn.execute("SELECT COUNT(*) FROM crime_reports WHERE offender_actor_id=?", (int(actor_id),)).fetchone()[0]
            if n >= need:
                return have[g]
    draws = basis("draw")
    if draws:
        w = [max(1e-9, _figure(gcfg[g].get("share"), 1.0)) for g in draws]
        return have[_rng(conn, "group", actor_id).choices(draws, weights=w)[0]]
    for g in basis("unaligned"):
        return have[g]
    return next(iter(have.values()), None)


def _low_level(conn: sqlite3.Connection) -> int:
    from .org_lifecycle import _levels_pair
    return _levels_pair(conn)[1]


def _seat_inside(conn: sqlite3.Connection, actor_id: int, group_id: int, day: int) -> None:
    from . import orgs
    org = int(conn.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (int(group_id),)).fetchone()[0])
    standing = _outside_standing(conn, actor_id)
    standing = _figure(rules(conn).get("entry_standing"), 0.3) if standing is None else standing
    head = orgs.head_of(conn, org)
    old = orgs.seat_of(conn, actor_id, org)
    if old is not None:  # he has been in this group before: the same seat row comes back (one seat per man and organisation)
        conn.execute("UPDATE org_seats SET status='active', left_day=NULL, role_key='member', superior_actor_id=?, standing=?, joined_day=? WHERE id=?",
                     (head, standing, int(day), int(old["id"])))
        conn.execute("UPDATE institution_memberships SET status='active', left_day=NULL WHERE institution_actor_id=? AND member_actor_id=?", (org, int(actor_id)))
        return
    orgs.seat(conn, actor_id, org, "member", unit_id=None, superior_actor_id=head, level=_low_level(conn), day=int(day), standing=standing, provenance="prison")


def _facility_row(conn: sqlite3.Connection, facility_id: int):
    return conn.execute("SELECT * FROM facilities WHERE id=?", (int(facility_id),)).fetchone()


def _move(conn: sqlite3.Connection, actor_id: int, location_id, day: int) -> None:
    conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (location_id, int(actor_id)))
    conn.execute("UPDATE player_state SET current_location_id=?, updated_day=? WHERE player_actor_id=?", (location_id, int(day), int(actor_id)))


def _is_protective_group(conn: sqlite3.Connection, group_id) -> bool:
    if group_id is None:
        return False
    key = conn.execute("SELECT group_key FROM facility_groups WHERE id=?", (int(group_id),)).fetchone()[0]
    return ((rules(conn).get("groups") or {}).get(key) or {}).get("basis", {}).get("kind") == "protective"


def admit(conn: sqlite3.Connection, actor_id: int, day: int, *, sentence_id: int | None = None, case_id: int | None = None) -> int:
    """Place a man: the facility the intake rules name (remand while he awaits trial, a facility for his term once sentenced), his group,
    and, as a man of the case chain, a seat in that group. Returns the stay id. A man already inside who is sentenced stays in the
    same stay when the same facility takes him, else the old stay closes as `transferred`."""
    ensure_facilities(conn)
    sen = conn.execute("SELECT * FROM sentences WHERE id=?", (int(sentence_id),)).fetchone() if sentence_id is not None else None
    term = int(sen["term_days"]) if sen is not None else None
    fid = assign_facility(conn, actor_id, term_days=term, authority=_authority(conn, actor_id, sen), pretrial=sen is None, day=int(day))
    cur = conn.execute("SELECT * FROM inmate_stays WHERE actor_id=? AND status='inside'", (int(actor_id),)).fetchone()
    if cur is not None:
        if int(cur["facility_id"]) == fid:
            conn.execute("UPDATE inmate_stays SET sentence_id=?, case_id=COALESCE(?,case_id), until_day=? WHERE id=?",
                         (sentence_id, case_id, int(sen["end_day"]) if sen is not None else None, int(cur["id"])))
            _name_facility(conn, sen, fid)
            return int(cur["id"])
        leave(conn, int(cur["id"]), int(day), "transferred")
    fac = _facility_row(conn, fid)
    prior = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(actor_id),)).fetchone()
    came_from = prior[0] if prior is not None else None
    if cur is not None and came_from == fac["location_id"]:
        came_from = json.loads(cur["metadata_json"] or "{}").get("from_location_id")
    gid = assign_group(conn, actor_id, fid)
    stay = int(conn.execute(
        """INSERT INTO inmate_stays(actor_id,facility_id,group_id,sentence_id,case_id,since_day,until_day,status,protective,metadata_json)
           VALUES (?,?,?,?,?,?,?, 'inside', ?, ?)""",
        (int(actor_id), fid, gid, sentence_id, case_id, int(day), int(sen["end_day"]) if sen is not None else None,
         1 if _is_protective_group(conn, gid) else 0, json.dumps({"from_location_id": came_from}, sort_keys=True))).lastrowid)
    if gid is not None:
        _seat_inside(conn, actor_id, gid, int(day))
        conn.execute("UPDATE facility_groups SET headcount=headcount+1 WHERE id=?", (gid,))
    conn.execute("UPDATE facilities SET headcount=headcount+1 WHERE id=?", (fid,))
    _move(conn, actor_id, fac["location_id"], int(day))
    _name_facility(conn, sen, fid)
    return stay


def _name_facility(conn: sqlite3.Connection, sen, facility_id: int) -> None:
    if sen is not None:
        conn.execute("UPDATE sentences SET facility=? WHERE id=?", (_facility_row(conn, facility_id)["name"], int(sen["id"])))


def leave(conn: sqlite3.Connection, stay_id: int, day: int, status: str) -> None:
    """Close a stay (`released`, `bailed`, `transferred`, `escaped`, `dead`): the inside seat goes out, the headcounts fall, and he goes back
    to where he was (or home) unless he died or is moving to another facility."""
    st = conn.execute("SELECT * FROM inmate_stays WHERE id=?", (int(stay_id),)).fetchone()
    if st is None or st["status"] != "inside":
        return
    conn.execute("UPDATE inmate_stays SET status=?, until_day=? WHERE id=?", (status, int(day), int(stay_id)))
    a = int(st["actor_id"])
    if st["group_id"] is not None:
        org = conn.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (int(st["group_id"]),)).fetchone()[0]
        conn.execute("UPDATE org_seats SET status='out', left_day=? WHERE actor_id=? AND org_actor_id=? AND status IN ('active','held')", (int(day), a, int(org)))
        conn.execute("UPDATE institution_memberships SET status='former', left_day=? WHERE institution_actor_id=? AND member_actor_id=?", (int(day), int(org), a))
        conn.execute("UPDATE facility_groups SET headcount=headcount-1 WHERE id=?", (int(st["group_id"]),))
    conn.execute("UPDATE facilities SET headcount=headcount-1 WHERE id=?", (int(st["facility_id"]),))
    if status not in ("dead", "transferred"):
        try:
            back = json.loads(st["metadata_json"] or "{}").get("from_location_id")
        except (ValueError, TypeError):
            back = None
        if back is None or conn.execute("SELECT 1 FROM facilities WHERE location_id=?", (back,)).fetchone():
            back = conn.execute("SELECT home_location_id FROM actors WHERE id=?", (a,)).fetchone()[0]
        _move(conn, a, back, int(day))


# ---- the process ----

def _living(conn: sqlite3.Connection, actor_id: int) -> bool:
    from . import orgs
    return orgs.is_living(conn, int(actor_id))


def _unplaced(conn: sqlite3.Connection) -> list:
    """Sentences being served and men held for a case, with no stay (sentence rows first; a man held for trial is a custody row)."""
    out: list = []
    for s in conn.execute("""SELECT * FROM sentences s WHERE s.status='serving'
                             AND NOT EXISTS (SELECT 1 FROM inmate_stays t WHERE t.sentence_id=s.id AND t.status='inside') ORDER BY s.id""").fetchall():
        out.append(("sentence", s))
    for c in conn.execute("""SELECT * FROM custody c WHERE c.kind='held' AND c.case_id IS NOT NULL
                             AND NOT EXISTS (SELECT 1 FROM inmate_stays t WHERE t.actor_id=c.actor_id AND t.status='inside')
                             AND NOT EXISTS (SELECT 1 FROM sentences s WHERE s.actor_id=c.actor_id AND s.status='serving') ORDER BY c.id""").fetchall():
        out.append(("remand", c))
    return out


def _admissions(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    for kind, row in _unplaced(conn):
        a = int(row["actor_id"])
        if not _living(conn, a):
            continue
        if kind == "sentence":
            admit(conn, a, int(day), sentence_id=int(row["id"]), case_id=row["case_id"])
        else:
            admit(conn, a, int(day), case_id=int(row["case_id"]))
        n += 1
    return n


def _departures(conn: sqlite3.Connection, day: int) -> int:
    """A stay ends when the man is no longer held: bailed, released, or dead."""
    n = 0
    for st in conn.execute("SELECT * FROM inmate_stays WHERE status='inside' ORDER BY id").fetchall():
        a = int(st["actor_id"])
        if not _living(conn, a):
            leave(conn, int(st["id"]), int(day), "dead")
            n += 1
            continue
        if conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' LIMIT 1", (a,)).fetchone() is not None:
            continue
        last = conn.execute("SELECT kind FROM custody WHERE actor_id=? ORDER BY id DESC LIMIT 1", (a,)).fetchone()
        leave(conn, int(st["id"]), int(day), "bailed" if last is not None and last[0] == "bailed" else "released")
        n += 1
    return n


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    if not enabled(conn):
        return {}
    ensure_facilities(conn)
    out = {"admitted": _admissions(conn, int(day))}
    out["left"] = _departures(conn, int(day))
    return out


def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    """Tomorrow when a man is held and unplaced, or placed and no longer held; otherwise nothing is due."""
    try:
        if not enabled(conn):
            return None
        ensure_tables(conn)
        d = int(after_day) + 1
        if d > int(end_day):
            return None
        if _unplaced(conn) or conn.execute("""SELECT 1 FROM inmate_stays t WHERE t.status='inside'
                                              AND NOT EXISTS (SELECT 1 FROM custody c WHERE c.actor_id=t.actor_id AND c.kind='held') LIMIT 1""").fetchone():
            return d
        return None
    except sqlite3.OperationalError:
        return None
