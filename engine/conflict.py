from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any

from .decision_runtime import DecisionCandidate


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _stable_fraction(conn: sqlite3.Connection, *parts: object) -> float:
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    payload="|".join(map(str,(seed,*parts))).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8],"big")/2**64


def _polity(conn: sqlite3.Connection, name: str):
    return conn.execute("""SELECT p.*,a.name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id
                           WHERE a.name=? AND p.status!='dissolved'""",(name,)).fetchone()


def _location(conn: sqlite3.Connection, name: str | None) -> int | None:
    if not name: return None
    r=conn.execute("SELECT id FROM locations WHERE name=?",(name,)).fetchone()
    return int(r[0]) if r else None


def _relation_row(conn: sqlite3.Connection, a: int, b: int):
    lo,hi=sorted((a,b))
    return conn.execute("SELECT * FROM political_relations WHERE polity_a_id=? AND polity_b_id=?",(lo,hi)).fetchone()


def _adjust_relation(conn: sqlite3.Connection, a: int, b: int, *, tension_delta: float=0, stance_delta: float=0,
                     trust_delta: float=0, kind: str | None=None) -> None:
    lo,hi=sorted((a,b)); row=_relation_row(conn,a,b); day=_day(conn)
    if not row:
        conn.execute("INSERT INTO political_relations(polity_a_id,polity_b_id,relation_kind,stance,trust,tension,updated_day) VALUES (?,?,'neutral',0,0,0,?)",(lo,hi,day))
        row=_relation_row(conn,a,b)
    conn.execute("""UPDATE political_relations SET relation_kind=COALESCE(?,relation_kind),
                    stance=MAX(-100,MIN(100,stance+?)),trust=MAX(-100,MIN(100,trust+?)),tension=MAX(0,MIN(100,tension+?)),updated_day=?
                    WHERE polity_a_id=? AND polity_b_id=?""",(kind,stance_delta,trust_delta,tension_delta,day,lo,hi))


def activate_conflict_channels(conn: sqlite3.Connection) -> dict[str,int]:
    # The canon frontiers with live pressure; friendly (Greywood–Windmere) and purely commercial frontiers carry none.
    specs=[
        ("greywood_dunmoor_westbrook_stoneford","Greywood","Dunmoor","territorial_frontier","Westbrook","Stoneford",56,.22,42,60,22),
        ("dunmoor_underheaven_great_power_caution","Dunmoor","Underheaven Empire","security_frontier","Stoneford","Aldergate",34,.16,72,66,10),
        ("windmere_sunreach_maritime","Windmere","Sunreach Confederacy","maritime_competition","Saltmere","Southbay",46,.25,50,59,30),
        ("sunreach_underheaven_trade_wariness","Sunreach Confederacy","Underheaven Empire","trade_maritime","Southbay","Toll’s Reach",40,.18,57,62,25),
        # Canon: "Underheaven–Thornward: Western Thornward valleys; Eastwatch–Westgate. Armed peace. The principal
        # eastern invasion corridor."  (Its Thornward end was unset, so no campaign could ever resolve.)
        ("underheaven_thornward_armed_corridor","Underheaven Empire","Thornward","armed_corridor","Eastwatch","Westgate",62,.28,38,58,26),
        # Canon: "Thornward–Stormhollow: Broken southern ridges. Tense local peace. Raids, forts, cattle, disputed
        # valleys"; Stormhollow's "generations of border war with Thornward".
        ("thornward_stormhollow_southern_ridges","Thornward","Stormhollow","security_frontier","Dunbriar","Highcairn",54,.30,40,57,24),
    ]
    created=0; day=_day(conn)
    for key,an,bn,kind,la,lb,base,vol,restraint,threshold,opening in specs:
        a=_polity(conn,an); b=_polity(conn,bn)
        if not a or not b: continue
        existed=conn.execute("SELECT 1 FROM conflict_channels WHERE channel_key=?",(key,)).fetchone()
        conn.execute("""INSERT INTO conflict_channels(channel_key,polity_a_id,polity_b_id,issue_kind,location_a_id,location_b_id,base_pressure,volatility,restraint,
                      incident_threshold,accumulated_pressure,review_cadence_days,last_review_day,next_review_day,status,metadata_json)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?)
                      ON CONFLICT(channel_key) DO UPDATE SET polity_a_id=excluded.polity_a_id,polity_b_id=excluded.polity_b_id,issue_kind=excluded.issue_kind,
                      location_a_id=excluded.location_a_id,location_b_id=excluded.location_b_id,base_pressure=excluded.base_pressure,volatility=excluded.volatility,
                      restraint=excluded.restraint,incident_threshold=excluded.incident_threshold""",
                     (key,int(a["id"]),int(b["id"]),kind,_location(conn,la),_location(conn,lb),base,vol,restraint,threshold,opening,30,day,day+30,
                      json.dumps({"opening_geometry":True,"causal_not_quota":True},sort_keys=True)))
        if not existed: created+=1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('conflict_channel_activation_version','1')")
    return {"conflict_channels_configured":created}


