"""Men who inform, in every kind of organisation (task B12f). Generic; roles, terms and figures are outfits data `tension.informing`.

Before this a man could inform only through the weekly happening of a family's dependent seat. Here any seat the package lists for its
organisation kind (an independent's hand, a club's member, a bank's runner...) can be turned, by the law (a man with a case against him
and something to lose) or by another organisation (a rival that is aggrieved at his, with a man who is greedy or resentful). A turned man
reports now and then: to the police, which opens a case the way an informant's evidence always did (and the man's own head may find out
and answer it); or to the rival, who then knows more of what his rival does (a term in the strike and squeeze weighings) until the man
is found out, which sours the pair and puts the man on his own head's list.
"""
from __future__ import annotations

import json
import sqlite3

from . import org_tension as ot, outfit_motives as om
from .design import run_seed  # noqa: F401
from .orgs import add_agenda, clamp01, head_of, imposed, is_living, seat_of


def idata(conn: sqlite3.Connection) -> dict:
    return ot.data(conn).get("informing") or {}


def _v(conn, spec, default: float = 0.0) -> float:
    return ot._v(conn, spec, default)


def _rng(conn, stream: str, *keys):
    return ot._rng(conn, "informing:" + stream, *keys)


def active(conn: sqlite3.Connection) -> list:
    return conn.execute("SELECT * FROM org_informers WHERE status='active' ORDER BY id").fetchall()


def is_informer(conn: sqlite3.Connection, man: int) -> bool:
    return conn.execute("SELECT 1 FROM org_informers WHERE informer_actor_id=? AND status='active' LIMIT 1", (int(man),)).fetchone() is not None


def informed(conn: sqlite3.Connection, F: int, T: int) -> float:
    """1 when F has a man of T's who reports to it, else 0."""
    return 1.0 if conn.execute("SELECT 1 FROM org_informers WHERE status='active' AND turned_by_kind='org' AND turned_by_id=? AND org_actor_id=? LIMIT 1", (int(F), int(T))).fetchone() else 0.0


def _turnable(conn, man: int, org: int) -> bool:
    seat = seat_of(conn, man, org)
    if seat is None or seat["status"] != "active":
        return False
    kind = conn.execute("SELECT org_kind FROM org_profiles WHERE org_actor_id=?", (int(org),)).fetchone()
    return kind is not None and seat["role_key"] in ((idata(conn).get("roles") or {}).get(kind[0]) or [])


def _family_need(conn, man: int, day: int) -> float:
    """How far a held man's people are going without (prison data); 0 where the world has none."""
    try:
        from .prison import family_need
        return family_need(conn, man, day)
    except sqlite3.OperationalError:
        return 0.0


def _man_factors(conn, man: int, org: int, day: int) -> dict[str, float]:
    from .org_happenings import _arrested, _kin_tie, _open_case, _resentment
    seat = seat_of(conn, man, org)
    from . import org_heat
    return {"always": 1.0, "leverage": _open_case(conn, man, day), "arrested": _arrested(conn, man, day), "kin_tie": _kin_tie(conn, man, day),
            "greed": float(seat["greed"]), "disloyal": 1.0 - om._drive(conn, man, "loyalty"), "loyal": om._drive(conn, man, "loyalty"),
            "resentful": _resentment(conn, man, day, seat, org) if seat["superior_actor_id"] is not None else 0.0,
            "standing": clamp01(float(seat["standing"])), "made": 1.0 if seat["inducted_day"] is not None else 0.0,
            "afraid": 1.0 - om._drive(conn, man, "risk_tolerance"), "interest": org_heat.own_factor(conn, org, day),
            "family_need": _family_need(conn, man, day)}


def _turn(conn, man: int, org: int, by_kind: str, by_id: int | None, day: int) -> int:
    imposed(conn, man)
    return int(conn.execute("INSERT INTO org_informers(informer_actor_id,org_actor_id,turned_by_kind,turned_by_id,since_day) VALUES (?,?,?,?,?)",
                            (int(man), int(org), by_kind, by_id, int(day))).lastrowid)


def _law_turns(conn, day: int) -> int:
    d = idata(conn).get("law") or {}
    if not d:
        return 0
    n = 0
    seen = set()
    rows = conn.execute("SELECT DISTINCT offender_actor_id FROM crime_reports WHERE status IN ('open','arrest') AND offender_actor_id IS NOT NULL ORDER BY 1").fetchall()
    rows += conn.execute("SELECT DISTINCT actor_id FROM custody WHERE since_day>=? ORDER BY 1", (int(day) - int(_v(conn, d.get("lookback_days"), 90.0)),)).fetchall()
    for (a,) in rows:
        a = int(a)
        if a in seen or not is_living(conn, a) or is_informer(conn, a):
            continue
        seen.add(a)
        for (org,) in conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' ORDER BY org_actor_id", (a,)).fetchall():
            if not _turnable(conn, a, int(org)):
                continue
            f = _man_factors(conn, a, int(org), day)
            if _rng(conn, "law", a, day).random() < ot._blend(conn, d["terms"], f) * _v(conn, d.get("rate"), 0.0):
                _turn(conn, a, int(org), "law", None, day)
                n += 1
            break
    return n


