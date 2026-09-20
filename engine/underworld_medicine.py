from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from .health import add_treatment, apply_condition_harm
from .underworld import record_underworld_evidence


def _day(c): return int(c.execute("select current_day from world_state where id=1").fetchone()[0])
def _j(x): return json.dumps(x or {},sort_keys=True)

def create_medical_access(c, patient_actor_id:int, *, condition_id:int|None=None, provider_actor_id:int|None=None,
                          provider_enterprise_id:int|None=None, sponsor_institution_actor_id:int|None=None,
                          purpose_kind:str='discreet_care', consent_status:str='voluntary', confidentiality:float=80,
                          coercion:float=0, metadata:dict[str,Any]|None=None)->int:
    if provider_actor_id is None and provider_enterprise_id is None: raise ValueError('A real provider actor or enterprise is required')
    if not c.execute("select 1 from actors where id=? and status='active'",(patient_actor_id,)).fetchone(): raise ValueError('Patient must be living/active')
    if condition_id is not None:
        r=c.execute("select actor_id,status from health_conditions where id=?",(condition_id,)).fetchone()
        if not r or int(r['actor_id'])!=patient_actor_id or str(r['status']) not in ('active','recovering','chronic'): raise ValueError('Invalid unresolved condition')
    if provider_actor_id is not None and not c.execute("select 1 from actors where id=? and status='active'",(provider_actor_id,)).fetchone(): raise ValueError('Provider actor unavailable')
    if provider_enterprise_id is not None and not c.execute("select 1 from civilian_enterprises where id=? and status in ('active','strained')",(provider_enterprise_id,)).fetchone(): raise ValueError('Provider enterprise unavailable')
    loc=c.execute("select current_location_id from actors where id=?",(patient_actor_id,)).fetchone(); loc=int(loc[0]) if loc and loc[0] is not None else None
    cur=c.execute("""insert into underworld_medical_access(patient_actor_id,condition_id,provider_actor_id,provider_enterprise_id,sponsor_institution_actor_id,location_id,purpose_kind,consent_status,confidentiality,coercion,status,started_day,last_review_day,next_review_day,metadata_json)
                     values (?,?,?,?,?,?,?,?,?,?,'active',?,?,?,?)""",
                  (patient_actor_id,condition_id,provider_actor_id,provider_enterprise_id,sponsor_institution_actor_id,loc,purpose_kind,consent_status,max(0,min(100,confidentiality)),max(0,min(100,coercion)),_day(c),_day(c),_day(c)+30,_j(metadata)))
    return int(cur.lastrowid)

def record_medical_misconduct(c, access_id:int, *, treatment_id:int|None=None, misconduct_kind:str,
                              harm:float=0, financial_extraction:float=0, evidence_visibility:str='hidden', evidence_strength:float=0,
                              metadata:dict[str,Any]|None=None)->int:
    a=c.execute("select * from underworld_medical_access where id=?",(access_id,)).fetchone()
    if not a: raise ValueError('Unknown medical access')
    if evidence_visibility not in {'hidden','local','public'}: raise ValueError('Invalid evidence visibility')
    cond=int(a['condition_id']) if a['condition_id'] is not None else None
    if treatment_id is not None:
        t=c.execute("select actor_id,condition_id from medical_treatments where id=?",(treatment_id,)).fetchone()
        if not t or int(t['actor_id'])!=int(a['patient_actor_id']): raise ValueError('Treatment does not belong to patient')
        if cond is None and t['condition_id'] is not None: cond=int(t['condition_id'])
    cur=c.execute("""insert into medical_misconduct_events(access_id,treatment_id,condition_id,day,misconduct_kind,harm,financial_extraction,evidence_visibility,evidence_strength,status,metadata_json)
                     values (?,?,?,?,?,?,?,?,?,'active',?)""",(access_id,treatment_id,cond,_day(c),misconduct_kind,max(0,min(100,harm)),max(0,float(financial_extraction)),evidence_visibility,max(0,min(100,evidence_strength)),_j(metadata)))
    eid=int(cur.lastrowid)
    if harm>0 and cond is not None: apply_condition_harm(c,cond,severity_delta=min(25,float(harm)*0.25),reason=f'medical misconduct: {misconduct_kind}',metadata={'misconduct_event_id':eid})
    if financial_extraction>0:
        c.execute("insert into pressures(actor_id,kind,description,intensity,threshold,updated_day) values (?,?,?,?,20,?)",
                  (int(a['patient_actor_id']),'medical_exploitation','Exploitative medical costs are creating pressure.',min(100,float(financial_extraction)),_day(c)))
    if evidence_visibility!='hidden' and evidence_strength>0:
        subject_kind='actor' if a['provider_actor_id'] is not None else 'enterprise'; subject_id=int(a['provider_actor_id'] or a['provider_enterprise_id'])
        record_underworld_evidence(c,location_id=a['location_id'],subject_kind=subject_kind,subject_id=subject_id,evidence_kind=f'medical:{misconduct_kind}',visibility=evidence_visibility,strength=evidence_strength,source_kind='medical_misconduct',source_id=eid,metadata={'patient_actor_id':int(a['patient_actor_id'])})
    return eid

