from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any

from .ecology import find_route_path, start_travel
from .interactions import create_interaction
from .reputation import martial_instruction_public


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(v: Any) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def _actor_location(conn: sqlite3.Connection, actor_id: int) -> int | None:
    r = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _location_owner(conn: sqlite3.Connection, location_id: int | None) -> str | None:
    if location_id is None:
        return None
    r = conn.execute("SELECT political_owner FROM locations WHERE id=?", (location_id,)).fetchone()
    return str(r[0]) if r and r[0] else None


def register_offering(
    conn: sqlite3.Connection,
    provider_actor_id: int,
    offer_kind: str,
    domain_key: str,
    subject_key: str,
    *,
    provider_enterprise_id: int | None = None,
    provider_institution_actor_id: int | None = None,
    location_id: int | None = None,
    quality: float = 50,
    capacity_per_30: float = 1,
    availability: float = 100,
    public_reputation: float = 50,
    visibility: float = 50,
    scarcity: float = 50,
    access_mode: str = "open",
    metadata: dict[str, Any] | None = None,
) -> int:
    if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (provider_actor_id,)).fetchone():
        raise ValueError("provider actor is not active")
    if provider_enterprise_id is not None:
        e = conn.execute("SELECT owner_actor_id,institution_actor_id,location_id,status FROM civilian_enterprises WHERE id=?", (provider_enterprise_id,)).fetchone()
        if not e or str(e["status"]) not in {"active", "strained"}:
            raise ValueError("provider enterprise is not active")
        if e["owner_actor_id"] is not None and int(e["owner_actor_id"]) != provider_actor_id and (e["institution_actor_id"] is None or int(e["institution_actor_id"]) != provider_actor_id):
            raise ValueError("provider actor does not control enterprise")
        if location_id is None and e["location_id"] is not None:
            location_id = int(e["location_id"])
    if location_id is None:
        location_id = _actor_location(conn, provider_actor_id)
    existing = conn.execute(
        """SELECT id FROM seekable_offerings WHERE provider_actor_id=? AND COALESCE(provider_enterprise_id,0)=COALESCE(?,0)
           AND offer_kind=? AND domain_key=? AND subject_key=? AND status!='closed' ORDER BY id LIMIT 1""",
        (provider_actor_id, provider_enterprise_id, offer_kind, domain_key, subject_key),
    ).fetchone()
    day = _day(conn)
    if existing:
        oid = int(existing[0])
        conn.execute(
            """UPDATE seekable_offerings SET provider_institution_actor_id=?,location_id=?,quality=?,capacity_per_30=?,availability=?,
               public_reputation=?,visibility=?,scarcity=?,access_mode=?,status='active',last_review_day=?,next_review_day=?,metadata_json=? WHERE id=?""",
            (provider_institution_actor_id, location_id, max(0,min(100,float(quality))), max(0,float(capacity_per_30)),
             max(0,min(100,float(availability))), max(0,min(100,float(public_reputation))), max(0,min(100,float(visibility))),
             max(0,min(100,float(scarcity))), access_mode, day, day+30, _j(metadata or {}), oid),
        )
        return oid
    cur = conn.execute(
        """INSERT INTO seekable_offerings(provider_actor_id,provider_enterprise_id,provider_institution_actor_id,location_id,
           offer_kind,domain_key,subject_key,quality,capacity_per_30,availability,public_reputation,visibility,scarcity,access_mode,status,
           last_review_day,next_review_day,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
        (provider_actor_id, provider_enterprise_id, provider_institution_actor_id, location_id, offer_kind, domain_key, subject_key,
         max(0,min(100,float(quality))), max(0,float(capacity_per_30)), max(0,min(100,float(availability))),
         max(0,min(100,float(public_reputation))), max(0,min(100,float(visibility))), max(0,min(100,float(scarcity))), access_mode,
         day, day+30, _j(metadata or {})),
    )
    return int(cur.lastrowid)


def publish_enterprise_offering(
    conn: sqlite3.Connection,
    enterprise_id: int,
    offer_kind: str,
    domain_key: str,
    subject_key: str,
    *,
    good_id: int | None = None,
    access_mode: str = "appointment",
    scarcity: float = 50,
    metadata: dict[str, Any] | None = None,
) -> int:
    e = conn.execute(
        """SELECT e.*,bp.quality,bp.capacity,bp.service_reliability FROM civilian_enterprises e
           LEFT JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id WHERE e.id=?""",
        (enterprise_id,),
    ).fetchone()
    if not e or str(e["status"]) not in {"active","strained"}:
        raise ValueError("enterprise is not active")
    provider = e["owner_actor_id"] if e["owner_actor_id"] is not None else e["institution_actor_id"]
    if provider is None:
        raise ValueError("enterprise has no actor capable of receiving approaches")
    q = float(e["quality"] if e["quality"] is not None else e["admin_quality"])
    capacity = float(e["capacity"] if e["capacity"] is not None else e["labor_capacity"])
    rep = float(e["reputation"])
    meta = {"enterprise_id": enterprise_id, **(metadata or {})}
    if good_id is not None:
        meta["good_id"] = int(good_id)
    return register_offering(
        conn, int(provider), offer_kind, domain_key, subject_key,
        provider_enterprise_id=enterprise_id, provider_institution_actor_id=int(e["institution_actor_id"]) if e["institution_actor_id"] is not None else None,
        location_id=int(e["location_id"]) if e["location_id"] is not None else None,
        quality=q, capacity_per_30=max(1.0,capacity/5.0), availability=max(10.0,100.0-float(e["debt"])*.1),
        public_reputation=rep, visibility=min(100,35+rep*.65), scarcity=scarcity, access_mode=access_mode, metadata=meta,
    )


def publish_personal_instruction(
    conn: sqlite3.Connection,
    teacher_actor_id: int,
    domain_key: str,
    *,
    subject_key: str | None = None,
    reputation: float | None = None,
    visibility: float | None = None,
    access_mode: str = "visit",
    capacity: int = 3,
    duration_days: int = 360,
    min_entry_score: float = 0,
    completion_gain: float = 8,
    metadata: dict[str, Any] | None = None,
) -> int:
    subject_key = subject_key or domain_key
    score = conn.execute(
        """SELECT MAX(ac.score) FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id
           WHERE ac.actor_id=? AND d.domain_key=?""", (teacher_actor_id, domain_key)
    ).fetchone()[0]
    quality = float(score if score is not None else 50)
    day = _day(conn)
    rep_mode = "explicit" if reputation is not None else "social_derived"
    public_rep = max(0.0, min(100.0, float(reputation))) if reputation is not None else martial_instruction_public(conn, teacher_actor_id)
    public_visibility = max(0.0, min(100.0, float(visibility))) if visibility is not None else max(12.0, min(95.0, 18.0 + public_rep * .68))
    key = f"personal:{teacher_actor_id}:{domain_key}:{subject_key}"
    prog = conn.execute("SELECT id FROM education_programs WHERE program_key=? AND status='active' ORDER BY id LIMIT 1", (key,)).fetchone()
    if prog:
        program_id = int(prog[0])
    else:
        cur = conn.execute(
            """INSERT INTO education_programs(institution_actor_id,program_key,name,domain_key,program_kind,duration_days,capacity,
               min_entry_score,min_teacher_score,completion_gain,max_score_from_program,status,created_day,review_cadence_days,metadata_json)
               VALUES (NULL,?,?,?,?,?,?,?,?,?,95,'active',?,30,?)""",
            (key, f"Personal instruction under actor #{teacher_actor_id}", domain_key, "advanced_instruction", int(duration_days), int(capacity),
             float(min_entry_score), max(0.0,quality-12.0), float(completion_gain), day,
             _j({"personal_teacher_actor_id":teacher_actor_id,"seek01":True, **(metadata or {})})),
        )
        program_id = int(cur.lastrowid)
    return register_offering(
        conn, teacher_actor_id, "instruction", domain_key, subject_key,
        quality=quality, capacity_per_30=max(1,float(capacity)), public_reputation=public_rep, visibility=public_visibility,
        scarcity=max(20,100-quality), access_mode=access_mode,
        metadata={"program_id":program_id,"personal_instruction":True,"reputation_mode":rep_mode, **(metadata or {})},
    )


def create_seek_intent(
    conn: sqlite3.Connection,
    seeker_actor_id: int,
    need_kind: str,
    domain_key: str,
    subject_key: str,
    *,
    intensity: float = 50,
    min_quality: float = 0,
    quantity: float = 1,
    budget: float | None = None,
    preferred_location_id: int | None = None,
    source_kind: str | None = None,
    source_id: int | None = None,
    expires_in_days: int | None = 365,
    metadata: dict[str, Any] | None = None,
) -> int:
    if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (seeker_actor_id,)).fetchone():
        raise ValueError("seeker actor is not active")
    existing = conn.execute(
        """SELECT id FROM actor_seek_intents WHERE seeker_actor_id=? AND need_kind=? AND domain_key=? AND subject_key=?
           AND status IN ('searching','traveling','approaching') ORDER BY id LIMIT 1""",
        (seeker_actor_id, need_kind, domain_key, subject_key),
    ).fetchone()
    if existing:
        return int(existing[0])
    day = _day(conn)
    cur = conn.execute(
        """INSERT INTO actor_seek_intents(seeker_actor_id,need_kind,domain_key,subject_key,intensity,min_quality,quantity,budget,
           preferred_location_id,status,source_kind,source_id,created_day,last_review_day,next_review_day,expires_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,'searching',?,?,?,?,?,?,?)""",
        (seeker_actor_id,need_kind,domain_key,subject_key,max(0,min(100,float(intensity))),max(0,min(100,float(min_quality))),
         max(.01,float(quantity)),budget,preferred_location_id,source_kind,source_id,day,day,day+1,
         None if expires_in_days is None else day+int(expires_in_days),_j(metadata or {})),
    )
    return int(cur.lastrowid)


def _relation_knows(conn: sqlite3.Connection, seeker: int, provider: int) -> bool:
    return conn.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (seeker,provider)).fetchone() is not None


def _discoverable(conn: sqlite3.Connection, seeker: int, offer: sqlite3.Row) -> tuple[bool,float,float,str]:
    provider = int(offer["provider_actor_id"])
    if _relation_knows(conn,seeker,provider):
        return True,.95,1.0,"known_person"
    mode = str(offer["access_mode"])
    if mode in {"closed","invitation"}:
        return False,0,0,"closed"
    sloc = _actor_location(conn,seeker)
    ploc = int(offer["location_id"]) if offer["location_id"] is not None else _actor_location(conn,provider)
    fame = .45*float(offer["public_reputation"]) + .35*float(offer["visibility"]) + .20*float(offer["scarcity"])
    if sloc is not None and ploc is not None and sloc == ploc:
        return fame >= 20, min(.95,.55+fame/220), 1.0, "local_reputation"
    same_owner = _location_owner(conn,sloc) is not None and _location_owner(conn,sloc)==_location_owner(conn,ploc)
    if same_owner and fame >= 43:
        return True,min(.9,.45+fame/200),.9,"regional_reputation"
    if fame >= 76:
        return True,min(.88,.35+fame/180),.78 if mode!="rumoured" else .45,"wide_reputation"
    return False,0,0,"insufficient_reputation_reach"


def _offering_active_load(conn: sqlite3.Connection, offering_id: int) -> float:
    r = conn.execute(
        """SELECT COALESCE(SUM(quantity),0) FROM actor_seek_intents
           WHERE selected_offering_id=? AND status IN ('traveling','approaching')""", (offering_id,)
    ).fetchone()
    load = float(r[0] or 0.0)
    offer = conn.execute("SELECT offer_kind,metadata_json FROM seekable_offerings WHERE id=?", (offering_id,)).fetchone()
    if offer and str(offer["offer_kind"]) == "instruction":
        meta = _loads(offer["metadata_json"], {})
        program_id = meta.get("program_id")
        if program_id is not None:
            active = conn.execute(
                "SELECT COUNT(*) FROM education_enrollments WHERE program_id=? AND status='active'", (int(program_id),)
            ).fetchone()[0]
            load += float(active or 0)
    return load


def _offering_capacity_now(conn: sqlite3.Connection, offer: sqlite3.Row) -> float:
    return max(0.0, float(offer["capacity_per_30"]) * max(0.0, float(offer["availability"])) / 100.0)


def discover_for_intent(conn: sqlite3.Connection, intent_id: int) -> list[dict[str,Any]]:
    intent = conn.execute("SELECT * FROM actor_seek_intents WHERE id=?",(intent_id,)).fetchone()
    if not intent:
        raise ValueError("unknown seek intent")
    rows = conn.execute(
        """SELECT * FROM seekable_offerings WHERE status='active' AND domain_key=? AND subject_key=? AND quality>=? AND availability>0
           ORDER BY quality DESC,public_reputation DESC,id""",
        (str(intent["domain_key"]),str(intent["subject_key"]),float(intent["min_quality"])),
    ).fetchall()
    day=_day(conn); out=[]
    for o in rows:
        if int(o["provider_actor_id"])==int(intent["seeker_actor_id"]):
            continue
        ok,conf,locc,source=_discoverable(conn,int(intent["seeker_actor_id"]),o)
        if not ok:
            continue
        conn.execute(
            """INSERT INTO seek_awareness(seeker_actor_id,offering_id,confidence,location_certainty,source_kind,learned_day,updated_day,metadata_json)
               VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(seeker_actor_id,offering_id) DO UPDATE SET
               confidence=MAX(seek_awareness.confidence,excluded.confidence),location_certainty=MAX(seek_awareness.location_certainty,excluded.location_certainty),
               source_kind=excluded.source_kind,updated_day=excluded.updated_day""",
            (int(intent["seeker_actor_id"]),int(o["id"]),conf,locc,source,day,day,_j({"seek_intent_id":intent_id})),
        )
        sloc=_actor_location(conn,int(intent["seeker_actor_id"])); ploc=int(o["location_id"]) if o["location_id"] is not None else _actor_location(conn,int(o["provider_actor_id"]))
        route_ok = True if sloc==ploc else bool(sloc is not None and ploc is not None and find_route_path(conn,sloc,ploc,day=day))
        capacity_now = _offering_capacity_now(conn, o)
        active_load = _offering_active_load(conn, int(o["id"]))
        # Capacity is a real access constraint, not a reputation penalty.  A provider may be famous
        # enough to be known by many seekers while temporarily unable to accept another named approach.
        if capacity_now <= 0 or active_load + float(intent["quantity"]) > capacity_now + 1e-9:
            continue
        load_ratio = active_load / max(0.01, capacity_now)
        score=(float(o["quality"])-float(intent["min_quality"]))*0.45 + float(o["public_reputation"])*.18 + float(o["scarcity"])*.12 + conf*18 + (8 if route_ok else -25) - load_ratio*9
        out.append({"offering_id":int(o["id"]),"score":score,"confidence":conf,"location_certainty":locc,"route_ok":route_ok,"source_kind":source,
                    "active_load":round(active_load,3),"capacity_now":round(capacity_now,3)})
    return sorted(out,key=lambda x:(-x["score"],x["offering_id"]))


def _pending_seek_interaction(conn: sqlite3.Connection, intent_id: int) -> sqlite3.Row | None:
    rows=conn.execute("SELECT * FROM interactions WHERE status='pending' ORDER BY id DESC LIMIT 100").fetchall()
    for r in rows:
        terms=_loads(r["terms_json"],{})
        if int(terms.get("seek_intent_id") or 0)==int(intent_id):
            return r
    return None


def _approach(conn: sqlite3.Connection, intent: sqlite3.Row, offer: sqlite3.Row, day: int) -> int:
    meta=_loads(offer["metadata_json"],{})
    provider=int(offer["provider_actor_id"]); seeker=int(intent["seeker_actor_id"])
    domain_action: dict[str,Any]
    interaction_type="request"
    if str(offer["offer_kind"])=="instruction":
        pid=meta.get("program_id")
        if pid is None:
            raise ValueError("instruction offering has no program")
        domain_action={"kind":"seek_personal_instruction","initiator_actor_id":seeker,"payload":{"program_id":int(pid),"offering_id":int(offer["id"]),"teacher_actor_id":provider}}
    elif str(offer["offer_kind"])=="goods":
        good_id=meta.get("good_id")
        if good_id is None or offer["provider_enterprise_id"] is None:
            raise ValueError("goods offering lacks good/enterprise")
        interaction_type="contract"
        domain_action={"kind":"seek_direct_procurement","initiator_actor_id":seeker,"payload":{"offering_id":int(offer["id"]),"seller_enterprise_id":int(offer["provider_enterprise_id"]),"good_id":int(good_id),"quantity":float(intent["quantity"])}}
    else:
        domain_action={"kind":"seek_provider_service","initiator_actor_id":seeker,"payload":{"offering_id":int(offer["id"]),"subject_key":str(offer["subject_key"])}}
    terms={"purpose":f"seek {offer['subject_key']}","seek_intent_id":int(intent["id"]),"offering_id":int(offer["id"]),"domain_action":domain_action}
    iid=create_interaction(conn,seeker,provider,interaction_type,day,urgency=3 if float(intent["intensity"])>=70 else 2,stakes=max(1,min(5,int(math.ceil(float(intent["intensity"])/22)))),terms=terms,
                           rationale=f"The proposer sought out a provider because persisted need and public/known capability made this offering attractive.")
    conn.execute("UPDATE actor_seek_intents SET status='approaching',selected_offering_id=?,last_review_day=?,next_review_day=? WHERE id=?",(int(offer["id"]),day,day+7,int(intent["id"])))
    return iid


def process_seek_intent(conn: sqlite3.Connection, intent_id: int, day: int | None=None) -> dict[str,Any]:
    day=_day(conn) if day is None else int(day)
    intent=conn.execute("SELECT * FROM actor_seek_intents WHERE id=?",(intent_id,)).fetchone()
    if not intent or str(intent["status"]) not in {"searching","traveling","approaching"}:
        return {"intent_id":intent_id,"action":"none"}
    if intent["expires_day"] is not None and day>int(intent["expires_day"]):
        conn.execute("UPDATE actor_seek_intents SET status='expired',last_review_day=?,next_review_day=? WHERE id=?",(day,day,intent_id)); return {"intent_id":intent_id,"action":"expired"}
    pending=_pending_seek_interaction(conn,intent_id)
    if pending:
        conn.execute("UPDATE actor_seek_intents SET status='approaching',last_review_day=?,next_review_day=? WHERE id=?",(day,day+7,intent_id)); return {"intent_id":intent_id,"action":"pending_interaction","interaction_id":int(pending["id"])}
    # If a prior interaction resolved, domain callback marks fulfilled on acceptance. Rejection returns search to market.
    if str(intent["status"])=="approaching":
        last=conn.execute("SELECT * FROM interactions WHERE proposer_actor_id=? ORDER BY id DESC LIMIT 20",(int(intent["seeker_actor_id"]),)).fetchall()
        for r in last:
            t=_loads(r["terms_json"],{})
            if int(t.get("seek_intent_id") or 0)==intent_id and str(r["status"]) in {"rejected","cancelled","expired"}:
                conn.execute("UPDATE actor_seek_intents SET status='searching',selected_offering_id=NULL,last_review_day=?,next_review_day=? WHERE id=?",(day,day+14,intent_id)); break
    selected=intent["selected_offering_id"]
    offer=conn.execute("SELECT * FROM seekable_offerings WHERE id=? AND status='active'",(int(selected),)).fetchone() if selected is not None else None
    if offer is None:
        matches=discover_for_intent(conn,intent_id)
        if not matches and str(intent["need_kind"]) == "instruction" and str(intent["domain_key"]) == "martial_instruction":
            # Actual demand may reveal a suitable pre-existing background teacher. It never creates one.
            from .teaching_ecology import ensure_provider_for_seek_intent
            ensure_provider_for_seek_intent(conn,intent_id)
            matches=discover_for_intent(conn,intent_id)
        if not matches:
            conn.execute("UPDATE actor_seek_intents SET status='searching',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,intent_id)); return {"intent_id":intent_id,"action":"no_provider_known"}
        offer=conn.execute("SELECT * FROM seekable_offerings WHERE id=?",(matches[0]["offering_id"],)).fetchone()
        conn.execute("UPDATE actor_seek_intents SET selected_offering_id=? WHERE id=?",(int(offer["id"]),intent_id))
    seeker=int(intent["seeker_actor_id"]); sloc=_actor_location(conn,seeker); ploc=int(offer["location_id"]) if offer["location_id"] is not None else _actor_location(conn,int(offer["provider_actor_id"]))
    physical = str(offer["offer_kind"])=="instruction" or str(offer["access_mode"]) in {"visit","rumoured"}
    if physical and (sloc is None or ploc is None):
        conn.execute("UPDATE actor_seek_intents SET status='blocked',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,intent_id))
        return {"intent_id":intent_id,"action":"blocked_unknown_location"}
    if physical and sloc!=ploc:
        active=conn.execute("SELECT * FROM travel_plans WHERE subject_kind='actor' AND subject_id=? AND status IN ('active','stalled') ORDER BY id DESC LIMIT 1",(seeker,)).fetchone()
        if active:
            conn.execute("UPDATE actor_seek_intents SET status='traveling',last_review_day=?,next_review_day=? WHERE id=?",(day,day+3,intent_id)); return {"intent_id":intent_id,"action":"traveling","travel_plan_id":int(active["id"])}
        if not find_route_path(conn,sloc,ploc,day=day):
            conn.execute("UPDATE actor_seek_intents SET status='blocked',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,intent_id)); return {"intent_id":intent_id,"action":"blocked_no_route"}
        tid=start_travel(conn,"actor",seeker,ploc,metadata={"purpose":"seek_provider","seek_intent_id":intent_id,"offering_id":int(offer["id"]),"provider_actor_id":int(offer["provider_actor_id"])})
        conn.execute("UPDATE actor_seek_intents SET status='traveling',last_review_day=?,next_review_day=? WHERE id=?",(day,day+3,intent_id)); return {"intent_id":intent_id,"action":"started_travel","travel_plan_id":tid}
    iid=_approach(conn,intent,offer,day)
    return {"intent_id":intent_id,"action":"approach","interaction_id":iid,"provider_actor_id":int(offer["provider_actor_id"])}


def refresh_enterprise_offerings(conn: sqlite3.Connection) -> int:
    """Project discoverable capabilities from real enterprise state.

    This is intentionally conservative.  Only domains with a real SEEK consequence bridge should
    auto-publish here; adding an archetype to the business catalogue is not enough by itself.
    """
    horses = conn.execute("SELECT id FROM market_goods WHERE good_key='horses_remounts'").fetchone()
    if not horses:
        return 0
    horse_good = int(horses[0])
    rows = conn.execute(
        """SELECT e.id enterprise_id
           FROM civilian_enterprises e
           JOIN enterprise_business_profiles bp ON bp.enterprise_id=e.id
           JOIN business_archetypes ba ON ba.id=bp.archetype_id
           WHERE e.status IN ('active','strained') AND ba.archetype_key='horse_breeder'
             AND EXISTS (SELECT 1 FROM production_sites ps WHERE ps.enterprise_id=e.id AND ps.good_id=? AND ps.active=1 AND ps.inventory>0)
           ORDER BY e.id""", (horse_good,)
    ).fetchall()
    published = 0
    for r in rows:
        eid = int(r["enterprise_id"])
        publish_enterprise_offering(
            conn, eid, "goods", "military_logistics", "remounts", good_id=horse_good,
            access_mode="appointment", scarcity=68,
            metadata={"auto_projected_from_enterprise": True, "capability_basis": "horse_breeder_with_remount_stock"},
        )
        published += 1
    # If the material capability disappears, pause only auto-projected remount offerings; explicit
    # campaign offerings remain under their owner's chosen state.
    conn.execute(
        """UPDATE seekable_offerings SET status='paused',last_review_day=?
           WHERE domain_key='military_logistics' AND subject_key='remounts' AND status='active'
             AND json_extract(metadata_json,'$.auto_projected_from_enterprise')=1
             AND (provider_enterprise_id IS NULL OR NOT EXISTS (
                 SELECT 1 FROM production_sites ps
                 WHERE ps.enterprise_id=seekable_offerings.provider_enterprise_id AND ps.good_id=? AND ps.active=1 AND ps.inventory>0
             ))""", (_day(conn), horse_good)
    )
    return published


def _stable_propensity(conn: sqlite3.Connection, actor_id: int, cycle: int, salt: str) -> float:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    raw = f"{seed}:{actor_id}:{cycle}:{salt}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") / float(2**64 - 1)


def ensure_martial_instruction_intents(conn: sqlite3.Connection, day: int | None=None) -> int:
    """Let individual practitioners form a real need to seek outside instruction.

    This is deliberately sparse at named resolution.  Ordinary aspirants remain aggregate social
    attention; a tracked actor becomes a named seeker only when poor teacher access, advancement
    pressure and their own deterministic propensity make the search consequential enough to track.
    The player actor is excluded because the engine must not invent the player's goals.
    """
    day = _day(conn) if day is None else int(day)
    cycle = day // 90
    player = conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id = int(player[0]) if player and player[0] is not None else None
    rows = conn.execute(
        """SELECT cp.actor_id,cp.current_stage,cp.teacher_support,cp.plateau_days,cp.training_effort,
                  cp.realization_integration,er.resolution_level
           FROM cultivation_profiles cp
           JOIN actors a ON a.id=cp.actor_id AND a.status='active'
           JOIN entity_resolution er ON er.entity_kind='actor' AND er.entity_id=cp.actor_id
           WHERE cp.active=1
             AND cp.current_stage IN ('First','Temper','Third','Breach','Fifth')
             AND er.resolution_level IN ('TRACKED','ACTIVE')
             AND cp.teacher_support < 36
           ORDER BY cp.actor_id"""
    ).fetchall()
    stage_pressure = {"First": 12.0, "Temper": 20.0, "Third": 18.0, "Breach": 14.0, "Fifth": 9.0}
    min_quality = {"First": 50.0, "Temper": 58.0, "Third": 66.0, "Breach": 76.0, "Fifth": 86.0}
    created = 0
    for r in rows:
        aid = int(r["actor_id"])
        if player_id is not None and aid == player_id:
            continue
        if conn.execute("SELECT 1 FROM teaching_relationships WHERE student_actor_id=? AND status='active' LIMIT 1", (aid,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND status='active' LIMIT 1", (aid,)).fetchone():
            continue
        if conn.execute(
            """SELECT 1 FROM actor_seek_intents WHERE seeker_actor_id=? AND need_kind='instruction'
               AND domain_key='martial_instruction' AND subject_key='martial_instruction'
               AND status IN ('searching','traveling','approaching') LIMIT 1""", (aid,)
        ).fetchone():
            continue
        support_gap = max(0.0, 40.0 - float(r["teacher_support"]))
        plateau = min(30.0, max(0.0, float(r["plateau_days"])) / 45.0)
        effort = max(0.0, float(r["training_effort"]) - 45.0) * 0.45
        integration_gap = max(0.0, 70.0 - float(r["realization_integration"])) * 0.12
        need_score = 22.0 + support_gap * 0.72 + plateau + effort + integration_gap + stage_pressure[str(r["current_stage"])]
        # No quota: each actor independently forms the goal.  The probability rises sharply only
        # when the actor has a genuine access/progression problem, keeping named seekers sparse.
        probability = max(0.0, min(0.22, (need_score - 62.0) / 180.0))
        if probability <= 0 or _stable_propensity(conn, aid, cycle, "martial_instruction") >= probability:
            continue
        intensity = max(45.0, min(92.0, need_score))
        create_seek_intent(
            conn, aid, "instruction", "martial_instruction", "martial_instruction",
            intensity=intensity, min_quality=min_quality[str(r["current_stage"])], quantity=1,
            source_kind="cultivation_instruction_need", source_id=aid, expires_in_days=270,
            metadata={"opening_stage": str(r["current_stage"]), "teacher_support": float(r["teacher_support"]),
                      "plateau_days": int(r["plateau_days"]), "named_need_score": round(need_score, 3)},
        )
        created += 1
    return created


def ensure_military_remount_intents(conn: sqlite3.Connection, day: int | None=None) -> int:
    """Create ordinary remount-procurement needs for polity governments.

    Needs exist independently of whether a famous breeder happens to be available.  The seeking
    layer then decides whether any known provider is worth approaching.
    """
    day=_day(conn) if day is None else int(day)
    created=0
    good=conn.execute("SELECT id FROM market_goods WHERE good_key='horses_remounts'").fetchone()
    if not good:
        return 0
    rows=conn.execute("""SELECT p.id polity_id,p.military_capacity,p.treasury_pressure,pga.decision_actor_id,ml.readiness,ml.transport_capacity,ml.status
                         FROM political_polities p JOIN polity_government_actors pga ON pga.polity_id=p.id
                         LEFT JOIN military_logistics_profiles ml ON ml.polity_id=p.id WHERE p.status!='dissolved'""").fetchall()
    for r in rows:
        aid=int(r["decision_actor_id"])
        if conn.execute("""SELECT 1 FROM actor_seek_intents WHERE seeker_actor_id=? AND domain_key='military_logistics' AND subject_key='remounts'
                           AND status IN ('searching','traveling','approaching')""",(aid,)).fetchone():
            continue
        readiness=float(r["readiness"] if r["readiness"] is not None else 50); transport=float(r["transport_capacity"] if r["transport_capacity"] is not None else 50)
        intensity=max(28,min(90,35+(100-readiness)*.28+float(r["military_capacity"])*.18+(12 if str(r["status"] or '')=='mobilized' else 0)))
        qty=max(2.0,round((float(r["military_capacity"])+transport)/18.0,1))
        create_seek_intent(conn,aid,"procurement","military_logistics","remounts",intensity=intensity,min_quality=45,quantity=qty,
                           source_kind="polity_remount_cycle",source_id=int(r["polity_id"]),expires_in_days=240,
                           metadata={"buyer_polity_id":int(r["polity_id"]),"good_id":int(good[0]),"ordinary_replacement_demand":True})
        created+=1
    return created


def next_seeking_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    r=conn.execute("SELECT MIN(next_review_day) FROM actor_seek_intents WHERE status IN ('searching','traveling','approaching') AND next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()
    if r and r[0] is not None: vals.append(int(r[0]))
    # Slow structural demand refresh, independent of whether a provider already exists.
    cyc=((int(after_day)//90)+1)*90
    if cyc<=int(end_day) and conn.execute("SELECT 1 FROM political_polities WHERE status!='dissolved' LIMIT 1").fetchone(): vals.append(cyc)
    return min(vals) if vals else None


def process_due_seeking(conn: sqlite3.Connection, day: int, *, event_logger=None) -> dict[str,int]:
    # Real capabilities are projected before needs search, so no actor must manually "register with SEEK".
    refresh_enterprise_offerings(conn)
    for offer in conn.execute("SELECT id,provider_actor_id,metadata_json FROM seekable_offerings WHERE status='active' AND offer_kind='instruction'").fetchall():
        meta = _loads(offer["metadata_json"], {})
        if meta.get("personal_instruction") and meta.get("reputation_mode") == "social_derived":
            rep = martial_instruction_public(conn, int(offer["provider_actor_id"]))
            vis = max(12.0, min(95.0, 18.0 + rep * .68))
            conn.execute("UPDATE seekable_offerings SET public_reputation=?,visibility=?,last_review_day=?,next_review_day=? WHERE id=?", (rep,vis,day,day+30,int(offer["id"])))
    # Demand renewal is intentionally slow; seven polity governments create at most seven standing remount searches.
    ensure_military_remount_intents(conn,day)
    ensure_martial_instruction_intents(conn,day)
    rows=conn.execute("SELECT id FROM actor_seek_intents WHERE status IN ('searching','traveling','approaching') AND next_review_day<=? ORDER BY next_review_day,id",(day,)).fetchall()
    counts={"seek_intents_reviewed":0,"seek_travel_started":0,"seek_approaches":0,"seek_blocked":0}
    for r in rows:
        res=process_seek_intent(conn,int(r[0]),day); counts["seek_intents_reviewed"]+=1
        if res.get("action")=="started_travel": counts["seek_travel_started"]+=1
        elif res.get("action")=="approach": counts["seek_approaches"]+=1
        elif str(res.get("action","")).startswith("blocked"): counts["seek_blocked"]+=1
    return counts


def mark_intent_fulfilled(conn: sqlite3.Connection, intent_id: int, *, detail: dict[str,Any] | None=None) -> None:
    day=_day(conn)
    row=conn.execute("SELECT metadata_json FROM actor_seek_intents WHERE id=?",(intent_id,)).fetchone()
    if not row:
        return
    meta=_loads(row[0],{}); meta.setdefault("fulfillment",{}).update(detail or {}); meta["fulfilled_day"]=day
    conn.execute("UPDATE actor_seek_intents SET status='fulfilled',last_review_day=?,next_review_day=?,metadata_json=? WHERE id=?",(day,day,_j(meta),intent_id))


def summary(conn: sqlite3.Connection) -> dict[str,int]:
    q=lambda sql:int(conn.execute(sql).fetchone()[0])
    return {
        "active_offerings":q("SELECT COUNT(*) FROM seekable_offerings WHERE status='active'"),
        "active_intents":q("SELECT COUNT(*) FROM actor_seek_intents WHERE status IN ('searching','traveling','approaching')"),
        "fulfilled_intents":q("SELECT COUNT(*) FROM actor_seek_intents WHERE status='fulfilled'"),
        "awareness_edges":q("SELECT COUNT(*) FROM seek_awareness"),
        "procurement_contracts":q("SELECT COUNT(*) FROM seek_procurement_contracts"),
    }
