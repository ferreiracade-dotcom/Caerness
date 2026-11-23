"""Crime brings a law response (task B13): reports, publicity, cases, the arrangements' reach, arrests, dispositions and sentences.

Sphere-free. A crime is a `crime_reports` row (a harm row that someone could report, or a later sphere's own filing through
`open_report`: bribery, fraud, bid-rigging). Every figure comes from the package's law data (`law.json` "response"), each a Design
proposal with its reasoning; a logistic term there is a weighed pressure, never a threshold, and no outcome has a fixed share.

The chain: report -> `public_attention` (the weighed publicity, 0..100, a starting value the information layer will later move) ->
a case at the agency that takes the matter (and at the federal one when the victim is an officer) -> evidence -> the case officer and
the arrangements' reach (`org_arrangements` read where the offender is the payer or sits in the paying organisation) -> buried, an
arrest (`custody`), or open and reviewed -> bail -> a disposition (dismissed, plea, trial verdict) weighed from the evidence, a lawyer,
money, witness pressure and the arrangements -> on a conviction a `sentences` row and the man held until his scheduled release day,
which returns him. The organisations answer an arrest through `orgs` (his unit leader and head in every organisation where he sits
a seat get a `member_arrested` agenda item) and through the held-man decisions of the lifecycle process. Prison phase 1 will replace
the minimal disposition chain; the record shapes here are generic so it can extend them.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3

from . import orgs, org_motives
from .design import figure, run_seed
from .law_opening import agency_for
from .orgs import add_agenda, imposed, resolve_agenda
from .org_choices import register_agenda_action, register_executor
from .world_package import law_rules, package_for

DDL = """
CREATE TABLE IF NOT EXISTS public_attention (
    report_id INTEGER PRIMARY KEY REFERENCES crime_reports(id) ON DELETE CASCADE,
    publicity REAL NOT NULL,
    loudness REAL NOT NULL,
    audience_json TEXT NOT NULL DEFAULT '{}',
    updated_day INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS case_dispositions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    report_id INTEGER,
    actor_id INTEGER,
    day INTEGER NOT NULL,
    kind TEXT NOT NULL,
    factors_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS sentences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER NOT NULL REFERENCES actors(id),
    case_id INTEGER,
    report_id INTEGER,
    disposition_id INTEGER,
    crime_kind TEXT NOT NULL,
    victim_actor_id INTEGER,
    location_id INTEGER,
    term_days INTEGER NOT NULL,
    start_day INTEGER NOT NULL,
    earliest_release_day INTEGER NOT NULL,
    end_day INTEGER NOT NULL,
    facility TEXT,
    status TEXT NOT NULL DEFAULT 'serving',
    released_day INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sentences_release ON sentences(status, earliest_release_day);
CREATE INDEX IF NOT EXISTS idx_sentences_actor ON sentences(actor_id, status);
CREATE INDEX IF NOT EXISTS idx_case_dispositions_case ON case_dispositions(case_id);
"""

CURSOR_KEY = "crime_response_harm_cursor"
_READY: dict = {"key": None}


def ensure_tables(conn: sqlite3.Connection) -> None:
    """The three tables this layer adds (also created by the schema; a no-op once they exist)."""
    key = org_motives.db_key(conn)
    if _READY["key"] != key:
        fresh = conn.execute("SELECT 1 FROM engine_meta WHERE key=?", (CURSOR_KEY,)).fetchone() is None  # the tables come with the schema, so the cursor says whether this layer has run here
        for stmt in DDL.split(";"):  # not executescript: that commits, and a time skip is running inside a savepoint
            if stmt.strip():
                conn.execute(stmt)
        if fresh:  # a campaign that predates this layer: what was already done is not prosecuted after the fact
            conn.execute("INSERT INTO engine_meta(key,value) VALUES (?, CAST((SELECT COALESCE(MAX(id),0) FROM harm_incidents WHERE day < (SELECT current_day FROM world_state WHERE id=1)) AS TEXT)) ON CONFLICT(key) DO NOTHING", (CURSOR_KEY,))
        _READY["key"] = key


# ---- data ----

def _cfg(conn: sqlite3.Connection) -> dict:
    return law_rules(package_for(conn)).get("response") or {}


def _n(spec, default: float | None = None) -> float:
    """A number as written, or `{"value": n, ...}` with its reasoning."""
    if isinstance(spec, dict):
        spec = spec.get("value")
    if spec is None:
        if default is None:
            raise KeyError("a figure the law data should give is missing")
        return float(default)
    return float(spec)


def _rng(conn: sqlite3.Connection, stream: str, key) -> random.Random:
    return random.Random(f"{run_seed(conn)}:crime:{stream}:{key}")


def _meta(row) -> dict:
    try:
        return json.loads(row["metadata_json"] or "{}")
    except (ValueError, TypeError):
        return {}


def _logit(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _name(conn: sqlite3.Connection, actor_id) -> str:
    r = conn.execute("SELECT name FROM actors WHERE id=?", (int(actor_id),)).fetchone() if actor_id is not None else None
    return str(r[0]) if r else "someone"


def _living(conn: sqlite3.Connection, actor_id) -> bool:
    return actor_id is not None and orgs.is_living(conn, int(actor_id))


def _orgs_of(conn: sqlite3.Connection, actor_id) -> list[int]:
    if actor_id is None:
        return []
    return sorted({int(s["org_actor_id"]) for s in orgs.seats_of(conn, int(actor_id)) if s["status"] in ("active", "held")})


# ---- who is who in the law's eyes ----

def _police_institutions(conn: sqlite3.Connection) -> set[int]:
    return {int(r[0]) for r in conn.execute("SELECT institution_actor_id FROM law_enforcement_profiles WHERE institution_actor_id IS NOT NULL")}


def is_officer(conn: sqlite3.Connection, actor_id) -> bool:
    """A member of any institution that a law enforcement profile stands for."""
    if actor_id is None:
        return False
    return conn.execute(
        """SELECT 1 FROM institution_memberships m JOIN law_enforcement_profiles p ON p.institution_actor_id=m.institution_actor_id
           WHERE m.member_actor_id=? AND m.status='active' LIMIT 1""", (int(actor_id),)).fetchone() is not None


def _notable(conn: sqlite3.Connection, victim, spec: dict) -> tuple[float, str | None]:
    """How notable the victim is (0..1: the largest of the kinds he is) and which kind."""
    best, which = 0.0, None
    if victim is None:
        return best, which
    for key, k in sorted(spec.items()):
        x = _n(k.get("x"), 0.0)
        if x <= best:
            continue
        hit = False
        if key == "officer":
            hit = is_officer(conn, victim)
        elif key == "reporter":
            names = list(k.get("institutions") or [])
            if names:
                hit = conn.execute(
                    "SELECT 1 FROM institution_memberships m JOIN actors i ON i.id=m.institution_actor_id WHERE m.member_actor_id=? AND m.status='active' AND i.name IN (%s) LIMIT 1"
                    % ",".join("?" * len(names)), (int(victim), *names)).fetchone() is not None
        elif key == "office_holder":
            hit = conn.execute("SELECT 1 FROM world_facts WHERE holder_actor_id=? AND key LIKE ? LIMIT 1", (int(victim), str(k.get("fact_prefix") or "") + "%")).fetchone() is not None
        elif key == "inducted":
            hit = conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND inducted_day IS NOT NULL LIMIT 1", (int(victim),)).fetchone() is not None
        if hit:
            best, which = x, key
    return best, which


# ---- publicity ----

def _publicity(conn: sqlite3.Connection, *, key, victim, location_id, declared_public: bool, meta: dict, victims_n: int, bystander: bool) -> dict:
    pc = _cfg(conn).get("publicity") or {}
    if not pc:
        return {"publicity": 100.0 if declared_public else 0.0, "drivers": {}, "witnesses": 0}
    w = pc["weights"]
    rng = _rng(conn, "publicity", key)
    kind = None
    if location_id is not None:
        r = conn.execute("SELECT kind FROM locations WHERE id=?", (int(location_id),)).fetchone()
        kind = r[0] if r else None
    hour = meta.get("hour")
    if hour is None:
        hour = rng.choices(range(len(pc["hour_weights"])), weights=pc["hour_weights"])[0]
    hour = int(hour) % len(pc["hour_exposure"])
    traffic = float(pc["hour_exposure"][hour])
    crowd = float(pc["place_crowd"].get(kind, pc["place_crowd"]["default"]))
    seen = _poisson(rng, crowd * traffic)
    notable, notable_kind = _notable(conn, victim, pc.get("notable") or {})
    method = meta.get("method")
    x = {
        "declared_public": 1.0 if declared_public else 0.0,
        "witnesses": 1.0 - math.exp(-seen / float(pc["witness_scale"])),
        "place": float(pc["place_exposure"].get(kind, pc["place_exposure"]["default"])),
        "time_of_day": traffic,
        "bystander": 1.0 if bystander else 0.0,
        "notable_victim": notable,
        "method": float(pc["method"].get(method, pc["method"]["default"])),
        "victims": 1.0 - math.exp(-max(0, victims_n - 1) / float(pc["victims_scale"])),
    }
    rest = 1.0
    for name, xi in x.items():
        rest *= 1.0 - _n(w.get(name), 0.0) * xi
    return {"publicity": round(100.0 * (1.0 - rest), 3), "drivers": {k: round(v, 4) for k, v in x.items()}, "witnesses": seen, "hour": hour,
            "place_kind": kind, "notable_kind": notable_kind, "officer_victim": notable_kind == "officer"}


def publicity_of(conn: sqlite3.Connection, report_id: int) -> float:
    """The report's publicity, 0..100: the public attention record's loudness when there is one (the information layer may have moved
    it), else the starting value in the report's metadata, else 0."""
    ensure_tables(conn)
    r = conn.execute("SELECT loudness FROM public_attention WHERE report_id=?", (int(report_id),)).fetchone()
    if r is not None:
        return float(r[0])
    r = conn.execute("SELECT metadata_json FROM crime_reports WHERE id=?", (int(report_id),)).fetchone()
    return float(_meta(r).get("publicity") or 0.0) if r is not None else 0.0


# ---- filing a report ----

def open_report(conn: sqlite3.Connection, *, crime_kind: str, day: int, offender_actor_id: int | None = None, victim_actor_id: int | None = None,
                location_id: int | None = None, public: bool = False, metadata: dict | None = None) -> int:
    """File a crime and run the law's first response to it (a case at the agency that takes this kind of matter, evidence, the
    arrangements' reach, an arrest or an open case). Later spheres call this for fraud, bribery and bid-rigging with no harm row."""
    ensure_tables(conn)
    meta = dict(metadata or {})
    harm_id = meta.get("harm_incident_id")
    if location_id is None and victim_actor_id is not None:
        r = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(victim_actor_id),)).fetchone()
        location_id = r[0] if r else None
    key = f"{harm_id}" if harm_id is not None else f"{crime_kind}:{day}:{offender_actor_id}:{victim_actor_id}:{location_id}"
    pub = _publicity(conn, key=key, victim=victim_actor_id, location_id=location_id, declared_public=bool(public), meta=meta,
                     victims_n=int(meta.get("victims") or 1), bystander=bool(meta.get("bystander")))
    meta.update(publicity=pub["publicity"], publicity_drivers=pub["drivers"], witnesses=pub["witnesses"], hour=pub.get("hour"),
                notable_victim=pub.get("notable_victim") or pub.get("notable_kind"), officer_victim=bool(pub.get("officer_victim")))
    if offender_actor_id is not None and harm_id is not None and "identified" not in meta and _cfg(conn).get("identification"):
        meta["identified"] = _identified_at_filing(conn, int(harm_id), int(day), offender_actor_id, victim_actor_id, pub)
    rid = int(conn.execute(
        """INSERT INTO crime_reports(day,harm_incident_id,crime_kind,location_id,victim_actor_id,offender_actor_id,public,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,'open',?)""",
        (int(day), harm_id, crime_kind, location_id, victim_actor_id, offender_actor_id, 1 if public else 0, json.dumps(meta, sort_keys=True, default=str))).lastrowid)
    audience = {"witnesses": pub["witnesses"], "place": location_id, "place_kind": pub.get("place_kind"),
                "orgs": sorted(set(_orgs_of(conn, offender_actor_id)) | set(_orgs_of(conn, victim_actor_id))),
                "scope": "place" if pub["publicity"] < 50 else "city"}
    conn.execute("INSERT OR REPLACE INTO public_attention(report_id,publicity,loudness,audience_json,updated_day,metadata_json) VALUES (?,?,?,?,?,?)",
                 (rid, pub["publicity"], pub["publicity"], json.dumps(audience, sort_keys=True), int(day), json.dumps({"drivers": pub["drivers"]}, sort_keys=True)))
    _respond(conn, rid, int(day))
    return rid