def next_conflict_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    r=conn.execute("SELECT MIN(next_review_day) FROM conflict_channels WHERE status='active' AND next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _incident_kind(issue_kind: str, armed: bool) -> str:
    if issue_kind in {"territorial_frontier","armed_corridor","security_frontier"}:
        return "border_raid" if armed else "border_incident"
    if issue_kind=="maritime_competition": return "ship_seizure" if armed else "maritime_restriction"
    if issue_kind=="trade_maritime": return "trade_restriction"
    return "political_incident"


# Channels name the frontier's character; polity issue states name the underlying issue.  Without this
# mapping the lookup never matched, so issue pressure silently read 0 in every incident (lower severity,
# slower pressure, and a coin-flip instead of grievance deciding who struck first).
_CHANNEL_ISSUE_KIND = {"territorial_frontier": "territorial", "security_frontier": "security",
                       "maritime_competition": "maritime", "trade_maritime": "trade", "armed_corridor": "frontier"}


def _issue_pressure(conn: sqlite3.Connection, a: int, b: int, kind: str) -> float:
    kinds = sorted({kind, _CHANNEL_ISSUE_KIND.get(kind, kind)})
    rows=conn.execute(f"SELECT pressure FROM polity_issue_states WHERE polity_id=? AND other_polity_id=? AND issue_kind IN ({','.join('?'*len(kinds))})",
                      (a,b,*kinds)).fetchall()
    return max([float(r[0]) for r in rows] or [0.0])


def process_due_conflict(conn: sqlite3.Connection, day: int, event_logger=None) -> dict[str,int]:
    created=0; reviewed=0
    for ch in conn.execute("SELECT * FROM conflict_channels WHERE status='active' AND next_review_day<=? ORDER BY next_review_day,id",(day,)).fetchall():
        reviewed+=1; cid=int(ch["id"]); a=int(ch["polity_a_id"]); b=int(ch["polity_b_id"])
        rel=_relation_row(conn,a,b); tension=float(rel["tension"] if rel else 0)
        issue=max(_issue_pressure(conn,a,b,str(ch["issue_kind"])),_issue_pressure(conn,b,a,str(ch["issue_kind"])))
        cadence=max(1,day-int(ch["last_review_day"]))
        deterministic_noise=(_stable_fraction(conn,"conflict",cid,day)-.5)*2*float(ch["volatility"])*8
        monthly=max(0.0,float(ch["base_pressure"])*.07 + tension*.02 + issue*.025 - float(ch["restraint"])*.03 + deterministic_noise*.45)
        accum=float(ch["accumulated_pressure"])+monthly*(cadence/30.0)
        threshold=float(ch["incident_threshold"])
        if accum>=threshold:
            # Direction follows current issue pressure, with deterministic tie-breaking; not a generic aggression roll.
            pa=_issue_pressure(conn,a,b,str(ch["issue_kind"])); pb=_issue_pressure(conn,b,a,str(ch["issue_kind"]))
            if abs(pa-pb)>3: initiator,target=(a,b) if pa>pb else (b,a)
            else: initiator,target=(a,b) if _stable_fraction(conn,"direction",cid,day)<.5 else (b,a)
            severity=max(20.0,min(92.0,35 + (accum-threshold)*.9 + tension*.28 + issue*.18))
            armed=str(ch["issue_kind"]) in {"territorial_frontier","armed_corridor","security_frontier"} and severity>=48
            location=ch["location_a_id"] if initiator==a else ch["location_b_id"]
            cur=conn.execute("""INSERT INTO conflict_incidents(channel_id,day,initiator_polity_id,target_polity_id,incident_kind,severity,location_id,status,response_state,metadata_json)
                                VALUES (?,?,?,?,?,?,?,'open','none',?)""",
                             (cid,day,initiator,target,_incident_kind(str(ch["issue_kind"]),armed),severity,location,
                              json.dumps({"issue_kind":str(ch["issue_kind"]),"armed":armed,"pressure_at_creation":accum},sort_keys=True)))
            incident_id=int(cur.lastrowid); created+=1
            _adjust_relation(conn,a,b,tension_delta=max(3,severity*.08),stance_delta=-max(1,severity*.025),trust_delta=-max(1,severity*.03))
            accum=max(0.0,accum-threshold)
            if event_logger:
                event_logger(day=day,event_type="political_conflict_incident",title=f"Political conflict incident #{incident_id}",
                             summary=f"{ch['channel_key']} produced a { _incident_kind(str(ch['issue_kind']),armed) } at severity {severity:.1f}.",
                             severity=max(2,min(5,int(math.ceil(severity/22.0)))),
                             location_id=int(location) if location is not None else None,visibility="limited",rumorability=.75,reliability=.75)
        conn.execute("UPDATE conflict_channels SET accumulated_pressure=?,last_review_day=?,next_review_day=? WHERE id=?",(accum,day,day+int(ch["review_cadence_days"]),cid))
    return {"reviewed":reviewed,"created":created}


def _government_polity(conn: sqlite3.Connection, actor_id: int):
    return conn.execute("""SELECT p.*,g.authority_kind FROM polity_government_actors g JOIN political_polities p ON p.id=g.polity_id
                           WHERE g.decision_actor_id=? AND p.status!='dissolved'""",(actor_id,)).fetchone()


def _campaign_endpoints(conn: sqlite3.Connection, incident: sqlite3.Row, responding_polity_id: int) -> tuple[int,int] | None:
    ch=conn.execute("SELECT * FROM conflict_channels WHERE id=?",(incident["channel_id"],)).fetchone() if incident["channel_id"] is not None else None
    if not ch: return None
    if responding_polity_id==int(ch["polity_a_id"]): origin,target=ch["location_a_id"],ch["location_b_id"]
    elif responding_polity_id==int(ch["polity_b_id"]): origin,target=ch["location_b_id"],ch["location_a_id"]
    else: return None
    if origin is None or target is None or int(origin)==int(target): return None
    return int(origin),int(target)


def _campaign_feasible(conn: sqlite3.Connection, incident: sqlite3.Row, responding_polity_id: int, day: int) -> tuple[bool,dict[str,Any]]:
    ends=_campaign_endpoints(conn,incident,responding_polity_id)
    if not ends: return False,{"reason":"unresolved_campaign_endpoints"}
    origin,target=ends
    from .ecology import find_route_path
    path=find_route_path(conn,origin,target,day=day)
    if not path: return False,{"reason":"no_traversable_route","origin_location_id":origin,"target_location_id":target}
    logistics=conn.execute("SELECT readiness,transport_capacity,food_fodder_capacity,status FROM military_logistics_profiles WHERE polity_id=?",(responding_polity_id,)).fetchone()
    if not logistics: return False,{"reason":"no_military_logistics_profile"}
    score=(float(logistics["readiness"])+float(logistics["transport_capacity"])+float(logistics["food_fodder_capacity"]))/3
    if score<38: return False,{"reason":"insufficient_logistics","logistics_score":score}
    active=conn.execute("""SELECT 1 FROM war_campaign_operations WHERE attacker_polity_id=? AND defender_polity_id=? AND status NOT IN ('closed','cancelled') LIMIT 1""",
                        (responding_polity_id,int(incident["initiator_polity_id"]))).fetchone()
    if active: return False,{"reason":"campaign_already_active"}
    return True,{"origin_location_id":origin,"target_location_id":target,"route_ids":[int(x) for x in path],"logistics_score":score}


def polity_conflict_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str,Any]) -> list[DecisionCandidate]:
    polity=_government_polity(conn,actor_id)
    if not polity: return []
    pid=int(polity["id"]); drives=envelope.get("drives") or {}; aggression=float(drives.get("aggression",.5)); prag=float(drives.get("pragmatism",.5)); patience=float(drives.get("patience",.5))
    out=[]
    incidents=conn.execute("""SELECT i.* FROM conflict_incidents i WHERE i.target_polity_id=? AND i.status='open' AND i.response_state='none'
                              AND NOT EXISTS (SELECT 1 FROM conflict_responses r WHERE r.incident_id=i.id AND r.responding_polity_id=?)
                              ORDER BY i.severity DESC,i.day,i.id LIMIT 4""",(pid,pid)).fetchall()
    for inc in incidents:
        iid=int(inc["id"]); sev=float(inc["severity"]); initiator=int(inc["initiator_polity_id"])
        issue=conn.execute("SELECT issue_kind FROM conflict_channels WHERE id=?",(inc["channel_id"],)).fetchone() if inc["channel_id"] is not None else None
        posture=conn.execute("SELECT preferred_posture,restraint,pressure FROM polity_issue_states WHERE polity_id=? AND other_polity_id=? ORDER BY pressure DESC LIMIT 1",(pid,initiator)).fetchone()
        restraint=float(posture["restraint"] if posture else 50); pressure=float(posture["pressure"] if posture else 0); pref=str(posture["preferred_posture"] if posture else "cautious")
        out.append(DecisionCandidate(key=f"conflict:settle:{iid}",provider_key="polity_conflict",action_kind="settle_incident",
            utility=4.0+patience*1.5+prag*1.2+restraint/45-sev/80,rationale=f"Seek a bounded settlement of specific incident #{iid}.",execution_kind="political_action",
            payload={"incident_id":iid},information_basis={"incident_id":iid,"own_issue_posture":pref},tags=("politics","specific_incident","deescalation"),risk=.08))
        out.append(DecisionCandidate(key=f"conflict:redress:{iid}",provider_key="polity_conflict",action_kind="demand_incident_redress",
            utility=5.0+prag*.8+pressure/60+sev/70,rationale=f"Issue one formal demand for redress over specific incident #{iid}.",execution_kind="political_action",
            payload={"incident_id":iid},information_basis={"incident_id":iid,"own_issue_posture":pref},tags=("politics","specific_incident","formal_response"),risk=.12))
        if sev>=42:
            out.append(DecisionCandidate(key=f"conflict:retaliate:{iid}",provider_key="polity_conflict",action_kind="limited_retaliation",
                utility=3.8+aggression*2.2+pressure/45+sev/55-restraint/55,rationale=f"Authorize a limited retaliation tied to incident #{iid}, not an open-ended war.",execution_kind="political_action",
                payload={"incident_id":iid},information_basis={"incident_id":iid,"own_issue_posture":pref},tags=("politics","specific_incident","retaliation"),risk=.48))
        feasible,why=_campaign_feasible(conn,inc,pid,day)
        if sev>=70 and feasible:
            out.append(DecisionCandidate(key=f"conflict:campaign:{iid}",provider_key="polity_conflict",action_kind="launch_limited_campaign",
                utility=3.5+aggression*2.0+pressure/45+sev/45-restraint/50,rationale=f"Launch a geographically feasible limited campaign in response to incident #{iid}.",execution_kind="political_action",
                payload={"incident_id":iid,**why},information_basis={"incident_id":iid,"route_ids":why.get("route_ids",[]),"logistics_score":why.get("logistics_score")},
                tags=("politics","specific_incident","campaign","physical_feasibility"),estimated_cost=6,risk=.78))
    return out


