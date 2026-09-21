from __future__ import annotations

"""PERSONECO-01 — pre-existing background people and parity crystallization.

The population owner remains POPLIFE/SCALE.  This module only gives a bounded sample of
ordinary people stable, demand-independent identity/professional traits before any scene or
institution asks for them.  Resolution turns one of those already-existing identities into an
actor; it never adds a person to population totals.
"""

import hashlib
import json
import random
import sqlite3
from typing import Any, Iterable

from .background_population import create_partition, load_partition
from .continuity import upsert_continuity_core, set_resolution
from .health import ensure_health_profile

_FIRST = (
    "Alden","Bren","Caro","Darian","Elias","Garran","Hale","Iven","Joren","Kellan",
    "Lucan","Marek","Nolan","Orin","Perrin","Rafe","Soren","Tomas","Varen","Willem",
    "Ada","Bera","Celia","Dara","Elin","Fara","Greta","Hessa","Iria","Jana",
    "Kara","Lena","Mira","Nessa","Orla","Petra","Rina","Sela","Tara","Vera",
)
_LAST = (
    "Vale","Kerr","Marr","Rooke","Brann","Voss","Dane","Kestrel","Torve","Renn",
    "Holt","Serrin","Marrow","Verran","Dorn","Pell","Reese","Ashe","Lowe","March",
    "Sten","Grey","Fenn","Toll","Mere","Dale","Ward","Harrow","Keen","Briar",
)
_OCCUPATIONS = (
    "labor","labor","labor","artisan","artisan","merchant","merchant","clerk","soldier",
    "teacher","physician","artist","transport","hospitality","criminal","criminal",
)
_STAGES = ("First","First","First","First","Temper","Temper","Third","Breach")


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, sort_keys=True, ensure_ascii=False)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _score(seed: int, uid: int, stream: str) -> float:
    raw = hashlib.sha256(f"{seed}:{uid}:{stream}".encode()).digest()
    return int.from_bytes(raw[:8], "big") / float(2**64 - 1)


def _pick(seq: tuple[str, ...], seed: int, uid: int, stream: str) -> str:
    x = _score(seed, uid, stream)
    return seq[min(len(seq)-1, int(x * len(seq)))]


def _source_location(conn: sqlite3.Connection, source: sqlite3.Row, seed: int, uid: int) -> int | None:
    if source["location_id"] is not None:
        return int(source["location_id"])
    rows = conn.execute(
        "SELECT location_id FROM settlement_scale_profiles WHERE bucket_key=? ORDER BY location_id",
        (str(source["bucket_key"]),),
    ).fetchall()
    if not rows:
        return None
    idx = min(len(rows)-1, int(_score(seed, uid, "location") * len(rows)))
    return int(rows[idx][0])


def _profile_stage(seed: int, uid: int, urban: bool) -> tuple[int, str | None]:
    # Identity traits are drawn before demand.  The rates are a bounded identity sample, not a
    # new population census; aggregate cultivation ecology remains authoritative elsewhere.
    p_open = 0.13 if urban else 0.08
    if _score(seed, uid, "open_core") >= p_open:
        return 0, None
    x = _score(seed, uid, "stage")
    if x < .58:
        return 1, "First"
    if x < .86:
        return 1, "Temper"
    if x < .965:
        return 1, "Third"
    if x < .994:
        return 1, "Breach"
    return 1, "Fifth"