def _organised(conn: sqlite3.Connection, actor_id) -> float:
    """1 when the man holds a seat in any organisation, else 0."""
    return 1.0 if _orgs_of(conn, actor_id) else 0.0


def _identified_at_filing(conn: sqlite3.Connection, harm_id: int, day: int, offender, victim, pub: dict) -> bool:
    """Whether the law has the offender's name when the crime is filed (data `identification`): the witnesses and the loudness of the
    story raise it, an organised man's work and a victim from the same world lower it."""
    c = _cfg(conn)["identification"]
    x = pub.get("drivers") or {}
    z = (_n(c["bias"]) + _n(c["witnesses"]) * float(x.get("witnesses") or 0.0) + _n(c["publicity"]) * float(pub["publicity"]) / 100.0
         + _n(c["offender_organised"]) * _organised(conn, offender) + _n(c["victim_organised"]) * _organised(conn, victim))
    return org_motives._roll(conn, harm_id, day, "identify") < _logit(z)  # drawn as the arrangements' roll is, so a test can pin it


def _knows_offender(conn: sqlite3.Connection, rep) -> bool:
    """The report names an offender the law has: no offender, or one nobody has yet put a name to, is no one."""
    if rep["offender_actor_id"] is None:
        return False
    return bool(_meta(rep).get("identified", True))


