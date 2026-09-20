from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def seed_religious_traditions(conn: sqlite3.Connection) -> None:
    # Setting vocabulary only. These rows do not create adherents, feast days, clergy, or
    # universal local practice. Numeric centralization/exclusivity values are coarse runtime
    # calibrations used by the generic institution model, not in-world scores.
    # Migrate the old pre-MASTER-FINAL placeholder to the Witness in-place so legacy saves
    # retain referential integrity without keeping stale canon vocabulary alive.
    old = conn.execute("SELECT id FROM religious_traditions WHERE tradition_key='true_faith'").fetchone()
    witness = conn.execute("SELECT id FROM religious_traditions WHERE tradition_key='witness'").fetchone()
    if old and not witness:
        conn.execute("UPDATE religious_traditions SET tradition_key='witness',name='The Witness' WHERE id=?", (int(old[0]),))

    rows = [
        ("witness", "The Witness", "revealed", 70, 95, "working",
         "Exclusive revealed communion centred in Greywood with established external minorities and institutions; local political expression varies by state.",
         {"authority":"WORLD_BIBLE","no_universal_local_calendar":True}),
        ("hearth_rites", "Hearth Rites", "household_rite", 5, 15, "settled",
         "Near-universal Hearthfolk remembrance and household tradition centred on family, dead, season, place and inherited obligation.",
         {"authority":"WORLD_BIBLE","central_priesthood_required":False}),
        ("vigil", "The Vigil", "organized", 35, 35, "working",
         "Interpretive religion gathered around the First Current and the meaning of cultivation; internal schools and local forms remain plural.",
         {"authority":"WORLD_BIBLE","known_internal_disagreement":True}),
        ("imperial_observance", "Imperial Observance", "organized", 80, 45, "working",
         "Underheaven's public religious order of Heaven, mandate, sacred-but-not-divine sovereignty, ceremony and ancestral obligations.",
         {"authority":"WORLD_BIBLE","state_embedded":True}),
        ("dunmoor_pantheon", "Dunmoor Pantheon", "organized", 65, 55, "working",
         "Dunmoor's national civic-and-household pantheon with public temples, household Wardings and state ritual.",
         {"authority":"WORLD_BIBLE","national_tradition":True}),
        ("hollow_faith", "Hollow Faith", "organized", 55, 80, "working",
         "Small, organized but non-unitary Hollow religious world in which the Grand Coven claims leading religious and historical primacy without governing all Hollows.",
         {"authority":"WORLD_BIBLE","hidden_population":True,"not_single_church":True}),
        ("tidefaith", "Tidefaith", "local", 20, 15, "working",
         "Windmere's decentralized, port-varying and non-exclusive majority sea-and-fortune religion.",
         {"authority":"WORLD_BIBLE","nonexclusive":True,"no_central_high_priest":True}),
        ("dayfire", "Dayfire", "organized", 25, 45, "working",
         "Sunreach civic religion of borrowed sacred Light expressed through the Common Flames of many charter polities rather than one confederal priesthood.",
         {"authority":"WORLD_BIBLE","confederal_plurality":True,"no_high_priest":True}),
        ("thornward_old_gods", "Thornward Old Gods", "organized", 55, 55, "working",
         "Thornward's own civic-and-household pantheon, structurally akin to Dunmoor's kind of religion while worshipping different gods.",
         {"authority":"WORLD_BIBLE","distinct_from_dunmoor_gods":True}),
        ("keeping_of_names", "Keeping of Names", "local", 20, 25, "working",
         "Stormhollow remembrance religion of living families, their dead and inherited places, without a pantheon of governing gods.",
         {"authority":"WORLD_BIBLE","remembrance_tradition":True,"ancestors_not_gods":True}),
    ]
    for key, name, kind, cent, excl, status, desc, meta in rows:
        conn.execute(
            """INSERT INTO religious_traditions(
                   tradition_key,name,tradition_kind,centralization,exclusivity_claim,canon_status,description,metadata_json
               ) VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(tradition_key) DO UPDATE SET name=excluded.name,tradition_kind=excluded.tradition_kind,
                 centralization=excluded.centralization,exclusivity_claim=excluded.exclusivity_claim,canon_status=excluded.canon_status,
                 description=excluded.description,metadata_json=excluded.metadata_json""",
            (key, name, kind, cent, excl, status, desc, json.dumps(meta, sort_keys=True)),
        )


def _require_actor(conn: sqlite3.Connection, actor_id: int, *, actor_type: str | None = None) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not row:
        raise ValueError("Unknown actor")
    if actor_type and str(row["actor_type"]) != actor_type:
        raise ValueError(f"Actor must be {actor_type}")
    return row


