"""Prison (J1): facilities as places, the men inside them, and the groups they belong to.

Sphere-free. A facility is a package-data institution (`prison.json` "facilities"): level, security, who it takes, a headcount and
character figures that drift. Each facility has inside groups (`facility_groups`), each an org-core organisation of the data's society
kind whose seats exist only for notable inmates; everyone else is a headcount. The case chain (`crime_response`: report, case, arrest,
bail, disposition, `sentences`, `custody`) is unchanged and stays the only writer of `custody`; this layer sits beside it, places a man
(`inmate_stays`), and from J1.2 owns his release. Every figure is a Design proposal in the package data, never a cap.
"""
from __future__ import annotations

import json
import math
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
WEEK_KEY = "prison_last_week"


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
    if cur is not None and sen is not None and cur["sentence_id"] is not None:  # already serving one: this sentence runs with it
        conn.execute("UPDATE inmate_stays SET until_day=MAX(COALESCE(until_day,0),?) WHERE id=?", (int(sen["end_day"]), int(cur["id"])))
        _mark(conn, sen, int(cur["id"]))
        _name_facility(conn, sen, int(cur["facility_id"]))
        return int(cur["id"])
    if cur is not None:
        if int(cur["facility_id"]) == fid:
            conn.execute("UPDATE inmate_stays SET sentence_id=?, case_id=COALESCE(?,case_id), until_day=? WHERE id=?",
                         (sentence_id, case_id, int(sen["end_day"]) if sen is not None else None, int(cur["id"])))
            _mark(conn, sen, int(cur["id"]))
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
    _mark(conn, sen, stay)
    _name_facility(conn, sen, fid)
    return stay


def _mark(conn: sqlite3.Connection, sen, stay_id: int) -> None:
    """The sentence has been placed: its row says which stay holds it."""
    if sen is not None:
        conn.execute("UPDATE sentences SET metadata_json=json_set(COALESCE(metadata_json,'{}'),'$.stay_id',?) WHERE id=?", (int(stay_id), int(sen["id"])))


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
    conn.execute("UPDATE prison_channels SET status='closed' WHERE stay_id=? AND status='open'", (int(stay_id),))
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
    for s in conn.execute("""SELECT * FROM sentences s WHERE s.status='serving' AND json_extract(s.metadata_json,'$.stay_id') IS NULL ORDER BY s.id""").fetchall():
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
    cadence = int(rules(conn).get("cadence_days") or 7)
    cur = conn.execute("SELECT value FROM engine_meta WHERE key=?", (WEEK_KEY,)).fetchone()
    if cur is None:
        conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?)", (WEEK_KEY, str(int(day))))
    elif int(day) - int(cur[0]) >= cadence:
        conn.execute("UPDATE engine_meta SET value=? WHERE key=?", (str(int(day)), WEEK_KEY))
        out.update(weekly(conn, int(day)))
        from . import prison_channels
        out["channels"] = prison_channels.weekly(conn, int(day))
        out["outside"] = carry_on(conn, int(day))
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
        if conn.execute("SELECT 1 FROM inmate_stays WHERE status='inside' LIMIT 1").fetchone() is None:
            return None
        cur = conn.execute("SELECT value FROM engine_meta WHERE key=?", (WEEK_KEY,)).fetchone()
        due = (int(cur[0]) if cur else int(after_day)) + int(rules(conn).get("cadence_days") or 7)
        return max(d, due) if max(d, due) <= int(end_day) else None
    except sqlite3.OperationalError:
        return None


# ---- the inside week ----

def _wk(conn: sqlite3.Connection) -> dict:
    return rules(conn).get("week") or {}


def facility_state(conn: sqlite3.Connection, fac) -> dict:
    """Crowding, violence, corruption and contraband now: the facility's base figures bent by how full it is. Stored back on the row."""
    base = (rules(conn)["facilities"].get(fac["key"]) or {}).get("character") or {}
    cr = _wk(conn).get("crowding") or {}
    crowd = float(fac["headcount"]) / float(fac["capacity"]) if int(fac["capacity"] or 0) > 0 else 1.0
    bend = crowd - 1.0
    state = {"crowding": round(crowd, 4),
             "violence": float(base.get("violence", 0.0)) * (1.0 + _figure(cr.get("violence_gain"), 0.0) * bend),
             "corruption": float(base.get("corruption", 0.0)) * (1.0 + _figure(cr.get("corruption_gain"), 0.0) * bend),
             "contraband": float(base.get("contraband", 0.0))}
    state = {k: max(0.0, v) for k, v in state.items()}  # a facility cannot have less than none of anything
    conn.execute("UPDATE facilities SET character_json=? WHERE id=?", (json.dumps(state, sort_keys=True), int(fac["id"])))
    return state