def activate_background_people(conn: sqlite3.Connection) -> dict[str, int]:
    """Ensure disjoint identity reservoirs and demand-independent profiles exist.

    Most sources use 32 identities. Aldergate receives a larger bounded local sample because the
    already-existing v0.60 city ecology resolves many command figures there at opening.  The
    larger reservoir prevents causal demand from exhausting rare pre-existing traits such as
    Open-Core status; it changes only resolution granularity, never the population denominator.
    """
    day = _day(conn)
    sources = conn.execute("SELECT * FROM background_population_sources ORDER BY id").fetchall()
    created_partitions = created_profiles = 0
    for source in sources:
        sid = int(source["id"])
        part = conn.execute("SELECT * FROM background_population_partitions WHERE source_id=?", (sid,)).fetchone()
        if part is None:
            locname = None
            if source["location_id"] is not None:
                r = conn.execute("SELECT name FROM locations WHERE id=?", (int(source["location_id"]),)).fetchone()
                locname = str(r[0]) if r else None
            sample = 128 if locname == "Aldergate" else 32
            sample = max(1, min(sample, int(source["population_estimate"])))
            pid = create_partition(
                conn, sid, sample_size=sample,
                partition_key=f"personeco:source:{sid}",
                metadata={"personeco01": True, "demand_independent": True},
            )
            part = conn.execute("SELECT * FROM background_population_partitions WHERE id=?", (pid,)).fetchone()
            created_partitions += 1
        pid = int(part["id"])
        _, state = load_partition(conn, pid)
        seed = int(part["seed"])
        for uid in state.uid.tolist():
            uid = int(uid)
            if conn.execute("SELECT 1 FROM background_person_profiles WHERE partition_id=? AND local_uid=?", (pid, uid)).fetchone():
                continue
            snap = state.snapshot(uid)
            open_core, stage = _profile_stage(seed, uid, bool(source["urban"]))
            occupation = _pick(_OCCUPATIONS, seed, uid, "occupation")
            loc = _source_location(conn, source, seed, uid)
            given = _pick(_FIRST, seed, uid, "given")
            family = _pick(_LAST, seed, uid, "family")
            # The local uid is not visible in ordinary naming unless a collision must be resolved.
            # Store the stable identity's ordinary name before any demand appears.
            base = f"{given} {family}"
            # Profiles may share names; uniqueness is enforced only when an identity becomes tracked.
            conn.execute(
                """INSERT INTO background_person_profiles(
                     partition_id,local_uid,source_id,current_location_id,given_name,family_name,birth_day,
                     demographic_sex,occupation_domain,social_archetype,open_core,current_stage,
                     command_aptitude,economic_aptitude,medical_aptitude,teaching_aptitude,criminal_familiarity,
                     status,seeded_day,metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'background',?,?)""",
                (
                    pid,uid,sid,loc,given,family,day-int(snap["age_days"]),snap["demographic_sex"],occupation,
                    f"ordinary_{occupation}",open_core,stage,
                    round(_score(seed,uid,"command")*100,6),
                    round(_score(seed,uid,"economic")*100,6),
                    round(_score(seed,uid,"medical")*100,6),
                    round(_score(seed,uid,"teaching")*100,6),
                    round(_score(seed,uid,"criminal")*100,6),
                    day,_j({"profiled_before_demand":True,"stable_name":base,"population_delta":0}),
                ),
            )
            created_profiles += 1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('personeco01_activation_version','1')")
    total = int(conn.execute("SELECT COUNT(*) FROM background_person_profiles").fetchone()[0])
    return {"background_partitions_created": created_partitions, "background_person_profiles_created": created_profiles, "background_person_profiles": total}


def _unique_actor_name(conn: sqlite3.Connection, profile: sqlite3.Row) -> str:
    base = f"{profile['given_name']} {profile['family_name']}"
    if not conn.execute("SELECT 1 FROM actors WHERE name=?", (base,)).fetchone():
        return base
    suffix = int(profile["partition_id"]) * 10000 + int(profile["local_uid"])
    return f"{base} {suffix}"


def _candidate_rows(
    conn: sqlite3.Connection, *, location_id: int | None = None, occupation_domains: Iterable[str] | None = None,
    min_age: int = 18, max_age: int = 85, require_open_core: bool | None = None,
    required_stage: str | None = None,
) -> list[sqlite3.Row]:
    day = _day(conn)
    where = ["p.status='background'", "l.actor_id IS NULL", "(l.status IS NULL OR l.status<>'dead')", "p.birth_day<=?", "p.birth_day>=?"]
    args: list[Any] = [day-min_age*365, day-(max_age+1)*365]
    if location_id is not None:
        where.append("p.current_location_id=?")
        args.append(int(location_id))
    if occupation_domains:
        vals = [str(x) for x in occupation_domains]
        where.append("p.occupation_domain IN (%s)" % ",".join("?" for _ in vals))
        args.extend(vals)
    if require_open_core is not None:
        where.append("p.open_core=?")
        args.append(1 if require_open_core else 0)
    if required_stage:
        order = {"First":1,"Temper":2,"Third":3,"Breach":4,"Fifth":5,"Sixth":6}
        allowed = [s for s,v in order.items() if v >= order.get(required_stage,1)]
        where.append("p.current_stage IN (%s)" % ",".join("?" for _ in allowed))
        args.extend(allowed)
    sql = f"""SELECT p.* FROM background_person_profiles p
              LEFT JOIN background_population_identity_links l
                ON l.partition_id=p.partition_id AND l.local_uid=p.local_uid
              WHERE {' AND '.join(where)} ORDER BY p.partition_id,p.local_uid"""
    return conn.execute(sql, args).fetchall()