# ---- agencies, officers, the arrangements' reach ----

def _agency_rule(conn: sqlite3.Connection, profile) -> dict:
    return (law_rules(package_for(conn)).get("agencies") or {}).get(profile["profile_key"], {})


def _threshold(conn: sqlite3.Connection, kind: str) -> float:
    rules = law_rules(package_for(conn)).get("rules") or {}
    spec = (rules.get(kind) or {}).get("evidence_threshold")
    if spec is None:
        return _n(_cfg(conn)["arrest"]["evidence"]["default_threshold"])
    if isinstance(spec, (int, float, dict)):
        return _n(spec)
    return float(figure(conn, spec))


def _review_days(conn: sqlite3.Connection, kind: str) -> int:
    rules = law_rules(package_for(conn)).get("rules") or {}
    spec = (rules.get(kind) or {}).get("review_days")
    return int(_n(spec)) if spec is not None else int(figure(conn, "case_review_days"))


def _effort(conn: sqlite3.Connection, profile, pub: float, officer_victim: bool) -> float:
    e = _cfg(conn)["arrest"]["effort"]
    rest = (1.0 - _n(e["base"])) * (1.0 - _n(e["publicity"]) * pub / 100.0) * (1.0 - (_n(e["officer_victim"]) if officer_victim else 0.0))
    return float(profile["capacity"]) / 100.0 * (1.0 - rest)


def case_officer(conn: sqlite3.Connection, profile, key) -> int | None:
    """The officer who catches a case at an agency: a seeded draw among the institution's living members weighted by role."""
    inst = profile["institution_actor_id"]
    if inst is None:
        return None
    roles = _cfg(conn)["arrest"]["officer_roles"]
    pool: list[tuple[int, float]] = []
    for r in conn.execute("SELECT member_actor_id,role_text FROM institution_memberships WHERE institution_actor_id=? AND status='active' ORDER BY member_actor_id", (int(inst),)):
        wt = max((_n(x["weight"]) for x in roles if str(r["role_text"] or "").startswith(x["prefix"])), default=0.0)
        if wt > 0 and orgs.is_living(conn, int(r[0])):
            pool.append((int(r[0]), wt))
    if not pool:
        return None
    return _rng(conn, "officer", f"{profile['id']}:{key}").choices([a for a, _ in pool], weights=[w for _, w in pool])[0]


def _envelope(conn: sqlite3.Connection, officer: int, offender: int):
    """An active arrangement paid to this officer by the offender or by an organisation he sits in."""
    mine = _orgs_of(conn, offender)
    return conn.execute(
        """SELECT * FROM org_arrangements WHERE official_actor_id=? AND status='active' AND
             ((payer_kind='actor' AND payer_id=?) OR (payer_kind='org' AND payer_id IN (%s))) ORDER BY id LIMIT 1""" % (",".join("?" * len(mine)) or "NULL"),
        (int(officer), int(offender), *mine)).fetchone()


def pad_reaches(conn: sqlite3.Connection, profile, officer: int | None, offender: int | None) -> bool:
    """Whether the arrangements reach this case: the agency is one they reach and its case officer holds an envelope from the offender
    (or the organisation he sits in)."""
    if officer is None or offender is None or not _agency_rule(conn, profile).get("arrangements_reach"):
        return False
    return _envelope(conn, int(officer), int(offender)) is not None


def _bought(conn: sqlite3.Connection, profile, officer, offender, kind: str, pub: float, officer_victim: bool, rid: int, day: int) -> bool:
    """The arrangements bury a case they reach, weighed: a homicide detective may be one of the honest ones (the package's share), and
    publicity and a killed officer resist, very strongly but never absolutely."""
    if not pad_reaches(conn, profile, officer, offender):
        return False
    c = _cfg(conn)
    limits = law_rules(package_for(conn)).get("pad_limits") or {}
    if kind == c["harm"]["fatal_kind"] and limits.get("honest_homicide_figure"):
        if org_motives._roll(conn, rid, day, "honest") < float(figure(conn, limits["honest_homicide_figure"])):
            return False
    p = c["arrest"]["arrangements"]
    resist = 1.0 - (1.0 - _n(p["publicity_resistance"]) * pub / 100.0) * (1.0 - (_n(p["officer_victim_resistance"]) if officer_victim else 0.0))
    return org_motives._roll(conn, rid, day, "pad_publicity") >= resist


# ---- cases ----

def _open_case(conn: sqlite3.Connection, profile, rid: int, kind: str, offender, victim, day: int, evidence: float, officer, note: dict) -> int:
    meta = {"crime_report_id": rid, "officer": officer, "victim": victim, "crime_kind": kind, **note}
    subject = int(offender) if offender is not None else -int(rid)  # no offender known: the case is about the event, keyed by the report
    args = (int(profile["id"]), "actor", subject)
    status = "open" if offender is not None else "monitoring"
    nxt = int(day) + _review_days(conn, kind)
    last: Exception = sqlite3.IntegrityError("case could not be filed")
    for allegation in (kind, f"{kind}:{rid}"):
        try:
            return int(conn.execute(
                """INSERT INTO law_enforcement_cases(profile_id,subject_kind,subject_id,allegation_kind,evidence_score,status,opened_day,last_review_day,next_review_day,metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""", (*args, allegation, round(min(100.0, max(0.0, 100.0 * evidence)), 3), status, int(day), int(day), nxt, json.dumps(meta, sort_keys=True))).lastrowid)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" not in str(exc):
                raise
            last = exc
    raise last


