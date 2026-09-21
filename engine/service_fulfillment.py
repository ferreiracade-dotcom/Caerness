from __future__ import annotations
"""SERVICEFULFILL-01 — conserved service demand routed to concrete providers."""
import json, sqlite3
from typing import Any

def _day(conn): return int(conn.execute('SELECT current_day FROM world_state WHERE id=1').fetchone()[0])
def _j(v): return json.dumps(v if v is not None else {},sort_keys=True,ensure_ascii=False)

def activate_structural_provider_contracts(conn):
    created=0
    for row in conn.execute("""SELECT * FROM service_engagements WHERE status='active' AND client_institution_actor_id IS NOT NULL AND provider_kind IN ('institution','enterprise') ORDER BY id"""):
        pi=int(row['provider_id']) if str(row['provider_kind'])=='institution' else None; pe=int(row['provider_id']) if str(row['provider_kind'])=='enterprise' else None
        exists=conn.execute("""SELECT id FROM structural_provider_contracts WHERE consumer_institution_actor_id=? AND domain_key=? AND status='active' AND COALESCE(provider_institution_actor_id,-1)=COALESCE(?,-1) AND COALESCE(provider_enterprise_id,-1)=COALESCE(?,-1) ORDER BY id LIMIT 1""",(int(row['client_institution_actor_id']),str(row['domain_key']),pi,pe)).fetchone()
        if exists: continue
        conn.execute("""INSERT INTO structural_provider_contracts(consumer_institution_actor_id,provider_institution_actor_id,provider_enterprise_id,domain_key,authority_kind,started_day,ended_day,status,terms_json,metadata_json) VALUES (?,?,?,?,'collective_contractual',?,?,'active',?,?)""",
                     (int(row['client_institution_actor_id']),pi,pe,str(row['domain_key']),int(row['started_day']),row['end_day'],_j({'service_kind':row['service_kind'],'scope':json.loads(row['scope_json'] or '{}'),'compensation':json.loads(row['compensation_json'] or '{}')}),_j({'source_service_engagement_id':int(row['id']),'projected_existing_contract':True,'people_created':0}))); created+=1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('servicefulfill01_runtime_version','1')")
    return {'structural_provider_contracts_created':created,'structural_provider_contracts':int(conn.execute('SELECT COUNT(*) FROM structural_provider_contracts').fetchone()[0])}

def create_service_request(conn,domain_key,*,requester_actor_id=None,requester_institution_actor_id=None,requester_enterprise_id=None,location_id=None,need_level=50,requested_day=None,due_day=None,metadata=None):
    vals=[requester_actor_id,requester_institution_actor_id,requester_enterprise_id]
    if sum(v is not None for v in vals)!=1: raise ValueError('service request requires exactly one requester')
    day=_day(conn) if requested_day is None else int(requested_day)
    if location_id is None:
        if requester_actor_id is not None:
            r=conn.execute('SELECT current_location_id FROM actors WHERE id=?',(int(requester_actor_id),)).fetchone(); location_id=r[0] if r else None
        elif requester_institution_actor_id is not None:
            r=conn.execute('SELECT COALESCE(a.current_location_id,ip.primary_location_id) FROM actors a LEFT JOIN institution_profiles ip ON ip.actor_id=a.id WHERE a.id=?',(int(requester_institution_actor_id),)).fetchone(); location_id=r[0] if r else None
        elif requester_enterprise_id is not None:
            r=conn.execute('SELECT location_id FROM civilian_enterprises WHERE id=?',(int(requester_enterprise_id),)).fetchone(); location_id=r[0] if r else None
    cur=conn.execute("""INSERT INTO service_requests(requester_actor_id,requester_institution_actor_id,requester_enterprise_id,domain_key,location_id,need_level,requested_day,due_day,status,metadata_json) VALUES (?,?,?,?,?,?,?,?,'open',?)""",
                     (requester_actor_id,requester_institution_actor_id,requester_enterprise_id,str(domain_key),location_id,max(0,min(100,float(need_level))),day,due_day,_j(metadata)))
    return int(cur.lastrowid)

def _structural_provider(conn,req):
    if req['requester_institution_actor_id'] is None: return None
    return conn.execute("""SELECT * FROM structural_provider_contracts WHERE consumer_institution_actor_id=? AND domain_key=? AND status='active' AND (ended_day IS NULL OR ended_day>=?) ORDER BY id LIMIT 1""",(int(req['requester_institution_actor_id']),str(req['domain_key']),_day(conn))).fetchone()

def _engaged_provider(conn,req):
    client_actor=req['requester_actor_id']; client_inst=req['requester_institution_actor_id']
    if client_actor is None and client_inst is None: return None
    return conn.execute("""SELECT * FROM service_engagements WHERE status='active' AND domain_key=? AND ((client_actor_id IS NOT NULL AND client_actor_id=?) OR (client_institution_actor_id IS NOT NULL AND client_institution_actor_id=?)) AND (end_day IS NULL OR end_day>=?) ORDER BY id LIMIT 1""",(str(req['domain_key']),client_actor,client_inst,_day(conn))).fetchone()