def _rival_turns(conn, day: int) -> int:
    d = idata(conn).get("rival") or {}
    if not d:
        return 0
    n = 0
    for F, T in ot.pairs(conn, day):
        h = ot.heat(conn, F, T, day)
        if h <= 0 or _rng(conn, "rival", F, T, day).random() >= _v(conn, d.get("rate"), 0.0) * h:
            continue
        hF = head_of(conn, F)
        if hF is None or not ot._free(conn, hF):
            continue
        best, who = 0.0, None
        for (m,) in conn.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id", (int(T),)).fetchall():
            m = int(m)
            if m == head_of(conn, T) or is_informer(conn, m) or not _turnable(conn, m, T) or not ot._free(conn, m):
                continue
            f = _man_factors(conn, m, T, day)
            w = ot._blend(conn, d["weigh"], f)
            if w > best:
                best, who = w, m
        if who is None:
            continue
        f = _man_factors(conn, who, T, day)
        f.update({"heat": h, "ambition": om._drive(conn, hF, "ambition")})
        if _rng(conn, "rival_accept", who, F, day).random() < ot._blend(conn, d["accept"], f):
            _turn(conn, who, T, "org", F, day)
            n += 1
    return n


def _target_of(conn, man: int, org: int, day: int) -> int | None:
    """Who an informant gives the law: the man he answers to; with no one above him (an independent's principal), the head of the organisation
    that presses him hardest."""
    seat = seat_of(conn, man, org)
    if seat is not None and seat["superior_actor_id"] is not None and is_living(conn, int(seat["superior_actor_id"])):
        return int(seat["superior_actor_id"])
    best, who = 0.0, None
    for a, b in ot.pairs(conn, day):
        if a == org:
            h = ot.heat(conn, org, b, day) + ot.heat(conn, b, org, day)
            if h >= best and head_of(conn, b) is not None:
                best, who = h, int(head_of(conn, b))
    return who


def _reports(conn, day: int) -> int:
    d = idata(conn).get("report") or {}
    if not d:
        return 0
    from .crime_response import open_report
    from .org_happenings import _record
    n = 0
    for r in active(conn):
        man, org = int(r["informer_actor_id"]), int(r["org_actor_id"])
        if not is_living(conn, man) or (seat_of(conn, man, org) or {"status": ""})["status"] != "active":
            conn.execute("UPDATE org_informers SET status='ended', ended_day=? WHERE id=?", (int(day), r["id"]))
            continue
        if r["turned_by_kind"] != "law" or not ot._free(conn, man):
            continue
        f = _man_factors(conn, man, org, day)
        if _rng(conn, "report", r["id"], day).random() >= ot._blend(conn, d["terms"], f) * _v(conn, d.get("rate"), 0.0):
            continue
        target = _target_of(conn, man, org, day)
        if target is None:
            continue
        loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (target,)).fetchone()
        open_report(conn, crime_kind=d["crime_kind"], day=int(day), offender_actor_id=int(target), location_id=loc[0] if loc else None,
                    metadata={"source": "org_happening", "informant": man, "discovered": 0, "identified": True, "close_day": int(day) + int(_v(conn, d.get("report_days"), 30.0))})
        _record(conn, int(day), "informs", man, victim=int(target), status="open", group="wrong", summary="an informant gave the police evidence")
        n += 1
    return n


def _exposures(conn, day: int) -> int:
    d = idata(conn).get("exposed") or {}
    if not d:
        return 0
    from .org_happenings import _record
    n = 0
    for r in active(conn):
        if r["turned_by_kind"] != "org":
            continue
        man, org, F = int(r["informer_actor_id"]), int(r["org_actor_id"]), r["turned_by_id"]
        f = _man_factors(conn, man, org, day)
        if _rng(conn, "exposed", r["id"], day).random() >= ot._blend(conn, d["terms"], f) * _v(conn, d.get("rate"), 0.0):
            continue
        conn.execute("UPDATE org_informers SET status='exposed', ended_day=? WHERE id=?", (int(day), r["id"]))
        if F is not None:
            ot.add(conn, org, int(F), "informer_exposed", _v(conn, (ot.data(conn).get("raise") or {}).get("informer_exposed"), 0.0), day, actor=man)
        head = head_of(conn, org)
        iid = _record(conn, int(day), "informs", man, victim=None, status="open", group="wrong", summary="a man was found reporting to a rival")
        conn.execute("UPDATE org_incidents SET matters=1, raised_to_org_actor_id=? WHERE id=?", (org, iid))
        if head is not None and head != man:
            add_agenda(conn, head, "respond_incident", int(day) + int(_v(conn, d.get("respond_delay"), 1.0)), subject_kind="incident", subject_id=iid,
                       metadata={"incident": iid, "offender": man, "offender_org": org, "victim": head, "org": org, "kind": "informs"})
            imposed(conn, head)
        n += 1
    return n


def process_due(conn: sqlite3.Connection, day: int) -> dict:
    if not ot.enabled(conn) or not idata(conn):
        return {}
    out = {}
    for name, fn in (("law_turned", _law_turns), ("rival_turned", _rival_turns), ("reports", _reports), ("exposed", _exposures)):
        n = fn(conn, int(day))
        if n:
            out[f"informing:{name}"] = n
    return out