def _respond(conn: sqlite3.Connection, rid: int, day: int) -> None:
    rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (rid,)).fetchone()
    meta, kind = _meta(rep), rep["crime_kind"]
    offender, victim, loc = (rep["offender_actor_id"] if _knows_offender(conn, rep) else None), rep["victim_actor_id"], rep["location_id"]
    actual = rep["offender_actor_id"]  # a paid precinct steers away from its payer before he is named: the arrangements look at the man who did it
    pub = float(meta.get("publicity") or 0.0)
    officer_victim = bool(meta.get("officer_victim"))
    primary = agency_for(conn, loc, kind)
    profiles = []
    if primary is not None:
        profiles.append(int(primary))
    if officer_victim and _cfg(conn)["arrest"].get("officer_victim_federal"):
        fed = agency_for(conn, loc, kind, federal=True)
        if fed is not None and int(fed) not in profiles:
            profiles.append(int(fed))
    if not profiles:
        meta["unrouted"] = True
        conn.execute("UPDATE crime_reports SET status='closed', metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), rid))
        return
    ev = _cfg(conn)["arrest"]["evidence"]
    rows = []
    for pid in profiles:
        prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (pid,)).fetchone()
        effort = _effort(conn, prof, pub, officer_victim)
        noise = (_rng(conn, "evidence", f"{rid}:{pid}").random() * 2.0 - 1.0) * _n(ev["noise"])
        score = _n(ev["base"]) + _n(ev["publicity"]) * pub / 100.0 + (_n(ev["offender_known"]) if offender is not None else 0.0) + _n(ev["effort"]) * effort + noise
        officer = case_officer(conn, prof, rid)
        bought = _bought(conn, prof, officer, actual, kind, pub, officer_victim, rid, day)
        cid = _open_case(conn, prof, rid, kind, offender, victim, day, score, officer,
                         {"effort": round(effort, 4), "bought": bool(bought), **({"co_defendants": meta["co_defendants"]} if meta.get("co_defendants") else {})})
        if bought:
            conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cid))
            m = json.loads(conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (cid,)).fetchone()[0])
            m["reason"] = "arrangements"
            conn.execute("UPDATE law_enforcement_cases SET metadata_json=? WHERE id=?", (json.dumps(m, sort_keys=True), cid))
        rows.append({"case": cid, "profile": prof, "score": score, "bought": bought})
    meta["case_ids"] = [r["case"] for r in rows]
    first = rows[0]
    conn.execute("UPDATE crime_reports SET jurisdiction_id=NULL, agency_profile_id=?, case_id=?, metadata_json=? WHERE id=?",
                 (int(first["profile"]["id"]), first["case"], json.dumps(meta, sort_keys=True), rid))
    if offender is not None and _living(conn, offender):
        for r in rows:
            if not r["bought"] and r["score"] >= _threshold(conn, kind):
                _arrest(conn, rid, r["case"], r["profile"], int(offender), int(day))
                return
    if rows and all(r["bought"] for r in rows):
        meta["reason"] = "arrangements"
        conn.execute("UPDATE crime_reports SET status='buried', metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), rid))


# ---- arrest, bail, disposition, sentence, release ----

def _set_case_meta(conn: sqlite3.Connection, case_id: int, **kv) -> dict:
    row = conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (int(case_id),)).fetchone()
    m = json.loads(row[0] or "{}")
    m.update(kv)
    conn.execute("UPDATE law_enforcement_cases SET metadata_json=? WHERE id=?", (json.dumps(m, sort_keys=True, default=str), int(case_id)))
    return m


def _lognormal_days(conn: sqlite3.Connection, table: dict, kind: str, stream: str, key) -> int:
    spec = table.get(kind) or table["default"]
    return max(1, int(round(_n(spec["median"]) * math.exp(_n(spec["sigma"]) * _rng(conn, stream, key).gauss(0.0, 1.0)))))


def _arrest(conn: sqlite3.Connection, rid: int, case_id: int, profile, offender: int, day: int) -> None:
    c = _cfg(conn)
    rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (rid,)).fetchone()
    kind, meta = rep["crime_kind"], _meta(rep)
    bailable = c["arrest"]["bail"]["bailable"]
    bail_day = int(day) + int(figure(conn, "bail_days")) if bailable.get(kind, bailable["default"]) else None
    dispo = int(day) + _lognormal_days(conn, c["disposition"]["days"], kind, "dispo", rid)
    conn.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held',?,?,NULL)",
                 (offender, case_id, int(profile["id"]), kind, int(day)))
    stage_day = bail_day if bail_day is not None else dispo
    with_him = []  # co-defendants on the one case: the men a sweep named with him are held on it as he is
    for co in (_meta_of_case(conn, case_id).get("co_defendants") or []):
        if int(co) != offender and _living(conn, co) and conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' AND case_id IS NOT NULL LIMIT 1", (int(co),)).fetchone() is None:
            conn.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held',?,?,NULL)", (int(co), case_id, int(profile["id"]), kind, int(day)))
            with_him.append(int(co))
    _set_case_meta(conn, case_id, stage="bail" if bail_day is not None else "disposition", bail_day=bail_day, disposition_day=dispo, arrest_day=int(day), arrested=offender, held_with=with_him)
    conn.execute("UPDATE law_enforcement_cases SET status='actionable', next_review_day=?, evidence_score=MAX(evidence_score,?) WHERE id=?",
                 (stage_day, float(conn.execute("SELECT evidence_score FROM law_enforcement_cases WHERE id=?", (case_id,)).fetchone()[0]), case_id))
    meta["arrest_day"] = int(day)
    conn.execute("UPDATE crime_reports SET status='arrest', metadata_json=? WHERE id=?", (json.dumps(meta, sort_keys=True), rid))
    _answer_arrest(conn, rid, case_id, offender, kind, int(day), float(meta.get("publicity") or 0.0))
    for co in with_him:
        _answer_arrest(conn, rid, case_id, co, kind, int(day), float(meta.get("publicity") or 0.0))


def _meta_of_case(conn: sqlite3.Connection, case_id: int) -> dict:
    row = conn.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (int(case_id),)).fetchone()
    return json.loads(row[0] or "{}") if row else {}


def _answer_arrest(conn: sqlite3.Connection, rid: int, case_id: int, offender: int, kind: str, day: int, pub: float) -> None:
    """What an arrest sets going: he is looked at tomorrow, his history is flagged, his organisations' heat rises, and his unit leader and
    head in each organisation where he holds a seat have `member_arrested` on their list."""
    from .org_lifecycle import mark_for_history
    imposed(conn, offender)
    mark_for_history(conn, offender, "was arrested", day)
    delay = int(_n(_cfg(conn)["arrest"]["respond_delay_days"]))
    seen: set[tuple[int, int]] = set()
    for org in _orgs_of(conn, offender):
        for who in (orgs.unit_leader_of(conn, offender, org), orgs.head_of(conn, org)):
            if who is None or int(who) == offender or (int(who), org) in seen or not _living(conn, who):
                continue
            seen.add((int(who), org))
            add_agenda(conn, int(who), "member_arrested", day + delay, subject_kind="actor", subject_id=offender,
                       metadata={"held": offender, "org": org, "case": case_id, "report": rid, "charge": kind})
    _heat(conn, offender, day, pub)


def _heat(conn: sqlite3.Connection, offender: int, day: int, pub: float) -> None:
    try:
        from . import org_heat
        if not org_heat.enabled(conn):
            return
    except (ImportError, sqlite3.OperationalError):
        return
    h = _cfg(conn)["arrest"]["heat"]
    own, city = org_heat._v(conn, org_heat._data(conn).get("own_full"), 1.0), org_heat._v(conn, org_heat._data(conn).get("city_full"), 1.0)
    for org in _orgs_of(conn, offender):
        org_heat.add(conn, org, day, investigative=_n(h["investigative_share"]) * own, public=_n(h["public_share"]) * city * pub / 100.0)