def _outside_orgs(conn: sqlite3.Connection, actor_id: int) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        """SELECT s.org_actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
           WHERE s.actor_id=? AND s.status IN ('active','held') AND p.sphere<>'prison'""", (int(actor_id),))]


def _event(conn: sqlite3.Connection, day: int, fac_id: int, kind: str, actor=None, other=None, severity: float = 0.0, summary: str = "") -> int:
    return int(conn.execute("INSERT INTO prison_events(day,facility_id,actor_id,other_actor_id,kind,severity,summary) VALUES (?,?,?,?,?,?,?)",
                            (int(day), int(fac_id), actor, other, kind, float(severity), summary)).lastrowid)


def _name(conn: sqlite3.Connection, actor_id) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(actor_id),)).fetchone()
    return str(r[0]) if r is not None else "someone"


def _heat_between(conn: sqlite3.Connection, orgs_a: list[int], orgs_b: list[int], day: int) -> float:
    from . import org_tension
    best = 0.0
    for x in orgs_a:
        for y in orgs_b:
            if x != y:
                best = max(best, org_tension.heat(conn, x, y, int(day)), org_tension.heat(conn, y, x, int(day)))
    return best


def _fights(conn: sqlite3.Connection, day: int, fac, men: list, state: dict) -> int:
    """A named man is in a fight or an infraction by a weighed chance (the facility's violence); the other man is one of the named men
    drawn by how his group and his outfit stand to the first (rival outfits meet far more often than strangers) or an unnamed one. A serious
    fight is recorded as harm with an offender, so the law's chain takes it like any crime; the rest go on his conduct record."""
    from .harm import record_harm
    cfg = _wk(conn).get("fight") or {}
    if not cfg:
        return 0
    rate, same_w = _figure(cfg["rate"]), _figure(cfg["same_group_weight"])
    tscale, unnamed, serious = _figure(cfg["tension_scale"]), _figure(cfg["unnamed_share"]), _figure(cfg["serious_share"])
    lo, hi = float(cfg["severity"]["low"]), float(cfg["severity"]["high"])
    methods = {k: float(v) for k, v in cfg["methods"].items() if k != "why"}
    orgs_of = {int(st["actor_id"]): _outside_orgs(conn, int(st["actor_id"])) for st in men}
    n = 0
    p_any = 1.0 - math.exp(-rate * state["violence"])
    for st in men:
        a = int(st["actor_id"])
        rng = _rng(conn, "fight", f"{day}:{a}")
        if rng.random() >= p_any or not _living(conn, a):
            continue
        others = [s2 for s2 in men if int(s2["actor_id"]) != a and _living(conn, int(s2["actor_id"]))]
        b = None
        if others and rng.random() >= unnamed:
            w = [(same_w if s2["group_id"] == st["group_id"] else 1.0) * (1.0 + tscale * _heat_between(conn, orgs_of[a], orgs_of[int(s2["actor_id"])], day)) for s2 in others]
            b = int(rng.choices(others, weights=w)[0]["actor_id"])
        started = rng.random() < _figure(cfg["offender_share"])
        offender, victim = (a, b) if started else (b, a)
        hard = rng.random() < serious
        sev = lo + rng.random() * (hi - lo)
        method = rng.choices(sorted(methods), weights=[methods[k] for k in sorted(methods)])[0]
        eid = _event(conn, day, int(fac["id"]), "fight", a, b, sev if hard else 0.0, f"{_name(conn, a)} in a fight")
        if offender is not None:
            _event(conn, day, int(fac["id"]), "infraction", offender, victim, sev if hard else 0.0, f"{_name(conn, offender)} started a fight")
        n += 1
        if hard and victim is not None and _living(conn, victim):
            meta = {"public": False}
            if offender is not None:
                meta["offender_actor_id"] = offender
            record_harm(conn, victim, source_kind="prison_fight", source_ref_id=eid, severity=sev, intent_class="hostile", method=method,
                        location_id=fac["location_id"], metadata=meta)
    return n