def _provider_actor(c, location_id:int|None, patient:int)->int|None:
    if location_id is None:return None
    r=c.execute("""select ac.actor_id from actor_competence ac join competence_domains d on d.id=ac.domain_id join actors a on a.id=ac.actor_id
                   where d.domain_key='medicine' and ac.score>=35 and a.status='active' and a.current_location_id=? and a.id<>? order by ac.score desc,ac.actor_id limit 1""",(location_id,patient)).fetchone()
    return int(r[0]) if r else None

def _provider_enterprise(c, location_id:int|None)->int|None:
    if location_id is None:return None
    r=c.execute("""select e.id from civilian_enterprises e left join enterprise_business_profiles bp on bp.enterprise_id=e.id
                   where e.location_id=? and e.status in ('active','strained') and (e.enterprise_kind='physician_practice' or bp.archetype_key='physician_practice') order by e.id limit 1""",(location_id,)).fetchone()
    return int(r[0]) if r else None

def next_underworld_medicine_due_day(c,after_day:int,end_day:int)->int|None:
    r=c.execute("select min(next_review_day) from underworld_medical_access where status='active' and next_review_day>? and next_review_day<=?",(after_day,end_day)).fetchone()
    vals=[int(r[0])] if r and r[0] is not None else []
    m=((after_day//30)+1)*30
    if m<=end_day:vals.append(m)
    return min(vals) if vals else None

def process_due_underworld_medicine(c, day:int, *, event_logger:Callable[...,int]|None=None)->dict[str,int]:
    created=treatments=closed=0
    rows=c.execute("""select distinct im.institution_actor_id,im.member_actor_id,h.id condition_id,a.current_location_id
                      from institution_memberships im join underworld_institution_profiles u on u.institution_actor_id=im.institution_actor_id
                      join actors a on a.id=im.member_actor_id join health_conditions h on h.actor_id=im.member_actor_id
                      where im.status='active' and u.status in ('active','strained') and a.status='active' and h.status in ('active','recovering','chronic') and h.severity>=20""").fetchall()
    for r in rows:
        if c.execute("select 1 from underworld_medical_access where patient_actor_id=? and condition_id=? and status='active'",(r['member_actor_id'],r['condition_id'])).fetchone(): continue
        pa=_provider_actor(c,r['current_location_id'],int(r['member_actor_id'])); pe=None if pa is not None else _provider_enterprise(c,r['current_location_id'])
        if pa is None and pe is None: continue
        aid=create_medical_access(c,int(r['member_actor_id']),condition_id=int(r['condition_id']),provider_actor_id=pa,provider_enterprise_id=pe,sponsor_institution_actor_id=int(r['institution_actor_id']),purpose_kind='discreet_care',consent_status='voluntary',confidentiality=85,metadata={'autonomous':'real injury + local provider'})
        created+=1
        if pa is not None:
            add_treatment(c,int(r['member_actor_id']),'ordinary_medicine',condition_id=int(r['condition_id']),provider_actor_id=pa,quality=60,adherence=75,metadata={'underworld_medical_access_id':aid,'confidentiality':'discreet'})
            treatments+=1
    for a in c.execute("select * from underworld_medical_access where status='active' and next_review_day<=?",(day,)).fetchall():
        if a['condition_id'] is not None:
            h=c.execute("select status from health_conditions where id=?",(a['condition_id'],)).fetchone()
            if not h or str(h[0]) in ('resolved','fatal'):
                c.execute("update underworld_medical_access set status='ended',last_review_day=?,next_review_day=? where id=?",(day,day,a['id']));closed+=1;continue
        c.execute("update underworld_medical_access set last_review_day=?,next_review_day=? where id=?",(day,day+30,a['id']))
    return {'eligible_patients':len(rows),'access_created':created,'treatments_created':treatments,'access_closed':closed}