def _void_envelopes(conn: sqlite3.Connection, day: int) -> int:
    """A precinct whose commander has changed no longer has the envelope its old commander took: the arrangement is reopened (to be
    renegotiated). Read from the institution's membership: the first-tier envelope whose official is no longer a current commander."""
    c = _cfg(conn)["arrest"]
    tier = c["commander_tier"]
    prefix = c["commander_role_prefix"]
    n = 0
    for e in conn.execute("SELECT * FROM org_arrangements WHERE status='active' AND position_key LIKE ?", (f"%:{tier}:1",)).fetchall():
        row = conn.execute("SELECT institution_actor_id FROM institution_memberships WHERE member_actor_id=? AND role_text LIKE ? ORDER BY status='active' DESC LIMIT 1", (e["official_actor_id"], prefix + "%")).fetchone()
        if row is None:
            continue
        holders = {int(r[0]) for r in conn.execute("SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND status='active' AND role_text LIKE ?", (row[0], prefix + "%"))}
        if holders and int(e["official_actor_id"]) not in holders:
            conn.execute("UPDATE org_arrangements SET status='reopened', ended_day=? WHERE id=?", (int(day), e["id"]))
            n += 1
    return n


def _intake(conn: sqlite3.Connection, day: int) -> int:
    c = _cfg(conn)
    h = c.get("harm") or {}
    if not h:
        return 0
    row = conn.execute("SELECT value FROM engine_meta WHERE key=?", (CURSOR_KEY,)).fetchone()
    cursor = int(row[0]) if row else 0
    top = int(conn.execute("SELECT COALESCE(MAX(id),0) FROM harm_incidents").fetchone()[0])
    if top <= cursor:
        return 0
    intents = list(h["intents"]) + list(h["bystander_intents"])
    n = 0
    for r in conn.execute("SELECT * FROM harm_incidents WHERE id>? AND id<=? AND intent_class IN (%s) ORDER BY id" % ",".join("?" * len(intents)), (cursor, top, *intents)).fetchall():
        meta = _meta(r)
        if meta.get("crime") is False:
            continue
        offender = meta.get("offender_actor_id")
        bystander = r["intent_class"] in h["bystander_intents"]
        if bystander and offender is None:
            continue  # a plain accident is no one's crime
        if offender is not None and int(offender) == int(r["actor_id"]):
            continue
        near = conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE source_ref_id=? AND day=? AND intent_class IN (%s)" % ",".join("?" * len(intents)),
                            (r["source_ref_id"], r["day"], *intents)).fetchone()[0]
        others_hurt = conn.execute("SELECT 1 FROM harm_incidents WHERE source_ref_id=? AND day=? AND intent_class IN (%s) AND actor_id<>? LIMIT 1" % ",".join("?" * len(h["bystander_intents"])),
                                   (r["source_ref_id"], r["day"], *h["bystander_intents"], r["actor_id"])).fetchone()
        kind = h["fatal_kind"] if r["fatal"] else h["other_kind"]
        open_report(conn, crime_kind=kind, day=int(r["day"]), offender_actor_id=int(offender) if offender is not None else None, victim_actor_id=int(r["actor_id"]),
                    location_id=r["location_id"], public=bool(meta.get("public")),
                    metadata={"harm_incident_id": int(r["id"]), "method": meta.get("method"), "victims": int(near), "bystander": bool(bystander or others_hurt),
                              "source_kind": r["source_kind"]})
        n += 1
    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (CURSOR_KEY, str(top)))
    return n


def _reviews(conn: sqlite3.Connection, day: int) -> int:
    """Open cases whose review has come: the work adds evidence (scaled by the effort and noise); an arrest follows when the offender is
    known and the evidence passes the kind's threshold (the arrangements may still bury it); a case not solved in `case_close_days` closes."""
    c = _cfg(conn)["arrest"]
    n = 0
    for cs in conn.execute("""SELECT * FROM law_enforcement_cases WHERE status IN ('monitoring','open') AND next_review_day<=?
                              AND json_extract(metadata_json,'$.crime_report_id') IS NOT NULL ORDER BY id""", (int(day),)).fetchall():
        m = _meta(cs)
        rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (m["crime_report_id"],)).fetchone()
        if rep is None:
            continue
        kind, offender = rep["crime_kind"], rep["offender_actor_id"]
        pub = publicity_of(conn, rep["id"])
        rng = _rng(conn, "review", f"{cs['id']}:{day}")
        named = 0.0
        if offender is not None and not _knows_offender(conn, rep):  # the work may put a name to it
            rate = _n(_cfg(conn)["identification"]["review_rate"]) * float(m.get("effort") or 0.0)
            if org_motives._roll(conn, int(rep["id"]), int(day), "name") < rate:
                rm = _meta(rep)
                named = _n(c["evidence"]["offender_known"])  # the name is evidence like any other
                rm.update(identified=True, identified_day=int(day))
                conn.execute("UPDATE crime_reports SET metadata_json=? WHERE id=?", (json.dumps(rm, sort_keys=True, default=str), rep["id"]))
            else:
                offender = None
        gain = (_n(c["review"]["gain"]) + (rng.random() * 2.0 - 1.0) * _n(c["review"]["noise"])) * float(m.get("effort") or 0.0)
        score = float(cs["evidence_score"]) / 100.0 + gain + named
        prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (cs["profile_id"],)).fetchone()
        conn.execute("UPDATE law_enforcement_cases SET evidence_score=?, last_review_day=? WHERE id=?", (round(min(100.0, max(0.0, 100.0 * score)), 3), int(day), cs["id"]))  # the column's own 0-100 domain; the test below uses the unbounded score
        n += 1
        if offender is not None and _living(conn, offender) and score >= _threshold(conn, kind):
            if _bought(conn, prof, m.get("officer"), int(offender), kind, pub, bool(_meta(rep).get("officer_victim")), int(rep["id"]), int(day)):
                conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cs["id"]))
                _set_case_meta(conn, cs["id"], reason="arrangements")
                if conn.execute("SELECT COUNT(*) FROM law_enforcement_cases WHERE json_extract(metadata_json,'$.crime_report_id')=? AND status<>'closed'", (rep["id"],)).fetchone()[0] == 0:
                    conn.execute("UPDATE crime_reports SET status='buried' WHERE id=? AND status='open'", (rep["id"],))
                continue
            if rep["status"] in ("open",):
                _arrest(conn, int(rep["id"]), int(cs["id"]), prof, int(offender), int(day))
                continue
        if int(day) - int(cs["opened_day"]) >= int(figure(conn, "case_close_days")):
            conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cs["id"]))
            _set_case_meta(conn, cs["id"], reason="unsolved")
            if conn.execute("SELECT COUNT(*) FROM law_enforcement_cases WHERE json_extract(metadata_json,'$.crime_report_id')=? AND status<>'closed'", (rep["id"],)).fetchone()[0] == 0 and rep["status"] == "open":
                conn.execute("UPDATE crime_reports SET status='closed' WHERE id=?", (rep["id"],))
        else:
            conn.execute("UPDATE law_enforcement_cases SET next_review_day=? WHERE id=?", (int(day) + _review_days(conn, kind), cs["id"]))
    return n