def _economy(conn: sqlite3.Connection, day: int, men: list) -> int:
    """Dues to the group's shot caller and the commissary, from each man's own purse; a man who pays gains standing in his group, one who
    cannot pay loses it."""
    from . import ledger, orgs
    cfg = _wk(conn).get("economy") or {}
    if not cfg:
        return 0
    dues, shop = _figure(cfg["dues_weekly"]), _figure(cfg["commissary_weekly"])
    gain, loss = _figure(cfg["paid_gain"]), _figure(cfg["unpaid_loss"])
    paying = set(cfg.get("dues_groups") or [])
    n = 0
    for st in men:
        a = int(st["actor_id"])
        if st["group_id"] is None:
            continue
        g = conn.execute("SELECT group_key,org_actor_id FROM facility_groups WHERE id=?", (int(st["group_id"]),)).fetchone()
        head = orgs.head_of(conn, int(g["org_actor_id"]))
        try:
            if shop > 0 and ledger.balance(conn, ("person", a)) > 0:
                ledger.spend(conn, ("person", a), shop, purpose="the commissary", allow_partial=True)
            if g["group_key"] in paying and head is not None and head != a:
                paid = ledger.transfer(conn, ("person", a), ("person", head), dues, flow_kind=str(cfg.get("flow_kind") or "other"), purpose="dues inside", allow_partial=True)
                ok = paid >= dues - 1e-6
                conn.execute("UPDATE org_seats SET standing=standing + ? * (1.0 - standing) WHERE actor_id=? AND org_actor_id=?", (gain, a, int(g["org_actor_id"]))) if ok else \
                    conn.execute("UPDATE org_seats SET standing=standing * (1.0 - ?) WHERE actor_id=? AND org_actor_id=?", (loss, a, int(g["org_actor_id"])))
                n += 1
        except (ValueError, KeyError):
            continue
    return n


def _regroup(conn: sqlite3.Connection, st, group_key: str, day: int, standing_loss: float) -> bool:
    """Move a man from his group to another of the same facility (protective custody for a man who talked): his standing in the old
    group is cut, the old seat goes out, and he takes a seat in the new one."""
    new = conn.execute("SELECT id,org_actor_id FROM facility_groups WHERE facility_id=? AND group_key=?", (int(st["facility_id"]), group_key)).fetchone()
    if new is None or st["group_id"] == new["id"]:
        return False
    a = int(st["actor_id"])
    old = conn.execute("SELECT org_actor_id FROM facility_groups WHERE id=?", (int(st["group_id"]),)).fetchone() if st["group_id"] is not None else None
    if old is not None:
        conn.execute("UPDATE org_seats SET standing=standing * (1.0 - ?), status='out', left_day=? WHERE actor_id=? AND org_actor_id=? AND status IN ('active','held')",
                     (standing_loss, int(day), a, int(old["org_actor_id"])))
        conn.execute("UPDATE institution_memberships SET status='former', left_day=? WHERE institution_actor_id=? AND member_actor_id=?", (int(day), int(old["org_actor_id"]), a))
        conn.execute("UPDATE facility_groups SET headcount=headcount-1 WHERE id=?", (int(st["group_id"]),))
    conn.execute("UPDATE inmate_stays SET group_id=?, protective=1 WHERE id=?", (int(new["id"]), int(st["id"])))
    _seat_inside(conn, a, int(new["id"]), int(day))
    conn.execute("UPDATE facility_groups SET headcount=headcount+1 WHERE id=?", (int(new["id"]),))
    return True


def _informers(conn: sqlite3.Connection, day: int, men: list) -> int:
    """A man found to have informed while he is inside loses his place in his group and goes to protective custody."""
    from . import org_informing
    cfg = _wk(conn).get("informing") or {}
    n = 0
    for st in men:
        if int(st["protective"]):
            continue
        a = int(st["actor_id"])
        if not org_informing.is_informer(conn, a) or _rng(conn, "found", f"{day}:{a}").random() >= _figure(cfg.get("found_rate"), 0.0):
            continue
        for g, spec in (rules(conn).get("groups") or {}).items():
            if (spec.get("basis") or {}).get("kind") == "protective" and _regroup(conn, st, g, int(day), _figure(cfg.get("standing_loss"), 0.0)):
                _event(conn, day, int(st["facility_id"]), "protective", a, None, 0.0, f"{_name(conn, a)} went into protective custody")
                n += 1
                break
    return n