def find_background_candidate(
    conn: sqlite3.Connection, *, location_id: int | None = None, occupation_domains: Iterable[str] | None = None,
    min_age: int = 18, max_age: int = 85, require_open_core: bool | None = None,
    required_stage: str | None = None, command_weight: float = 0, economic_weight: float = 0,
    medical_weight: float = 0, teaching_weight: float = 0, criminal_weight: float = 0,
) -> sqlite3.Row | None:
    rows = _candidate_rows(
        conn, location_id=location_id, occupation_domains=occupation_domains, min_age=min_age, max_age=max_age,
        require_open_core=require_open_core, required_stage=required_stage,
    )
    if not rows and location_id is not None:
        # The world may reveal someone from the same broader population bucket rather than conjure
        # a local person.  Prefer exact location, but broaden only to already-profiled identities.
        bucket = conn.execute(
            """SELECT s.bucket_key FROM background_population_sources s
               JOIN background_person_profiles p ON p.source_id=s.id
               WHERE p.current_location_id=? LIMIT 1""", (int(location_id),)
        ).fetchone()
        if bucket:
            day = _day(conn)
            vals = [str(x) for x in occupation_domains] if occupation_domains else []
            where = ["p.status='background'", "p.birth_day<=?", "p.birth_day>=?", "s.bucket_key=?"]
            args: list[Any] = [day-min_age*365, day-(max_age+1)*365, str(bucket[0])]
            if vals:
                where.append("p.occupation_domain IN (%s)" % ",".join("?" for _ in vals)); args.extend(vals)
            if require_open_core is not None:
                where.append("p.open_core=?"); args.append(1 if require_open_core else 0)
            rows = conn.execute(
                f"""SELECT p.* FROM background_person_profiles p
                    JOIN background_population_sources s ON s.id=p.source_id
                    LEFT JOIN background_population_identity_links l ON l.partition_id=p.partition_id AND l.local_uid=p.local_uid
                    WHERE {' AND '.join(where)} AND (l.actor_id IS NULL) ORDER BY p.partition_id,p.local_uid""", args
            ).fetchall()
    if not rows:
        return None
    def score(r: sqlite3.Row) -> float:
        return (
            float(r["command_aptitude"])*command_weight + float(r["economic_aptitude"])*economic_weight +
            float(r["medical_aptitude"])*medical_weight + float(r["teaching_aptitude"])*teaching_weight +
            float(r["criminal_familiarity"])*criminal_weight +
            (8.0 if r["open_core"] else 0.0)
        )
    return max(rows, key=score)


