from __future__ import annotations

import json
import sqlite3
from typing import Any

from .decision_runtime import DecisionCandidate
from .underworld_aggression import aggression_candidates, execute_aggression, leader_is_player, retaliate as _retaliate_effect


def _jload(raw: str | None) -> dict[str, Any]:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _leader_org(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT p.*,o.organization_type,o.treasury,o.current_leader_actor_id,o.primary_location_id,o.status organization_status
           FROM underworld_personnel p JOIN underworld_organizations o ON o.id=p.organization_id
           WHERE p.actor_id=? AND p.status='active' AND p.role_kind IN ('boss','underboss','lieutenant')
             AND o.status IN ('active','strained','fragmented')
           ORDER BY p.authority DESC LIMIT 1""", (actor_id,),
    ).fetchone()


def _org_name(conn: sqlite3.Connection, org_id: int) -> str:
    r = conn.execute("SELECT name FROM underworld_organizations WHERE id=?", (org_id,)).fetchone()
    return str(r[0]) if r else f"organization #{org_id}"


def underworld_decision_candidates(conn: sqlite3.Connection, actor_id: int, tier: str, day: int, envelope: dict[str, Any]) -> list[DecisionCandidate]:
    membership = _leader_org(conn, actor_id)
    if not membership:
        return []
    oid = int(membership["organization_id"])
    drives = envelope.get("drives") or {}
    aggression = float(drives.get("aggression", .5)); pragmatism = float(drives.get("pragmatism", .5))
    patience = float(drives.get("patience", .5)); ambition = float(drives.get("ambition", .5)); loyalty = float(drives.get("loyalty", .5))
    treasury = float(membership["treasury"] or 0)
    heat = conn.execute("SELECT * FROM underworld_heat WHERE organization_id=?", (oid,)).fetchone()
    investigative_heat = float(heat["investigative_heat"] or 0) if heat else 0.0
    violence_heat = float(heat["violence_heat"] or 0) if heat else 0.0
    out: list[DecisionCandidate] = []

    # Directly suffered poaching is actor-accessible operational information, not omniscient rival knowledge.
    incidents = conn.execute(
        """SELECT * FROM underworld_incidents WHERE target_organization_id=? AND status='open'
           AND incident_kind IN ('protection_poach','protection_dispute','attack_on_client','attack_on_member','extortion_attempt','territorial_challenge')
           ORDER BY severity DESC,day,id LIMIT 3""", (oid,),
    ).fetchall()
    for inc in incidents:
        meta = _jload(inc["metadata_json"]); source = int(inc["source_organization_id"]) if inc["source_organization_id"] is not None else None
        enterprise_id = int(meta["enterprise_id"]) if meta.get("enterprise_id") is not None else None
        if source is None:
            continue
        base = 7.0 + float(inc["severity"]) / 50.0
        common = dict(incident_id=int(inc["id"]), source_organization_id=source, zone_id=int(inc["zone_id"]) if inc["zone_id"] is not None else None, enterprise_id=enterprise_id)
        out.append(DecisionCandidate(
            key=f"underworld:poach:warn:{inc['id']}", provider_key="underworld", action_kind="warn_protection_poacher",
            utility=base + pragmatism * 1.2 + loyalty * .5, rationale=f"Answer {_org_name(conn, source)}'s specific protection poaching attempt with a warning backed by the existing account.",
            execution_kind="underworld_action", payload={**common, "response": "warn"},
            information_basis={"underworld_incident_id": int(inc["id"]), "access": "target_organization"}, tags=("protection", "grievance", "specific_incident"), risk=.25,
        ))
        if not leader_is_player(conn, oid):
          out.append(DecisionCandidate(
            key=f"underworld:poach:retaliate:{inc['id']}", provider_key="underworld", action_kind="retaliate_protection_poach",
            utility=base - .4 + aggression * 2.2 - investigative_heat / 80.0 - violence_heat / 90.0,
            rationale=f"Retaliate against {_org_name(conn, source)} for the concrete poaching attempt rather than escalating against an abstract rival.",
            execution_kind="underworld_action", payload={**common, "response": "retaliate"},
            information_basis={"underworld_incident_id": int(inc["id"]), "access": "target_organization"}, tags=("protection", "retaliation", "specific_incident"), risk=.70,
        ))
        out.append(DecisionCandidate(
            key=f"underworld:poach:negotiate:{inc['id']}", provider_key="underworld", action_kind="negotiate_protection_poach",
            utility=base - .2 + patience * 1.4 + pragmatism * 1.2 + investigative_heat / 70.0,
            rationale=f"Open a concrete settlement over {_org_name(conn, source)}'s poaching attempt and the named disputed account.",
            execution_kind="underworld_action", payload={**common, "response": "negotiate"},
            information_basis={"underworld_incident_id": int(inc["id"]), "access": "target_organization"}, tags=("protection", "truce_path", "specific_incident"), risk=.15,
        ))

    # Truce targets are existing recorded organization relations; this is not recursive theory-of-mind.
    rels = conn.execute(
        """SELECT * FROM underworld_relations WHERE (organization_a_id=? OR organization_b_id=?)
           AND relation_kind IN ('rival','war','hostile_peace') AND hostility>=45 ORDER BY hostility DESC,organization_a_id,organization_b_id LIMIT 4""", (oid, oid),
    ).fetchall()
    for rel in rels:
        other = int(rel["organization_b_id"]) if int(rel["organization_a_id"]) == oid else int(rel["organization_a_id"])
        util = 4.4 + patience * 1.2 + pragmatism * 1.1 + investigative_heat / 45.0 - aggression * .8
        out.append(DecisionCandidate(
            key=f"underworld:truce:{other}", provider_key="underworld", action_kind="seek_truce", utility=util,
            rationale=f"Seek a truce with {_org_name(conn, other)} based on the existing hostile relationship and current organizational pressure.",
            execution_kind="underworld_action", payload={"target_organization_id": other, "relation_pair": [int(rel["organization_a_id"]), int(rel["organization_b_id"])]},
            information_basis={"underworld_relation_pair": [int(rel["organization_a_id"]), int(rel["organization_b_id"])], "access": "organization_record"}, tags=("diplomacy", "specific_counterpart"), risk=.10,
        ))

    # Discipline and promotion use concrete existing people/crews.
    weak = conn.execute(
        """SELECT c.id,c.name,c.loyalty,c.cohesion,c.leader_actor_id FROM underworld_crews c
           WHERE c.organization_id=? AND c.status='active' AND (c.loyalty<48 OR c.cohesion<45)
           ORDER BY MIN(c.loyalty,c.cohesion),c.id LIMIT 1""", (oid,),
    ).fetchone()
    if weak:
        out.append(DecisionCandidate(
            key=f"underworld:discipline_crew:{weak['id']}", provider_key="underworld", action_kind="discipline_crew",
            utility=5.2 + (50.0-min(float(weak['loyalty']),float(weak['cohesion'])))/18.0 + aggression*.7,
            rationale=f"Discipline the concrete {weak['name']} crew because its recorded cohesion/loyalty is weak.", execution_kind="underworld_action",
            target_actor_id=int(weak["leader_actor_id"]) if weak["leader_actor_id"] is not None else None,
            payload={"crew_id": int(weak["id"])}, information_basis={"crew_id": int(weak["id"]), "access":"own_organization"}, tags=("discipline", "crew"), risk=.20,
        ))
    senior = conn.execute("SELECT 1 FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind IN ('underboss','lieutenant') LIMIT 1", (oid,)).fetchone()
    if not senior:
        cand = conn.execute(
            """SELECT * FROM underworld_personnel WHERE organization_id=? AND status='active' AND role_kind IN ('crew_leader','enforcer','fixer','accountant','member')
               ORDER BY earning_power DESC,authority DESC,actor_id LIMIT 1""", (oid,),
        ).fetchone()
        if cand and float(cand["earning_power"]) >= 28:
            out.append(DecisionCandidate(
                key=f"underworld:promote:{cand['actor_id']}", provider_key="underworld", action_kind="promote_personnel",
                utility=4.6 + ambition*.9 + loyalty*.6 + float(cand["earning_power"])/55.0,
                rationale="Promote a specific proven member into a vacant senior role rather than advancing an abstract hierarchy meter.",
                execution_kind="underworld_action", target_actor_id=int(cand["actor_id"]), payload={"target_actor_id": int(cand["actor_id"]), "new_role":"lieutenant"},
                information_basis={"personnel_actor_id": int(cand["actor_id"]), "access":"own_organization"}, tags=("promotion", "specific_person"), risk=.08,
            ))

    # Delegate a concrete organization-operated racket to a real crew.
    racket = conn.execute(
        """SELECT r.id,r.racket_kind FROM underworld_racket_sites r
           JOIN economic_interests ei ON ei.target_racket_id=r.id AND ei.status='active' AND ei.interest_kind='operator' AND ei.holder_organization_id=?
           WHERE r.organization_id=? AND r.status='active' ORDER BY r.gross_income_per_30 DESC,r.id LIMIT 1""", (oid, oid),
    ).fetchone()
    crew = conn.execute("SELECT id,name FROM underworld_crews WHERE organization_id=? AND status='active' ORDER BY loyalty DESC,cohesion DESC,id LIMIT 1", (oid,)).fetchone()
    if racket and crew:
        out.append(DecisionCandidate(
            key=f"underworld:delegate:{racket['id']}:{crew['id']}", provider_key="underworld", action_kind="delegate_racket",
            utility=4.2 + pragmatism*1.0, rationale=f"Delegate the concrete {racket['racket_kind']} operation to {crew['name']}.",
            execution_kind="underworld_action", payload={"racket_id":int(racket["id"]),"crew_id":int(crew["id"])},
            information_basis={"racket_id":int(racket["id"]),"crew_id":int(crew["id"]),"access":"own_organization"}, tags=("delegation","racket"), risk=.05,
        ))

    # Expand protection only onto a real currently unprotected enterprise in controlled city territory.
    zone = conn.execute("SELECT zone_id FROM underworld_zone_claims WHERE organization_id=? AND claim_kind='controller' AND status='active' ORDER BY strength DESC,zone_id LIMIT 1", (oid,)).fetchone()
    if zone:
        zid = int(zone[0]); city = conn.execute("SELECT city_location_id FROM underworld_zones WHERE id=?", (zid,)).fetchone()
        if city:
            ent = conn.execute(
                """SELECT e.id,e.name FROM civilian_enterprises e WHERE e.location_id=? AND e.status IN ('active','strained')
                   AND NOT EXISTS (SELECT 1 FROM underworld_protection_accounts p WHERE p.enterprise_id=e.id AND p.status='active')
                   ORDER BY e.reputation DESC,e.id LIMIT 1""", (int(city[0]),),
            ).fetchone()
            if ent:
                out.append(DecisionCandidate(
                    key=f"underworld:expand_protection:{ent['id']}:{zid}", provider_key="underworld", action_kind="expand_protection_account",
                    utility=4.8 + ambition*1.3 + pragmatism*.6, rationale=f"Offer/demand protection from the specific unprotected enterprise {ent['name']} inside controlled territory.",
                    execution_kind="underworld_action", payload={"enterprise_id":int(ent["id"]),"zone_id":zid},
                    information_basis={"enterprise_id":int(ent["id"]),"controlled_zone_id":zid,"access":"local_operational_opportunity"}, tags=("protection","expansion","specific_enterprise"), estimated_cost=.5, risk=.22,
                ))

    # Spend organizational treasury on a concrete existing racket rather than an abstract investment stat.
    invest = conn.execute("SELECT id,racket_kind FROM underworld_racket_sites WHERE organization_id=? AND status='active' ORDER BY gross_income_per_30 DESC,id LIMIT 1", (oid,)).fetchone()
    if invest and treasury >= 6:
        out.append(DecisionCandidate(
            key=f"underworld:invest_racket:{invest['id']}", provider_key="underworld", action_kind="invest_in_racket",
            utility=4.0 + ambition*.9 + pragmatism*.8, rationale=f"Invest organizational treasury in the concrete {invest['racket_kind']} operation.",
            execution_kind="underworld_action", payload={"racket_id":int(invest["id"]),"amount":min(5.0,max(2.0,treasury*.12))},
            information_basis={"racket_id":int(invest["id"]),"treasury_known":True,"access":"own_organization"}, tags=("investment","racket"), estimated_cost=min(5.0,max(2.0,treasury*.12)), risk=.12,
        ))

    out.extend(aggression_candidates(conn, actor_id, oid, {"aggression": aggression, "patience": patience, "ambition": ambition, "pragmatism": pragmatism},
                                     day, investigative_heat, violence_heat, treasury))

    # Low-confidence underworld claims can trigger a domain-owned investigation record.
    for belief in envelope.get("beliefs") or []:
        if float(belief.get("confidence") or 0) >= .48 or str(belief.get("stance")) not in {"uncertain","accepts","rejects"}:
            continue
        evidence = belief.get("evidence") or []
        if not evidence:
            continue
        cid = int(belief["claim_id"]); eids = tuple(int(e["id"]) for e in evidence)
        out.append(DecisionCandidate(
            key=f"underworld:investigate_claim:{cid}", provider_key="underworld", action_kind="investigate_underworld_claim",
            utility=4.6 + pragmatism*1.4 + (1-float(belief.get("confidence") or 0)),
            rationale="Commission an investigation into a claim the actor actually possesses but does not yet hold confidently.",
            execution_kind="underworld_action", payload={"claim_id":cid}, information_basis={"claim_id":cid,"accessible_evidence_ids":list(eids)},
            claim_ids=(cid,), evidence_ids=eids, tags=("belief_bounded","investigation"), risk=.08,
        ))
        break
    return out


def execute_underworld_action(conn: sqlite3.Connection, actor_id: int, action_kind: str, payload: dict[str, Any], day: int) -> dict[str, Any]:
    membership = _leader_org(conn, actor_id)
    if not membership:
        return {"summary":"Underworld action blocked: actor lacks active command authority.","blocked":True}
    oid = int(membership["organization_id"])
    from . import underworld_rebuild as uw
    try:
        if action_kind in {"warn_protection_poacher","retaliate_protection_poach","negotiate_protection_poach"}:
            inc_id=int(payload["incident_id"]); inc=conn.execute("SELECT * FROM underworld_incidents WHERE id=? AND target_organization_id=? AND status='open'",(inc_id,oid)).fetchone()
            if not inc: raise ValueError("poaching incident no longer open")
            source=int(inc["source_organization_id"]); enterprise=int(payload["enterprise_id"]) if payload.get("enterprise_id") is not None else None
            if action_kind=="retaliate_protection_poach":
                uw.change_relation(conn,oid,source,kind="rival",hostility_delta=12,respect_delta=2,metadata={"response_to_incident":inc_id})
                uw.add_heat(conn,oid,public=2,investigative=2,violence=5)
                import random as _r
                effect=_retaliate_effect(conn,oid,source,inc_id,_r.Random(inc_id*104729+day))
                op=uw._operation(conn,oid,"retaliate_protection_poach",zone_id=inc["zone_id"],target_organization_id=source,enterprise_id=enterprise,result="completed",success=.65,metadata={"incident_id":inc_id,"effect":effect})
            elif action_kind=="negotiate_protection_poach":
                uw.change_relation(conn,oid,source,kind="hostile_peace",hostility_delta=-8,respect_delta=1,metadata={"response_to_incident":inc_id})
                op=uw._operation(conn,oid,"negotiate_protection_poach",zone_id=inc["zone_id"],target_organization_id=source,enterprise_id=enterprise,result="completed",success=.7,metadata={"incident_id":inc_id})
            else:
                uw.change_relation(conn,oid,source,hostility_delta=4,respect_delta=1,metadata={"response_to_incident":inc_id})
                op=uw._operation(conn,oid,"warn_protection_poacher",zone_id=inc["zone_id"],target_organization_id=source,enterprise_id=enterprise,result="completed",success=.8,metadata={"incident_id":inc_id})
            conn.execute("UPDATE underworld_incidents SET status='answered' WHERE id=?",(inc_id,))
            return {"summary":f"Answered protection-poaching incident #{inc_id} through {action_kind}.","operation_id":op}
        if action_kind in {"occupy_vacant_turf","challenge_zone","poach_protection","targeted_hit","negotiate_settlement"}:
            return execute_aggression(conn,actor_id,oid,action_kind,payload,day)
        if action_kind=="seek_truce":
            other=int(payload["target_organization_id"]); uw.make_truce(conn,oid,other,metadata={"dec01_actor_id":actor_id}); return {"summary":f"Made a truce with {_org_name(conn,other)}."}
        if action_kind=="discipline_crew":
            cid=int(payload["crew_id"]); row=conn.execute("SELECT loyalty,cohesion FROM underworld_crews WHERE id=? AND organization_id=? AND status='active'",(cid,oid)).fetchone()
            if not row: raise ValueError("crew unavailable")
            conn.execute("UPDATE underworld_crews SET loyalty=MIN(100,loyalty+5),cohesion=MIN(100,cohesion+4) WHERE id=?",(cid,)); op=uw._operation(conn,oid,"discipline_crew",crew_id=cid,result="completed",success=.7,metadata={"dec01_actor_id":actor_id}); return {"summary":f"Disciplined crew #{cid}.","operation_id":op}
        if action_kind=="promote_personnel":
            target=int(payload["target_actor_id"]); row=conn.execute("SELECT role_kind FROM underworld_personnel WHERE actor_id=? AND organization_id=? AND status='active'",(target,oid)).fetchone()
            if not row: raise ValueError("personnel unavailable")
            conn.execute("UPDATE underworld_personnel SET role_kind='lieutenant',authority=MAX(authority,68) WHERE actor_id=?",(target,)); op=uw._operation(conn,oid,"promote_personnel",target_actor_id=target,result="completed",success=1,metadata={"prior_role":str(row[0])}); return {"summary":f"Promoted actor #{target} to lieutenant.","operation_id":op}
        if action_kind=="delegate_racket":
            rid=int(payload["racket_id"]); cid=int(payload["crew_id"])
            if not conn.execute("SELECT 1 FROM underworld_racket_sites WHERE id=? AND organization_id=? AND status='active'",(rid,oid)).fetchone(): raise ValueError("racket unavailable")
            if not conn.execute("SELECT 1 FROM underworld_crews WHERE id=? AND organization_id=? AND status='active'",(cid,oid)).fetchone(): raise ValueError("crew unavailable")
            conn.execute("UPDATE economic_interests SET status='ended',ended_day=? WHERE target_racket_id=? AND interest_kind='operator' AND status='active'",(day,rid))
            uw._insert_economic_interest(conn,interest_kind="operator",holder_crew_id=cid,target_racket_id=rid,metadata={"dec01_delegated_by":actor_id})
            op=uw._operation(conn,oid,"delegate_racket",crew_id=cid,result="completed",success=1,metadata={"racket_id":rid}); return {"summary":f"Delegated racket #{rid} to crew #{cid}.","operation_id":op}
        if action_kind=="expand_protection_account":
            eid=int(payload["enterprise_id"]); zid=int(payload["zone_id"])
            result=uw.protect_business(conn,oid,eid,zid,payment_per_30=1.0,service_strength=50,fear_component=45,metadata={"dec01_actor_id":actor_id})
            op=uw._operation(conn,oid,"expand_protection_account",zone_id=zid,enterprise_id=eid,result="completed" if result.get("created") else "attempted",success=1 if result.get("created") else .35,metadata=result)
            return {"summary":f"Protection-account expansion resolved for enterprise #{eid}: created={bool(result.get('created'))}.","operation_id":op,**result}
        if action_kind=="invest_in_racket":
            rid=int(payload["racket_id"]); amount=max(0.0,float(payload["amount"])); org=conn.execute("SELECT treasury FROM underworld_organizations WHERE id=?",(oid,)).fetchone()
            if not org or float(org[0])+1e-9<amount: raise ValueError("treasury no longer sufficient")
            rack=conn.execute("SELECT gross_income_per_30 FROM underworld_racket_sites WHERE id=? AND organization_id=? AND status='active'",(rid,oid)).fetchone()
            if not rack: raise ValueError("racket unavailable")
            conn.execute("UPDATE underworld_organizations SET treasury=treasury-?,updated_day=? WHERE id=?",(amount,day,oid)); conn.execute("UPDATE underworld_racket_sites SET gross_income_per_30=gross_income_per_30+? WHERE id=?",(amount*.10,rid))
            uw._finance(conn,oid,"racket_investment",-amount,metadata={"racket_id":rid,"dec01_actor_id":actor_id}); op=uw._operation(conn,oid,"invest_in_racket",result="completed",success=.8,metadata={"racket_id":rid,"amount":amount}); return {"summary":f"Invested {amount:.2f} treasury in racket #{rid}.","operation_id":op}
        if action_kind=="investigate_underworld_claim":
            cid=int(payload["claim_id"]); belief=conn.execute("SELECT 1 FROM actor_beliefs WHERE actor_id=? AND claim_id=?",(actor_id,cid)).fetchone()
            if not belief: raise ValueError("claim is not in actor belief state")
            op=uw._operation(conn,oid,"investigate_claim",result="ongoing",success=0,metadata={"claim_id":cid,"dec01_actor_id":actor_id}); return {"summary":f"Commissioned investigation of claim #{cid}.","operation_id":op}
        raise ValueError(f"unsupported underworld decision action {action_kind}")
    except Exception as exc:
        return {"summary":f"Underworld action blocked: {exc}","blocked":True}