def _escapes(conn: sqlite3.Connection, day: int, fac, men: list, state: dict) -> int:
    from .crime_response import open_report
    from .orgs import imposed
    cfg = _wk(conn).get("escape") or {}
    if not cfg:
        return 0
    sec = float((cfg.get("security") or {}).get(fac["security"], 1.0))
    p = _figure(cfg["rate"]) * sec * (1.0 + _figure(cfg["corruption_gain"]) * state["corruption"])
    n = 0
    for st in men:
        a = int(st["actor_id"])
        if _rng(conn, "escape", f"{day}:{a}").random() >= p or not _living(conn, a):
            continue
        leave(conn, int(st["id"]), int(day), "escaped")
        conn.execute("UPDATE sentences SET status='escaped', released_day=? WHERE actor_id=? AND status='serving'", (int(day), a))
        conn.execute("UPDATE custody SET kind='released', until_day=? WHERE actor_id=? AND kind='held'", (int(day), a))
        imposed(conn, a)
        _event(conn, day, int(fac["id"]), "escape", a, None, 1.0, f"{_name(conn, a)} got out")
        open_report(conn, crime_kind=str(cfg.get("crime_kind") or "escape"), day=int(day), offender_actor_id=a, location_id=fac["location_id"], public=True)
        n += 1
    return n


def _contraband(conn: sqlite3.Connection, day: int, fac, men: list, state: dict) -> int:
    cfg = _wk(conn).get("contraband") or {}
    if not cfg:
        return 0
    rng = _rng(conn, "contraband", f"{day}:{fac['id']}")
    if rng.random() >= 1.0 - math.exp(-_figure(cfg["rate"]) * state["contraband"] * (1.0 + state["corruption"])):
        return 0
    caught = None
    if men and rng.random() < _figure(cfg["caught_share"]):
        caught = int(rng.choice(men)["actor_id"])
    _event(conn, day, int(fac["id"]), "contraband", caught, None, 0.0, "contraband turned up" if caught is None else f"{_name(conn, caught)} was caught with contraband")
    return 1


def _heads(conn: sqlite3.Connection, day: int, fac_id: int) -> int:
    """A group that has men and has never had a shot caller gets one: the man of highest standing in it. (Once a group has had one, the
    org core's own succession fills the seat when it falls vacant.)"""
    n = 0
    for g in conn.execute("SELECT * FROM facility_groups WHERE facility_id=?", (int(fac_id),)).fetchall():
        org = int(g["org_actor_id"])
        head_role = (__import__("engine.orgs", fromlist=["kind_rules"]).kind_rules(conn, org) or {}).get("head")
        if not head_role or conn.execute("SELECT 1 FROM org_seats WHERE org_actor_id=? AND role_key=? LIMIT 1", (org, head_role)).fetchone():
            continue
        top = conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY standing DESC, actor_id LIMIT 1", (org,)).fetchone()
        if top is None:
            continue
        a = int(top[0])
        conn.execute("UPDATE org_seats SET role_key=?, superior_actor_id=NULL WHERE actor_id=? AND org_actor_id=?", (head_role, a, org))
        conn.execute("UPDATE org_seats SET superior_actor_id=? WHERE org_actor_id=? AND actor_id<>? AND status='active'", (a, org, a))
        _event(conn, day, int(fac_id), "shot_caller", a, None, 0.0, f"{_name(conn, a)} took the lead of {_name(conn, org)}")
        n += 1
    return n


def weekly(conn: sqlite3.Connection, day: int) -> dict:
    """One inside week for every facility: its state, the fights, the economy, men who talked, escapes, contraband, and the lead of each group.
    The work is per facility and per named man, never per member of the headcount."""
    out = {"fights": 0, "paid": 0, "protected": 0, "escapes": 0, "contraband": 0, "heads": 0}
    by_fac: dict[int, list] = {}
    for st in conn.execute("SELECT * FROM inmate_stays WHERE status='inside' ORDER BY id").fetchall():
        by_fac.setdefault(int(st["facility_id"]), []).append(st)
    for fac in conn.execute("SELECT * FROM facilities WHERE status='open' ORDER BY id").fetchall():
        men = by_fac.get(int(fac["id"]), [])
        state = facility_state(conn, fac)
        out["heads"] += _heads(conn, int(day), int(fac["id"]))
        if not men:
            continue
        out["fights"] += _fights(conn, int(day), fac, men, state)
        out["paid"] += _economy(conn, int(day), men)
        out["protected"] += _informers(conn, int(day), men)
        out["escapes"] += _escapes(conn, int(day), fac, men, state)
        out["contraband"] += _contraband(conn, int(day), fac, men, state)
    return out


