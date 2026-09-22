from __future__ import annotations

import json
import random
import sqlite3
from .relationships import adjust_relationship_pair, ensure_reciprocal_relationship
from .presence import actor_is_present_candidate
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _name(conn: sqlite3.Connection, actor_id: int | None) -> str:
    if actor_id is None:
        return "Unknown"
    row = conn.execute("SELECT name FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(row[0]) if row else f"Actor {actor_id}"


def _actor_is_living(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute("SELECT status FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not row or str(row[0]) == "deceased":
        return False
    prof = conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    return not prof or str(prof[0]) == "living"


def _active_household_member(conn: sqlite3.Connection, household_id: int, actor_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM household_members WHERE household_id=? AND actor_id=? AND status='active'",
        (household_id, actor_id),
    ).fetchone()


def _close_other_household_memberships(conn: sqlite3.Connection, actor_id: int, keep_household_id: int, day: int) -> None:
    conn.execute(
        "UPDATE household_members SET status='former',left_day=? WHERE actor_id=? AND household_id<>? AND status='active'",
        (day, actor_id, keep_household_id),
    )


def _repair_household_head(conn: sqlite3.Connection, household_id: int, day: int) -> None:
    hh = conn.execute("SELECT head_actor_id,status FROM households WHERE id=?", (household_id,)).fetchone()
    if not hh:
        return
    head = hh["head_actor_id"]
    if head is not None and _active_household_member(conn, household_id, int(head)):
        return
    replacement = conn.execute(
        "SELECT actor_id FROM household_members WHERE household_id=? AND status='active' ORDER BY authority DESC,actor_id ASC LIMIT 1",
        (household_id,),
    ).fetchone()
    if replacement:
        aid = int(replacement[0])
        conn.execute("UPDATE households SET head_actor_id=?,updated_day=? WHERE id=?", (aid, day, household_id))
        conn.execute("UPDATE household_members SET role='head',authority=100 WHERE household_id=? AND actor_id=?", (household_id, aid))
    else:
        conn.execute("UPDATE households SET head_actor_id=NULL,status='dissolved',updated_day=? WHERE id=?", (day, household_id))


def _record_life_event(conn: sqlite3.Connection, event_kind: str, summary: str, *, actor_id: int | None = None,
                       related_actor_id: int | None = None, household_id: int | None = None,
                       location_id: int | None = None, day: int | None = None,
                       metadata: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO life_events(day,event_kind,actor_id,related_actor_id,household_id,location_id,summary,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (_day(conn) if day is None else int(day), event_kind, actor_id, related_actor_id, household_id,
         location_id, summary, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _stage_for_age(age_days: int) -> str:
    years = age_days / 365.0
    if years < 2:
        return "infant"
    if years < 13:
        return "child"
    if years < 18:
        return "youth"
    if years < 60:
        return "adult"
    return "elder"


def set_life_profile(conn: sqlite3.Connection, actor_id: int, *, birth_day: int | None = None,
                     demographic_sex: str | None = None, origin_household_id: int | None = None,
                     current_household_id: int | None = None, family_formation_eligible: bool | None = None,
                     metadata: dict[str, Any] | None = None) -> None:
    day = _day(conn)
    stage = _stage_for_age(max(0, day - int(birth_day))) if birth_day is not None else "adult"
    conn.execute(
        """INSERT INTO actor_life_profiles(actor_id,birth_day,demographic_sex,life_stage,origin_household_id,current_household_id,
                                            family_formation_eligible,life_status,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,'living',?,?)
           ON CONFLICT(actor_id) DO UPDATE SET birth_day=COALESCE(excluded.birth_day,actor_life_profiles.birth_day),
             demographic_sex=COALESCE(excluded.demographic_sex,actor_life_profiles.demographic_sex),
             life_stage=CASE WHEN excluded.birth_day IS NOT NULL THEN excluded.life_stage ELSE actor_life_profiles.life_stage END,
             origin_household_id=COALESCE(excluded.origin_household_id,actor_life_profiles.origin_household_id),
             current_household_id=COALESCE(excluded.current_household_id,actor_life_profiles.current_household_id),
             family_formation_eligible=CASE WHEN ? THEN excluded.family_formation_eligible ELSE actor_life_profiles.family_formation_eligible END,
             last_review_day=excluded.last_review_day,
             metadata_json=CASE WHEN ? THEN excluded.metadata_json ELSE actor_life_profiles.metadata_json END""",
        (actor_id, birth_day, demographic_sex, stage, origin_household_id, current_household_id,
         1 if family_formation_eligible else 0, day, json.dumps(metadata or {}, sort_keys=True),
         1 if family_formation_eligible is not None else 0, 1 if metadata is not None else 0),
    )


def add_kinship(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int, kin_kind: str, *,
                reciprocal_kind: str | None = None, legal_status: str = "recognized",
                metadata: dict[str, Any] | None = None) -> tuple[int, int | None]:
    if actor_a_id == actor_b_id:
        raise ValueError("Kinship cannot relate an actor to themselves")
    day = _day(conn)
    existing = conn.execute(
        "SELECT id FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind=? AND legal_status=? AND ended_day IS NULL ORDER BY id LIMIT 1",
        (actor_a_id, actor_b_id, kin_kind, legal_status),
    ).fetchone()
    if existing:
        rid = None
        if reciprocal_kind:
            reciprocal = conn.execute(
                "SELECT id FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind=? AND legal_status=? AND ended_day IS NULL ORDER BY id LIMIT 1",
                (actor_b_id, actor_a_id, reciprocal_kind, legal_status),
            ).fetchone()
            if reciprocal:
                rid = int(reciprocal[0])
            else:
                cur2 = conn.execute(
                    "INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day,metadata_json) VALUES (?,?,?,?,?,?)",
                    (actor_b_id, actor_a_id, reciprocal_kind, legal_status, day, json.dumps(metadata or {}, sort_keys=True)),
                )
                rid = int(cur2.lastrowid)
        return int(existing[0]), rid
    cur = conn.execute(
        "INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day,metadata_json) VALUES (?,?,?,?,?,?)",
        (actor_a_id, actor_b_id, kin_kind, legal_status, day, json.dumps(metadata or {}, sort_keys=True)),
    )
    rid = None
    if reciprocal_kind:
        reciprocal = conn.execute(
            "SELECT id FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind=? AND legal_status=? AND ended_day IS NULL ORDER BY id LIMIT 1",
            (actor_b_id, actor_a_id, reciprocal_kind, legal_status),
        ).fetchone()
        if reciprocal:
            rid = int(reciprocal[0])
        else:
            cur2 = conn.execute(
                "INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day,metadata_json) VALUES (?,?,?,?,?,?)",
                (actor_b_id, actor_a_id, reciprocal_kind, legal_status, day, json.dumps(metadata or {}, sort_keys=True)),
            )
            rid = int(cur2.lastrowid)
    return int(cur.lastrowid), rid


def create_union(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int, *, household_id: int | None = None,
                 union_kind: str = "marriage", family_plan: dict[str, Any] | None = None,
                 create_new_household_name: str | None = None) -> int:
    from .civilian import create_household, add_household_member
    day = _day(conn)
    if actor_a_id == actor_b_id:
        raise ValueError("A union requires two distinct actors")
    if not _actor_is_living(conn, actor_a_id) or not _actor_is_living(conn, actor_b_id):
        raise ValueError("A union requires living actors")
    kin_reason = prohibited_union_kinship_reason(conn, actor_a_id, actor_b_id)
    if kin_reason:
        raise ValueError(f"FAMILY-02 prohibits union between close known kin: {kin_reason}")
    existing_union = conn.execute(
        "SELECT id FROM household_unions WHERE status='active' AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)) ORDER BY id LIMIT 1",
        (actor_a_id, actor_b_id, actor_b_id, actor_a_id),
    ).fetchone()
    if existing_union:
        return int(existing_union[0])
    # A person cannot enter two simultaneous active unions merely because two proposals were
    # pending when the first was accepted. Re-check the global invariant at mutation time.
    conflicting = conn.execute(
        "SELECT id,actor_a_id,actor_b_id FROM household_unions WHERE status='active' AND "
        "(actor_a_id IN (?,?) OR actor_b_id IN (?,?)) ORDER BY id LIMIT 1",
        (actor_a_id, actor_b_id, actor_a_id, actor_b_id),
    ).fetchone()
    if conflicting:
        raise ValueError("one or both actors are already in an active union")
    family_plan = dict(family_plan or {})
    if family_plan.get("auto_children"):
        resolved_parent = resolved_biological_birth_parent(conn, actor_a_id, actor_b_id)
        if resolved_parent is None:
            raise ValueError("FAMILY-02 auto-children require a resolved female/male reproductive pair")
        planned_parent = family_plan.get("birth_parent_actor_id")
        if planned_parent is not None and int(planned_parent) != int(resolved_parent):
            raise ValueError("FAMILY-02 family plan names an invalid biological birth parent")
        family_plan["birth_parent_actor_id"] = int(resolved_parent)
        family_plan.pop("birth_parent_unresolved", None)
    if create_new_household_name:
        location = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_a_id,)).fetchone()
        household_id = create_household(
            conn, create_new_household_name, head_actor_id=actor_a_id,
            location_id=int(location[0]) if location and location[0] else None,
            metadata={
                "authority": "ENGINE_DERIVED_HOUSEHOLD_FORMATION",
                "economic_resolution": "STRUCTURAL_ONLY",
                "economic_state": "NOT_SEPARATELY_QUANTIFIED",
                "reason": "Household existence is known; private finances are not inferred from absent source data.",
            },
        )
        add_household_member(conn, household_id, actor_b_id, role="partner", authority=80, dependency=0)
        _record_life_event(conn, "household_formation", f"{create_new_household_name} was formed.", actor_id=actor_a_id,
                           related_actor_id=actor_b_id, household_id=household_id)
    if household_id is not None:
        old_households: set[int] = set()
        for aid in (actor_a_id, actor_b_id):
            for r in conn.execute("SELECT household_id FROM household_members WHERE actor_id=? AND status='active' AND household_id<>?", (aid, household_id)).fetchall():
                old_households.add(int(r[0]))
            _close_other_household_memberships(conn, aid, household_id, day)
        for old_hid in old_households:
            _repair_household_head(conn, old_hid, day)
    cur = conn.execute(
        """INSERT INTO household_unions(actor_a_id,actor_b_id,household_id,union_kind,status,started_day,family_plan_json)
           VALUES (?,?,?,?, 'active', ?,?)""",
        (actor_a_id, actor_b_id, household_id, union_kind, day, json.dumps(family_plan, sort_keys=True)),
    )
    add_kinship(conn, actor_a_id, actor_b_id, "spouse", reciprocal_kind="spouse")
    if household_id is not None:
        for aid, role in ((actor_a_id, "head"), (actor_b_id, "partner")):
            conn.execute(
                """INSERT INTO household_members(household_id,actor_id,role,authority,dependency,joined_day,status)
                   VALUES (?,?,?,?,?,?, 'active')
                   ON CONFLICT(household_id,actor_id) DO UPDATE SET role=CASE WHEN household_members.role='head' THEN 'head' ELSE excluded.role END,
                     status='active',left_day=NULL""",
                (household_id, aid, role, 80 if role == "partner" else 100, 0, day),
            )
            conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (household_id, aid))
    _record_life_event(conn, "union", f"{_name(conn, actor_a_id)} and {_name(conn, actor_b_id)} entered a {union_kind}.",
                       actor_id=actor_a_id, related_actor_id=actor_b_id, household_id=household_id)
    return int(cur.lastrowid)


def end_union(conn: sqlite3.Connection, union_id: int, *, status: str = "dissolved", reason: str | None = None) -> None:
    if status not in {"separated", "dissolved"}:
        raise ValueError("Union end status must be separated or dissolved")
    day = _day(conn)
    row = conn.execute("SELECT * FROM household_unions WHERE id=? AND status='active'", (union_id,)).fetchone()
    if not row:
        raise ValueError("Unknown or inactive household union")
    a, b = int(row["actor_a_id"]), int(row["actor_b_id"])
    conn.execute("UPDATE household_unions SET status=?,ended_day=? WHERE id=?", (status, day, union_id))
    conn.execute(
        "UPDATE kinship_links SET legal_status='former',ended_day=? WHERE kin_kind='spouse' AND ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))",
        (day, a, b, b, a),
    )
    _record_life_event(conn, "separation" if status == "separated" else "dissolution",
                       f"{_name(conn, a)} and {_name(conn, b)} ended their {row['union_kind']}." + (f" {reason}" if reason else ""),
                       actor_id=a, related_actor_id=b, household_id=row["household_id"], day=day)


def update_family_plan(conn: sqlite3.Connection, union_id: int, *, desired_children: int | None = None,
                       auto_children: bool | None = None, birth_parent_actor_id: int | None = None,
                       earliest_next_child_day: int | None = None, spacing_days: int | None = None) -> None:
    row = conn.execute("SELECT family_plan_json FROM household_unions WHERE id=?", (union_id,)).fetchone()
    if not row:
        raise ValueError("Unknown household union")
    urow = conn.execute("SELECT actor_a_id,actor_b_id FROM household_unions WHERE id=?", (union_id,)).fetchone()
    plan = json.loads(row[0] or "{}")
    resolved_parent = resolved_biological_birth_parent(conn, int(urow[0]), int(urow[1])) if urow else None
    if birth_parent_actor_id is not None and (resolved_parent is None or int(birth_parent_actor_id) != int(resolved_parent)):
        raise ValueError("FAMILY-02 family plan names an invalid biological birth parent")
    if auto_children is True and resolved_parent is None:
        raise ValueError("FAMILY-02 auto-children require a resolved female/male reproductive pair")
    if auto_children is True and birth_parent_actor_id is None:
        birth_parent_actor_id = int(resolved_parent)
    for key, val in {
        "desired_children": desired_children, "auto_children": auto_children,
        "birth_parent_actor_id": birth_parent_actor_id, "earliest_next_child_day": earliest_next_child_day,
        "spacing_days": spacing_days,
    }.items():
        if val is not None:
            plan[key] = val
    conn.execute("UPDATE household_unions SET family_plan_json=? WHERE id=?", (json.dumps(plan, sort_keys=True), union_id))


def _existing_children(conn: sqlite3.Connection, actor_a: int, actor_b: int) -> list[int]:
    a = {int(r[0]) for r in conn.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent' AND legal_status='recognized'", (actor_a,)).fetchall()}
    b = {int(r[0]) for r in conn.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent' AND legal_status='recognized'", (actor_b,)).fetchall()}
    return sorted(a & b)


def _children_of_either_parent(conn: sqlite3.Connection, actor_a: int, actor_b: int) -> list[int]:
    out: set[int] = set()
    for parent in (actor_a, actor_b):
        out.update(int(r[0]) for r in conn.execute(
            "SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent' AND legal_status='recognized' AND ended_day IS NULL",
            (parent,),
        ).fetchall())
    return sorted(out)


def register_birth(conn: sqlite3.Connection, union_id: int, *, child_name: str | None = None,
                   demographic_sex: str = "unspecified", day: int | None = None) -> int:
    row = conn.execute("SELECT * FROM household_unions WHERE id=? AND status='active'", (union_id,)).fetchone()
    if not row:
        raise ValueError("Birth requires an active household union")
    birth_day = _day(conn) if day is None else int(day)
    if birth_day != _day(conn):
        raise ValueError("Birth registration must occur on the current story day; use historical crystallization for retroactive births")
    if birth_day < int(row["started_day"]):
        raise ValueError("Birth cannot predate the union")
    a, b = int(row["actor_a_id"]), int(row["actor_b_id"])
    if not _actor_is_living(conn, a) or not _actor_is_living(conn, b):
        raise ValueError("Birth requires both union actors to be living")
    birth_parent = resolved_biological_birth_parent(conn, a, b)
    if birth_parent is None:
        raise ValueError("FAMILY-02 birth requires a resolved female/male reproductive pair")
    plan = json.loads(row["family_plan_json"] or "{}")
    planned_parent = plan.get("birth_parent_actor_id")
    if planned_parent is not None and int(planned_parent) != int(birth_parent):
        raise ValueError("FAMILY-02 birth parent conflicts with resolved demographic sex")
    hid = row["household_id"]
    existing = _existing_children(conn, a, b)
    siblings = _children_of_either_parent(conn, a, b)
    if child_name is None:
        hname = conn.execute("SELECT name FROM households WHERE id=?", (hid,)).fetchone() if hid else None
        base = str(hname[0]) if hname else f"Union {union_id}"
        child_name = f"[Latent child] {base} D{birth_day}-{len(existing)+1}"
    loc = conn.execute("SELECT location_id FROM households WHERE id=?", (hid,)).fetchone() if hid else None
    location_id = int(loc[0]) if loc and loc[0] is not None else None
    cur = conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,is_demo) VALUES (?,'character','child',?,?, 'active',0)",
        (child_name, location_id, location_id),
    )
    child = int(cur.lastrowid)
    set_life_profile(conn, child, birth_day=birth_day, demographic_sex=demographic_sex,
                     origin_household_id=hid, current_household_id=hid, family_formation_eligible=False,
                     metadata={"generated_by":"v0.19 life-course"})
    if hid:
        from .civilian import add_household_member
        add_household_member(conn, hid, child, role="child", authority=0, dependency=100)
        head = conn.execute("SELECT head_actor_id FROM households WHERE id=?", (hid,)).fetchone()
        sponsor = int(head[0]) if head and head[0] is not None and _actor_is_living(conn, int(head[0])) else a
        conn.execute(
            """INSERT INTO household_dependencies(household_id,dependent_actor_id,sponsor_actor_id,dependency_kind,support_level,status,started_day)
               VALUES (?,?,?,?,100,'active',?)""",
            (hid, child, sponsor, "child", birth_day),
        )
    for parent in (a, b):
        add_kinship(conn, parent, child, "parent", reciprocal_kind="child")
    for sib in siblings:
        if sib != child:
            add_kinship(conn, child, sib, "sibling", reciprocal_kind="sibling")
    _record_life_event(conn, "birth", f"{child_name} was born into the household.", actor_id=child,
                       related_actor_id=a, household_id=hid, location_id=location_id, day=birth_day)
    return child


def create_guardianship(conn: sqlite3.Connection, guardian_actor_id: int, ward_actor_id: int, *,
                        household_id: int | None = None, authority: float = 70, support_level: float = 70) -> int:
    day = _day(conn)
    if guardian_actor_id == ward_actor_id:
        raise ValueError("Guardian and ward must be distinct actors")
    if not _actor_is_living(conn, guardian_actor_id) or not _actor_is_living(conn, ward_actor_id):
        raise ValueError("Guardianship requires living actors")
    existing = conn.execute(
        "SELECT id FROM guardianships WHERE guardian_actor_id=? AND ward_actor_id=? AND status='active' ORDER BY id LIMIT 1",
        (guardian_actor_id, ward_actor_id),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO guardianships(guardian_actor_id,ward_actor_id,household_id,authority,support_level,status,started_day)
           VALUES (?,?,?,?,?,'active',?)""",
        (guardian_actor_id, ward_actor_id, household_id, authority, support_level, day),
    )
    add_kinship(conn, guardian_actor_id, ward_actor_id, "guardian", reciprocal_kind="ward")
    if household_id:
        from .civilian import add_household_member
        old_households = [int(r[0]) for r in conn.execute(
            "SELECT household_id FROM household_members WHERE actor_id=? AND status='active' AND household_id<>?",
            (ward_actor_id, household_id),
        ).fetchall()]
        _close_other_household_memberships(conn, ward_actor_id, household_id, day)
        for old_hid in old_households:
            _repair_household_head(conn, old_hid, day)
        conn.execute(
            "UPDATE household_dependencies SET status='ended',ended_day=? WHERE dependent_actor_id=? AND household_id<>? AND status='active'",
            (day, ward_actor_id, household_id),
        )
        add_household_member(conn, household_id, ward_actor_id, role="ward", authority=0, dependency=90)
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (household_id, ward_actor_id))
        conn.execute("""INSERT INTO household_dependencies(household_id,dependent_actor_id,sponsor_actor_id,dependency_kind,support_level,status,started_day)
                        VALUES (?,?,?,?,?,'active',?)""",
                     (household_id, ward_actor_id, guardian_actor_id, "ward", support_level, day))
    _record_life_event(conn, "guardianship", f"{_name(conn, guardian_actor_id)} became guardian of {_name(conn, ward_actor_id)}.",
                       actor_id=guardian_actor_id, related_actor_id=ward_actor_id, household_id=household_id)
    return int(cur.lastrowid)


def end_guardianship(conn: sqlite3.Connection, guardianship_id: int, *, reason: str | None = None) -> None:
    day = _day(conn)
    row = conn.execute("SELECT * FROM guardianships WHERE id=? AND status='active'", (guardianship_id,)).fetchone()
    if not row:
        raise ValueError("Unknown or inactive guardianship")
    g, w = int(row["guardian_actor_id"]), int(row["ward_actor_id"])
    conn.execute("UPDATE guardianships SET status='ended',ended_day=? WHERE id=?", (day, guardianship_id))
    conn.execute(
        "UPDATE kinship_links SET legal_status='former',ended_day=? WHERE ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=? AND kin_kind='guardian') OR (actor_a_id=? AND actor_b_id=? AND kin_kind='ward'))",
        (day, g, w, w, g),
    )
    if row["household_id"] is not None:
        conn.execute(
            "UPDATE household_dependencies SET status='ended',ended_day=? WHERE household_id=? AND dependent_actor_id=? AND sponsor_actor_id=? AND dependency_kind='ward' AND status='active'",
            (day, row["household_id"], w, g),
        )
    _record_life_event(conn, "guardianship", f"Guardianship of {_name(conn, w)} by {_name(conn, g)} ended." + (f" {reason}" if reason else ""),
                       actor_id=g, related_actor_id=w, household_id=row["household_id"], day=day)


def split_household(conn: sqlite3.Connection, source_household_id: int, new_name: str, moving_actor_ids: list[int], *,
                    new_head_actor_id: int, destination_location_id: int | None = None,
                    wealth_share: float = 0.0, liquidity_share: float = 0.0) -> int:
    from .civilian import create_household, add_household_member
    src = conn.execute("SELECT * FROM households WHERE id=?", (source_household_id,)).fetchone()
    if not src:
        raise ValueError("Unknown source household")
    if not 0.0 <= wealth_share <= 1.0 or not 0.0 <= liquidity_share <= 1.0:
        raise ValueError("Household split shares must be between 0 and 1")
    moving = sorted(set(moving_actor_ids + [new_head_actor_id]))
    for aid in moving:
        if not _active_household_member(conn, source_household_id, aid):
            raise ValueError(f"Actor {aid} is not an active member of the source household")
    location_id = destination_location_id if destination_location_id is not None else src["location_id"]
    wealth = float(src["wealth"]) * wealth_share
    liquidity = float(src["liquidity"]) * liquidity_share
    hid = create_household(conn, new_name, head_actor_id=new_head_actor_id, location_id=location_id,
                           wealth=wealth, liquidity=liquidity, cohesion=float(src["cohesion"]), hospitality=float(src["hospitality"]))
    conn.execute("UPDATE households SET wealth=wealth-?,liquidity=liquidity-?,updated_day=? WHERE id=?",
                 (wealth, liquidity, _day(conn), source_household_id))
    for aid in moving:
        old = _active_household_member(conn, source_household_id, aid)
        conn.execute("UPDATE household_members SET status='former',left_day=? WHERE household_id=? AND actor_id=? AND status='active'", (_day(conn), source_household_id, aid))
        if aid != new_head_actor_id:
            add_household_member(conn, hid, aid, role=str(old["role"]) if old else "member",
                                 authority=float(old["authority"]) if old else 20, dependency=float(old["dependency"]) if old else 20)
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (hid, aid))
        if location_id is not None:
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (location_id, aid))
        conn.execute("UPDATE household_dependencies SET household_id=? WHERE household_id=? AND dependent_actor_id=? AND status='active'",
                     (hid, source_household_id, aid))
        conn.execute("UPDATE guardianships SET household_id=? WHERE household_id=? AND ward_actor_id=? AND status='active'",
                     (hid, source_household_id, aid))
        conn.execute("UPDATE household_service_terms SET household_id=? WHERE household_id=? AND actor_id=? AND status='active'",
                     (hid, source_household_id, aid))
    # A union belongs to the new household only when both partners moved together. If only one moved,
    # it no longer truthfully belongs to the old shared household.
    for u in conn.execute("SELECT id,actor_a_id,actor_b_id FROM household_unions WHERE household_id=? AND status='active'", (source_household_id,)).fetchall():
        am, bm = int(u["actor_a_id"]) in moving, int(u["actor_b_id"]) in moving
        if am and bm:
            conn.execute("UPDATE household_unions SET household_id=? WHERE id=?", (hid, u["id"]))
        elif am or bm:
            conn.execute("UPDATE household_unions SET household_id=NULL WHERE id=?", (u["id"],))
    if src["head_actor_id"] is not None and int(src["head_actor_id"]) in moving:
        _repair_household_head(conn, source_household_id, _day(conn))
    else:
        remaining = conn.execute("SELECT COUNT(*) FROM household_members WHERE household_id=? AND status='active'", (source_household_id,)).fetchone()[0]
        if int(remaining) == 0:
            _repair_household_head(conn, source_household_id, _day(conn))
    _record_life_event(conn, "household_split", f"{new_name} separated from {src['name']}.", actor_id=new_head_actor_id,
                       household_id=hid, location_id=location_id, metadata={"source_household_id": source_household_id})
    return hid


def add_service_term(conn: sqlite3.Connection, household_id: int, actor_id: int, service_role: str, *,
                     review_in_days: int = 365, loyalty: float = 50, satisfaction: float = 50,
                     renewal_bias: float = 50) -> int:
    from .civilian import add_household_member
    day = _day(conn)
    hh = conn.execute("SELECT status FROM households WHERE id=?", (household_id,)).fetchone()
    if not hh or str(hh[0]) in {"dissolved", "historical"}:
        raise ValueError("Service requires an active household")
    if not _actor_is_living(conn, actor_id):
        raise ValueError("Service requires a living actor")
    existing = conn.execute(
        "SELECT id FROM household_service_terms WHERE household_id=? AND actor_id=? AND service_role=? AND status='active' ORDER BY id LIMIT 1",
        (household_id, actor_id, service_role),
    ).fetchone()
    if existing:
        return int(existing[0])
    cur = conn.execute(
        """INSERT INTO household_service_terms(household_id,actor_id,service_role,start_day,review_day,loyalty,satisfaction,renewal_bias,status)
           VALUES (?,?,?,?,?,?,?,?,'active')""",
        (household_id, actor_id, service_role, day, day + max(1, review_in_days), loyalty, satisfaction, renewal_bias),
    )
    if not _active_household_member(conn, household_id, actor_id):
        add_household_member(conn, household_id, actor_id, role=service_role, authority=15 if service_role not in ('steward','retainer') else 35,
                             dependency=20)
    _record_life_event(conn, "service_change", f"{_name(conn, actor_id)} entered {service_role} service in household #{household_id}.",
                       actor_id=actor_id, household_id=household_id, day=day)
    return int(cur.lastrowid)


def schedule_household_migration(conn: sqlite3.Connection, household_id: int, destination_location_id: int,
                                 planned_day: int, *, reason: str | None = None) -> int:
    day = _day(conn)
    hh = conn.execute("SELECT location_id,status FROM households WHERE id=?", (household_id,)).fetchone()
    if not hh or str(hh["status"]) in {"dissolved", "historical"}:
        raise ValueError("Migration requires an active household")
    if int(planned_day) < day:
        raise ValueError("Migration cannot be scheduled in the past")
    if hh["location_id"] is not None and int(hh["location_id"]) == int(destination_location_id):
        raise ValueError("Migration destination is already the household location")
    if not conn.execute("SELECT 1 FROM locations WHERE id=?", (destination_location_id,)).fetchone():
        raise ValueError("Unknown migration destination")
    # A newly scheduled move supersedes any earlier unresolved plan for the same household.
    if conn.execute("SELECT 1 FROM household_migration_plans WHERE household_id=? AND status='in_transit'", (household_id,)).fetchone():
        raise ValueError("Household already has a migration in transit")
    conn.execute("UPDATE household_migration_plans SET status='cancelled' WHERE household_id=? AND status='planned'", (household_id,))
    cur = conn.execute(
        """INSERT INTO household_migration_plans(household_id,destination_location_id,planned_day,reason,status,created_day)
           VALUES (?,?,?,?,'planned',?)""",
        (household_id, destination_location_id, planned_day, reason, day),
    )
    return int(cur.lastrowid)


def set_demographic_cohort(conn: sqlite3.Connection, location_id: int, cohort_key: str, age_band: str, population: float, *,
                           annual_birth_pressure: float = 0, annual_migration_rate: float = 0,
                           metadata: dict[str, Any] | None = None) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT INTO demographic_cohorts(location_id,cohort_key,age_band,population,annual_birth_pressure,annual_migration_rate,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(location_id,cohort_key,age_band) DO UPDATE SET population=excluded.population,
             annual_birth_pressure=excluded.annual_birth_pressure,annual_migration_rate=excluded.annual_migration_rate,
             last_review_day=excluded.last_review_day,metadata_json=excluded.metadata_json""",
        (location_id, cohort_key, age_band, population, annual_birth_pressure, annual_migration_rate, day,
         json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(conn.execute("SELECT id FROM demographic_cohorts WHERE location_id=? AND cohort_key=? AND age_band=?",
                            (location_id, cohort_key, age_band)).fetchone()[0])


def mark_actor_deceased(conn: sqlite3.Connection, actor_id: int, *, reason: str = "deceased",
                        event_logger: Callable[..., int] | None = None) -> None:
    day = _day(conn)
    prof = conn.execute("SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?", (actor_id,)).fetchone()
    hid = int(prof[0]) if prof and prof[0] is not None else None
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    location_id = int(loc[0]) if loc and loc[0] is not None else None
    conn.execute("UPDATE actors SET status='deceased' WHERE id=?", (actor_id,))
    conn.execute("UPDATE actor_life_profiles SET life_status='deceased',last_review_day=? WHERE actor_id=?", (day, actor_id))
    # A dead character has no future autonomous review. Historical resolution metadata is
    # retained elsewhere, but the live scheduler row must disappear immediately.
    conn.execute("DELETE FROM simulation_profiles WHERE actor_id=?", (actor_id,))
    conn.execute("UPDATE household_members SET status='deceased',left_day=? WHERE actor_id=? AND status='active'", (day, actor_id))
    unions = conn.execute("SELECT id,actor_a_id,actor_b_id FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (actor_id, actor_id)).fetchall()
    for u in unions:
        other = int(u["actor_b_id"] if int(u["actor_a_id"]) == actor_id else u["actor_a_id"])
        conn.execute("UPDATE household_unions SET status='widowed',ended_day=? WHERE id=?", (day, u["id"]))
        conn.execute("UPDATE kinship_links SET legal_status='former',ended_day=? WHERE kin_kind='spouse' AND actor_a_id IN (?,?) AND actor_b_id IN (?,?) AND legal_status='recognized'",
                     (day, actor_id, other, actor_id, other))
    conn.execute("UPDATE household_service_terms SET status='former',end_day=? WHERE actor_id=? AND status='active'", (day, actor_id))
    guardian_rows = conn.execute("SELECT id,guardian_actor_id,ward_actor_id FROM guardianships WHERE status='active' AND (guardian_actor_id=? OR ward_actor_id=?)", (actor_id, actor_id)).fetchall()
    for g in guardian_rows:
        conn.execute("UPDATE guardianships SET status='ended',ended_day=? WHERE id=?", (day, g["id"]))
        ga, wa = int(g["guardian_actor_id"]), int(g["ward_actor_id"])
        conn.execute("UPDATE kinship_links SET legal_status='former',ended_day=? WHERE ended_day IS NULL AND ((actor_a_id=? AND actor_b_id=? AND kin_kind='guardian') OR (actor_a_id=? AND actor_b_id=? AND kin_kind='ward'))",
                     (day, ga, wa, wa, ga))
        if wa == actor_id:
            conn.execute("UPDATE household_dependencies SET status='ended',ended_day=? WHERE dependent_actor_id=? AND dependency_kind='ward' AND status='active'", (day, wa))
        else:
            conn.execute("UPDATE household_dependencies SET sponsor_actor_id=NULL WHERE dependent_actor_id=? AND sponsor_actor_id=? AND dependency_kind='ward' AND status='active'", (wa, ga))
    conn.execute("UPDATE household_dependencies SET sponsor_actor_id=NULL WHERE sponsor_actor_id=? AND status='active'", (actor_id,))
    conn.execute("UPDATE household_dependencies SET status='ended',ended_day=? WHERE dependent_actor_id=? AND status='active'", (day, actor_id))
    # Health treatment cannot continue after death, regardless of which subsystem recorded the death.
    try:
        conn.execute("UPDATE medical_treatments SET status='stopped',end_day=COALESCE(end_day,?) WHERE actor_id=? AND status='active'", (day, actor_id))
        conn.execute("UPDATE medical_treatments SET status='stopped',end_day=COALESCE(end_day,?) WHERE provider_actor_id=? AND status='active'", (day, actor_id))
        conn.execute("UPDATE actor_health_profiles SET last_review_day=?,next_review_day=? WHERE actor_id=?", (day, day, actor_id))
    except sqlite3.OperationalError:
        pass
    _record_life_event(conn, "death", f"{_name(conn, actor_id)} died: {reason}.", actor_id=actor_id, household_id=hid, location_id=location_id)
    if event_logger:
        event_logger(day=day, event_type="life:death", title=f"Death: {_name(conn, actor_id)}", summary=reason,
                     severity=2, source_actor_id=actor_id, target_actor_ids=(), location_id=location_id)



def _age_years(profile: sqlite3.Row, day: int) -> float | None:
    if profile['birth_day'] is None:
        return None
    return max(0.0,(day-int(profile['birth_day']))/365.0)


def _family_eligible(profile: sqlite3.Row, day: int) -> bool:
    """Social eligibility for courtship/household formation, not a fertility guarantee."""
    if str(profile['life_status'])!='living' or str(profile['life_stage'])!='adult':
        return False
    age=_age_years(profile,day)
    if age is None:
        return bool(profile['family_formation_eligible'])
    return 18.0 <= age <= 70.0


def _known_close_kin(conn: sqlite3.Connection, a: int, b: int) -> bool:
    return conn.execute("""SELECT 1 FROM kinship_links WHERE ended_day IS NULL AND
                           ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))
                           AND kin_kind NOT IN ('spouse') LIMIT 1""",(a,b,b,a)).fetchone() is not None


def _has_active_union(conn: sqlite3.Connection, actor_id: int) -> bool:
    return conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?) LIMIT 1",(actor_id,actor_id)).fetchone() is not None


def _parents(conn: sqlite3.Connection, actor_id: int) -> set[int]:
    return {int(r[0]) for r in conn.execute(
        "SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND kin_kind='parent' AND legal_status='recognized' AND ended_day IS NULL",
        (actor_id,),
    ).fetchall()}


def prohibited_union_kinship_reason(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int) -> str | None:
    """Return a hard FAMILY-02 kinship prohibition, without guessing culture-specific cousin rules."""
    if actor_a_id == actor_b_id:
        return "same_actor"
    direct = conn.execute(
        """SELECT kin_kind FROM kinship_links WHERE ended_day IS NULL AND legal_status='recognized' AND
           ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)) AND kin_kind<>'spouse'
           ORDER BY id LIMIT 1""",
        (actor_a_id, actor_b_id, actor_b_id, actor_a_id),
    ).fetchone()
    if direct:
        return f"direct_{direct[0]}"
    pa, pb = _parents(conn, actor_a_id), _parents(conn, actor_b_id)
    if pa & pb:
        return "shared_parent"
    # Grandparent/grandchild.
    grandparents_a = {gp for p in pa for gp in _parents(conn, p)}
    grandparents_b = {gp for p in pb for gp in _parents(conn, p)}
    if actor_a_id in grandparents_b or actor_b_id in grandparents_a:
        return "grandparent_descendant"
    # Aunt/uncle with niece/nephew: one actor shares a parent with the other's parent.
    if any(_parents(conn, p) & pa for p in pb) or any(_parents(conn, p) & pb for p in pa):
        return "aunt_uncle_niece_nephew"
    return None


def resolved_biological_birth_parent(conn: sqlite3.Connection, actor_a_id: int, actor_b_id: int) -> int | None:
    """Return the explicit female birth parent only for a resolved female/male reproductive pair."""
    rows = {}
    for aid in (actor_a_id, actor_b_id):
        row = conn.execute("SELECT demographic_sex,life_status FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()
        if not row or str(row['life_status']) != 'living':
            return None
        sex = str(row['demographic_sex'] or 'unspecified')
        if sex not in {'female','male'}:
            return None
        rows[aid] = sex
    females = [aid for aid, sex in rows.items() if sex == 'female']
    males = [aid for aid, sex in rows.items() if sex == 'male']
    return females[0] if len(females) == 1 and len(males) == 1 else None


def _contact_rng(conn: sqlite3.Connection, a: int, b: int, context_id: int, salt: int=0) -> random.Random:
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed*1000003 + min(a,b)*1709 + max(a,b)*9151 + int(context_id)*271 + salt)


def _resolve_social_contacts(conn: sqlite3.Connection, day: int) -> int:
    """Grow sparse courtship-capable relationships only from sustained shared context.

    This is not matchmaking. Most eligible pairs never become a contact, and contact only creates
    familiarity; the existing interaction/consent system still owns any later union proposal.
    """
    changed=0
    # Existing contact familiarity grows slowly and can also cool if one party is no longer eligible.
    due=conn.execute("SELECT * FROM social_contact_links WHERE status='active' AND next_review_day<=? ORDER BY id",(day,)).fetchall()
    for link in due:
        a,b=int(link['actor_a_id']),int(link['actor_b_id'])
        pa=conn.execute("SELECT * FROM actor_life_profiles WHERE actor_id=?",(a,)).fetchone(); pb=conn.execute("SELECT * FROM actor_life_profiles WHERE actor_id=?",(b,)).fetchone()
        if not pa or not pb or not _family_eligible(pa,day) or not _family_eligible(pb,day) or _has_active_union(conn,a) or _has_active_union(conn,b):
            conn.execute("UPDATE social_contact_links SET status='dormant',last_review_day=?,next_review_day=? WHERE id=?",(day,day+365,int(link['id'])))
            continue
        affinity=float(link['affinity'])
        # Sustained shared context is reciprocal contact, but later reactions can diverge.
        delta=max(-1.5,min(5.0,(affinity-42.0)/18.0))
        adjust_relationship_pair(
            conn, a, b, day,
            symmetric={"trust_delta": delta, "stance_delta": max(-1.0,delta*0.75), "familiarity_delta": 3.0},
        )
        conn.execute("UPDATE social_contact_links SET last_review_day=?,next_review_day=? WHERE id=?",(day,day+180,int(link['id'])))
        changed+=1

    # At most one new institutional contact per single eligible actor per annual review window.
    candidates=conn.execute("""SELECT lp.actor_id,lp.birth_day,im.institution_actor_id,a.current_location_id
        FROM actor_life_profiles lp JOIN actors a ON a.id=lp.actor_id
        JOIN institution_memberships im ON im.member_actor_id=lp.actor_id AND im.status='active'
        WHERE lp.life_status='living' AND lp.life_stage='adult' AND lp.family_formation_eligible=1
          AND a.status='active' AND a.actor_type='character'
          AND NOT EXISTS (SELECT 1 FROM household_unions u WHERE u.status='active' AND (u.actor_a_id=lp.actor_id OR u.actor_b_id=lp.actor_id))
        ORDER BY im.institution_actor_id,lp.actor_id""").fetchall()
    by_inst={}
    for r in candidates: by_inst.setdefault(int(r['institution_actor_id']),[]).append(r)
    already=set()
    for inst,rows in by_inst.items():
        inst_loc_row=conn.execute("SELECT current_location_id FROM actors WHERE id=?",(inst,)).fetchone()
        inst_loc=int(inst_loc_row[0]) if inst_loc_row and inst_loc_row[0] is not None else None
        if inst_loc is None:
            continue
        for i,r in enumerate(rows):
            a=int(r['actor_id'])
            if a in already: continue
            if conn.execute("SELECT 1 FROM social_contact_links WHERE status='active' AND (actor_a_id=? OR actor_b_id=?) AND started_day>? LIMIT 1",(a,a,day-365)).fetchone(): continue
            agea=(day-int(r['birth_day']))/365.0 if r['birth_day'] is not None else None
            options=[]
            for q in rows[i+1:]:
                b=int(q['actor_id'])
                if b in already or _known_close_kin(conn,a,b): continue
                if conn.execute("SELECT 1 FROM social_contact_links WHERE status='active' AND (actor_a_id=? OR actor_b_id=?) AND started_day>? LIMIT 1",(b,b,day-365)).fetchone(): continue
                lo,hi=sorted((a,b))
                purpose=f"social_contact:{inst}:{lo}:{hi}"
                if not actor_is_present_candidate(conn,a,inst_loc,day=day,purpose=purpose+':a'):
                    continue
                if not actor_is_present_candidate(conn,b,inst_loc,day=day,purpose=purpose+':b'):
                    continue
                ageb=(day-int(q['birth_day']))/365.0 if q['birth_day'] is not None else None
                if agea is not None and ageb is not None and abs(agea-ageb)>20: continue
                lo,hi=sorted((a,b))
                if conn.execute("SELECT 1 FROM social_contact_links WHERE actor_a_id=? AND actor_b_id=? AND status IN ('active','dormant') LIMIT 1",(lo,hi)).fetchone(): continue
                rng=_contact_rng(conn,lo,hi,inst)
                affinity=35.0+rng.random()*55.0
                if affinity<58.0: continue
                options.append((affinity,lo,hi))
            if not options: continue
            affinity,lo,hi=max(options,key=lambda x:(x[0],-x[2]))
            conn.execute("""INSERT INTO social_contact_links(actor_a_id,actor_b_id,context_kind,context_id,affinity,started_day,last_review_day,next_review_day,status,metadata_json)
                          VALUES (?,?,'institution',?,?,?, ?,?,'active','{\"authority\":\"ENGINE_DERIVED_SHARED_CONTEXT\"}')""",
                         (lo,hi,inst,affinity,day,day,day+180))
            ensure_reciprocal_relationship(conn, lo, hi, day, stance=8, trust=8, familiarity=10)
            already.update((lo,hi)); changed+=1
    return changed

def _review_profiles(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    rows = conn.execute("SELECT * FROM actor_life_profiles WHERE life_status='living' AND last_review_day<?", (day,)).fetchall()
    for row in rows:
        old = str(row["life_stage"])
        new = _stage_for_age(max(0, day - int(row["birth_day"]))) if row["birth_day"] is not None else old
        eligible=1 if _family_eligible(row,day) and new=='adult' else 0
        # Re-evaluate using the newly derived life stage; unknown-age profiles retain explicit source state.
        if row['birth_day'] is not None:
            age=max(0.0,(day-int(row['birth_day']))/365.0)
            eligible=1 if new=='adult' and 18.0<=age<=70.0 else 0
        conn.execute("UPDATE actor_life_profiles SET life_stage=?,family_formation_eligible=?,last_review_day=? WHERE actor_id=?", (new,eligible,day,row["actor_id"]))
        if old != new and new in ("youth","adult","elder"):
            summary = f"{_name(conn, int(row['actor_id']))} entered the {new} life stage."
            _record_life_event(conn, "coming_of_age" if new == "adult" else "other", summary, actor_id=int(row["actor_id"]),
                               household_id=row["current_household_id"], day=day)
            if event_logger and new == "adult":
                event_logger(day=day, event_type="life:coming_of_age", title=f"Coming of age: {_name(conn, int(row['actor_id']))}",
                             summary=summary, severity=1, source_actor_id=int(row["actor_id"]), target_actor_ids=(), location_id=None)
        count += 1
    return count


def _resolve_planned_births(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    for u in conn.execute("SELECT * FROM household_unions WHERE status='active'").fetchall():
        plan = json.loads(u["family_plan_json"] or "{}")
        if not plan.get("auto_children"):
            continue
        desired = int(plan.get("desired_children", 0))
        children = _existing_children(conn, int(u["actor_a_id"]), int(u["actor_b_id"]))
        if desired <= len(children):
            continue
        due = int(plan.get("earliest_next_child_day", int(u["started_day"]) + int(plan.get("spacing_days", 730))))
        if day < due:
            continue
        a, b = int(u["actor_a_id"]), int(u["actor_b_id"])
        if not _actor_is_living(conn, a) or not _actor_is_living(conn, b):
            continue
        birth_parent = resolved_biological_birth_parent(conn, a, b)
        if birth_parent is None:
            # Unknown demographic sex or a non-female/male reproductive pairing is unresolved,
            # not permission to fabricate a biological birth.
            continue
        planned_parent = plan.get("birth_parent_actor_id")
        if planned_parent is not None and int(planned_parent) != int(birth_parent):
            continue
        p = conn.execute("SELECT family_formation_eligible,life_status,birth_day FROM actor_life_profiles WHERE actor_id=?", (int(birth_parent),)).fetchone()
        if not p or not bool(p[0]) or str(p[1]) != "living":
            continue
        age = _age_years(p, day)
        if age is None or not 18.0 <= age <= 48.0:
            continue
        if planned_parent is None:
            plan["birth_parent_actor_id"] = int(birth_parent)
            plan.pop("birth_parent_unresolved", None)
        # register_birth requires the current story day, which is exactly the due-processing day.
        child = register_birth(conn, int(u["id"]), day=day)
        plan["earliest_next_child_day"] = day + max(365, int(plan.get("spacing_days", 730)))
        conn.execute("UPDATE household_unions SET family_plan_json=? WHERE id=?", (json.dumps(plan, sort_keys=True), u["id"]))
        if event_logger:
            event_logger(day=day, event_type="life:birth", title=f"Birth: {_name(conn, child)}",
                         summary=f"A child was born into household #{u['household_id']}.", severity=1,
                         source_actor_id=child, target_actor_ids=(a, b), location_id=None)
        count += 1
    return count


def _adult_living_actor(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute(
        """SELECT a.status,lp.life_status,lp.life_stage FROM actors a
           JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""",
        (actor_id,),
    ).fetchone()
    return bool(row and str(row['status']) == 'active' and str(row['life_status']) == 'living'
                and str(row['life_stage']) in {'adult','elder'})


def _resolve_guardianship_needs(conn: sqlite3.Connection, day: int) -> int:
    """Repair real dependent-child support gaps using only already-existing household adults.

    This resolver never creates a relative, moves a child to a guessed household, or assigns a remote
    stranger. It acts only when an active child/ward dependency has actually lost its sponsor and a
    living adult already in the same household can carry the legal/support role.
    """
    rows = conn.execute(
        """SELECT d.*,lp.life_stage,lp.life_status
           FROM household_dependencies d
           JOIN actor_life_profiles lp ON lp.actor_id=d.dependent_actor_id
           LEFT JOIN actors sa ON sa.id=d.sponsor_actor_id
           LEFT JOIN actor_life_profiles slp ON slp.actor_id=d.sponsor_actor_id
           WHERE d.status='active' AND d.dependency_kind IN ('child','ward')
             AND lp.life_status='living' AND lp.life_stage IN ('infant','child','youth')
             AND (d.sponsor_actor_id IS NULL OR sa.status IS NULL OR sa.status<>'active' OR slp.life_status<>'living')
           ORDER BY d.id"""
    ).fetchall()
    resolved = 0
    for dep in rows:
        ward = int(dep['dependent_actor_id'])
        hid = int(dep['household_id']) if dep['household_id'] is not None else None
        if hid is None:
            continue

        # A still-valid legal guardian can simply resume sponsorship without creating another relation.
        existing = conn.execute(
            """SELECT g.guardian_actor_id FROM guardianships g
               JOIN household_members hm ON hm.actor_id=g.guardian_actor_id AND hm.household_id=? AND hm.status='active'
               WHERE g.ward_actor_id=? AND g.status='active' ORDER BY g.id LIMIT 1""",
            (hid, ward),
        ).fetchone()
        if existing and _adult_living_actor(conn, int(existing[0])):
            guardian = int(existing[0])
            conn.execute("UPDATE household_dependencies SET sponsor_actor_id=? WHERE id=?", (guardian, int(dep['id'])))
            resolved += 1
            continue

        candidates: list[int] = []
        # Surviving recognized parents/adoptive parents in the same household take priority.
        for r in conn.execute(
            """SELECT k.actor_a_id FROM kinship_links k
               JOIN household_members hm ON hm.actor_id=k.actor_a_id AND hm.household_id=? AND hm.status='active'
               WHERE k.actor_b_id=? AND k.kin_kind IN ('parent','adoptive_parent')
                 AND k.legal_status='recognized' AND k.ended_day IS NULL ORDER BY k.id""",
            (hid, ward),
        ).fetchall():
            candidates.append(int(r[0]))
        # Then adult siblings already sharing the household.
        for r in conn.execute(
            """SELECT k.actor_a_id FROM kinship_links k
               JOIN household_members hm ON hm.actor_id=k.actor_a_id AND hm.household_id=? AND hm.status='active'
               WHERE k.actor_b_id=? AND k.kin_kind='sibling' AND k.legal_status='recognized' AND k.ended_day IS NULL
               ORDER BY k.id""",
            (hid, ward),
        ).fetchall():
            candidates.append(int(r[0]))
        # Household head, then other high-authority adult members, are conservative fallback custodians.
        head = conn.execute("SELECT head_actor_id FROM households WHERE id=? AND status IN ('active','declining')", (hid,)).fetchone()
        if head and head[0] is not None:
            candidates.append(int(head[0]))
        for r in conn.execute(
            """SELECT actor_id FROM household_members WHERE household_id=? AND status='active' AND actor_id<>?
               ORDER BY authority DESC,actor_id""", (hid, ward)
        ).fetchall():
            candidates.append(int(r[0]))

        seen: set[int] = set()
        guardian = None
        for aid in candidates:
            if aid in seen or aid == ward:
                continue
            seen.add(aid)
            if _adult_living_actor(conn, aid):
                guardian = aid
                break
        if guardian is None:
            continue

        create_guardianship(conn, guardian, ward, household_id=None,
                            authority=70, support_level=float(dep['support_level']))
        conn.execute("UPDATE household_dependencies SET sponsor_actor_id=? WHERE id=?", (guardian, int(dep['id'])))
        resolved += 1
    return resolved


def _resolve_service_terms(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for s in conn.execute("SELECT * FROM household_service_terms WHERE status='active' AND review_day<=?", (day,)).fetchall():
        h = conn.execute("SELECT cohesion,wealth,status FROM households WHERE id=?", (s["household_id"],)).fetchone()
        if not h:
            continue
        score = float(s["loyalty"]) * .3 + float(s["satisfaction"]) * .3 + float(s["renewal_bias"]) * .2 + float(h["cohesion"]) * .2
        household_closed = str(h["status"]) in ("dissolved","historical")
        if str(h["status"]) == "declining":
            score -= 20
        if not household_closed and score >= 45:
            conn.execute("UPDATE household_service_terms SET review_day=? WHERE id=?", (day + 365, s["id"]))
        else:
            conn.execute("UPDATE household_service_terms SET status='former',end_day=? WHERE id=?", (day, s["id"]))
            conn.execute("UPDATE household_members SET status='former',left_day=? WHERE household_id=? AND actor_id=? AND role=? AND status='active'",
                         (day, s["household_id"], s["actor_id"], s["service_role"]))
            _record_life_event(conn, "service_change", f"{_name(conn, int(s['actor_id']))} left service in household #{s['household_id']}.",
                               actor_id=int(s["actor_id"]), household_id=int(s["household_id"]), day=day)
        count += 1
    return count


def _resolve_migrations(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    for m in conn.execute("SELECT * FROM household_migration_plans WHERE status='planned' AND planned_day<=? ORDER BY planned_day,id", (day,)).fetchall():
        hid, dest = int(m["household_id"]), int(m["destination_location_id"])
        hh = conn.execute("SELECT status,location_id FROM households WHERE id=?", (hid,)).fetchone()
        if not hh or str(hh["status"]) in {"dissolved", "historical"}:
            conn.execute("UPDATE household_migration_plans SET status='cancelled' WHERE id=?", (m["id"],))
            continue
        if hh["location_id"] is not None and int(hh["location_id"]) == dest:
            conn.execute("UPDATE household_migration_plans SET status='completed',completed_day=? WHERE id=?", (day, m["id"]))
            continue
        origin = int(hh["location_id"]) if hh["location_id"] is not None else None
        # v0.22: when campaign route geography exists, household migration must traverse it rather than teleport.
        if origin is not None:
            from .ecology import find_route_path, start_travel
            touching = conn.execute(
                "SELECT COUNT(*) FROM travel_routes WHERE from_location_id IN (?,?) OR to_location_id IN (?,?)",
                (origin, dest, origin, dest),
            ).fetchone()[0]
            if touching:
                path = find_route_path(conn, origin, dest, day=day)
                if not path:
                    conn.execute("UPDATE household_migration_plans SET planned_day=? WHERE id=?", (day + 3, m["id"]))
                    continue
                plan_id = start_travel(conn, "household", hid, dest, metadata={"migration_plan_id": int(m["id"]), "reason": m["reason"]})
                conn.execute("UPDATE household_migration_plans SET status='in_transit',metadata_json=? WHERE id=?",
                             (json.dumps({"travel_plan_id": plan_id}, sort_keys=True), m["id"]))
                count += 1
                continue
        # Structural fallback for locations whose travel geography has not been crystallized yet.
        conn.execute("UPDATE households SET location_id=?,updated_day=? WHERE id=?", (dest, day, hid))
        members = conn.execute("SELECT actor_id FROM household_members WHERE household_id=? AND status='active'", (hid,)).fetchall()
        for r in members:
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (dest, r[0]))
            conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?", (hid, r[0]))
        conn.execute("UPDATE household_migration_plans SET status='completed',completed_day=? WHERE id=?", (day, m["id"]))
        _record_life_event(conn, "migration", f"Household #{hid} migrated to location #{dest}.", household_id=hid, location_id=dest, day=day,
                           metadata={"reason": m["reason"], "resolution": "structural_unrouted"})
        if event_logger:
            event_logger(day=day, event_type="life:migration", title=f"Household migration #{hid}",
                         summary=f"Household #{hid} moved to location #{dest}.", severity=1, source_actor_id=None,
                         target_actor_ids=tuple(int(r[0]) for r in members), location_id=dest)
        count += 1
    return count


def _resolve_demography(conn: sqlite3.Connection, day: int) -> int:
    rows = conn.execute("SELECT * FROM demographic_cohorts WHERE last_review_day<? ORDER BY location_id,cohort_key,id", (day,)).fetchall()
    due = [r for r in rows if day - int(r["last_review_day"]) >= 365]
    if not due:
        return 0
    widths = {"0_4": 5.0, "5_12": 8.0, "13_17": 5.0, "18_39": 22.0, "40_59": 20.0}
    nxt = {"0_4": "5_12", "5_12": "13_17", "13_17": "18_39", "18_39": "40_59", "40_59": "60_plus"}
    # Snapshot every due cohort before writing, so a person cannot age through multiple bands in one review.
    due_updates: dict[tuple[int,str,str], float] = {}
    inflow: dict[tuple[int,str,str], float] = {}
    inflow_source: dict[tuple[int,str,str], sqlite3.Row] = {}
    for c in due:
        key = (int(c["location_id"]), str(c["cohort_key"]), str(c["age_band"]))
        years = (day - int(c["last_review_day"])) / 365.0
        pop = float(c["population"])
        migration = pop * float(c["annual_migration_rate"]) * years
        births = float(c["annual_birth_pressure"]) * years if str(c["age_band"]) == "0_4" else 0.0
        working = max(0.0, pop + migration + births)
        age_band = str(c["age_band"])
        aged_out = 0.0
        if age_band in widths:
            # Aggregate Leslie-style aging. The bounded fraction prevents an overdue review from
            # moving more people than the source band contains.
            aged_out = working * min(1.0, years / widths[age_band])
            working -= aged_out
            nk = (key[0], key[1], nxt[age_band])
            inflow[nk] = inflow.get(nk, 0.0) + aged_out
            inflow_source[nk] = c
        due_updates[key] = working
    # Add inflow to due destinations in-memory. Non-due destinations receive population only;
    # their last_review_day is deliberately preserved so partial-year migration/aging time is not lost.
    for key, amount in inflow.items():
        if key in due_updates:
            due_updates[key] += amount
            continue
        existing = conn.execute("SELECT * FROM demographic_cohorts WHERE location_id=? AND cohort_key=? AND age_band=?", key).fetchone()
        if existing:
            conn.execute("UPDATE demographic_cohorts SET population=population+? WHERE id=?", (amount, existing["id"]))
        else:
            source = inflow_source.get(key)
            conn.execute(
                """INSERT INTO demographic_cohorts(location_id,cohort_key,age_band,population,annual_birth_pressure,annual_migration_rate,last_review_day,metadata_json)
                   VALUES (?,?,?,?,0,?,?,?)""",
                (key[0], key[1], key[2], amount, float(source["annual_migration_rate"]) if source else 0.0, day,
                 source["metadata_json"] if source else "{}"),
            )
    for key, value in due_updates.items():
        conn.execute("UPDATE demographic_cohorts SET population=?,last_review_day=? WHERE location_id=? AND cohort_key=? AND age_band=?",
                     (max(0.0, value), day, key[0], key[1], key[2]))
    return len(due)


def next_household_life_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals: list[int] = []
    for sql in (
        "SELECT MIN(review_day) FROM household_service_terms WHERE status='active' AND review_day>? AND review_day<=?",
        "SELECT MIN(planned_day) FROM household_migration_plans WHERE status='planned' AND planned_day>? AND planned_day<=?",
    ):
        r = conn.execute(sql, (after_day, end_day)).fetchone()[0]
        if r is not None:
            vals.append(int(r))
    # Exact family-plan due dates are decision-relevant history; do not round them to a monthly tick.
    for u in conn.execute("SELECT started_day,family_plan_json FROM household_unions WHERE status='active'").fetchall():
        plan = json.loads(u["family_plan_json"] or "{}")
        if plan.get("auto_children"):
            due = int(plan.get("earliest_next_child_day", int(u["started_day"]) + int(plan.get("spacing_days", 730))))
            if after_day < due <= end_day:
                vals.append(due)
    # Life-stage boundaries are also scheduled on their exact threshold day when a birth day is known.
    for r in conn.execute("SELECT birth_day,life_stage FROM actor_life_profiles WHERE life_status='living' AND birth_day IS NOT NULL").fetchall():
        thresholds = {"infant": 2*365, "child": 13*365, "youth": 18*365, "adult": 60*365}
        offset = thresholds.get(str(r["life_stage"]))
        if offset is not None:
            d = int(r["birth_day"]) + offset
            if after_day < d <= end_day:
                vals.append(d)
    # Profiles without an exact upcoming boundary still receive a bounded periodic review.
    if conn.execute("SELECT 1 FROM actor_life_profiles WHERE life_status='living' LIMIT 1").fetchone():
        d = ((after_day // 30) + 1) * 30
        if d <= end_day:
            vals.append(d)
    # Aggregate cohorts are due one year from their own last review, not on global calendar-year boundaries.
    for r in conn.execute("SELECT last_review_day FROM demographic_cohorts").fetchall():
        d = int(r["last_review_day"]) + 365
        if after_day < d <= end_day:
            vals.append(d)
    # POPLIFE-01 owns the full 52m-scale live age-cohort process. It shares this household/life
    # process owner so births/aging/death remain one life-course phase rather than a rival clock.
    try:
        from .background_population import next_population_life_course_due_day
        d = next_population_life_course_due_day(conn, after_day, end_day)
        if d is not None:
            vals.append(d)
    except sqlite3.OperationalError:
        pass
    return min(vals) if vals else None


def process_due_household_life(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int | float]:
    from .background_population import process_due_population_life_course
    poplife = process_due_population_life_course(conn, day)
    return {
        "life_profiles": _review_profiles(conn, day, event_logger),
        "births": _resolve_planned_births(conn, day, event_logger),
        "social_contacts": _resolve_social_contacts(conn, day),
        "guardianship_resolutions": _resolve_guardianship_needs(conn, day),
        "service_reviews": _resolve_service_terms(conn, day),
        "migrations": _resolve_migrations(conn, day, event_logger),
        "demographic_cohorts": _resolve_demography(conn, day),
        "population_sources_reviewed": int(poplife.get("sources_reviewed", 0)),
        "population_source_year_periods": int(poplife.get("source_year_periods", 0)),
        "population_births": float(poplife.get("births", 0.0)),
        "population_deaths": float(poplife.get("deaths", 0.0)),
    }


def household_life_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "living_profiles": int(conn.execute("SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='living'").fetchone()[0]),
        "active_unions": int(conn.execute("SELECT COUNT(*) FROM household_unions WHERE status='active'").fetchone()[0]),
        "active_guardianships": int(conn.execute("SELECT COUNT(*) FROM guardianships WHERE status='active'").fetchone()[0]),
        "active_dependencies": int(conn.execute("SELECT COUNT(*) FROM household_dependencies WHERE status='active'").fetchone()[0]),
        "active_service_terms": int(conn.execute("SELECT COUNT(*) FROM household_service_terms WHERE status='active'").fetchone()[0]),
        "planned_migrations": int(conn.execute("SELECT COUNT(*) FROM household_migration_plans WHERE status='planned'").fetchone()[0]),
        "life_events": int(conn.execute("SELECT COUNT(*) FROM life_events").fetchone()[0]),
        "aggregate_population": round(float(__import__('engine.background_population', fromlist=['current_world_population']).current_world_population(conn)), 2),
    }