def _stage_cases(conn: sqlite3.Connection, day: int):
    return conn.execute("""SELECT * FROM law_enforcement_cases WHERE status='actionable' AND next_review_day<=?
                           AND json_extract(metadata_json,'$.crime_report_id') IS NOT NULL ORDER BY id""", (int(day),)).fetchall()


def _bail(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    for cs in _stage_cases(conn, day):
        m = _meta(cs)
        if m.get("stage") != "bail":
            continue
        for a in [int(m["arrested"]), *[int(x) for x in m.get("held_with") or []]]:
            conn.execute("UPDATE custody SET kind='bailed', until_day=? WHERE case_id=? AND actor_id=? AND kind='held'", (int(day), cs["id"], a))
            imposed(conn, a)  # he is out: looked at tomorrow
        _set_case_meta(conn, cs["id"], stage="disposition", bailed_day=int(day))
        conn.execute("UPDATE law_enforcement_cases SET next_review_day=? WHERE id=?", (int(m["disposition_day"]), cs["id"]))
        n += 1
    return n


def _lawyer(conn: sqlite3.Connection, m: dict) -> float:
    half = _n(_cfg(conn)["backing"]["lawyer_half_fee"])
    fee = float(m.get("lawyer_fee") or 0.0)
    return fee / (fee + half) if fee > 0 else 0.0


def _witness_pressure(conn: sqlite3.Connection, offender: int, rep_meta: dict, day: int) -> float:
    try:
        from . import org_heat
        if not org_heat.enabled(conn):
            return 0.0
        own = max((org_heat.own_factor(conn, o, day) for o in _orgs_of(conn, offender)), default=0.0)
    except (ImportError, sqlite3.OperationalError):
        return 0.0
    seen = float(rep_meta.get("witnesses") or 0)
    share = 1.0 - math.exp(-seen / float(_cfg(conn)["publicity"]["witness_scale"]))
    return share * own


def _facility(conn: sqlite3.Connection, profile, term: int) -> str:
    f = _cfg(conn)["sentence"]["facilities"]
    spec = f.get(profile["authority_kind"]) or f.get("municipal")
    return str(spec["short"] if term <= int(_n(spec["short_max_days"])) else spec["long"])


def _dispose(conn: sqlite3.Connection, cs, day: int) -> None:
    """The case's disposition, once for the man arrested and once for each co-defendant held on it (his own plea, trial or walk)."""
    m = _meta(cs)
    lead = int(m["arrested"])
    for a in [lead, *[int(x) for x in m.get("held_with") or []]]:
        if a != lead and conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND case_id=? AND kind IN ('held','bailed') LIMIT 1", (a, cs["id"])).fetchone() is None:
            continue
        _dispose_one(conn, cs, day, a, cs["id"] if a == lead else f"{cs['id']}:{a}")


def _dispose_one(conn: sqlite3.Connection, cs, day: int, a: int, key) -> None:
    c = _cfg(conn)
    d = c["disposition"]
    m = _meta(cs)
    rep = conn.execute("SELECT * FROM crime_reports WHERE id=?", (m["crime_report_id"],)).fetchone()
    kind, rid = rep["crime_kind"], int(rep["id"])
    rmeta = _meta(rep)
    prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (cs["profile_id"],)).fetchone()
    pub = publicity_of(conn, rid) / 100.0
    s = float(cs["evidence_score"]) / 100.0
    law = _lawyer(conn, m)
    padx = 1.0 if (m.get("officer") is not None and pad_reaches(conn, prof, m.get("officer"), a)) else 0.0
    wp = _witness_pressure(conn, a, rmeta, day)
    inducted = 1.0 if conn.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND inducted_day IS NOT NULL LIMIT 1", (a,)).fetchone() else 0.0
    x = {"strength": s, "lawyer": law, "arrangements": padx, "witness_pressure": wp, "publicity": pub, "inducted": inducted}

    def z(spec) -> float:
        return _n(spec["bias"]) + sum(_n(v) * x[k] for k, v in spec.items() if k in x)

    p_dismiss, p_trial, p_guilty = _logit(z(d["dismiss"])), _logit(z(d["trial"])), _logit(z(d["conviction"]))
    rng = _rng(conn, "disposition", key)
    r1, r2, r3 = rng.random(), rng.random(), rng.random()
    if r1 < p_dismiss:
        kind_out, convicted = "dismissed", False
    elif r2 < p_trial:
        convicted = r3 < p_guilty
        kind_out = "verdict_guilty" if convicted else "verdict_not_guilty"
    else:
        kind_out, convicted = "plea", True
    dispo_id = int(conn.execute("INSERT INTO case_dispositions(case_id,report_id,actor_id,day,kind,factors_json,metadata_json) VALUES (?,?,?,?,?,?,?)",
                                (cs["id"], rid, a, int(day), kind_out, json.dumps({**{k: round(v, 4) for k, v in x.items()}, "p_dismiss": round(p_dismiss, 4), "p_trial": round(p_trial, 4), "p_guilty": round(p_guilty, 4)}, sort_keys=True),
                                 json.dumps({"crime_kind": kind}))).lastrowid)
    conn.execute("UPDATE law_enforcement_cases SET status='closed', closed_day=? WHERE id=?", (int(day), cs["id"]))
    _set_case_meta(conn, cs["id"], stage="done", disposition=kind_out, disposition_id=dispo_id)
    rmeta["disposition"] = kind_out
    from .org_lifecycle import mark_for_history
    if not convicted:
        conn.execute("UPDATE custody SET kind='released', until_day=? WHERE case_id=? AND actor_id=? AND kind IN ('held','bailed')", (int(day), cs["id"], a))
        conn.execute("UPDATE crime_reports SET status='closed', metadata_json=? WHERE id=?", (json.dumps(rmeta, sort_keys=True), rid))
        imposed(conn, a)
        mark_for_history(conn, a, "walked free" if kind_out == "dismissed" else "was acquitted", int(day))
        return
    sen = c["sentence"]
    term = _lognormal_days(conn, sen["term_days"], kind, "term", cs["id"])
    term = max(1, int(round(term * (_n(sen["plea_factor"]) if kind_out == "plea" else 1.0) * (1.0 + _n(sen["publicity_factor"]) * pub)
                            * (1.0 + (_n(sen["officer_victim_factor"]) if rmeta.get("officer_victim") else 0.0)))))
    earliest = int(day) + max(1, int(round(term * _n(sen["parole_share"]))))
    facility = _facility(conn, prof, term)
    conn.execute(
        """INSERT INTO sentences(actor_id,case_id,report_id,disposition_id,crime_kind,victim_actor_id,location_id,term_days,start_day,earliest_release_day,end_day,facility,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'serving',?)""",
        (a, cs["id"], rid, dispo_id, kind, rep["victim_actor_id"], rep["location_id"], term, int(day), earliest, int(day) + term, facility,
         json.dumps({"how": kind_out, "agency_profile_id": int(prof["id"])}, sort_keys=True)))
    n = conn.execute("UPDATE custody SET kind='held', until_day=?, charge=? WHERE case_id=? AND actor_id=? AND kind IN ('held','bailed')", (earliest, kind, cs["id"], a)).rowcount
    if not n:
        conn.execute("INSERT INTO custody(actor_id,case_id,agency_profile_id,kind,charge,since_day,until_day) VALUES (?,?,?,'held',?,?,?)", (a, cs["id"], int(prof["id"]), kind, int(day), earliest))
    conn.execute("UPDATE crime_reports SET status='closed', metadata_json=? WHERE id=?", (json.dumps(rmeta, sort_keys=True), rid))
    imposed(conn, a)  # the seats weigh a long absence through the held-man decisions of the lifecycle
    mark_for_history(conn, a, f"was sentenced to {term} days at {facility}", int(day))


