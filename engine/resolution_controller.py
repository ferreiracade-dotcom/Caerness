from __future__ import annotations

import json
import math
import random
import sqlite3
from typing import Any

from .continuity import RESOLUTION_LEVELS, resolution_state, set_institution_profile, set_resolution, upsert_continuity_core

RANK = {name: i for i, name in enumerate(RESOLUTION_LEVELS)}


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, ensure_ascii=False, sort_keys=True)


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _entity_row(conn: sqlite3.Connection, entity_kind: str, entity_id: int) -> sqlite3.Row:
    if entity_kind not in {"actor", "institution"}:
        raise ValueError("Resolution controller currently supports actor and institution")
    row = conn.execute("SELECT * FROM actors WHERE id=?", (entity_id,)).fetchone()
    if not row or (entity_kind == "institution" and row["actor_type"] != "institution") or (entity_kind == "actor" and row["actor_type"] != "character"):
        raise ValueError(f"Unknown {entity_kind} #{entity_id}")
    return row


def significance_score(conn: sqlite3.Connection, entity_kind: str, entity_id: int, *, signals: dict[str, float] | None = None) -> tuple[float, dict[str, float]]:
    """Objective consequence score. Camera/player attention is intentionally not a signal."""
    row = _entity_row(conn, entity_kind, entity_id)
    parts: dict[str, float] = {}
    if entity_kind == "actor":
        lp=conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(entity_id,)).fetchone()
        if str(row["status"]) in {"deceased","historical"} or (lp and str(lp[0])=="deceased"):
            return 0.0, {"life_state": -100.0}
    sim = conn.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?", (entity_id,)).fetchone()
    if sim:
        parts["simulation_tier"] = {"ACTIVE": 35.0, "STRATEGIC": 30.0, "DORMANT": 6.0}.get(str(sim[0]), 0.0)

    if entity_kind == "actor":
        enterprises = conn.execute(
            "SELECT capital,cash,reputation,status FROM civilian_enterprises WHERE owner_actor_id=? AND status IN ('active','strained','insolvent')",
            (entity_id,),
        ).fetchall()
        if enterprises:
            scale = sum(max(0.0, float(r["capital"])) + max(0.0, float(r["cash"])) for r in enterprises)
            rep = max(float(r["reputation"]) for r in enterprises)
            parts["enterprise_reach"] = min(35.0, 8.0 + 5.0 * math.log10(1.0 + scale) + max(0.0, rep - 50.0) * 0.15)
        staff = conn.execute(
            """SELECT s.authority,e.capital,e.cash,e.reputation FROM enterprise_staff s
               JOIN civilian_enterprises e ON e.id=s.enterprise_id
               WHERE s.actor_id=? AND s.status='active' AND s.authority>=40 AND e.status IN ('active','strained','insolvent')""",
            (entity_id,),
        ).fetchall() if _table(conn,'enterprise_staff') else []
        if staff:
            max_auth=max(float(r['authority']) for r in staff)
            scale=sum(max(0.0,float(r['capital']))+max(0.0,float(r['cash'])) for r in staff)
            parts['enterprise_authority']=min(26.0,10.0+max_auth*.12+3.0*math.log10(1.0+scale))
        memberships = conn.execute(
            "SELECT role_text FROM institution_memberships WHERE member_actor_id=? AND status='active'", (entity_id,)
        ).fetchall()
        if _table(conn,"cultivation_profiles"):
            cp=conn.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=? AND core_state='Open-Core'",(entity_id,)).fetchone()
            if cp and cp[0] is not None:
                parts["martial_standing"]={"First":2.0,"Temper":4.0,"Third":7.0,"Breach":11.0,"Fifth":20.0,"Sixth":35.0}.get(str(cp[0]),0.0)
        leadership_words = ("head", "king", "queen", "emperor", "empress", "prince", "minister", "prefect", "bishop", "master", "heir", "patriarch", "matriarch", "chief", "captain")
        if any(any(w in str(r[0] or "").lower() for w in leadership_words) for r in memberships):
            parts["office_or_leadership"] = 20.0
        active_threads = conn.execute(
            "SELECT COUNT(*) FROM thread_participants tp JOIN threads t ON t.id=tp.thread_id WHERE tp.actor_id=? AND t.status='active'",
            (entity_id,),
        ).fetchone() if _table(conn, "thread_participants") else None
        if active_threads and int(active_threads[0]):
            parts["active_threads"] = min(15.0, 4.0 * int(active_threads[0]))
    else:
        members = int(conn.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'", (entity_id,)).fetchone()[0])
        if members:
            parts["persistent_membership"] = min(22.0, 4.0 + 4.0 * math.log2(1 + members))
        ip = conn.execute("SELECT trajectory,economic_json,succession_json FROM institution_profiles WHERE actor_id=?", (entity_id,)).fetchone()
        if ip:
            parts["trajectory"] = {"rising":15.0,"crisis":18.0,"transforming":12.0,"stable":4.0,"declining":2.0,"dormant":0.0}.get(str(ip["trajectory"]), 0.0)
        ents = int(conn.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE institution_actor_id=? AND status IN ('active','strained','insolvent')", (entity_id,)).fetchone()[0])
        if ents: parts["enterprise_footprint"] = min(20.0, 6.0 + 4.0 * ents)
        proc = int(conn.execute("SELECT COUNT(*) FROM canon_process_anchors WHERE entity_actor_id=? AND status NOT IN ('closed','resolved')", (entity_id,)).fetchone()[0]) if _table(conn,"canon_process_anchors") else 0
        if proc: parts["open_institutional_process"] = min(18.0, 8.0 * proc)

    # External domain systems may contribute objective signals such as regional market share,
    # case exposure, follower count, military command, or cross-border contract load.
    for key, value in (signals or {}).items():
        if key.lower() in {"camera", "player_attention", "narrative_interest"}:
            continue
        parts[f"signal:{key}"] = max(-40.0, min(40.0, float(value)))
    return max(0.0, min(100.0, sum(parts.values()))), parts


def _table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def proposed_level(score: float) -> str:
    # Automatic world simulation never promotes an entity to SCENE; scene is a camera state.
    if score >= 75.0: return "ACTIVE"
    if score >= 32.0: return "TRACKED"
    return "STRUCTURAL"


def _sync_sim_tier(conn: sqlite3.Connection, entity_id: int, level: str, day: int) -> None:
    tier, cadence = ({"ACTIVE":("ACTIVE",30), "TRACKED":("STRATEGIC",90)}.get(level, ("DORMANT",180)))
    conn.execute(
        """INSERT INTO simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold)
           VALUES (?,?,?,?,?,?,?,3)
           ON CONFLICT(actor_id) DO UPDATE SET tier=excluded.tier,cadence_days=excluded.cadence_days,last_review_day=excluded.last_review_day,next_review_day=excluded.next_review_day""",
        (entity_id,tier,cadence,0.25,0.5,day,day+cadence),
    )


def review_entity(conn: sqlite3.Connection, entity_kind: str, entity_id: int, *, signals: dict[str,float] | None = None, day: int | None = None, demotion_reviews: int = 2) -> dict[str, Any]:
    _entity_row(conn, entity_kind, entity_id)
    day = _day(conn) if day is None else int(day)
    state = resolution_state(conn, entity_kind, entity_id)
    current = str(state["resolution_level"]) if state else "STRUCTURAL"
    score, parts = significance_score(conn, entity_kind, entity_id, signals=signals)
    target = proposed_level(score)
    lock=str(state.get("locked_min_level")) if state and state.get("locked_min_level") else None
    life=conn.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?",(entity_id,)).fetchone() if entity_kind=="actor" else None
    deceased = entity_kind=="actor" and (str(_entity_row(conn,entity_kind,entity_id)["status"]) in {"deceased","historical"} or (life and str(life[0])=="deceased"))
    if deceased:
        target="STRUCTURAL"
    elif lock in RANK and RANK[target] < RANK[lock]:
        target=lock
    # Respect a manually/camera elevated SCENE state; autonomous reviews do not overwrite it.
    if current == "SCENE":
        action, applied, reason = "defer", current, "SCENE is camera-controlled; autonomous controller did not alter it"
    elif RANK[target] > RANK[current]:
        action, applied, reason = "promote", target, "objective consequence threshold crossed"
        set_resolution(conn, entity_kind, entity_id, target, day=day, reason=reason, source_kind="engine", review_cadence_days=30 if target=="ACTIVE" else 90, next_review_day=day+(30 if target=="ACTIVE" else 90), metadata={"significance_score":score,"score_parts":parts})
        _sync_sim_tier(conn, entity_id, target, day)
    elif RANK[target] < RANK[current]:
        prior = conn.execute(
            """SELECT proposed_level FROM resolution_reviews WHERE entity_kind=? AND entity_id=? AND day<? ORDER BY day DESC,id DESC LIMIT ?""",
            (entity_kind,entity_id,day,max(1,demotion_reviews-1)),
        ).fetchall()
        sustained = len(prior) >= max(1,demotion_reviews-1) and all(str(r[0]) == target for r in prior)
        if sustained:
            action, applied, reason = "demote", target, "lower consequence state sustained across reviews; persistence retained"
            set_resolution(conn, entity_kind, entity_id, target, day=day, reason=reason, source_kind="engine", review_cadence_days=180 if target=="STRUCTURAL" else 90, next_review_day=day+(180 if target=="STRUCTURAL" else 90), metadata={"significance_score":score,"score_parts":parts,"history_retained":True})
            _sync_sim_tier(conn, entity_id, target, day)
        else:
            action, applied, reason = "defer", current, "demotion hysteresis: lower significance must persist across reviews"
    else:
        action, applied, reason = "none", current, "resolution level remains appropriate"

    conn.execute(
        """INSERT INTO resolution_reviews(day,entity_kind,entity_id,prior_level,proposed_level,applied_level,significance_score,trigger_json,reason,action)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (day,entity_kind,entity_id,current,target,applied,score,_j(parts),reason,action),
    )
    return {"entity_kind":entity_kind,"entity_id":entity_id,"prior_level":current,"proposed_level":target,"applied_level":applied,"significance_score":score,"score_parts":parts,"action":action,"reason":reason}



def _latent_significance(conn: sqlite3.Connection, latent: sqlite3.Row, day: int) -> tuple[float,dict[str,float]]:
    parts:dict[str,float]={}
    count=max(1,int(latent['count_estimate']))
    if count==1: parts['individualized_identity']=18.0
    elif count<=5: parts['small_specific_group']=8.0
    archetype=str(latent['archetype'] or '').lower()
    if 'champion' in archetype: parts['recognized_champion_role']=16.0
    if latent['institution_actor_id'] is not None: parts['institutional_context']=8.0
    age=max(0,int(day)-int(latent['created_day']))
    parts['persistence']=min(12.0,age/365.0*3.0)
    try: hist=json.loads(latent['historical_context_json'] or '{}')
    except Exception: hist={}
    streak=float(hist.get('champion_streak') or 0)
    if streak: parts['durable_record']=min(28.0,streak*5.0)
    consequences=float(hist.get('consequence_score') or hist.get('regional_significance') or 0)
    if consequences: parts['recorded_consequence']=min(30.0,max(0.0,consequences))
    return max(0.0,min(100.0,sum(parts.values()))),parts


def _latent_level(score: float) -> str:
    if score>=40.0:return 'TRACKED'
    if score>=18.0:return 'STRUCTURAL'
    return 'LATENT'



_FIRST_NAMES=("Adrian","Bram","Celia","Darin","Elena","Ferran","Galen","Hessa","Ilan","Jora","Kellen","Lysa","Marek","Nessa","Orin","Pella","Rian","Sera","Tomas","Vera")
_SURNAMES=("Alder","Bennet","Cairn","Dale","Evers","Fenn","Grey","Hale","Ives","Kerr","Lorne","Merrin","North","Pike","Quill","Rook","Senn","Tarn","Vale","Wren")

def _generated_person_name(conn: sqlite3.Connection, latent_id: int, day: int) -> str:
    seedrow=conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone(); seed=int(seedrow[0] if seedrow else 1)
    rng=random.Random(seed*1000003+latent_id*9176+day*37)
    for i in range(200):
        name=f"{rng.choice(_FIRST_NAMES)} {rng.choice(_SURNAMES)}" if i<80 else f"{rng.choice(_FIRST_NAMES)} {rng.choice(_SURNAMES)} {i}"
        if not conn.execute("SELECT 1 FROM actors WHERE name=?",(name,)).fetchone(): return name
    raise RuntimeError('could not produce unique crystallized latent-person name')

def _materialize_latent_person(conn: sqlite3.Connection, latent: sqlite3.Row, day: int, score: float, parts: dict[str,float]) -> int | None:
    if str(latent['latent_kind'])!='person' or int(latent['count_estimate'])!=1: return None
    if latent['crystallized_entity_kind']=='actor' and latent['crystallized_entity_id'] is not None:
        return int(latent['crystallized_entity_id'])
    try: constraints=json.loads(latent['constraints_json'] or '{}')
    except Exception: constraints={}
    try: hist=json.loads(latent['historical_context_json'] or '{}')
    except Exception: hist={}
    name=str(constraints.get('name') or hist.get('proposed_name') or '').strip() or _generated_person_name(conn,int(latent['id']),day)
    birth_raw=constraints.get('birth_day') if constraints.get('birth_day') is not None else hist.get('birth_day')
    age_raw=constraints.get('age') if constraints.get('age') is not None else hist.get('age')
    if birth_raw is not None:
        # Exact chronology already exists upstream (for example POPBACK-01); preserve it.
        birth=int(birth_raw)
        age=max(0,min(110,int(max(0,day-birth)/365.2425)))
    else:
        if age_raw is None:
            ar=constraints.get('age_range')
            if isinstance(ar,(list,tuple)) and len(ar)>=2: age_raw=(float(ar[0])+float(ar[1]))/2.0
        age=max(0,min(110,int(age_raw if age_raw is not None else 28+(int(latent['id'])%23))))
        birth=day-int(age*365.2425)
    subtype=str(latent['archetype'] or 'ordinary person').replace('_',' ')
    lid=int(latent['location_id']) if latent['location_id'] is not None else None
    cur=conn.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'character',?,?,?,'active',?,0)",
                     (name,subtype,lid,lid,f"Crystallized from latent person #{int(latent['id'])}; no retroactive biography invented."))
    aid=int(cur.lastrowid); stage='elder' if age>=60 else ('child' if age<13 else ('youth' if age<20 else 'adult'))
    family_eligible=1 if age>=16 else 0
    upstream_sex=constraints.get('demographic_sex') or hist.get('demographic_sex')
    conn.execute("""INSERT INTO actor_life_profiles(actor_id,birth_day,demographic_sex,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json)
                    VALUES (?,?,?,?,?, 'living',?,?)""",(aid,birth,upstream_sex if upstream_sex in ('female','male') else None,stage,family_eligible,day,_j({'latent_entity_id':int(latent['id']),'source_age':age,'source_birth_day':birth,'generated_from_existing_population':True})))
    # FAMILY-02: no unresolved sex for a new named person (given name, else seeded roll).
    from .demographic_sex import resolve_missing_demographic_sex
    resolve_missing_demographic_sex(conn,actor_id=aid)
    # Ordinary crystallization starts Closed-Core unless the latent evidence explicitly says otherwise.
    open_core=bool(constraints.get('open_core') or hist.get('open_core'))
    stage_name=(constraints.get('stage') or hist.get('stage')) if open_core else None
    conn.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
                    training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,
                    next_realization_check_day,last_review_day,next_review_day,status,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (aid,'Open-Core' if open_core else 'Closed-Core',stage_name,1 if open_core and stage_name else 0,
                  30 if open_core else 0,20 if open_core else 0,45 if open_core else 0,45,0,0,1.0,1.0,day+365,day,day+30,
                  'active' if open_core and stage_name else 'paused',_j({'latent_entity_id':int(latent['id']),'not_canon':True})))
    # A Stage held before crystallization sits somewhere inside that Stage, like any canon person's.
    from .cultivation import calibrate_revealed_profile
    calibrate_revealed_profile(conn,aid)
    # The shared stable draw (DRIVES-01), not a near-constant formula: everyone revealed is a distinct person.
    from .drives import DRIVES, seeded_drives
    dv = seeded_drives(conn, aid)
    conn.execute(f"INSERT INTO actor_drives(actor_id,{','.join(DRIVES)},basis) VALUES (?,?,?,?,?,?,?,'seeded_draw')",
                 (aid, *(dv[d] for d in DRIVES)))
    from .health import ensure_health_profile
    ensure_health_profile(conn,aid,metadata={'latent_entity_id':int(latent['id']),'generated_from_existing_population':True})
    from .presence import ensure_presence_profile
    ensure_presence_profile(conn,aid,base_location_id=lid,confidence=.65,source_kind='latent_crystallization',effective_from_day=day,notes='Crystallized from latent population')
    if 'merchant' in subtype.lower() or 'trade' in subtype.lower():
        from .education import _set_competence_floor
        _set_competence_floor(conn,aid,'commerce',55,source_kind='crystallization')
    if latent['institution_actor_id'] is not None:
        conn.execute("INSERT OR IGNORE INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,status,joined_day,provenance_json,metadata_json) VALUES (?,?,'ordinary_member','active',?,?,?)",
                     (int(latent['institution_actor_id']),aid,day,_j(['latent crystallization']),_j({'latent_entity_id':int(latent['id'])})))
    enterprise_id=hist.get('enterprise_id') or constraints.get('enterprise_id')
    if enterprise_id and conn.execute("SELECT 1 FROM civilian_enterprises WHERE id=?",(int(enterprise_id),)).fetchone():
        conn.execute("UPDATE civilian_enterprises SET owner_actor_id=COALESCE(owner_actor_id,?) WHERE id=?",(aid,int(enterprise_id)))
        from .merchant import add_enterprise_staff
        add_enterprise_staff(conn,int(enterprise_id),aid,role='owner-factor',authority=90,specialty='trade',metadata={'latent_entity_id':int(latent['id'])})
    upsert_continuity_core(conn,'actor',aid,{'latent_entity_id':int(latent['id']),'latent_constraints':constraints,'latent_history':hist,'significance_at_crystallization':score,'score_parts':parts},source_kind='engine',crystallized_day=day,notes='Identity materialized from pre-existing latent population; prior context preserved, missing biography not invented.')
    set_resolution(conn,'actor',aid,'TRACKED',day=day,reason='latent person crossed persistent causal significance threshold',source_kind='engine',locked_min_level='STRUCTURAL',review_cadence_days=90,next_review_day=day+90,metadata={'latent_entity_id':int(latent['id'])})
    _sync_sim_tier(conn,aid,'TRACKED',day)
    conn.execute("UPDATE latent_entities SET status='crystallized',crystallized_entity_kind='actor',crystallized_entity_id=?,updated_day=? WHERE id=?",(aid,day,int(latent['id'])))
    # POPBACK-01 continuity: if this latent person originated as a sampled ordinary identity,
    # carry the same identity link through to the named actor instead of spawning a replacement.
    if _table(conn,'background_population_identity_links'):
        conn.execute("""UPDATE background_population_identity_links
                        SET status='crystallized',actor_id=?,last_update_day=?
                        WHERE latent_entity_id=?""",(aid,day,int(latent['id'])))
    return aid

def _review_latent(conn: sqlite3.Connection, latent_id: int, day: int) -> dict[str,Any]:
    latent=conn.execute("SELECT * FROM latent_entities WHERE id=?",(latent_id,)).fetchone()
    if not latent: raise ValueError('Unknown latent entity')
    prof=conn.execute("SELECT * FROM latent_resolution_profiles WHERE latent_entity_id=?",(latent_id,)).fetchone()
    current=str(prof['resolution_level']) if prof else 'LATENT'
    score,parts=_latent_significance(conn,latent,day); target=_latent_level(score)
    applied=target; action='none' if target==current else ('promote' if {'LATENT':0,'STRUCTURAL':1,'TRACKED':2}[target]>{'LATENT':0,'STRUCTURAL':1,'TRACKED':2}[current] else 'demote')
    cadence={'TRACKED':90,'STRUCTURAL':180,'LATENT':365}[target]
    conn.execute("""INSERT INTO latent_resolution_profiles(latent_entity_id,resolution_level,significance_score,previous_level,last_review_day,next_review_day,last_changed_day,metadata_json)
                  VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(latent_entity_id) DO UPDATE SET previous_level=latent_resolution_profiles.resolution_level,
                  resolution_level=excluded.resolution_level,significance_score=excluded.significance_score,last_review_day=excluded.last_review_day,
                  next_review_day=excluded.next_review_day,last_changed_day=CASE WHEN latent_resolution_profiles.resolution_level<>excluded.resolution_level THEN excluded.last_changed_day ELSE latent_resolution_profiles.last_changed_day END,
                  metadata_json=excluded.metadata_json""",
                 (latent_id,target,score,current,day,day+cadence,day,_j({'score_parts':parts})))
    materialized_actor_id=None
    if target=='TRACKED' and str(latent['latent_kind'])=='person' and int(latent['count_estimate'])==1:
        materialized_actor_id=_materialize_latent_person(conn,latent,day,score,parts)
    ek='latent_person' if str(latent['latent_kind'])=='person' else 'latent_institution'
    conn.execute("""INSERT INTO resolution_reviews(day,entity_kind,entity_id,prior_level,proposed_level,applied_level,significance_score,trigger_json,reason,action)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (day,ek,latent_id,current,target,applied,score,_j(parts),'autonomous latent consequence review',action if action in {'none','promote','demote'} else 'none'))
    return {'latent_entity_id':latent_id,'prior_level':current,'applied_level':target,'significance_score':score,'action':action,'materialized_actor_id':materialized_actor_id}


def next_resolution_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    """Pure due-date query for resolution work.

    Scheduler lookahead must never mutate world state and must never depend on the caller's
    requested horizon.  The previous implementation inserted missing latent profiles here
    with ``MIN(created_day + 180, end_day)``; consequently advance(30) could crystallize a
    person months earlier than advance(365).  Missing profiles now advertise their natural
    first review date directly and are materialized only when the resolution owner runs.
    """
    vals=[]
    r=conn.execute("""SELECT MIN(next_review_day) FROM entity_resolution
                      WHERE entity_kind IN ('actor','institution') AND next_review_day>? AND next_review_day<=?""",(after_day,end_day)).fetchone()
    if r and r[0] is not None: vals.append(int(r[0]))
    if _table(conn,'latent_entities'):
        lr=conn.execute("""SELECT MIN(lr.next_review_day)
                           FROM latent_resolution_profiles lr
                           JOIN latent_entities le ON le.id=lr.latent_entity_id
                           WHERE le.status IN ('latent','partially_crystallized')
                             AND lr.next_review_day>? AND lr.next_review_day<=?""",(after_day,end_day)).fetchone()
        if lr and lr[0] is not None: vals.append(int(lr[0]))
        missing=conn.execute("""SELECT MIN(le.created_day + 180)
                                FROM latent_entities le
                                LEFT JOIN latent_resolution_profiles lr ON lr.latent_entity_id=le.id
                                WHERE le.status IN ('latent','partially_crystallized')
                                  AND lr.latent_entity_id IS NULL
                                  AND le.created_day + 180>? AND le.created_day + 180<=?""",(after_day,end_day)).fetchone()
        if missing and missing[0] is not None: vals.append(int(missing[0]))
    if _table(conn,'emergent_institution_candidates'):
        org=conn.execute("""SELECT MIN(updated_day + 1) FROM emergent_institution_candidates
                            WHERE status='eligible' AND updated_day + 1>? AND updated_day + 1<=?""",(after_day,end_day)).fetchone()
        if org and org[0] is not None: vals.append(int(org[0]))
    return min(vals) if vals else None


def process_due_resolution(conn: sqlite3.Connection, day: int) -> dict[str,int]:
    reviewed=promoted=demoted=latent_reviewed=latent_promoted=latent_materialized=institution_crystallized=0
    rows=conn.execute("""SELECT er.entity_kind,er.entity_id,er.resolution_level,er.review_cadence_days
                         FROM entity_resolution er JOIN actors a ON a.id=er.entity_id
                         WHERE er.entity_kind IN ('actor','institution') AND er.next_review_day<=?
                           AND ((er.entity_kind='actor' AND a.actor_type='character') OR (er.entity_kind='institution' AND a.actor_type='institution'))
                         ORDER BY er.next_review_day,er.entity_kind,er.entity_id""",(day,)).fetchall()
    for row in rows:
        out=review_entity(conn,str(row['entity_kind']),int(row['entity_id']),day=day)
        reviewed+=1
        if out['action']=='promote': promoted+=1
        if out['action']=='demote': demoted+=1
        # None/defer reviews must still advance their own clock; a due row must never become permanently stale.
        state=conn.execute("SELECT resolution_level,review_cadence_days,next_review_day FROM entity_resolution WHERE entity_kind=? AND entity_id=?",(row['entity_kind'],row['entity_id'])).fetchone()
        if state and int(state['next_review_day'] or 0)<=day:
            cadence=int(state['review_cadence_days'] or ({'ACTIVE':30,'TRACKED':90}.get(str(state['resolution_level']),180)))
            conn.execute("UPDATE entity_resolution SET next_review_day=? WHERE entity_kind=? AND entity_id=?",(day+cadence,row['entity_kind'],row['entity_id']))
    # Seed/review latent resolution identities.
    conn.execute("""INSERT OR IGNORE INTO latent_resolution_profiles(latent_entity_id,resolution_level,significance_score,last_review_day,next_review_day,last_changed_day,metadata_json)
                  SELECT id,'LATENT',0,created_day,created_day+180,created_day,'{}' FROM latent_entities
                  WHERE status IN ('latent','partially_crystallized')""")
    for row in conn.execute("SELECT lr.latent_entity_id,lr.resolution_level FROM latent_resolution_profiles lr JOIN latent_entities le ON le.id=lr.latent_entity_id WHERE le.status IN ('latent','partially_crystallized') AND lr.next_review_day<=? ORDER BY lr.next_review_day,lr.latent_entity_id",(day,)).fetchall():
        out=_review_latent(conn,int(row['latent_entity_id']),day);latent_reviewed+=1
        if out['action']=='promote':latent_promoted+=1
        if out.get('materialized_actor_id'): latent_materialized+=1
    # Eligible organizations cross into persistent structural identity whether or not their
    # ordinary/social name is yet known.  Naming is a social fact, not an ontology gate.
    if _table(conn,'emergent_institution_candidates'):
        candidates=conn.execute("SELECT id FROM emergent_institution_candidates WHERE status='eligible' ORDER BY id").fetchall()
        for cand in candidates:
            crystallize_institution_candidate(conn,int(cand[0]),day=day); institution_crystallized+=1
    return {'entities_reviewed':reviewed,'promotions':promoted,'demotions':demoted,'latent_reviewed':latent_reviewed,'latent_promotions':latent_promoted,'latent_materialized':latent_materialized,'institution_crystallized':institution_crystallized}

def create_institution_candidate(conn: sqlite3.Connection, candidate_kind: str, *, location_id: int | None = None, enterprise_id: int | None = None, founder_actor_id: int | None = None, proposed_name: str | None = None, significance_score: float = 0.0, resources: dict[str,Any] | None = None, participants: list[int] | None = None, evidence: list[dict[str,Any]] | None = None, day: int | None = None) -> int:
    """Records causal formation. This does not itself invent/crystallize an organization."""
    day = _day(conn) if day is None else int(day)
    if not evidence:
        raise ValueError("Emergent institution candidates require causal evidence")
    cur = conn.execute(
        """INSERT INTO emergent_institution_candidates(candidate_kind,location_id,enterprise_id,founder_actor_id,proposed_name,significance_score,resources_json,participants_json,evidence_json,status,created_day,updated_day)
           VALUES (?,?,?,?,?,?,?,?,?,'forming',?,?)""",
        (candidate_kind,location_id,enterprise_id,founder_actor_id,proposed_name,float(significance_score),_j(resources),_j(participants or []),_j(evidence),day,day),
    )
    return int(cur.lastrowid)


def _institution_candidate_eligible(candidate_kind: str, score: float, evidence: list[dict[str,Any]], resources: dict[str,Any]) -> bool:
    """Domain-aware persistence threshold. A successful enterprise is not automatically an institution.

    In particular, the old commercial slice used ``merchant_house`` as a business archetype for
    ordinary wholesalers.  ORGLIFE must not interpret that implementation label as evidence that
    a durable merchant institution exists.  A merchant firm needs organizational depth beyond one
    operator: staff/branches, or a sustained multi-market contracting footprint.
    """
    if not evidence:
        return False
    kind = str(candidate_kind or "").strip().lower().replace('_',' ')
    if kind in {"merchant firm", "merchant house"}:
        age_days = int(resources.get("business_age_days") or 0)
        active_staff = int(resources.get("active_staff") or 0)
        branch_count = int(resources.get("branch_count") or 0)
        completed = int(resources.get("completed_trade_contracts") or 0)
        markets = int(resources.get("distinct_trade_locations") or 0)
        organizational_depth = active_staff >= 2 or branch_count >= 2 or (completed >= 12 and markets >= 3)
        return score >= 45.0 and age_days >= 3 * 365 and organizational_depth
    return score >= 32.0


def update_institution_candidate(conn: sqlite3.Connection, candidate_id: int, *, significance_score: float | None = None, resources: dict[str,Any] | None = None, participants: list[int] | None = None, evidence_append: dict[str,Any] | None = None, day: int | None = None) -> dict[str,Any]:
    day = _day(conn) if day is None else int(day)
    row = conn.execute("SELECT * FROM emergent_institution_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not row: raise ValueError("Unknown emergent institution candidate")
    evidence = json.loads(row["evidence_json"] or "[]")
    if evidence_append: evidence.append(evidence_append)
    score = float(row["significance_score"] if significance_score is None else significance_score)
    next_resources = resources if resources is not None else json.loads(row["resources_json"] or "{}")
    # Eligibility is recomputed rather than made sticky. If later evidence reveals that an old
    # generic candidate never possessed institutional depth, it remains a forming enterprise
    # instead of being grandfathered into a durable organization. Crystallized rows are immutable.
    prior_status = str(row["status"])
    if prior_status == "crystallized":
        status = prior_status
    else:
        status = "eligible" if _institution_candidate_eligible(str(row["candidate_kind"]), score, evidence, next_resources) else "forming"
    conn.execute(
        "UPDATE emergent_institution_candidates SET significance_score=?,resources_json=?,participants_json=?,evidence_json=?,status=?,updated_day=? WHERE id=?",
        (score,_j(next_resources),_j(participants if participants is not None else json.loads(row["participants_json"] or "[]")),_j(evidence),status,day,candidate_id),
    )
    return dict(conn.execute("SELECT * FROM emergent_institution_candidates WHERE id=?", (candidate_id,)).fetchone())


def crystallize_institution_candidate(conn: sqlite3.Connection, candidate_id: int, *, name: str | None = None, day: int | None = None) -> int:
    """Turns a causally formed organization into a persistent institution. History comes from evidence; none is retro-invented."""
    day = _day(conn) if day is None else int(day)
    row = conn.execute("SELECT * FROM emergent_institution_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not row: raise ValueError("Unknown emergent institution candidate")
    if row["status"] != "eligible": raise ValueError("Candidate is not yet eligible for crystallization")
    grounded_name = name or row["proposed_name"]
    unresolved_name = not bool(grounded_name and str(grounded_name).strip())
    final_name = str(grounded_name).strip() if not unresolved_name else f"[STRUCTURAL] {row['candidate_kind']} candidate #{candidate_id}"
    if conn.execute("SELECT 1 FROM actors WHERE name=?", (final_name,)).fetchone():
        final_name = f"{final_name} / day {day}"
    participants = json.loads(row["participants_json"] or "[]")
    evidence = json.loads(row["evidence_json"] or "[]")
    resources = json.loads(row["resources_json"] or "{}")
    preexisting = bool(resources.get("preexisting_organization"))
    note = "Crystallized from pre-existing organization evidence" if preexisting else "Crystallized from causal formation evidence"
    if unresolved_name:
        note += "; structural identity only, ordinary/social name unresolved"
    cur = conn.execute(
        "INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) VALUES (?,'institution',?,?,?,?,?,0)",
        (final_name,row["candidate_kind"],row["location_id"],row["location_id"],"active",note),
    )
    aid = int(cur.lastrowid)
    set_institution_profile(conn, aid, str(row["candidate_kind"]), primary_location_id=row["location_id"], capacity={"participant_count":len(participants)}, trajectory="rising", notes="Emergent institution; no retroactive perfect history invented.")
    upsert_continuity_core(conn,"institution",aid,{"formation_candidate_id":candidate_id,"participants":participants,"evidence":evidence,"resources":resources,"preexisting_before_crystallization":preexisting,"unresolved_name":unresolved_name},source_kind="engine",crystallized_day=day,notes="Pre-existing history preserved through crystallization." if preexisting else "Formation history preserved from causal candidate.")
    for pid in participants:
        if conn.execute("SELECT 1 FROM actors WHERE id=? AND actor_type='character'", (int(pid),)).fetchone():
            membership_kind = 'existing_member' if preexisting else 'founding_member'
            conn.execute("INSERT OR IGNORE INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,status,joined_day,provenance_json,metadata_json) VALUES (?,?,?,'active',?,?,?)", (aid,int(pid),membership_kind,day,_j(["pre-existing organization crystallization" if preexisting else "emergent institution candidate"]),_j({"candidate_id":candidate_id,"preexisting":preexisting})))
    set_resolution(conn,"institution",aid,"TRACKED",day=day,reason="causally formed organization crossed persistence threshold",source_kind="engine",locked_min_level="STRUCTURAL",review_cadence_days=90,next_review_day=day+90,metadata={"candidate_id":candidate_id})
    _sync_sim_tier(conn,aid,"TRACKED",day)
    if "criminal" in str(row["candidate_kind"]).lower() and _table(conn,"underworld_organizations"):
        org_type=str(resources.get("organization_type") or "gang")
        leader=row["founder_actor_id"] or (participants[0] if participants else None)
        conn.execute("""INSERT OR IGNORE INTO underworld_organizations(organization_key,organization_type,name,founder_actor_id,institution_actor_id,
                          primary_location_id,member_count_estimate,command_depth,territorial_presence,racket_breadth,front_depth,corrupt_access,
                          reputation_deterrence,violence_capacity,cohesion,membership_stability,succession_depth,status,created_day,updated_day,metadata_json,current_leader_actor_id,treasury)
                          VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,'active',?,?,?, ?,?)""",
                     (f"emergent:candidate:{candidate_id}",org_type,final_name,row["founder_actor_id"],aid,row["location_id"],
                      max(1.0,float(resources.get("member_count_estimate") or len(participants) or 1)),
                      float(resources.get("territorial_presence") or 10),float(resources.get("racket_breadth") or 0),
                      float(resources.get("front_depth") or 0),float(resources.get("corrupt_access") or 0),
                      float(resources.get("reputation_deterrence") or 10),float(resources.get("violence_capacity") or 10),
                      float(resources.get("cohesion") or 50),float(resources.get("membership_stability") or 50),
                      float(resources.get("succession_depth") or 0),day,day,_j({"candidate_id":candidate_id,"crystallized_by":"resolution_controller"}),
                      int(leader) if leader is not None else None,float(resources.get("treasury") or 0)))
    conn.execute("UPDATE emergent_institution_candidates SET status='crystallized',crystallized_institution_actor_id=?,updated_day=? WHERE id=?", (aid,day,candidate_id))
    try:
        from .organization_lifecycle import record_formation
        record_formation(conn, aid, candidate_id=candidate_id, unresolved_name=unresolved_name,
                         detail={"candidate_kind": str(row["candidate_kind"]), "preexisting": preexisting})
    except sqlite3.OperationalError:
        # Compatibility for deliberately pre-ORGLIFE schemas opened in isolation.
        pass
    conn.execute("INSERT INTO resolution_reviews(day,entity_kind,entity_id,prior_level,proposed_level,applied_level,significance_score,trigger_json,reason,action) VALUES (?,?,?,?,?,?,?,?,?,?)", (day,"institution",aid,"LATENT","TRACKED","TRACKED",float(row["significance_score"]),_j({"candidate_id":candidate_id}),"causal organization formation reached persistent relevance","crystallize_institution"))
    return aid