# ---- the outside carries on ----

def _household(conn: sqlite3.Connection, actor_id: int):
    """The household a man belongs to (its id), where he has one with someone else in it."""
    r = conn.execute("""SELECT m.household_id FROM household_members m WHERE m.actor_id=? AND m.status IN ('active','absent')
                        AND EXISTS (SELECT 1 FROM household_members o WHERE o.household_id=m.household_id AND o.actor_id<>m.actor_id AND o.status='active')
                        ORDER BY m.household_id LIMIT 1""", (int(actor_id),)).fetchone()
    return int(r[0]) if r else None


def family_need(conn: sqlite3.Connection, actor_id: int, day: int) -> float:
    """How far his people are going without while he is held, 0..1: nothing when he has no household or the data has none, and
    otherwise exp(-savings / (cover weeks x weekly need)), so an empty household is at 1 and savings that last long are near 0. Read by
    the weighing of a man held on whether to talk."""
    cfg = rules(conn).get("outside") or {}
    if not cfg or conn.execute("SELECT 1 FROM sqlite_master WHERE name='inmate_stays'").fetchone() is None:
        return 0.0
    if conn.execute("SELECT 1 FROM inmate_stays WHERE actor_id=? AND status='inside' LIMIT 1", (int(actor_id),)).fetchone() is None:
        return 0.0
    hh = _household(conn, actor_id)
    if hh is None:
        return 0.0
    have = conn.execute("SELECT liquidity FROM households WHERE id=?", (hh,)).fetchone()
    cover = _figure(cfg["need_weekly"]) * _figure(cfg["cover_weeks"])
    return math.exp(-float(have[0] if have else 0.0) / cover) if cover > 0 else 0.0


def carry_on(conn: sqlite3.Connection, day: int) -> dict:
    """The week outside for each man inside: his seat outside (the org core keeps it, the weighing in `_held_decisions` reads his grip)
    loses standing by the share of silence (`decay_weekly` x (1 - grip)); and the head of that outfit pays his household an envelope,
    which shrinks with the weeks he has been held and with his standing, never a fixed sum."""
    from . import ledger, org_money, orgs, prison_channels
    cfg = rules(conn).get("outside") or {}
    out = {"standing": 0, "envelope": 0}
    if not cfg:
        return out
    decay, base, half = _figure(cfg["decay_weekly"]), _figure(cfg["envelope_weekly"]), _figure(cfg["envelope_halflife_weeks"])
    for st in conn.execute("SELECT * FROM inmate_stays WHERE status='inside' ORDER BY id").fetchall():
        a = int(st["actor_id"])
        grip = prison_channels.channel_grip(conn, a)
        weeks = max(0.0, (int(day) - int(st["since_day"])) / 7.0)
        for s in conn.execute("""SELECT s.* FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id
                                 WHERE s.actor_id=? AND s.status IN ('active','held') AND p.sphere<>'prison' ORDER BY s.id""", (a,)).fetchall():
            org = int(s["org_actor_id"])
            conn.execute("UPDATE org_seats SET standing=standing * (1.0 - ? * (1.0 - ?)) WHERE id=?", (decay, grip, int(s["id"])))
            out["standing"] += 1
            head = orgs.head_of(conn, org)
            ref = org_money.purse_ref(conn, org)
            hh = _household(conn, a)
            if head is None or head == a or ref is None or hh is None:
                continue
            amount = base * float(s["standing"]) * math.pow(0.5, weeks / half)
            if amount < _figure(cfg.get("envelope_floor"), 0.0):
                continue
            paid = ledger.transfer(conn, ledger.parse_holder(ref, a), ("household", hh), amount, flow_kind=str(cfg.get("flow_kind") or "support"),
                                   purpose="the outfit looks after a man's family while he is held", allow_partial=True)
            if paid > 0:
                out["envelope"] += 1
    return out