def resolve_background_person(
    conn: sqlite3.Connection, *, reason: str, demand_kind: str | None = None,
    location_id: int | None = None, occupation_domains: Iterable[str] | None = None,
    min_age: int = 18, max_age: int = 85, require_open_core: bool | None = None,
    required_stage: str | None = None, subtype: str | None = None,
    command_weight: float = 0, economic_weight: float = 0, medical_weight: float = 0,
    teaching_weight: float = 0, criminal_weight: float = 0,
) -> int | None:
    """Reveal one pre-existing POPBACK identity as a tracked actor.

    No population source/cohort count is incremented.  If no suitable profiled identity exists,
    return ``None``; callers must cope with genuine scarcity instead of manufacturing an adult.
    """
    profile = find_background_candidate(
        conn, location_id=location_id, occupation_domains=occupation_domains, min_age=min_age, max_age=max_age,
        require_open_core=require_open_core, required_stage=required_stage, command_weight=command_weight,
        economic_weight=economic_weight, medical_weight=medical_weight, teaching_weight=teaching_weight,
        criminal_weight=criminal_weight,
    )
    if profile is None:
        return None
    day = _day(conn)
    aid = int(conn.execute(
        """INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo)
           VALUES (?,'character',?,?,?,'active',?,0)""",
        (_unique_actor_name(conn, profile), subtype or f"resolved_{profile['occupation_domain']}", profile["current_location_id"], profile["current_location_id"],
         "Resolved from a pre-existing POPBACK identity; not created by demand."),
    ).lastrowid)
    age = max(0, (day-int(profile["birth_day"]))//365)
    life_stage = "elder" if age >= 60 else ("child" if age < 13 else ("adolescent" if age < 18 else "adult"))
    conn.execute(
        """INSERT INTO actor_life_profiles(actor_id,birth_day,demographic_sex,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json)
           VALUES (?,?,?,?,?,'living',?,?)""",
        (aid,int(profile["birth_day"]),str(profile["demographic_sex"]),life_stage,1 if age>=18 else 0,day,
         _j({"source":"PERSONECO01","partition_id":int(profile["partition_id"]),"local_uid":int(profile["local_uid"]),"population_delta":0})),
    )
    open_core = bool(profile["open_core"]); stage = str(profile["current_stage"]) if profile["current_stage"] else None
    conn.execute(
        """INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
             training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,
             next_realization_check_day,last_review_day,next_review_day,status,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (aid,"Open-Core" if open_core else "Closed-Core",stage,1 if open_core and stage else 0,
         32 if open_core else 0,20 if open_core else 0,45 if open_core else 0,45,0,0,1.0,1.0,
         day+365,day,day+30,"active" if open_core and stage else "paused",
         _j({"source":"PERSONECO01","preexisting_trait":True})),
    )
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold)
           VALUES (?,'DORMANT',180,.30,.55,?,?,3)""", (aid,day,day+180)
    )
    # Stable personality draw from the identity, not from the demand that exposed them.
    rr = random.Random(int(profile["partition_id"])*1_000_003 + int(profile["local_uid"])*7919)
    conn.execute(
        """INSERT OR IGNORE INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism)
           VALUES (?,?,?,?,?,?,?)""",
        (aid,rr.uniform(.20,.82),rr.uniform(.25,.85),rr.uniform(.25,.85),rr.uniform(.25,.90),rr.uniform(.20,.90),rr.uniform(.30,.92)),
    )
    ensure_health_profile(conn, aid, longevity_class=(stage or "ordinary").lower())
    upsert_continuity_core(
        conn,"actor",aid,
        {"birth_day":int(profile["birth_day"]),"demographic_sex":str(profile["demographic_sex"]),
         "occupation_domain":str(profile["occupation_domain"]),"crystallized_from_background":True,
         "background_partition_id":int(profile["partition_id"]),"background_local_uid":int(profile["local_uid"])},
        source_kind="campaign", notes="Identity existed in POPBACK before causal resolution.",
    )
    set_resolution(conn,"actor",aid,"TRACKED",day=day,reason=reason,source_kind="crystallization",source_id=int(profile["partition_id"]))
    conn.execute(
        """INSERT INTO background_population_identity_links(partition_id,local_uid,status,actor_id,first_link_day,last_update_day,snapshot_json,metadata_json)
           VALUES (?,?,'crystallized',?,?,?,?,?)
           ON CONFLICT(partition_id,local_uid) DO UPDATE SET status='crystallized',actor_id=excluded.actor_id,last_update_day=excluded.last_update_day,metadata_json=excluded.metadata_json""",
        (int(profile["partition_id"]),int(profile["local_uid"]),aid,day,day,
         _j({"birth_day":int(profile["birth_day"]),"demographic_sex":str(profile["demographic_sex"])}),
         _j({"reason":reason,"demand_kind":demand_kind,"population_delta":0})),
    )
    conn.execute("UPDATE background_person_profiles SET status='resolved',actor_id=? WHERE partition_id=? AND local_uid=?",
                 (aid,int(profile["partition_id"]),int(profile["local_uid"])))
    conn.execute(
        """INSERT INTO person_resolution_provenance(actor_id,partition_id,local_uid,resolved_day,resolution_reason,demand_kind,metadata_json)
           VALUES (?,?,?,?,?,?,?)""",
        (aid,int(profile["partition_id"]),int(profile["local_uid"]),day,reason,demand_kind,
         _j({"identity_profile_seeded_before_demand":True,"population_delta":0})),
    )
    try:
        from .profession_runtime import sync_actor_professions
        sync_actor_professions(conn, aid)
    except sqlite3.OperationalError:
        pass
    return aid


def background_person_summary(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "profiles": int(conn.execute("SELECT COUNT(*) FROM background_person_profiles").fetchone()[0]),
        "background": int(conn.execute("SELECT COUNT(*) FROM background_person_profiles WHERE status='background'").fetchone()[0]),
        "resolved": int(conn.execute("SELECT COUNT(*) FROM background_person_profiles WHERE status='resolved'").fetchone()[0]),
        "provenance": int(conn.execute("SELECT COUNT(*) FROM person_resolution_provenance").fetchone()[0]),
    }