def _record_response(conn: sqlite3.Connection, incident: sqlite3.Row, polity_id: int, actor_id: int, kind: str, operation_id: int | None=None, metadata: dict[str,Any] | None=None) -> int | None:
    try:
        cur=conn.execute("INSERT INTO conflict_responses(incident_id,day,responding_polity_id,actor_id,response_kind,operation_id,metadata_json) VALUES (?,?,?,?,?,?,?)",
                         (int(incident["id"]),_day(conn),polity_id,actor_id,kind,operation_id,json.dumps(metadata or {},sort_keys=True)))
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None


def execute_political_action(conn: sqlite3.Connection, actor_id: int, action_kind: str, payload: dict[str,Any], day: int) -> dict[str,Any]:
    polity=_government_polity(conn,actor_id)
    if not polity: return {"summary":"Political action blocked: actor lacks government decision authority.","blocked":True}
    pid=int(polity["id"]); iid=int(payload.get("incident_id") or 0)
    inc=conn.execute("SELECT * FROM conflict_incidents WHERE id=? AND target_polity_id=?",(iid,pid)).fetchone()
    if not inc or str(inc["status"])!='open' or str(inc["response_state"])!='none':
        return {"summary":f"Political response blocked: incident #{iid} is no longer unanswered.","blocked":True}
    # This is the duplicate-redress fix at the mutation boundary as well as candidate generation.
    if conn.execute("SELECT 1 FROM conflict_responses WHERE incident_id=? AND responding_polity_id=?",(iid,pid)).fetchone():
        return {"summary":f"Political response blocked: incident #{iid} already has a formal response.","blocked":True}
    initiator=int(inc["initiator_polity_id"]); response_state="other"; status="responded"; operation_id=None; meta={}
    if action_kind=="settle_incident":
        response_state="settlement"; status="settled"; _adjust_relation(conn,pid,initiator,tension_delta=-8,stance_delta=2,trust_delta=1)
    elif action_kind=="demand_incident_redress":
        response_state="formal_demand"; _adjust_relation(conn,pid,initiator,tension_delta=1,stance_delta=-1,trust_delta=-1)
    elif action_kind=="limited_retaliation":
        response_state="retaliation"; status="responded"; sev=max(20,min(75,float(inc["severity"])*.68))
        cur=conn.execute("""INSERT INTO conflict_incidents(channel_id,day,initiator_polity_id,target_polity_id,incident_kind,severity,location_id,status,response_state,metadata_json)
                            VALUES (?,?,?,?,?,?,?,'open','none',?)""",
                         (inc["channel_id"],day,pid,initiator,"retaliatory_raid",sev,inc["location_id"],json.dumps({"retaliation_for_incident_id":iid,"armed":True},sort_keys=True)))
        meta["retaliatory_incident_id"]=int(cur.lastrowid); _adjust_relation(conn,pid,initiator,tension_delta=7,stance_delta=-3,trust_delta=-2)
    elif action_kind=="launch_limited_campaign":
        feasible,why=_campaign_feasible(conn,inc,pid,day)
        if not feasible: return {"summary":f"Campaign blocked for incident #{iid}: {why.get('reason')}","blocked":True}
        from .war import create_campaign_operation, add_campaign_force
        origin=int(why["origin_location_id"]); target=int(why["target_location_id"])
        pname=conn.execute("SELECT a.name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.id=?",(pid,)).fetchone()[0]
        oname=conn.execute("SELECT a.name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.id=?",(initiator,)).fetchone()[0]
        operation_id=create_campaign_operation(conn,f"{pname} limited response to incident {iid}",objective_text=f"Limited coercive response to {oname} incident #{iid}.",
                                               origin_location_id=origin,target_location_id=target,attacker_polity_id=pid,defender_polity_id=initiator,
                                               commander_actor_id=actor_id if conn.execute("SELECT actor_type FROM actors WHERE id=?",(actor_id,)).fetchone()[0]=='character' else None,
                                               objective_kind="limited",metadata={"conflict_incident_id":iid,"bounded_objective":True})
        # Limited force is bounded by the state's accepted sustainable field capacity when available.
        actor_name=conn.execute("SELECT a.name FROM political_polities p JOIN actors a ON a.id=p.institution_actor_id WHERE p.id=?",(pid,)).fetchone()[0]
        try:
            from .scale import OWNER_TO_BUCKET
            bucket=OWNER_TO_BUCKET.get(str(actor_name).replace('Sunreach Confederacy','Sunreach Confederacy'))
            ms=conn.execute("SELECT sustainable_field_capacity FROM military_scale_profiles WHERE bucket_key=?",(bucket,)).fetchone() if bucket else None
            field=int(ms[0]) if ms else 6000
        except Exception: field=6000
        personnel=max(300,min(2400,int(field*.08)))
        force_id=add_campaign_force(conn,operation_id,f"{pname} limited expedition",personnel=personnel,polity_id=pid,current_location_id=origin,
                                    metadata={"conflict_incident_id":iid,"limited_mobilization":True})
        response_state="campaign"; status="escalated"; meta.update({"force_id":force_id,**why}); _adjust_relation(conn,pid,initiator,tension_delta=15,stance_delta=-8,trust_delta=-8,kind="war")
    else:
        return {"summary":f"Unknown political action {action_kind}.","blocked":True}
    response_id=_record_response(conn,inc,pid,actor_id,action_kind,operation_id,meta)
    if response_id is None:
        # A race/replay duplicate cannot mutate the incident twice.
        return {"summary":f"Political response blocked: incident #{iid} already has a response.","blocked":True}
    conn.execute("UPDATE conflict_incidents SET status=?,response_state=?,responded_day=?,response_actor_id=? WHERE id=?",(status,response_state,day,actor_id,iid))
    return {"summary":f"{action_kind} recorded as the formal response to incident #{iid}.","response_id":response_id,"operation_id":operation_id,**meta}
