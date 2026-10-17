"""Authoring: the GM's invented people, businesses, bodies and rumours become real only through existing engine paths.

People are pre-existing background identities of the settlement (population-preserving); authoring never hands the protagonist money, people, ownership, office or anything beyond acquaintance.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import ledger
from .household_life import _actor_is_living, _family_name, add_kinship, create_union, _has_active_union, prohibited_union_kinship_reason
from .person_ecology import FIRST_FEMALE, FIRST_MALE, _free_name, find_background_candidate, resolve_background_person
from .relationships import ensure_relationship


class AuthoringRefused(ValueError):
    """The world has no such thing here; the message says why."""


WORK = ("artisan", "artist", "clerk", "criminal", "hospitality", "labor", "merchant", "physician", "soldier", "teacher", "transport")
STAGES = ("First", "Temper", "Third", "Breach", "Fifth", "Sixth")
TIES = ("knows", "sibling", "parent", "child", "spouse")


def _no(msg: str):
    raise AuthoringRefused(msg)


def _day(conn) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _text(v: Any, field: str, n: int) -> str:
    s = " ".join(str(v or "").split())
    if not 1 <= len(s) <= n:
        _no(f"{field} must be 1-{n} characters")
    return s


def _place(conn, me: int, d: dict) -> int:
    loc = d.get("location_id")
    if loc is None:
        loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (int(me),)).fetchone()[0]
    if loc is None or not conn.execute("SELECT 1 FROM locations WHERE id=?", (int(loc),)).fetchone():
        _no("unknown location")
    return int(loc)


def _character(conn, aid: Any, what: str) -> int:
    try:
        aid = int(aid)
    except (TypeError, ValueError):
        _no(f"{what} must be an actor id")
    r = conn.execute("SELECT actor_type,status FROM actors WHERE id=?", (aid,)).fetchone()
    if not r or r[0] != "character" or r[1] != "active" or not _actor_is_living(conn, aid):
        _no(f"{what} must be a living character")
    return aid


def _his_person(conn, me: int, aid: int) -> bool:
    """The protagonist, or anyone in an outfit, business or household he belongs to or controls."""
    if aid == me:
        return True
    for (org,) in conn.execute("SELECT organization_id FROM underworld_personnel WHERE actor_id=? AND status='active'", (aid,)).fetchall():
        if ledger.can_draw(conn, me, ("outfit", int(org))) or conn.execute(
                "SELECT 1 FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'", (me, org)).fetchone():
            return True
    for (eid,) in conn.execute("SELECT enterprise_id FROM enterprise_staff WHERE actor_id=? AND status='active'", (aid,)).fetchall():
        if ledger.can_draw(conn, me, ("business", int(eid))):
            return True
    for (hid,) in conn.execute("SELECT household_id FROM household_service_terms WHERE actor_id=? AND status='active'", (aid,)).fetchall():
        if ledger.can_draw(conn, me, ("household", int(hid))):
            return True
    return False


def _not_his(conn, me: int, aid: int, what: str) -> None:
    if aid == me:
        _no(f"{what} cannot be the protagonist")
    if _his_person(conn, me, aid):
        _no(f"{what} cannot be one of his people; that is for act hire")


def _age(conn, aid: int, day: int) -> int:
    r = conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
    return int((day - r[0]) // 365) if r and r[0] is not None else 0


def _sex(conn, aid: int) -> str | None:
    r = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
    return r[0] if r else None


# ---------------------------------------------------------------- person

def _person(conn, me: int, d: dict, call_id: str) -> dict:
    sex = d.get("sex")
    if sex not in ("male", "female"):
        _no("sex must be male or female")
    age = d.get("age")
    if age is not None and (isinstance(age, bool) or not isinstance(age, int) or not 13 <= age <= 90):
        _no("age must be a whole number from 13 to 90")
    work = d.get("work")
    if work is not None and work not in WORK:
        _no("work must be one of " + ", ".join(WORK))
    stage = d.get("stage")
    if stage is not None and stage not in STAGES:
        _no("stage must be one of " + ", ".join(STAGES))
    loc = _place(conn, me, d)
    elsewhere = bool(d.get("from_elsewhere", False))
    wants = _text(d["wants"], "wants", 200) if d.get("wants") is not None else None
    full = None
    if d.get("name") is not None:
        full = _text(d["name"], "name", 60)
        given = full.split(" ", 1)[0]
        if given in (FIRST_FEMALE if sex == "male" else FIRST_MALE):
            _no(f"the name {given} belongs to the other sex; names follow sex")
        if conn.execute("SELECT 1 FROM actors WHERE name=?", (full,)).fetchone():
            _no(f"the name {full} is already in use")
    ties = d.get("ties") or []
    if not isinstance(ties, list) or len(ties) > 4:
        _no("ties must be a list of at most 4")
    seen = set()
    for t in ties:
        if not isinstance(t, dict) or t.get("as") not in TIES:
            _no("each tie needs actor_id and as: " + ", ".join(TIES))
        tid = _character(conn, t.get("actor_id"), "a tie")
        if tid in seen:
            _no("a person can be tied only once to the same actor")
        seen.add(tid)
        if t["as"] != "knows" and tid == me:
            _no("the protagonist cannot be given new kin; only a passing acquaintance")
    notes = [int(n) for n in (d.get("from_notes") or [])]
    if notes:
        have = {r[0] for r in conn.execute(
            f"SELECT id FROM gm_notes WHERE subject_kind='general' AND id IN ({','.join('?' * len(notes))})", notes)} \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='gm_notes'").fetchone() else set()
        for n in notes:
            if n not in have:
                _no(f"note {n} is not a general note that can be attached")

    day = _day(conn)
    pick = dict(location_id=loc, occupation_domains=(work,) if work else None, min_age=(age - 3) if age else 18,
                max_age=(age + 3) if age else 85, require_open_core=True if stage else None, required_stage=stage,
                demographic_sex=sex, allow_elsewhere=elsewhere, strict_stage=True)
    # A wife or a man's sibling/child carries his family name; the given name still comes from the identity.
    if full is None:
        for t in ties:
            tid = int(t["actor_id"])
            fam = _family_name(conn.execute("SELECT name FROM actors WHERE id=?", (tid,)).fetchone()[0])
            if fam and _sex(conn, tid) == "male" and (t["as"] in ("sibling", "child") or (t["as"] == "spouse" and sex == "female")):
                prof = find_background_candidate(conn, **pick)
                if prof is not None:
                    full = _free_name(conn, str(prof["given_name"]), fam, sex, int(prof["partition_id"]) * 10000 + int(prof["local_uid"]))
                break
    aid = resolve_background_person(conn, reason="Authored in play", demand_kind="authoring", subtype=f"authored_{work or 'person'}",
                                    name=full, **pick)
    if aid is None:
        _no(f"the settlement's population cannot supply that person{'' if elsewhere else ' (try from_elsewhere)'}; adapt the story")
    prof = conn.execute("SELECT * FROM background_person_profiles WHERE actor_id=?", (aid,)).fetchone()
    origin = None
    if int(conn.execute("SELECT current_location_id FROM actors WHERE id=?", (aid,)).fetchone()[0]) != loc:
        origin = conn.execute("SELECT name FROM locations WHERE id=?", (prof["current_location_id"],)).fetchone()[0]
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, aid))
    from .resolution_controller import _sync_sim_tier
    _sync_sim_tier(conn, aid, "TRACKED", day)  # resolution already made them TRACKED; give them a life of their own
    conn.execute("UPDATE actors SET notes=? WHERE id=?", ("Authored in play from a pre-existing identity.", aid))
    me_age = _age(conn, aid, day)

    for t in ties:
        tid, kind = int(t["actor_id"]), t["as"]
        if kind == "knows":
            for a, b in ((aid, tid), (tid, aid)):
                ensure_relationship(conn, a, b, day, familiarity=10)
        elif kind == "sibling":
            add_kinship(conn, aid, tid, "sibling", reciprocal_kind="sibling")
        elif kind in ("parent", "child"):
            gap = (me_age - _age(conn, tid, day)) if kind == "parent" else (_age(conn, tid, day) - me_age)
            if not 15 <= gap <= 55:
                _no("a parent must be 15 to 55 years older than the child")
            add_kinship(conn, *((aid, tid) if kind == "parent" else (tid, aid)), "parent", reciprocal_kind="child")
        else:
            if min(me_age, _age(conn, tid, day)) < 18 or _sex(conn, tid) == sex:
                _no("no union: both must be adults of opposite sex")
            if _has_active_union(conn, tid):
                _no("no union: that person is already married")
            why = prohibited_union_kinship_reason(conn, aid, tid)
            if why:
                _no(f"no union between close kin ({why})")
            create_union(conn, *((aid, tid) if sex == "male" else (tid, aid)))
    if wants:
        conn.execute("INSERT INTO goals(actor_id,description,priority,progress,status,created_day) VALUES (?,?,50,0,'active',?)", (aid, wants, day))
    for n in notes:
        conn.execute("UPDATE gm_notes SET subject_kind='actor',subject_id=? WHERE id=?", (aid, n))
    name = conn.execute("SELECT name FROM actors WHERE id=?", (aid,)).fetchone()[0]
    return {"status": "created", "kind": "person", "actor_id": aid, "name": name, "sex": sex, "age": me_age,
            "work": prof["occupation_domain"], "location": conn.execute("SELECT name FROM locations WHERE id=?", (loc,)).fetchone()[0],
            "from": origin}


_KINDS = {"person": _person}


def author(conn: sqlite3.Connection, me: int, kind: str, details: dict, call_id: str) -> dict:
    """Make something invented real, or raise AuthoringRefused saying why not. All-or-nothing."""
    if kind not in _KINDS:
        raise AuthoringRefused("kind must be one of " + ", ".join(_KINDS))
    d = details if isinstance(details, dict) else {}
    conn.execute("SAVEPOINT authoring")
    try:
        out = _KINDS[kind](conn, int(me), d, str(call_id))
    except BaseException as e:
        conn.execute("ROLLBACK TO SAVEPOINT authoring")
        conn.execute("RELEASE SAVEPOINT authoring")
        if isinstance(e, ValueError) and not isinstance(e, AuthoringRefused):
            raise AuthoringRefused(str(e)) from e
        raise
    conn.execute("RELEASE SAVEPOINT authoring")
    return out
