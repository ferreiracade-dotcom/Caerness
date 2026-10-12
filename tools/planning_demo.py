"""General planning integration demo on a COPY of the opening database.

The scripted model supplies two different plans, not gameplay handlers. All
interpretation is explicitly labelled simulated. --local attempts the configured
real model instead; arbitrary --intention text is sent unchanged to that model.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def fixture():
    from engine.db import connect, database_path, DEFAULT_DB_PATH, init_db
    path=database_path()
    if path==DEFAULT_DB_PATH: raise ValueError('The demonstration requires an isolated scratch database.')
    path.parent.mkdir(parents=True,exist_ok=True)
    for suffix in ('','-wal','-shm'): Path(str(path)+suffix).unlink(missing_ok=True)
    shutil.copy2(ROOT/'data/caerness.db',path)
    init_db(); c=connect()
    from engine.player import set_player
    from engine.organization_agency import start_regime
    from engine.relationships import ensure_reciprocal_relationship
    from engine.presence import add_presence_habit
    from engine.seeking import register_offering
    from engine.opportunity import register_asset
    from engine.model_gateway import set_model_config
    loc=int(c.execute("SELECT id FROM locations WHERE name='Crownhold'").fetchone()[0])
    def actor(name,kind,subtype):
        return int(c.execute("INSERT INTO actors(name,actor_type,subtype,current_location_id,home_location_id,status,is_demo) VALUES (?,?,?,?,?,'active',1)",(name,kind,subtype,loc,loc)).lastrowid)
    owner=actor('[DEMO] Commander Rowan','character','commander')
    institution=actor('[DEMO] Caravan Office','institution','escort and trade office')
    mara=actor('[DEMO] Mara Vale','character','merchant surveyor')
    builder=actor('[DEMO] Rurik Bell','character','master builder')
    set_player(c,owner,'General planning demonstration')
    start_regime(c,institution,leader_actor_id=owner)
    for person,domain,role in ((mara,'commerce','caravan factor'),(builder,'craft','builder')):
        ensure_reciprocal_relationship(c,owner,person,0,trust=85,stance=70,familiarity=80,loyalty=65)
        add_presence_habit(c,person,loc,habit_kind='workplace',weight=1,confidence=1)
        c.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,joined_day) VALUES (?,?,'service',?,0)",(institution,person,role))
        d=c.execute('SELECT id FROM competence_domains WHERE domain_key=?',(domain,)).fetchone()
        if not d: raise ValueError('Demo domain must already exist in the engine.')
        c.execute('INSERT INTO actor_competence(actor_id,domain_id,score) VALUES (?,?,75)',(person,d[0]))
    for resource,amount in (('capital',100),('paper',20),('timber',40)):
        c.execute('INSERT INTO resources(actor_id,resource_type,amount,unit) VALUES (?,?,?,?)',(institution,resource,amount,'engine abstract units'))
    archive=register_asset(c,'building','[DEMO] Company archive',owner_institution_actor_id=institution,location_id=loc,metadata={'work_slots':2})
    yard=register_asset(c,'land','[DEMO] Company yard',owner_institution_actor_id=institution,location_id=loc,metadata={'work_slots':2})
    def offer(person,domain,subject,kind,resources,duration,sites):
        return register_offering(c,person,'service',domain,subject,location_id=loc,visibility=90,quality=75,
            metadata={'work_order':{'project_kind':kind,'resources':resources,'duration_days':duration,'site_kinds':sites,'minimum_skill':40}})
    survey=offer(mara,'commerce','local market and route report','manuscript',{'capital':10,'paper':4},30,['building'])
    build=offer(builder,'craft','training yard construction','architecture',{'capital':20,'timber':10},60,['land'])
    set_model_config(c,packet_dir=str(path.parent/'planning_packets'))
    from engine.world_capabilities import known_offerings
    quotes={q['offering_id']:q['quotation_digest'] for q in known_offerings(c,owner)}
    return c,{'owner':owner,'institution':institution,'mara':mara,'builder':builder,'archive':archive,'yard':yard,'survey':survey,'build':build,'survey_digest':quotes[survey],'build_digest':quotes[build]}


EXAMPLES={
 'survey':{'text':'Have Mara compile a merchant route-and-price report. Establish a responsibility for her, reserve twelve capital and four paper, and use our archive. Delegate the work and return any unspent reserve.',
           'person':'mara','offering':'survey','site':'archive','domain':'commerce','title':'Market and road report','role':'Commercial Report Steward','resources':{'capital':12,'paper':4}},
 'yard':{'text':'I want a new practice yard for promising fighters. Have our qualified builder oversee construction on company land, use twenty capital and ten timber, and return any unspent reserve when the work is finished.',
         'person':'builder','offering':'build','site':'yard','domain':'craft','title':'New practice yard','role':'Development Overseer','resources':{'capital':20,'timber':10}},
}


def composed_spec(ids,example,source=None):
    """Model-output fixture builder, not part of the production interpreter."""
    cfg=EXAMPLES[example]; source=source or cfg['text']
    def step(key,op,args,deps=()): return {'id':key,'operation':op,'arguments':args,'depends_on':list(deps)}
    def ref(key,field): return {'ref':key+'.'+field}
    inst=ids['institution']
    steps=[
        step('role','define_role',{'institution_id':inst,'title':cfg['role'],'domain':cfg['domain'],'remit':cfg['title']}),
        step('consent','offer_service',{'institution_id':inst,'person_id':ids[cfg['person']],'role_id':ref('role','role_id'),'offering_id':ids[cfg['offering']],'quotation_digest':ids[cfg['offering']+'_digest'],'scope':cfg['title']},('role',)),
        step('budget','allocate_resources',{'institution_id':inst,'resources':cfg['resources']},('consent',)),
        step('work','commission_work',{'institution_id':inst,'allocation_id':ref('budget','allocation_id'),'engagement_id':ref('consent','engagement_id'),'offering_id':ids[cfg['offering']],'quotation_digest':ids[cfg['offering']+'_digest'],'site_id':ids[cfg['site']],'title':cfg['title']},('consent','budget')),
        step('refund','refund_resources',{'allocation_id':ref('budget','allocation_id')},('work','budget')),
    ]
    return {'source_text':source,'summary':f"Propose {cfg['title']} through a new responsibility, a consenting existing professional, the published quotation, existing company resources and its owned site. Return unspent reserves after completion.",
        'coverage':[{'start':0,'end':len(source),'handling':'planned','step_ids':[s['id'] for s in steps]}],'unresolved':[],'steps':steps}


class ScriptedModel:
    """Returns supplied JSON responses. Does not understand or classify input text."""
    def __init__(self,responses): self.responses=iter(responses)
    def run(self,c,request):
        from engine.model_gateway import import_response, apply_model_request
        rid=request['request_id']
        import_response(c,rid,json.dumps({'task_type':'action_interpretation','request_id':rid,'proposal':next(self.responses)}))
        return apply_model_request(c,rid)


def demonstration(c,ids,example):
    from engine.planning_gateway import start_request
    from engine.ai_planning import approve_plan, plan_view
    from engine.simulation import advance_connection
    text=EXAMPLES[example]['text']
    req=start_request(c,text,'generic')
    model=ScriptedModel([
        {'mode':'inspect','calls':[{'tool':'context','arguments':{'institution_id':ids['institution']}},{'tool':'offerings','arguments':{}}]},
        {'mode':'plan','plan':composed_spec(ids,example)},
    ])
    inspected=model.run(c,req)
    proposed=model.run(c,inspected['next_request'])
    assert proposed['status']=='awaiting_plan_review',proposed
    print('PLAYER:',text)
    print('PROPOSED:',proposed['plan']['summary'])
    print('SCRIPTED PLAYER AUTHORIZATION: approve the displayed scope after reviewing the original instruction.')
    result=approve_plan(c,proposed['plan']['id'],proposed['plan']['digest'])
    print('COMMITTED:',json.dumps(result,ensure_ascii=False))
    c.commit()
    advance_connection(c,30); c.commit()
    print('AFTER 30 DAYS:',json.dumps(plan_view(c,proposed['plan']['id']),ensure_ascii=False))
    advance_connection(c,60); c.commit()
    print('AFTER 90 DAYS:',json.dumps(plan_view(c,proposed['plan']['id']),ensure_ascii=False))
    return proposed['plan']['id']


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--example',choices=list(EXAMPLES),default='survey')
    ap.add_argument('--local',action='store_true')
    ap.add_argument('--intention',default=None)
    ap.add_argument('--serve',action='store_true',help='Prepare the two scripted plan proposals and time-skip proposals for the real mobile interface')
    ap.add_argument('--port',type=int,default=8767)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='caerness_general_plan_') as work:
        os.environ['CAERNESS_DB_PATH']=str(Path(work)/'world.db')
        os.environ['CAERNESS_BACKUP_DIR']=str(Path(work)/'backups')
        c,ids=fixture()
        try:
            if args.serve:
                from engine.planning_gateway import start_request
                for name in EXAMPLES:
                    req=start_request(c,EXAMPLES[name]['text'],'generic')
                    model=ScriptedModel([{'mode':'inspect','calls':[{'tool':'context','arguments':{'institution_id':ids['institution']}},{'tool':'offerings','arguments':{}}]}, {'mode':'plan','plan':composed_spec(ids,name)}])
                    inspected=model.run(c,req); proposed=model.run(c,inspected['next_request'])
                    assert proposed['status']=='awaiting_plan_review'
                for days in (30,60):
                    source=f'Let {days} days pass for the world and the work we have delegated.'
                    spec={'source_text':source,'summary':source,'unresolved':[], 'coverage':[{'start':0,'end':len(source),'handling':'planned','step_ids':['time']}], 'steps':[{'id':'time','operation':'advance_time','arguments':{'days':days},'depends_on':[]}]}
                    req=start_request(c,source,'generic')
                    out=ScriptedModel([{'mode':'plan','plan':spec}]).run(c,req)
                    assert out['status']=='awaiting_plan_review'
                c.commit(); c.close()
                from engine.mobile_server import serve
                print(f'OFFLINE SCRIPTED MODEL FIXTURES; REAL WORLD EXECUTION. Open http://127.0.0.1:{args.port}, open Matters, review/authorize the report and yard, then the 30- and 60-day proposals.',flush=True)
                print('Typing a new idea uses the real configured local/manual model integration; no demo phrase matcher is installed.',flush=True)
                serve(port=args.port)
                from engine.db import connect
                c=connect()
            elif args.local:
                from engine.planning_gateway import play
                from engine.local_model import local_health
                print('REAL CONFIGURED MODEL HEALTH:',json.dumps(local_health(c)))
                out=play(c,args.intention or EXAMPLES[args.example]['text'])
                print(json.dumps({k:v for k,v in out.items() if k not in ('chatgpt','claude')},ensure_ascii=False))
            else:
                print('SIMULATED MODEL RESPONSES; REAL CAPABILITIES, WORLD SIMULATION AND PERSISTENCE.')
                pid=demonstration(c,ids,args.example)
                c.close()
                from engine.db import connect
                c=connect()
                from engine.ai_planning import plan_view
                print('RELOADED:',json.dumps(plan_view(c,pid),ensure_ascii=False))
        finally: c.close()


if __name__=='__main__': main()