def _require_active_institution(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row:
    row = _require_actor(conn, actor_id, actor_type="institution")
    if str(row["status"]).lower() not in ("active", "strained", "dormant"):
        raise ValueError("Institution is not active enough for this operation")
    return row


def tradition_id(conn: sqlite3.Connection, key_or_name: str) -> int:
    row = conn.execute(
        "SELECT id FROM religious_traditions WHERE tradition_key=? OR lower(name)=lower(?)",
        (key_or_name, key_or_name),
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown religious tradition: {key_or_name}")
    return int(row[0])


def set_affiliation(
    conn: sqlite3.Connection,
    actor_id: int,
    tradition: str,
    *,
    affiliation_kind: str = "adherent",
    practice_intensity: float = 50,
    publicness: float = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    _require_actor(conn, actor_id)
    tid = tradition_id(conn, tradition)
    day = _day(conn)
    row = conn.execute(
        "SELECT id FROM religious_affiliations WHERE actor_id=? AND tradition_id=? AND status='active'",
        (actor_id, tid),
    ).fetchone()
    if row:
        conn.execute(
            """UPDATE religious_affiliations SET affiliation_kind=?,practice_intensity=?,publicness=?,metadata_json=?
               WHERE id=?""",
            (
                affiliation_kind,
                max(0, min(100, float(practice_intensity))),
                max(0, min(100, float(publicness))),
                json.dumps(metadata or {}, sort_keys=True),
                int(row[0]),
            ),
        )
        return int(row[0])
    cur = conn.execute(
        """INSERT INTO religious_affiliations(
               actor_id,tradition_id,affiliation_kind,practice_intensity,publicness,joined_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,'active',?)""",
        (
            actor_id,
            tid,
            affiliation_kind,
            max(0, min(100, float(practice_intensity))),
            max(0, min(100, float(publicness))),
            day,
            json.dumps(metadata or {}, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def end_affiliation(conn: sqlite3.Connection, affiliation_id: int) -> None:
    row = conn.execute("SELECT * FROM religious_affiliations WHERE id=?", (affiliation_id,)).fetchone()
    if not row:
        raise ValueError("Unknown affiliation")
    if str(row["status"]) != "active":
        return
    conn.execute(
        "UPDATE religious_affiliations SET status='former',affiliation_kind='former',left_day=? WHERE id=?",
        (_day(conn), affiliation_id),
    )


def configure_religious_institution(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    tradition: str,
    *,
    location_id: int | None = None,
    authority: float = 40,
    ritual_capacity: float = 50,
    charity_commitment: float = 10,
    treasury: float = 0,
    reputation: float = 50,
    review_days: int = 30,
    metadata: dict[str, Any] | None = None,
) -> None:
    actor = _require_active_institution(conn, institution_actor_id)
    tid = tradition_id(conn, tradition)
    day = _day(conn)
    loc = location_id if location_id is not None else actor["current_location_id"]
    conn.execute(
        """INSERT INTO religious_institutions(
               institution_actor_id,tradition_id,location_id,authority,ritual_capacity,charity_commitment,treasury,reputation,
               last_review_day,next_review_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)
           ON CONFLICT(institution_actor_id) DO UPDATE SET
             tradition_id=excluded.tradition_id,location_id=excluded.location_id,authority=excluded.authority,
             ritual_capacity=excluded.ritual_capacity,charity_commitment=excluded.charity_commitment,
             treasury=excluded.treasury,reputation=excluded.reputation,status='active',metadata_json=excluded.metadata_json""",
        (
            institution_actor_id, tid, loc,
            max(0, min(100, float(authority))),
            max(0, min(100, float(ritual_capacity))),
            max(0, min(100, float(charity_commitment))),
            max(0, float(treasury)),
            max(0, min(100, float(reputation))),
            day, day + max(1, int(review_days)), json.dumps(metadata or {}, sort_keys=True),
        ),
    )


def add_religious_office(
    conn: sqlite3.Connection,
    actor_id: int,
    institution_actor_id: int,
    role: str,
    *,
    standing: float = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    actor = _require_actor(conn, actor_id)
    if str(actor["status"]).lower() in ("dead", "deceased"):
        raise ValueError("Deceased actor cannot take office")
    _require_active_institution(conn, institution_actor_id)
    if not conn.execute("SELECT 1 FROM religious_institutions WHERE institution_actor_id=?", (institution_actor_id,)).fetchone():
        raise ValueError("Institution has no religious profile")
    cur = conn.execute(
        """INSERT INTO religious_offices(actor_id,institution_actor_id,role,standing,seniority_days,started_day,last_review_day,status,metadata_json)
           VALUES (?,?,?,?,0,?,?,'active',?)""",
        (actor_id, institution_actor_id, role, max(0, min(100, float(standing))), _day(conn), _day(conn), json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def add_observance(
    conn: sqlite3.Connection,
    tradition: str,
    name: str,
    *,
    due_day: int,
    observance_kind: str = "seasonal",
    recurrence_days: int | None = None,
    institution_actor_id: int | None = None,
    location_id: int | None = None,
    public_event: bool = True,
    significance: float = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    tid = tradition_id(conn, tradition)
    if int(due_day) < _day(conn):
        raise ValueError("Observance due_day cannot be in the past")
    if recurrence_days is not None and int(recurrence_days) < 1:
        raise ValueError("recurrence_days must be positive")
    if institution_actor_id is not None:
        _require_active_institution(conn, institution_actor_id)
        prof = conn.execute("SELECT tradition_id,location_id FROM religious_institutions WHERE institution_actor_id=?", (institution_actor_id,)).fetchone()
        if not prof:
            raise ValueError("Institution has no religious profile")
        if int(prof["tradition_id"]) != tid:
            raise ValueError("Observance tradition does not match institution tradition")
        if location_id is None:
            location_id = prof["location_id"]
    cur = conn.execute(
        """INSERT INTO religious_observances(
               tradition_id,name,observance_kind,institution_actor_id,location_id,recurrence_days,next_due_day,public_event,significance,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,'active',?)""",
        (
            tid, name, observance_kind, institution_actor_id, location_id, recurrence_days, int(due_day),
            1 if public_event else 0, max(0, min(100, float(significance))), json.dumps(metadata or {}, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def record_attendance(conn: sqlite3.Connection, instance_id: int, actor_id: int, participation_kind: str = "attended") -> None:
    _require_actor(conn, actor_id)
    inst = conn.execute(
        """SELECT roi.id,ro.tradition_id FROM religious_observance_instances roi
           JOIN religious_observances ro ON ro.id=roi.observance_id WHERE roi.id=?""",
        (instance_id,),
    ).fetchone()
    if not inst:
        raise ValueError("Unknown observance instance")
    conn.execute(
        "INSERT OR IGNORE INTO religious_attendance(instance_id,actor_id,participation_kind) VALUES (?,?,?)",
        (instance_id, actor_id, participation_kind),
    )
    conn.execute(
        "UPDATE religious_affiliations SET last_observance_day=? WHERE actor_id=? AND tradition_id=? AND status='active'",
        (_day(conn), actor_id, int(inst["tradition_id"])),
    )


def add_obligation(
    conn: sqlite3.Connection,
    description: str,
    *,
    obligation_kind: str,
    due_day: int,
    actor_id: int | None = None,
    household_id: int | None = None,
    institution_actor_id: int | None = None,
    tradition: str | None = None,
    recurrence_days: int | None = None,
    reputation_stakes: float = 10,
    metadata: dict[str, Any] | None = None,
) -> int:
    owners = [actor_id is not None, household_id is not None, institution_actor_id is not None]
    if sum(owners) != 1:
        raise ValueError("Exactly one obligation owner is required")
    if actor_id is not None:
        _require_actor(conn, actor_id)
    if institution_actor_id is not None:
        _require_actor(conn, institution_actor_id, actor_type="institution")
    if household_id is not None and not conn.execute("SELECT 1 FROM households WHERE id=?", (household_id,)).fetchone():
        raise ValueError("Unknown household")
    tid = tradition_id(conn, tradition) if tradition else None
    if int(due_day) < _day(conn):
        raise ValueError("Obligation due_day cannot be in the past")
    cur = conn.execute(
        """INSERT INTO religious_obligations(
               actor_id,household_id,institution_actor_id,tradition_id,obligation_kind,description,due_day,recurrence_days,reputation_stakes,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,'pending',?)""",
        (actor_id, household_id, institution_actor_id, tid, obligation_kind, description, int(due_day), recurrence_days,
         max(0, min(100, float(reputation_stakes))), json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _rep_subject(row: sqlite3.Row) -> tuple[str, int]:
    if row["actor_id"] is not None:
        return "actor", int(row["actor_id"])
    if row["household_id"] is not None:
        return "household", int(row["household_id"])
    return "institution", int(row["institution_actor_id"])


def _adjust_reputation(conn: sqlite3.Connection, subject_kind: str, subject_id: int, domain: str, delta: float, day: int) -> None:
    row = conn.execute(
        "SELECT value FROM social_reputation WHERE subject_kind=? AND subject_id=? AND domain=?",
        (subject_kind, subject_id, domain),
    ).fetchone()
    before = float(row[0]) if row else 50.0
    value = max(0.0, min(100.0, before + float(delta)))
    conn.execute(
        """INSERT INTO social_reputation(subject_kind,subject_id,domain,value,updated_day)
           VALUES (?,?,?,?,?)
           ON CONFLICT(subject_kind,subject_id,domain) DO UPDATE SET value=excluded.value,updated_day=excluded.updated_day""",
        (subject_kind, subject_id, domain, value, day),
    )


def fulfill_obligation(conn: sqlite3.Connection, obligation_id: int) -> None:
    row = conn.execute("SELECT * FROM religious_obligations WHERE id=?", (obligation_id,)).fetchone()
    if not row:
        raise ValueError("Unknown religious obligation")
    if str(row["status"]) in ("fulfilled", "waived", "cancelled"):
        return
    day = _day(conn)
    sk, sid = _rep_subject(row)
    _adjust_reputation(conn, sk, sid, "religious_reliability", float(row["reputation_stakes"]) * 0.12, day)
    recurrence = row["recurrence_days"]
    if recurrence is None:
        conn.execute("UPDATE religious_obligations SET status='fulfilled',fulfilled_day=? WHERE id=?", (day, obligation_id))
    else:
        conn.execute(
            "UPDATE religious_obligations SET status='pending',fulfilled_day=?,due_day=? WHERE id=?",
            (day, max(day, int(row["due_day"])) + int(recurrence), obligation_id),
        )


def create_sacred_site(
    conn: sqlite3.Connection,
    name: str,
    *,
    tradition: str | None = None,
    location_id: int | None = None,
    building_id: int | None = None,
    institution_actor_id: int | None = None,
    site_kind: str = "shrine",
    sanctity_reputation: float = 50,
    access_kind: str = "public",
    metadata: dict[str, Any] | None = None,
) -> int:
    tid = tradition_id(conn, tradition) if tradition else None
    if building_id is not None:
        b = conn.execute("SELECT location_id FROM buildings WHERE id=?", (building_id,)).fetchone()
        if not b:
            raise ValueError("Unknown building")
        if location_id is None:
            location_id = b["location_id"]
    if institution_actor_id is not None:
        _require_actor(conn, institution_actor_id, actor_type="institution")
    cur = conn.execute(
        """INSERT INTO sacred_sites(name,tradition_id,location_id,building_id,institution_actor_id,site_kind,sanctity_reputation,access_kind,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?, 'active',?)""",
        (name, tid, location_id, building_id, institution_actor_id, site_kind,
         max(0, min(100, float(sanctity_reputation))), access_kind, json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def configure_cultural_institution(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    cultural_domain: str,
    *,
    location_id: int | None = None,
    prestige: float = 50,
    resources: float = 0,
    public_reach: float = 50,
    continuity: float = 50,
    review_days: int = 30,
    metadata: dict[str, Any] | None = None,
) -> None:
    actor = _require_active_institution(conn, institution_actor_id)
    day = _day(conn)
    loc = location_id if location_id is not None else actor["current_location_id"]
    conn.execute(
        """INSERT INTO cultural_institution_profiles(
               institution_actor_id,cultural_domain,location_id,prestige,resources,public_reach,continuity,last_review_day,next_review_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,'active',?)
           ON CONFLICT(institution_actor_id) DO UPDATE SET cultural_domain=excluded.cultural_domain,location_id=excluded.location_id,
             prestige=excluded.prestige,resources=excluded.resources,public_reach=excluded.public_reach,continuity=excluded.continuity,
             status='active',metadata_json=excluded.metadata_json""",
        (
            institution_actor_id, cultural_domain, loc,
            max(0, min(100, float(prestige))), max(0, float(resources)), max(0, min(100, float(public_reach))),
            max(0, min(100, float(continuity))), day, day + max(1, int(review_days)), json.dumps(metadata or {}, sort_keys=True),
        ),
    )


def add_cultural_program(
    conn: sqlite3.Connection,
    institution_actor_id: int,
    name: str,
    program_kind: str,
    *,
    due_day: int,
    recurrence_days: int | None = None,
    location_id: int | None = None,
    style_id: int | None = None,
    prestige_effect: float = 1,
    reach: float = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    _require_active_institution(conn, institution_actor_id)
    prof = conn.execute("SELECT * FROM cultural_institution_profiles WHERE institution_actor_id=?", (institution_actor_id,)).fetchone()
    if not prof:
        raise ValueError("Institution has no cultural profile")
    if int(due_day) < _day(conn):
        raise ValueError("Program due_day cannot be in the past")
    if style_id is not None and not conn.execute("SELECT 1 FROM style_movements WHERE id=?", (style_id,)).fetchone():
        raise ValueError("Unknown style")
    cur = conn.execute(
        """INSERT INTO cultural_programs(
               institution_actor_id,name,program_kind,location_id,style_id,recurrence_days,next_due_day,prestige_effect,reach,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,'active',?)""",
        (
            institution_actor_id, name, program_kind, location_id if location_id is not None else prof["location_id"], style_id,
            recurrence_days, int(due_day), float(prestige_effect), max(0, min(100, float(reach))), json.dumps(metadata or {}, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def add_patronage(
    conn: sqlite3.Connection,
    amount: float,
    *,
    due_day: int,
    source_household_id: int | None = None,
    source_enterprise_id: int | None = None,
    target_religious_actor_id: int | None = None,
    target_cultural_actor_id: int | None = None,
    recurrence_days: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if sum(x is not None for x in (source_household_id, source_enterprise_id)) != 1:
        raise ValueError("Exactly one funded patronage source is required")
    if sum(x is not None for x in (target_religious_actor_id, target_cultural_actor_id)) != 1:
        raise ValueError("Exactly one patronage target is required")
    if float(amount) <= 0:
        raise ValueError("Patronage amount must be positive")
    if int(due_day) < _day(conn):
        raise ValueError("Patronage due_day cannot be in the past")
    if source_household_id is not None and not conn.execute("SELECT 1 FROM households WHERE id=?", (source_household_id,)).fetchone():
        raise ValueError("Unknown household")
    if source_enterprise_id is not None and not conn.execute("SELECT 1 FROM civilian_enterprises WHERE id=?", (source_enterprise_id,)).fetchone():
        raise ValueError("Unknown enterprise")
    if target_religious_actor_id is not None:
        if not conn.execute("SELECT 1 FROM religious_institutions WHERE institution_actor_id=?", (target_religious_actor_id,)).fetchone():
            raise ValueError("Unknown religious institution target")
    if target_cultural_actor_id is not None:
        if not conn.execute("SELECT 1 FROM cultural_institution_profiles WHERE institution_actor_id=?", (target_cultural_actor_id,)).fetchone():
            raise ValueError("Unknown cultural institution target")
    cur = conn.execute(
        """INSERT INTO institutional_patronage(
               source_household_id,source_enterprise_id,target_religious_actor_id,target_cultural_actor_id,amount,recurrence_days,next_due_day,status,metadata_json
           ) VALUES (?,?,?,?,?,?,?,'active',?)""",
        (source_household_id, source_enterprise_id, target_religious_actor_id, target_cultural_actor_id, float(amount), recurrence_days,
         int(due_day), json.dumps(metadata or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def _institution_is_live(conn: sqlite3.Connection, actor_id: int | None) -> bool:
    if actor_id is None:
        return True
    row = conn.execute("SELECT status FROM actors WHERE id=?", (actor_id,)).fetchone()
    return bool(row and str(row[0]).lower() not in ("dead", "deceased", "dissolved", "destroyed"))


def _process_observances(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    rows = conn.execute(
        "SELECT * FROM religious_observances WHERE status='active' AND next_due_day<=? ORDER BY next_due_day,id",
        (day,),
    ).fetchall()
    for row in rows:
        if row["institution_actor_id"] is not None and not _institution_is_live(conn, int(row["institution_actor_id"])):
            conn.execute("UPDATE religious_observances SET status='paused' WHERE id=?", (row["id"],))
            continue
        due = int(row["next_due_day"])
        existing = conn.execute("SELECT id FROM religious_observance_instances WHERE observance_id=? AND day=?", (row["id"], due)).fetchone()
        if not existing:
            cur = conn.execute(
                "INSERT INTO religious_observance_instances(observance_id,day,institution_actor_id,location_id,summary) VALUES (?,?,?,?,?)",
                (row["id"], due, row["institution_actor_id"], row["location_id"], f"{row['name']} was observed."),
            )
            if row["institution_actor_id"] is not None:
                conn.execute(
                    "UPDATE religious_institutions SET reputation=min(100,reputation+?) WHERE institution_actor_id=?",
                    (max(0.1, float(row["significance"]) / 500.0), row["institution_actor_id"]),
                )
            if event_logger and int(row["public_event"]):
                event_logger(
                    day=due, event_type="religion:observance", title=str(row["name"]),
                    summary=f"{row['name']} was observed as part of the local religious calendar.",
                    severity=max(1, min(3, int(float(row["significance"]) // 35) + 1)),
                    source_actor_id=row["institution_actor_id"], target_actor_ids=(), location_id=row["location_id"],
                )
            count += 1
        recurrence = row["recurrence_days"]
        if recurrence is None:
            conn.execute("UPDATE religious_observances SET status='ended' WHERE id=?", (row["id"],))
        else:
            nxt = due
            while nxt <= day:
                nxt += int(recurrence)
            conn.execute("UPDATE religious_observances SET next_due_day=? WHERE id=?", (nxt, row["id"]))
    return count


def _process_obligations(conn: sqlite3.Connection, day: int) -> int:
    changed = 0
    for row in conn.execute(
        "SELECT * FROM religious_obligations WHERE status='pending' AND due_day<? ORDER BY due_day,id", (day,)
    ).fetchall():
        sk, sid = _rep_subject(row)
        _adjust_reputation(conn, sk, sid, "religious_reliability", -float(row["reputation_stakes"]) * 0.25, day)
        conn.execute("UPDATE religious_obligations SET status='overdue' WHERE id=?", (row["id"],))
        changed += 1
    return changed


def _process_patronage(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    for row in conn.execute(
        "SELECT * FROM institutional_patronage WHERE status IN ('active','strained') AND next_due_day<=? ORDER BY next_due_day,id",
        (day,),
    ).fetchall():
        amount = float(row["amount"])
        paid = False
        if row["source_household_id"] is not None:
            src = conn.execute("SELECT liquidity FROM households WHERE id=?", (row["source_household_id"],)).fetchone()
            if src and float(src[0]) >= amount:
                conn.execute("UPDATE households SET liquidity=liquidity-? WHERE id=?", (amount, row["source_household_id"]))
                paid = True
        else:
            src = conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?", (row["source_enterprise_id"],)).fetchone()
            if src and float(src[0]) >= amount:
                conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?", (amount, day, row["source_enterprise_id"]))
                paid = True
        if paid:
            if row["target_religious_actor_id"] is not None:
                conn.execute("UPDATE religious_institutions SET treasury=treasury+? WHERE institution_actor_id=?", (amount, row["target_religious_actor_id"]))
            else:
                conn.execute("UPDATE cultural_institution_profiles SET resources=resources+? WHERE institution_actor_id=?", (amount, row["target_cultural_actor_id"]))
            status = "active"
        else:
            status = "strained"
        recurrence = row["recurrence_days"]
        if recurrence is None:
            status = "ended" if paid else "strained"
            next_due = int(row["next_due_day"])
        else:
            next_due = int(row["next_due_day"])
            while next_due <= day:
                next_due += int(recurrence)
        conn.execute("UPDATE institutional_patronage SET status=?,next_due_day=? WHERE id=?", (status, next_due, row["id"]))
        count += 1
    return count


def _process_religious_institutions(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    for row in conn.execute(
        "SELECT * FROM religious_institutions WHERE status IN ('active','strained','dormant') AND next_review_day<=? ORDER BY next_review_day,institution_actor_id",
        (day,),
    ).fetchall():
        if not _institution_is_live(conn, int(row["institution_actor_id"])):
            conn.execute("UPDATE religious_institutions SET status='dissolved' WHERE institution_actor_id=?", (row["institution_actor_id"],))
            conn.execute("UPDATE religious_offices SET status='former',ended_day=? WHERE institution_actor_id=? AND status='active'", (day, row["institution_actor_id"]))
            continue
        elapsed = max(1, day - int(row["last_review_day"]))
        treasury = float(row["treasury"])
        charity_fraction = float(row["charity_commitment"]) / 100.0
        charity_spend = min(treasury * 0.08 * (elapsed / 30.0) * charity_fraction, treasury)
        reputation = float(row["reputation"])
        if charity_spend > 0.01:
            treasury -= charity_spend
            reputation = min(100.0, reputation + min(1.5, charity_spend / 100.0))
        status = "strained" if treasury <= 0.01 and float(row["charity_commitment"]) > 40 else "active"
        conn.execute(
            "UPDATE religious_institutions SET treasury=?,reputation=?,status=?,last_review_day=?,next_review_day=? WHERE institution_actor_id=?",
            (treasury, reputation, status, day, day + 30, row["institution_actor_id"]),
        )
        count += 1
    # Religious service has career continuity, but seniority never auto-promotes office.
    for office in conn.execute("SELECT id,last_review_day,seniority_days FROM religious_offices WHERE status='active' AND last_review_day<?", (day,)).fetchall():
        elapsed=max(0, day-int(office['last_review_day']))
        conn.execute("UPDATE religious_offices SET seniority_days=?,last_review_day=? WHERE id=?",
                     (int(office['seniority_days'])+elapsed, day, office['id']))
    # Dead office-holders cannot silently remain active even if their institution is healthy.
    conn.execute(
        """UPDATE religious_offices SET status='former',ended_day=?
           WHERE status='active' AND actor_id IN (SELECT id FROM actors WHERE lower(status) IN ('dead','deceased'))""",
        (day,),
    )
    return count


def _process_cultural_programs(conn: sqlite3.Connection, day: int, event_logger: Callable[..., int] | None) -> int:
    count = 0
    rows = conn.execute(
        "SELECT * FROM cultural_programs WHERE status='active' AND next_due_day<=? ORDER BY next_due_day,id",
        (day,),
    ).fetchall()
    for row in rows:
        if not _institution_is_live(conn, int(row["institution_actor_id"])):
            conn.execute("UPDATE cultural_programs SET status='paused' WHERE id=?", (row["id"],))
            continue
        due = int(row["next_due_day"])
        existing = conn.execute("SELECT id FROM cultural_program_instances WHERE program_id=? AND day=?", (row["id"], due)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO cultural_program_instances(program_id,day,location_id,summary) VALUES (?,?,?,?)",
                (row["id"], due, row["location_id"], f"{row['name']} took place."),
            )
            conn.execute(
                "UPDATE cultural_institution_profiles SET prestige=max(0,min(100,prestige+?)) WHERE institution_actor_id=?",
                (float(row["prestige_effect"]), row["institution_actor_id"]),
            )
            if row["style_id"] is not None and row["location_id"] is not None:
                sa = conn.execute("SELECT adoption FROM style_adoption WHERE style_id=? AND location_id=?", (row["style_id"], row["location_id"])).fetchone()
                if sa:
                    boost = min(3.0, float(row["reach"]) / 100.0 * max(0.0, float(row["prestige_effect"])))
                    conn.execute(
                        "UPDATE style_adoption SET adoption=min(100,adoption+?),last_review_day=? WHERE style_id=? AND location_id=?",
                        (boost, day, row["style_id"], row["location_id"]),
                    )
            if event_logger:
                event_logger(
                    day=due, event_type="culture:program", title=str(row["name"]),
                    summary=f"{row['name']} took place as part of the institution's cultural program.",
                    severity=1, source_actor_id=row["institution_actor_id"], target_actor_ids=(), location_id=row["location_id"],
                )
            count += 1
        recurrence = row["recurrence_days"]
        if recurrence is None:
            conn.execute("UPDATE cultural_programs SET status='ended' WHERE id=?", (row["id"],))
        else:
            nxt = due
            while nxt <= day:
                nxt += int(recurrence)
            conn.execute("UPDATE cultural_programs SET next_due_day=? WHERE id=?", (nxt, row["id"]))
    return count


def _process_cultural_institutions(conn: sqlite3.Connection, day: int) -> int:
    count = 0
    for row in conn.execute(
        "SELECT * FROM cultural_institution_profiles WHERE status IN ('active','strained','dormant') AND next_review_day<=? ORDER BY next_review_day,institution_actor_id",
        (day,),
    ).fetchall():
        if not _institution_is_live(conn, int(row["institution_actor_id"])):
            conn.execute("UPDATE cultural_institution_profiles SET status='dissolved' WHERE institution_actor_id=?", (row["institution_actor_id"],))
            continue
        elapsed = max(1, day - int(row["last_review_day"]))
        resources = float(row["resources"])
        continuity = float(row["continuity"])
        cost = max(0.2, (100.0 - continuity) / 100.0 * 1.5) * elapsed / 30.0
        resources = max(0.0, resources - cost)
        status = "strained" if resources <= 0.01 and continuity < 50 else "active"
        conn.execute(
            "UPDATE cultural_institution_profiles SET resources=?,status=?,last_review_day=?,next_review_day=? WHERE institution_actor_id=?",
            (resources, status, day, day + 30, row["institution_actor_id"]),
        )
        count += 1
    return count


def next_religion_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    queries = [
        ("SELECT MIN(next_due_day) FROM religious_observances WHERE status='active' AND next_due_day>? AND next_due_day<=?",),
        ("SELECT MIN(due_day) FROM religious_obligations WHERE status='pending' AND due_day>? AND due_day<=?",),
        ("SELECT MIN(next_due_day) FROM institutional_patronage WHERE status IN ('active','strained') AND next_due_day>? AND next_due_day<=?",),
        ("SELECT MIN(next_review_day) FROM religious_institutions WHERE status IN ('active','strained','dormant') AND next_review_day>? AND next_review_day<=?",),
        ("SELECT MIN(next_due_day) FROM cultural_programs WHERE status='active' AND next_due_day>? AND next_due_day<=?",),
        ("SELECT MIN(next_review_day) FROM cultural_institution_profiles WHERE status IN ('active','strained','dormant') AND next_review_day>? AND next_review_day<=?",),
    ]
    vals: list[int] = []
    for (q,) in queries:
        v = conn.execute(q, (after_day, end_day)).fetchone()[0]
        if v is not None:
            vals.append(int(v))
    return min(vals) if vals else None


def process_due_religion(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    return {
        "observances": _process_observances(conn, day, event_logger),
        "obligations": _process_obligations(conn, day),
        "patronage": _process_patronage(conn, day, event_logger),
        "religious_institutions": _process_religious_institutions(conn, day, event_logger),
        "cultural_programs": _process_cultural_programs(conn, day, event_logger),
        "cultural_institutions": _process_cultural_institutions(conn, day),
    }


def religion_context(conn: sqlite3.Connection, actor_id: int, location_id: int | None = None) -> dict[str, Any]:
    affiliations = [dict(r) for r in conn.execute(
        """SELECT ra.id,rt.tradition_key,rt.name,rt.canon_status,ra.affiliation_kind,ra.practice_intensity,ra.publicness,ra.last_observance_day
           FROM religious_affiliations ra JOIN religious_traditions rt ON rt.id=ra.tradition_id
           WHERE ra.actor_id=? AND ra.status='active' ORDER BY rt.name""",
        (actor_id,),
    ).fetchall()]
    obligations = [dict(r) for r in conn.execute(
        """SELECT id,obligation_kind,description,due_day,status,reputation_stakes
           FROM religious_obligations WHERE actor_id=? AND status IN ('pending','overdue') ORDER BY due_day,id""",
        (actor_id,),
    ).fetchall()]
    local_institutions: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    if location_id is not None:
        local_institutions = [dict(r) for r in conn.execute(
            """SELECT a.id,a.name,rt.name tradition,ri.reputation,ri.status
               FROM religious_institutions ri JOIN actors a ON a.id=ri.institution_actor_id
               JOIN religious_traditions rt ON rt.id=ri.tradition_id
               WHERE ri.location_id=? AND ri.status!='dissolved' ORDER BY ri.reputation DESC,a.name""",
            (location_id,),
        ).fetchall()]
        upcoming = [dict(r) for r in conn.execute(
            """SELECT ro.id,ro.name,ro.observance_kind,ro.next_due_day,ro.significance,rt.name tradition
               FROM religious_observances ro JOIN religious_traditions rt ON rt.id=ro.tradition_id
               WHERE ro.location_id=? AND ro.status='active' ORDER BY ro.next_due_day,ro.id LIMIT 8""",
            (location_id,),
        ).fetchall()]
    return {
        "affiliations": affiliations,
        "obligations": obligations,
        "local_religious_institutions": local_institutions,
        "upcoming_observances": upcoming,
        "guardrails": [
            "religion_is_lived_social_reality_not_a_faction_alignment",
            "no_unwritten_feast_day_or_doctrine_becomes_canon_automatically",
            "hearth_rites_vigil_and_other_practices_may_overlap_socially",
            "true_faith_exact_historical_furniture_remains_author_signoff_pending",
        ],
    }


def cultural_context(conn: sqlite3.Connection, location_id: int | None) -> dict[str, Any]:
    if location_id is None:
        return {"local_cultural_institutions": [], "upcoming_programs": []}
    institutions=[dict(r) for r in conn.execute(
        """SELECT a.id,a.name,c.cultural_domain,c.prestige,c.public_reach,c.status
           FROM cultural_institution_profiles c JOIN actors a ON a.id=c.institution_actor_id
           WHERE c.location_id=? AND c.status!='dissolved' ORDER BY c.prestige DESC,a.name""",
        (location_id,),
    ).fetchall()]
    programs=[dict(r) for r in conn.execute(
        """SELECT cp.id,cp.name,cp.program_kind,cp.next_due_day,cp.reach,a.name institution_name
           FROM cultural_programs cp JOIN actors a ON a.id=cp.institution_actor_id
           WHERE cp.location_id=? AND cp.status='active' ORDER BY cp.next_due_day,cp.id LIMIT 10""",
        (location_id,),
    ).fetchall()]
    return {
        "local_cultural_institutions": institutions,
        "upcoming_programs": programs,
        "guardrails": ["culture_has_inherited_depth_before_player_arrival","cultural_institutions_have_agendas_not_player_service"],
    }


def religion_summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "traditions": int(conn.execute("SELECT COUNT(*) FROM religious_traditions").fetchone()[0]),
        "active_affiliations": int(conn.execute("SELECT COUNT(*) FROM religious_affiliations WHERE status='active'").fetchone()[0]),
        "religious_institutions": int(conn.execute("SELECT COUNT(*) FROM religious_institutions WHERE status!='dissolved'").fetchone()[0]),
        "active_offices": int(conn.execute("SELECT COUNT(*) FROM religious_offices WHERE status='active'").fetchone()[0]),
        "active_observances": int(conn.execute("SELECT COUNT(*) FROM religious_observances WHERE status='active'").fetchone()[0]),
        "sacred_sites": int(conn.execute("SELECT COUNT(*) FROM sacred_sites WHERE status NOT IN ('destroyed','abandoned')").fetchone()[0]),
        "cultural_institutions": int(conn.execute("SELECT COUNT(*) FROM cultural_institution_profiles WHERE status!='dissolved'").fetchone()[0]),
        "active_programs": int(conn.execute("SELECT COUNT(*) FROM cultural_programs WHERE status='active'").fetchone()[0]),
    }