def _dispositions(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    for cs in _stage_cases(conn, day):
        if _meta(cs).get("stage") == "disposition":
            _dispose(conn, cs, int(day))
            n += 1
    return n


def _prison_holds_release(conn: sqlite3.Connection) -> bool:
    """A world with prison data frees its men through the prison layer's hearings and good time (J1), not at the earliest release day."""
    try:
        from . import prison
        return prison.enabled(conn)
    except (ImportError, sqlite3.OperationalError):
        return False


def _releases(conn: sqlite3.Connection, day: int) -> int:
    n = 0
    if _prison_holds_release(conn):
        return n
    for s in conn.execute("SELECT * FROM sentences WHERE status='serving' AND earliest_release_day<=? ORDER BY id", (int(day),)).fetchall():
        a = int(s["actor_id"])
        if not _living(conn, a):
            conn.execute("UPDATE sentences SET status='ended', released_day=? WHERE id=?", (int(day), s["id"]))
            continue
        conn.execute("UPDATE sentences SET status='released', released_day=? WHERE id=?", (int(day), s["id"]))
        conn.execute("UPDATE custody SET kind='released', until_day=? WHERE case_id=? AND actor_id=? AND kind='held'", (int(day), s["case_id"], a))
        imposed(conn, a)  # what he does next is his own choice: he is looked at tomorrow
        from .org_lifecycle import mark_for_history
        mark_for_history(conn, a, "came home", int(day))
        try:
            from . import org_temperament
            org_temperament.drift(conn, a, "prison", int(day))
        except (ImportError, sqlite3.OperationalError):
            pass
        n += 1
    return n


# ---- the process ----

def next_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    try:
        if not _cfg(conn):
            return None
        ensure_tables(conn)
        due: list[int] = []
        cur = conn.execute("SELECT value FROM engine_meta WHERE key=?", (CURSOR_KEY,)).fetchone()
        if int(conn.execute("SELECT COALESCE(MAX(id),0) FROM harm_incidents").fetchone()[0]) > (int(cur[0]) if cur else 0):
            due.append(int(after_day) + 1)
        sqls = ["SELECT MIN(MAX(next_review_day, ?)) FROM law_enforcement_cases WHERE status IN ('monitoring','open','actionable') AND json_extract(metadata_json,'$.crime_report_id') IS NOT NULL"]
        if not _prison_holds_release(conn):
            sqls.append("SELECT MIN(MAX(earliest_release_day, ?)) FROM sentences WHERE status='serving'")
        for sql in sqls:
            r = conn.execute(sql, (int(after_day) + 1,)).fetchone()
            if r is not None and r[0] is not None:
                due.append(int(r[0]))
        d = min(due) if due else None
        return d if d is not None and d <= int(end_day) else None
    except sqlite3.OperationalError:
        return None


SWEEP_CURSOR = "crime_response_sweep_cursor"


def _sweeps(conn: sqlite3.Connection, day: int, since: int) -> int:
    """A killing the police take hard (a loud one, a hot group, an agency with the means) can bring a sweep: men tied to it, from the groups on
    either side, are picked up together under one joint case with co-defendants. The weighing is the package's (`response.sweep`): a pressure
    on the report, a number of men drawn around a mean that the pressure raises, and a pick weighted by how close each man stands to it. Nothing
    caps the men taken or the sweeps in a year."""
    sw = _cfg(conn).get("sweep")
    if not sw:
        return 0
    from . import org_heat
    kinds = list(sw["kinds"])
    n = 0
    for rep in conn.execute("SELECT * FROM crime_reports WHERE id>? AND crime_kind IN (%s) AND offender_actor_id IS NOT NULL ORDER BY id" % ",".join("?" * len(kinds)), (int(since), *kinds)).fetchall():
        meta = _meta(rep)
        if meta.get("source") == "sweep":
            continue
        offender, victim = int(rep["offender_actor_id"]), rep["victim_actor_id"]
        involved = sorted(set(_orgs_of(conn, offender)) | set(_orgs_of(conn, victim)))
        if not involved:
            continue
        pub = publicity_of(conn, int(rep["id"])) / 100.0
        heat = max((org_heat.own_factor(conn, o, int(day)) for o in involved), default=0.0) if org_heat.enabled(conn) else 0.0
        prof = conn.execute("SELECT * FROM law_enforcement_profiles WHERE id=?", (rep["agency_profile_id"],)).fetchone() if rep["agency_profile_id"] else None
        cap = float(prof["capacity"]) / 100.0 if prof is not None else 0.0
        x = {"publicity": pub, "heat": heat, "capacity": cap, "officer_victim": 1.0 if meta.get("officer_victim") else 0.0,
             "organised": 1.0 if _orgs_of(conn, offender) and _orgs_of(conn, victim) else 0.0}
        z = _n(sw["bias"]) + sum(_n(v) * x[k] for k, v in sw["weights"].items() if k in x)
        if _rng(conn, "sweep", rep["id"]).random() >= _logit(z):
            continue
        rng = _rng(conn, "sweep_men", rep["id"])
        want = _poisson(rng, _n(sw["men"]["base"]) + _n(sw["men"]["per_publicity"]) * pub + _n(sw["men"]["per_heat"]) * heat)
        pool = []
        offender_units = {int(r[0]) for r in conn.execute("SELECT unit_id FROM org_seats WHERE actor_id=? AND status='active' AND unit_id IS NOT NULL", (offender,))}
        offender_orgs = set(_orgs_of(conn, offender))
        for org in involved:
            for r in conn.execute("SELECT actor_id,unit_id,inducted_day FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id", (org,)).fetchall():
                a = int(r["actor_id"])
                if a == offender or a == victim or not _living(conn, a) or conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' LIMIT 1", (a,)).fetchone():
                    continue
                w = (_n(sw["pick"]["base"]) + (_n(sw["pick"]["same_unit"]) if r["unit_id"] in offender_units else 0.0)
                     + (_n(sw["pick"]["offender_org"]) if org in offender_orgs else 0.0) + (_n(sw["pick"]["inducted"]) if r["inducted_day"] is not None else 0.0))
                pool.append((a, w))
        taken: list[int] = []
        while pool and len(taken) < want:
            pick = rng.random() * sum(w for _, w in pool)
            for i, (a, w) in enumerate(pool):
                pick -= w
                if pick < 0 or i == len(pool) - 1:
                    taken.append(a)
                    pool.pop(i)
                    break
        if not taken:
            continue
        lead, others = taken[0], taken[1:]
        jr = open_report(conn, crime_kind=sw["conspiracy_kind"], day=int(day), offender_actor_id=lead, victim_actor_id=victim, location_id=rep["location_id"],
                         metadata={"source": "sweep", "sweep_of": int(rep["id"]), "identified": True, "co_defendants": others})
        jrow = conn.execute("SELECT * FROM crime_reports WHERE id=?", (jr,)).fetchone()
        for a in taken:
            if conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held' LIMIT 1", (a,)).fetchone() is None:  # picked up for a few days (the arrest of the lead holds all of them on the case)
                days = _lognormal_days(conn, {"default": sw["hold_days"]}, "default", "sweep_hold", f"{rep['id']}:{a}")
                conn.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held',?,?,?)", (a, "a sweep", int(day), int(day) + days))
                _answer_arrest(conn, jr, int(jrow["case_id"] or 0), a, sw["conspiracy_kind"], int(day), pub * 100.0)
            imposed(conn, a)
        n += 1
    return n


def process_due(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict:
    if not _cfg(conn):
        return {}
    ensure_tables(conn)
    cur = conn.execute("SELECT value FROM engine_meta WHERE key=?", (SWEEP_CURSOR,)).fetchone()
    since = int(cur[0]) if cur else int(conn.execute("SELECT COALESCE(MAX(id),0) FROM crime_reports").fetchone()[0])
    out = {"reports": _intake(conn, int(day))}
    out["swept"] = _sweeps(conn, int(day), since)
    conn.execute("INSERT INTO engine_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (SWEEP_CURSOR, str(int(conn.execute("SELECT COALESCE(MAX(id),0) FROM crime_reports").fetchone()[0]))))
    out["envelopes_reopened"] = _void_envelopes(conn, int(day))
    out["reviewed"] = _reviews(conn, int(day))
    out["bailed"] = _bail(conn, int(day))
    out["disposed"] = _dispositions(conn, int(day))
    out["released"] = _releases(conn, int(day))
    return out


# ---- the answer to an arrest (an agenda item: the unit leader or head weighs a lawyer or waiting) ----

def _fee_range(conn: sqlite3.Connection) -> tuple[float, float]:
    f = _cfg(conn)["backing"]["lawyer_fee"]
    return _n(f["low"]), _n(f["high"])


def _still_held(conn: sqlite3.Connection, held: int) -> bool:
    return conn.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind IN ('held','bailed') AND case_id IS NOT NULL LIMIT 1", (int(held),)).fetchone() is not None


def arrest_offers(conn: sqlite3.Connection, actor_id: int, item, day: int) -> list[dict]:
    from . import ledger
    m = _meta(item)
    held, org = int(m["held"]), int(m["org"])
    if not _still_held(conn, held):
        resolve_agenda(conn, int(item["id"]), int(day))
        return []
    b = _cfg(conn)["backing"]
    rel = conn.execute("SELECT loyalty FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (int(actor_id), held)).fetchone()
    loyalty = max(0.0, min(1.0, float(rel[0]) / 100.0)) if rel is not None else 0.5
    seat = orgs.seat_of(conn, held, org)
    standing = float(seat["standing"]) if seat is not None else 0.0
    low, high = _fee_range(conn)
    balance = ledger.balance(conn, ("person", int(actor_id)))
    base = {"payload": {"held": held, "org": org, "case": m.get("case"), "report": m.get("report"), "charge": m.get("charge")}, "target_actor_id": held}
    def utility(x: float) -> float:  # the same scale every organisation choice uses
        return float(figure(conn, "org_choice_utility_base", default=8.0)) + float(figure(conn, "org_choice_utility_span", default=10.0)) * orgs.clamp01(x)

    offers = [{**base, "kind": "member_arrested", "utility": utility(_n(b["wait_base"])), "rationale": "waits to see what the case brings",
               "payload": {**base["payload"], "response": "wait"}}]
    if balance >= low:
        offers.append({**base, "kind": "member_arrested", "cost": (low + high) / 2.0, "rationale": "sends him a lawyer",
                       "utility": utility(_n(b["send_base"]) + _n(b["send_loyalty"]) * loyalty + _n(b["send_standing"]) * standing
                                          - _n(b["send_cost"]) * (low + high) / 2.0 / max(balance, 1.0)),
                       "payload": {**base["payload"], "response": "send_lawyer"}})
    return offers


def execute_member_arrested(conn: sqlite3.Connection, actor_id: int, kind: str, payload: dict, day: int) -> dict:
    from . import ledger
    from .relationships import adjust_relationship
    held, resp = int(payload["held"]), str(payload.get("response") or "wait")
    if payload.get("agenda_id") is not None:
        resolve_agenda(conn, int(payload["agenda_id"]), int(day))
    b = _cfg(conn)["backing"]
    text = f"{_name(conn, actor_id)} waited on {_name(conn, held)}'s case."
    if resp == "send_lawyer" and payload.get("case") is not None:
        low, high = _fee_range(conn)
        fee = low + _rng(conn, "fee", f"{actor_id}:{held}:{day}").random() * (high - low)
        paid = ledger.spend(conn, ("person", int(actor_id)), fee, purpose="a lawyer for a man in custody", allow_partial=True)
        cs = conn.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (int(payload["case"]),)).fetchone()
        if cs is not None and paid > 0:
            cm = _meta(cs)
            upd = {"lawyer_fee": float(cm.get("lawyer_fee") or 0.0) + paid}
            if cm.get("stage") == "bail" and cm.get("bail_day") is not None:
                bail = min(int(cm["bail_day"]), int(day) + max(1, int(round(int(figure(conn, "bail_days")) * _n(b["bail_after_lawyer_share"])))))
                upd["bail_day"] = bail
                conn.execute("UPDATE law_enforcement_cases SET next_review_day=? WHERE id=?", (bail, cs["id"]))
            _set_case_meta(conn, cs["id"], **upd)
        text = f"{_name(conn, actor_id)} sent a lawyer to {_name(conn, held)} (${paid:,.0f})."
    if str(payload.get("charge")) == _cfg(conn)["harm"]["fatal_kind"]:
        lo, hi = b["homicide_trust_drop"]
        drop = int(_rng(conn, "trust", f"{actor_id}:{held}:{day}").randint(int(lo), int(hi)))
        if drop:
            adjust_relationship(conn, int(actor_id), held, int(day), trust_delta=-float(drop))
    return {"summary": text}


register_executor("member_arrested", execute_member_arrested)
register_agenda_action("member_arrested", arrest_offers)