def match_service_request(conn,request_id,*,allow_background_resolution=True):
    req=conn.execute('SELECT * FROM service_requests WHERE id=?',(int(request_id),)).fetchone()
    if not req: raise ValueError('unknown service request')
    if str(req['status'])!='open': return dict(req)
    provider_actor=provider_inst=provider_ent=None
    structural=_structural_provider(conn,req)
    if structural:
        provider_inst=structural['provider_institution_actor_id']; provider_ent=structural['provider_enterprise_id']
    if provider_actor is None and provider_inst is None and provider_ent is None:
        engaged=_engaged_provider(conn,req)
        if engaged:
            k=str(engaged['provider_kind']); pid=int(engaged['provider_id'])
            if k=='actor': provider_actor=pid
            elif k=='institution': provider_inst=pid
            elif k=='enterprise': provider_ent=pid
    if provider_actor is None and provider_inst is None and provider_ent is None:
        from .profession_runtime import available_professional_providers, resolve_background_professional
        providers=available_professional_providers(conn,str(req['domain_key']),location_id=req['location_id'],min_competence=max(0,float(req['need_level'])*.5))
        if providers: provider_actor=int(providers[0]['actor_id'])
        elif allow_background_resolution:
            provider_actor=resolve_background_professional(conn,str(req['domain_key']),location_id=req['location_id'],reason=f"service request {int(req['id'])}: {req['domain_key']}",min_competence=max(45,float(req['need_level'])*.5))
    if provider_actor is None and provider_inst is None and provider_ent is None: return dict(req)
    conn.execute("UPDATE service_requests SET provider_actor_id=?,provider_institution_actor_id=?,provider_enterprise_id=?,status='matched' WHERE id=?",(provider_actor,provider_inst,provider_ent,int(req['id'])))
    if provider_actor is not None:
        conn.execute("UPDATE professional_profiles SET current_load=current_load+1 WHERE actor_id=? AND domain_key=?",(provider_actor,str(req['domain_key'])))
    return dict(conn.execute('SELECT * FROM service_requests WHERE id=?',(int(request_id),)).fetchone())

def fulfill_service_request(conn,request_id):
    req=conn.execute('SELECT * FROM service_requests WHERE id=?',(int(request_id),)).fetchone()
    if not req: raise ValueError('unknown service request')
    if str(req['status'])=='fulfilled': return dict(req)
    if str(req['status'])=='open': match_service_request(conn,request_id); req=conn.execute('SELECT * FROM service_requests WHERE id=?',(int(request_id),)).fetchone()
    if str(req['status'])!='matched': return dict(req)
    quality=55.0
    if req['provider_actor_id'] is not None:
        row=conn.execute('SELECT competence,reputation FROM professional_profiles WHERE actor_id=? AND domain_key=?',(int(req['provider_actor_id']),str(req['domain_key']))).fetchone()
        if row: quality=max(0,min(100,float(row['competence'])*.7+float(row['reputation'])*.3))
    elif req['provider_institution_actor_id'] is not None: quality=62.0
    elif req['provider_enterprise_id'] is not None:
        er=conn.execute('SELECT reputation,admin_quality FROM civilian_enterprises WHERE id=?',(int(req['provider_enterprise_id']),)).fetchone()
        if er: quality=max(0,min(100,float(er['reputation'])*.6+float(er['admin_quality'])*.4))
    day=_day(conn)
    conn.execute("""INSERT OR IGNORE INTO service_fulfillments(request_id,provider_actor_id,provider_institution_actor_id,provider_enterprise_id,fulfilled_day,quality,metadata_json) VALUES (?,?,?,?,?,?,?)""",(int(req['id']),req['provider_actor_id'],req['provider_institution_actor_id'],req['provider_enterprise_id'],day,quality,_j({'concrete_provider':True,'people_created':0})))
    conn.execute("UPDATE service_requests SET status='fulfilled',fulfilled_day=? WHERE id=?",(day,int(req['id'])))
    if req['provider_actor_id'] is not None: conn.execute('UPDATE professional_profiles SET current_load=MAX(0,current_load-1) WHERE actor_id=? AND domain_key=?',(int(req['provider_actor_id']),str(req['domain_key'])))
    return dict(conn.execute('SELECT * FROM service_requests WHERE id=?',(int(request_id),)).fetchone())

def next_service_due_day(conn,after_day,end_day):
    overdue=conn.execute("SELECT 1 FROM service_requests WHERE status IN ('open','matched') AND requested_day<=? LIMIT 1",(int(after_day),)).fetchone(); vals=[]
    if overdue and after_day<end_day: vals.append(int(after_day)+1)
    row=conn.execute("SELECT MIN(COALESCE(due_day,requested_day)) FROM service_requests WHERE status IN ('open','matched') AND COALESCE(due_day,requested_day)>? AND COALESCE(due_day,requested_day)<=?",(int(after_day),int(end_day))).fetchone()
    if row and row[0] is not None: vals.append(int(row[0]))
    return min(vals) if vals else None

def process_due_services(conn,day,*,event_logger=None):
    matched=fulfilled=blocked=0
    rows=conn.execute("SELECT id FROM service_requests WHERE status IN ('open','matched') AND requested_day<=? AND (due_day IS NULL OR due_day<=?) ORDER BY id",(int(day),int(day))).fetchall()
    for row in rows:
        before=conn.execute('SELECT status FROM service_requests WHERE id=?',(int(row[0]),)).fetchone()[0]
        result=match_service_request(conn,int(row[0]),allow_background_resolution=True)
        if str(result['status'])=='matched' and before=='open': matched+=1
        result=fulfill_service_request(conn,int(row[0]))
        if str(result['status'])=='fulfilled': fulfilled+=1
        else: blocked+=1
    return {'service_requests_due':len(rows),'service_requests_matched':matched,'service_requests_fulfilled':fulfilled,'service_requests_blocked':blocked}
