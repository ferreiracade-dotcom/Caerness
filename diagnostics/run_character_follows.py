from __future__ import annotations
import json, shutil, sqlite3, sys, os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
BASE=ROOT/'diagnostics'/'follow_base.db'
sys.path.insert(0,str(ROOT))
from engine.db import connect, init_db
from engine.crystallization import prepare_crystallization_context, validate_crystallization_proposal, apply_crystallization_proposal
from engine.continuity import set_resolution
from engine.civilian import create_enterprise
from engine.business import configure_enterprise_business
from engine.underworld import record_underworld_evidence, derive_gang_opening_membership
from engine.religion import set_affiliation
from engine.simulation import advance_connection
from engine.education import enroll
from engine.cultivation import CORE_CAPACITY, _record_opening_stage_chain, _opening_depth_calibration, _realization_aptitude, _vessel_aptitude, _next_check_day
from engine.role_experience import _role_kind
from engine.career_reach import ensure_role_career


def advance_coarse(c, days, step=14):
    """Compressed unattended-decade scheduler. All subsystem owners still run; exact daily
    presentation clocks are coalesced to bounded checkpoints for long-horizon acceptance runs."""
    import engine.simulation as sim
    from engine.interactions import process_due_interactions
    from engine.world import process_due_world_processes, catch_up_world_processes
    from engine.civilian import process_due_civilian
    from engine.health import process_due_health
    from engine.psych import process_due_psychology
    from engine.religion import process_due_religion
    from engine.ecology import process_due_ecology
    from engine.politics import process_due_politics
    from engine.education import process_due_education
    from engine.logistics import process_due_logistics
    from engine.cultivation import process_due_cultivation
    from engine.groundbinding import process_due_groundbinding
    from engine.tournaments import process_due_tournaments
    from engine.spectacle import process_due_spectacle
    from engine.underworld import process_due_underworld
    from engine.underworld_medicine import process_due_underworld_medicine
    from engine.hollow import process_due_hollow
    from engine.war import process_due_war
    from engine.resolution_controller import process_due_resolution
    from engine.information import process_information
    from engine.player import process_camera_succession
    start=int(c.execute('select current_day from world_state where id=1').fetchone()[0]); end=start+int(days); now=start
    while now < end:
        checkpoint=min(end,now+step)
        c.execute('update world_state set current_day=?,updated_at=CURRENT_TIMESTAMP where id=1',(checkpoint,))
        sim._expire_forced_tiers(c,checkpoint); sim._expire_agreements(c,checkpoint)
        for clock in c.execute("select * from clocks where status='pending' and due_day<=? order by due_day,id",(checkpoint,)).fetchall(): sim._process_clock(c,clock,checkpoint)
        process_due_interactions(c,checkpoint)
        for profile in c.execute('select * from simulation_profiles where next_review_day<=? order by next_review_day,actor_id',(checkpoint,)).fetchall():
            # In an unattended decade, DORMANT individual choices are annually compressed.
            # Their background processes integrate elapsed time when reviewed, and world/cohort
            # owners continue every checkpoint.  STRATEGIC/ACTIVE actors retain normal resolution.
            if str(profile['tier'] or '').upper()=='DORMANT' and checkpoint-int(profile['last_review_day'] or 0) < 330:
                continue
            sim._review_actor(c,profile,checkpoint)
        logger=sim._world_event_logger(c)
        process_due_resolution(c,checkpoint)
        process_due_world_processes(c,checkpoint,event_logger=logger); process_due_ecology(c,checkpoint,event_logger=logger)
        process_due_logistics(c,checkpoint,event_logger=logger); process_due_civilian(c,checkpoint,event_logger=logger)
        process_due_underworld(c,checkpoint,event_logger=logger); process_due_underworld_medicine(c,checkpoint,event_logger=logger)
        process_due_war(c,checkpoint,event_logger=logger); process_due_groundbinding(c,checkpoint,event_logger=logger)
        process_due_health(c,checkpoint,event_logger=logger); process_due_psychology(c,checkpoint,event_logger=logger)
        process_due_hollow(c,checkpoint,event_logger=logger); process_camera_succession(c)
        process_due_religion(c,checkpoint,event_logger=logger); process_due_politics(c,checkpoint,event_logger=logger)
        process_due_education(c,checkpoint,event_logger=logger); process_due_cultivation(c,checkpoint,event_logger=logger)
        # Long-horizon checkpoints coalesce presentation cadence, not outcomes.  Tournament rounds
        # and accepted challenges therefore receive bounded same-checkpoint catch-up so a three-week
        # event does not unrealistically occupy several seasons merely because the audit samples quarterly.
        for _ in range(24):
            before_ch=int(c.execute("select count(*) from martial_challenges where status='active'").fetchone()[0])
            before_ev=int(c.execute("select count(*) from tournament_events where status in ('registration','active') and next_review_day<=?",(checkpoint,)).fetchone()[0])
            process_due_tournaments(c,checkpoint,event_logger=logger)
            # Pull only already-started, unresolved martial processes into this checkpoint.  This
            # never opens a future event early.
            c.execute("update martial_challenges set next_review_day=? where status='active' and next_review_day>? and next_review_day<=?",(checkpoint,checkpoint,checkpoint+step))
            c.execute("update tournament_events set next_review_day=? where status='active' and next_review_day>? and next_review_day<=?",(checkpoint,checkpoint,checkpoint+step))
            after_ch=int(c.execute("select count(*) from martial_challenges where status='active' and next_review_day<=?",(checkpoint,)).fetchone()[0])
            after_ev=int(c.execute("select count(*) from tournament_events where status='active' and next_review_day<=?",(checkpoint,)).fetchone()[0])
            if before_ch==0 and before_ev==0 and after_ch==0 and after_ev==0:
                break
        process_due_spectacle(c,checkpoint,event_logger=logger)
        if checkpoint==end:
            process_information(c,checkpoint)
        now=checkpoint
    return c.execute('select * from events where day>? and day<=? order by day,id',(start,end)).fetchall()

def open_db(path):
    os.environ['CAERNESS_DB_PATH']=str(path)
    return connect()

SCENARIOS={
 'underworld': dict(seed=9201,name='[SIM] Cale Brann',age=28,loc='Aldergate',subtype='boss of an independent Aldergate ward gang and cartage-yard operator',
    drives=(0.58,0.68,0.62,0.63,0.72,0.82),
    goals=[('Make the crew indispensable in one Aldergate ward without provoking a crackdown',86),('Turn irregular collections into durable income and useful contacts',74)],
    pressures=[('criminal_exposure','Rival crews, unpaid clients, and the watch can all make visible violence expensive',52,80)],
    resources=[('working_cash',14.0,'calibration units')], core=None),
 'longroad': dict(seed=9202,name='[SIM] Sella Marrin',age=24,loc='Waymeet',subtype='independent Long Road escort hand',
    drives=(0.48,0.66,0.58,0.52,0.69,0.70),
    goals=[('Build enough Road reputation to choose better contracts rather than take whatever appears',82),('Improve martial reliability without binding herself to a House or sect',78)],
    pressures=[('income','Travel, equipment, lodging and medicine have to be paid for between contracts',48,75)],
    resources=[('cash',8.0,'calibration units'),('road_reputation',12.0,'index')], core=('Open-Core','Temper',56.0,40.0,62.0,60.0)),
 'concord': dict(seed=9203,name='[SIM] Tobin Verra',age=23,loc='Wrenfield seat district',subtype='Wrenfield junior spear disciple',
    drives=(0.44,0.53,0.70,0.78,0.72,0.57),
    goals=[('Become a dependable professional spear disciple rather than merely a promising junior',84),('Earn responsibility through disciplined institutional service',70)],
    pressures=[('expectation','Training peers and instructors make stagnation visible',44,78)],
    resources=[('institutional_support',18.0,'index')], core=('Open-Core','Temper',60.0,42.0,70.0,65.0)),
 'dunmoor': dict(seed=9204,name='[SIM] Ansel Rooke',age=31,loc='Northwatch',subtype='Dunmoor estate retainer and horse-country fighter',
    drives=(0.55,0.57,0.68,0.76,0.55,0.64),
    goals=[('Remain valuable as a retainer through horsecraft, reliability and practical fighting',80),('Improve cultivation as far as circumstances allow without abandoning estate obligations',66)],
    pressures=[('duty','Estate and household work compete directly with training time',54,82)],
    resources=[('household_income',9.0,'calibration units'),('horse_access',14.0,'index')], core=('Open-Core','Temper',50.0,34.0,48.0,60.0)),
 'witness': dict(seed=9205,name='[SIM] Mara Elwick',age=34,loc='Eldenfell',subtype='Witness parish clerk and charitable organizer',
    drives=(0.20,0.34,0.78,0.86,0.43,0.68),
    goals=[('Keep parish records and poor-relief work dependable through ordinary local pressures',84),('Deepen religious service without seeking elite ecclesiastical office',58)],
    pressures=[('service','Needs routinely exceed the time and money available for relief',46,76)],
    resources=[('household_cash',6.0,'calibration units'),('local_trust',18.0,'index')], core=('Closed-Core',None,0,0,0,0)),
 'merchant': dict(seed=9206,name='[SIM] Elian Torve',age=36,loc='Saltmere',subtype='independent small freight and provisions merchant',
    drives=(0.28,0.61,0.67,0.52,0.76,0.84),
    goals=[('Turn a small independent concern into a reliable regional business without becoming dependent on a great house',86),('Protect cash flow while taking selective expansion opportunities',78)],
    pressures=[('commerce','Freight risk, delayed payment and competition can erase a thin margin',50,80)],
    resources=[('working_cash',18.0,'calibration units')], core=('Closed-Core',None,0,0,0,0)),
}

def loc_id(c,name):
 r=c.execute('select id from locations where name=?',(name,)).fetchone();
 if not r: raise RuntimeError(name)
 return int(r[0])

def create_focus(c,key,cfg):
 lid=loc_id(c,cfg['loc']); day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
 # Pre-existing latent life: crystallization discovers one member of the structural population.
 cur=c.execute("""insert into latent_entities(latent_kind,archetype,location_id,count_estimate,constraints_json,historical_context_json,status,created_day,updated_day,notes)
                  values('person',?,?,1,?,?,'latent',?,?,?)""",
               (key,lid,json.dumps({'age_range':[cfg['age'],cfg['age']],'scenario_archetype':key,'identity_status':'pre-existing unnamed person'}),
                json.dumps({'scenario':'character_follow','pre_exists_camera':True}),day,day,'Scenario crystallization from structural population; campaign-only identity.'))
 latent=int(cur.lastrowid)
 ctx=prepare_crystallization_context(c,latent,requested_depth='shallow',trigger_kind='engine')
 birth_day=day-cfg['age']*365
 prop={'name':cfg['name'],'actor_type':'character','subtype':cfg['subtype'],'birth_day':birth_day,
       'home_location_id':lid,'current_location_id':lid,
       'continuity':{'identity':{'scenario_generated':True,'canon_status':'CAMPAIGN_ONLY','archetype':key},'values':[],'goals':[g for g,_ in cfg['goals']]},
       'anchors':[],'career':None,'connections':[],'resolution_level':'TRACKED','notes':'Campaign-only non-ledger character resolved for follow simulation.'}
 v=validate_crystallization_proposal(c,ctx['run_id'],prop)
 if not v['valid']: raise RuntimeError((key,v))
 aid=apply_crystallization_proposal(c,ctx['run_id'])
 # Crystallization must participate in biological time immediately. Historical family state is not invented.
 c.execute("""insert or replace into actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json)
              values (?,?, 'adult',1,'living',?,?)""",
           (aid,birth_day,day,json.dumps({'authority':'SCENARIO_CALIBRATION','historical_household_state':'UNKNOWN'},sort_keys=True)))
 # Keep the focus actor autonomous; TRACKED here means persisted resolution, not camera/player control.
 c.execute("insert or replace into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,?,?,?,?,?,?,?)",
           (aid,'STRATEGIC',30,0.32,0.72,day,day+7,3))
 ag,rt,pa,lo,am,pr=cfg['drives']
 c.execute("insert or replace into actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) values (?,?,?,?,?,?,?)",(aid,ag,rt,pa,lo,am,pr))
 for desc,priority in cfg['goals']:
  c.execute("insert into goals(actor_id,description,priority,progress,status,created_day) values (?,?,?,?, 'active',?)",(aid,desc,priority,0.0,day))
 for kind,desc,intensity,threshold in cfg['pressures']:
  c.execute("insert into pressures(actor_id,kind,description,intensity,threshold,updated_day) values (?,?,?,?,?,?)",(aid,kind,desc,intensity,threshold,day))
 for typ,amount,unit in cfg['resources']:
  c.execute("insert into resources(actor_id,resource_type,amount,unit,updated_day) values (?,?,?,?,?)",(aid,typ,amount,unit,day))
 # Basic cultivation/body state where relevant. Rates are scenario opening calibration, never canon facts.
 core=cfg.get('core')
 if core:
  core_state,stage,vessel,real,teacher,resource=core
  cap=float(CORE_CAPACITY.get(stage,0.0)) if stage else 0.0
  active=1 if core_state=='Open-Core' else 0
  status='active' if active else 'paused'
  va=_vessel_aptitude(c,aid) if active else 1.0
  ra=_realization_aptitude(c,aid) if active else 1.0
  if active and stage:
   vessel,real,_=_opening_depth_calibration(c,aid,stage,cfg['age'],va,ra)
   next_check=_next_check_day(c,aid,day,stage)
  else:
   next_check=day+3650
  c.execute("""insert or replace into cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
      training_effort,resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,next_realization_check_day,
      observed_stage_days,plateau_days,last_review_day,next_review_day,status,metadata_json,core_capacity,current_reserve,sediment_burden)
      values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (aid,core_state,stage,active,vessel,real,58.0 if active else 0.0,resource,teacher,0.0,ra,va,next_check,0,0,day,day+30,status,
       json.dumps({'authority':'V0_58_SCENARIO_CALIBRATION','final_stage':'NOT_STORED','attainment_date':'UNKNOWN','current_age_not_attainment_age':True},sort_keys=True),cap,cap*0.6 if active else 0.0,0.0))
  _record_opening_stage_chain(c,aid,stage)
 # Archetype-specific social/economic wiring.
 if key=='concord':
  iid=int(c.execute("select id from actors where name='Wrenfield Sect' and actor_type='institution'").fetchone()[0])
  c.execute("insert into institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json) values (?,?, 'member','ordinary junior spear disciple','active',?, ?, ?)",
            (iid,aid,day,json.dumps(['scenario latent Concord member']),json.dumps({'campaign_only':True})))
  prog=c.execute("select id from education_programs where institution_actor_id=? and program_kind='martial_foundation' and status='active' order by id limit 1",(iid,)).fetchone()
  if prog: enroll(c,aid,int(prog[0]),practice_quality=1.15,metadata={'campaign_only':True,'basis':'ordinary Wrenfield foundation instruction'})
 if key=='dunmoor':
  ni=c.execute("select id from actors where name='Northwatch School' and actor_type='institution'").fetchone()
  if ni:
   prog=c.execute("select id from education_programs where institution_actor_id=? and program_kind='martial_foundation' and status='active' order by id limit 1",(int(ni[0]),)).fetchone()
   if prog: enroll(c,aid,int(prog[0]),practice_quality=0.90,metadata={'campaign_only':True,'basis':'bounded local retainer access; not School membership'})
 if key=='witness':
  set_affiliation(c,aid,'witness',affiliation_kind='adherent',practice_intensity=78,publicness=82,metadata={'campaign_only':True,'role':'parish clerk/charity organizer'})
 if key=='underworld':
  eid=create_enterprise(c,'[STRUCTURAL SIM] Aldergate ward cartage yard','service',owner_actor_id=aid,location_id=lid,capital=17,cash=10,debt=2,reputation=42,admin_quality=48,labor_capacity=38,risk_tolerance=67,
                        metadata={'campaign_only':True,'front_for_minor_crew':True,'named_underworld_institution':False})
  configure_enterprise_business(c,eid,'cartage_firm',quality=44,price_position=44,capacity=30,clientele_fit=58,service_reliability=46,regulatory_pressure=22,metadata={'campaign_only':True})
  # Two already-existing racket traces are enough for the engine to recognize a forming crew later,
  # but both start hidden so police knowledge is not fabricated.
  record_underworld_evidence(c,location_id=lid,subject_kind='enterprise',subject_id=eid,evidence_kind='protection_collection',visibility='hidden',strength=36,source_kind='scenario_history',source_id=eid,metadata={'preexisting_minor_crew':True},day=day)
  record_underworld_evidence(c,location_id=lid,subject_kind='enterprise',subject_id=eid,evidence_kind='stolen_goods_handling',visibility='hidden',strength=31,source_kind='scenario_history',source_id=eid,metadata={'preexisting_minor_crew':True},day=day)
  from engine.underworld import create_underworld_organization, ensure_underworld_membership_profile
  # Opening manpower is not a hidden constant.  The qualitative scenario says Cale already runs
  # a functioning ward gang with a legitimate front, two recurring rackets, group enforcement,
  # and enough criminal reach to commission targeted violence. Resolve the personnel stock from
  # that footprint only when the diagnostic needs individual-scale organization state.
  import random as _random
  opening=derive_gang_opening_membership(_random.Random(cfg['seed']+59091),
      racket_breadth=24,territorial_presence=22,front_depth=28,violence_capacity=28,command_depth=2,
      recurring_rackets=2,has_operating_front=True,can_mount_group_violence=True,can_commission_targeted_killing=True)
  oid=create_underworld_organization(c,'sim-cale-brann-gang','gang',name='[SIM] Cale Brann gang',founder_actor_id=aid,anchor_enterprise_id=eid,primary_location_id=lid,
      member_count_estimate=opening['full_members'],command_depth=2,territorial_presence=22,racket_breadth=24,front_depth=28,corrupt_access=5,reputation_deterrence=18,violence_capacity=28,
      cohesion=62,membership_stability=52,succession_depth=5,metadata={'campaign_only':True,'preexisting_local_gang':True,'organization_form_is_not_rank':True,'auto_type_change':False,
      'opening_scale_resolution':'derived_from_operational_footprint','opening_scale_inputs':{'recurring_rackets':2,'operating_front':True,'group_violence':True,'targeted_killing_capacity':True},
      'opening_scale_result':opening})
  ensure_underworld_membership_profile(c,oid,core_members=opening['core_members'],active_members=opening['active_members'],peripheral_associates=opening['peripheral_associates'],
      metadata={'membership_categories_are_analytic':True,'opening_stock_resolved_from_operational_footprint':True,'opening_scale_result':opening})
  # Legacy read-model for systems that still ask how many reliable gang hands Cale currently has.
  c.execute("insert into resources(actor_id,resource_type,amount,unit,updated_day) values (?,?,?,?,?)",(aid,'crew_loyalty',opening['full_members'],'people-equivalent',day))
 if key=='merchant':
  eid=create_enterprise(c,'[STRUCTURAL SIM] Saltmere independent provisions factor','merchant_house',owner_actor_id=aid,location_id=lid,capital=28,cash=16,debt=4,reputation=47,admin_quality=56,labor_capacity=36,risk_tolerance=54,
                        metadata={'campaign_only':True,'independent_non_house_merchant':True})
  configure_enterprise_business(c,eid,'wholesaler',quality=51,price_position=49,capacity=34,clientele_fit=57,service_reliability=55,regulatory_pressure=12,metadata={'campaign_only':True})
 # Attach the already-existing profession to v0.59's structural responsibility track at opening.
 kind,ctx=_role_kind(c,aid)
 if kind: ensure_role_career(c,aid,kind,ctx)
 return aid,latent

def snapshot(c,aid):
 a=dict(c.execute("select a.*,l.name location_name from actors a left join locations l on l.id=a.current_location_id where a.id=?",(aid,)).fetchone())
 out={'day':int(c.execute('select current_day from world_state where id=1').fetchone()[0]),'actor':a}
 out['goals']=[dict(r) for r in c.execute('select description,priority,progress,status,target_day from goals where actor_id=? order by id',(aid,))]
 out['pressures']=[dict(r) for r in c.execute('select kind,description,intensity,threshold from pressures where actor_id=? order by id',(aid,))]
 out['resources']=[dict(r) for r in c.execute('select resource_type,amount,unit from resources where actor_id=? order by id',(aid,))]
 cp=c.execute('select * from cultivation_profiles where actor_id=?',(aid,)).fetchone(); out['cultivation']=dict(cp) if cp else None
 if out['cultivation'] and out['cultivation'].get('metadata_json'):
  out['cultivation']['metadata']=json.loads(out['cultivation'].pop('metadata_json'))
 out['decisions']=[dict(r) for r in c.execute('select day,tier,action_type,rationale,outcome_summary from decisions where actor_id=? order by id',(aid,))]
 out['events']=[dict(r) for r in c.execute('''select distinct e.day,e.event_type,e.title,e.summary,e.severity from events e left join event_targets t on t.event_id=e.id where e.source_actor_id=? or t.actor_id=? order by e.day,e.id''',(aid,aid))]
 out['relationships']=[dict(r) for r in c.execute('''select r.id,case when r.actor_a_id=? then b.name else aa.name end as other_name,r.stance,r.trust,r.obligation,r.updated_day
        from relationships r join actors aa on aa.id=r.actor_a_id join actors b on b.id=r.actor_b_id where r.actor_a_id=? or r.actor_b_id=? order by abs(r.stance)+abs(r.trust)+abs(r.obligation) desc limit 20''',(aid,aid,aid))]
 out['memberships']=[dict(r) for r in c.execute('''select i.name,m.membership_kind,m.role_text,m.status from institution_memberships m join actors i on i.id=m.institution_actor_id where m.member_actor_id=?''',(aid,))]
 out['careers']=[dict(r) for r in c.execute('''select ac.id,ct.key track_key,ct.name track_name,cs.stage_key,cs.stage_name,cs.sequence_index,ac.started_day,ac.stage_started_day,ac.status,ac.experience_json,ac.reputation_json from actor_careers ac join career_tracks ct on ct.id=ac.track_id left join career_stages cs on cs.id=ac.current_stage_id where ac.actor_id=? order by ac.id''',(aid,))]
 out['religion']=[dict(r) for r in c.execute('''select t.name,r.affiliation_kind,r.practice_intensity,r.publicness,r.status,r.last_observance_day from religious_affiliations r join religious_traditions t on t.id=r.tradition_id where r.actor_id=?''',(aid,))]
 out['underworld_organizations']=[dict(r) for r in c.execute("select * from underworld_organizations where founder_actor_id=? or institution_actor_id=? order by id",(aid,aid))]
 out['underworld_membership_profiles']=[dict(r) for r in c.execute('''select ump.* from underworld_membership_profiles ump join underworld_organizations uo on uo.id=ump.organization_id where uo.founder_actor_id=? or uo.institution_actor_id=? order by ump.organization_id''',(aid,aid))]
 out['underworld_membership_flows']=[dict(r) for r in c.execute('''select umf.* from underworld_membership_flows umf join underworld_organizations uo on uo.id=umf.organization_id where uo.founder_actor_id=? or uo.institution_actor_id=? order by umf.day,umf.id''',(aid,aid))]
 out['enterprises']=[dict(r) for r in c.execute('select id,name,enterprise_kind,capital,cash,debt,reputation,status,created_day,updated_day from civilian_enterprises where owner_actor_id=? order by id',(aid,))]
 entids=[e['id'] for e in out['enterprises']]
 if entids:
  q=','.join('?'*len(entids))
  out['underworld_evidence']=[dict(r) for r in c.execute(f'select * from underworld_evidence where subject_kind="enterprise" and subject_id in ({q}) order by id',entids)]
  out['institution_candidates']=[dict(r) for r in c.execute(f'select * from emergent_institution_candidates where enterprise_id in ({q}) order by id',entids)]
 else:
  out['underworld_evidence']=[]; out['institution_candidates']=[]
 out['resolution']=[dict(r) for r in c.execute('select * from resolution_reviews where entity_kind="actor" and entity_id=? order by day,id',(aid,))]
 out['cultivation_history']=[dict(r) for r in c.execute('select day,history_kind,stage_before,stage_after,summary,metadata_json from cultivation_history where actor_id=? order by day,id',(aid,))]
 out['travel']=[dict(r) for r in c.execute('''select tp.id,tp.started_day,tp.arrived_day,tp.status,lo.name origin,ld.name destination,tp.metadata_json from travel_plans tp join locations lo on lo.id=tp.origin_location_id join locations ld on ld.id=tp.destination_location_id where tp.subject_kind='actor' and tp.subject_id=? order by tp.id''',(aid,))]
 out['tournament_entries']=[dict(r) for r in c.execute('''select te.registered_day,te.eliminated_day,te.status,ev.name event_name,tf.field_key from tournament_entries te join tournament_events ev on ev.id=te.event_id join tournament_fields tf on tf.id=te.field_id where te.actor_id=? order by te.id''',(aid,))]
 out['tournament_bouts']=[dict(r) for r in c.execute('''select tb.resolved_day,tb.round_index,ev.name event_name,tf.field_key,case when tb.actor_a_id=? then b.name else a.name end opponent,w.name winner,tb.status,tb.metadata_json from tournament_bouts tb join tournament_events ev on ev.id=tb.event_id join tournament_fields tf on tf.id=tb.field_id join actors a on a.id=tb.actor_a_id join actors b on b.id=tb.actor_b_id left join actors w on w.id=tb.winner_actor_id where tb.actor_a_id=? or tb.actor_b_id=? order by tb.resolved_day,tb.id''',(aid,aid,aid))]
 out['challenges']=[dict(r) for r in c.execute('''select mc.created_day,mc.resolved_day,mc.terms_kind,mc.lethal,mc.status,case when mc.proposer_actor_id=? then b.name else a.name end opponent from martial_challenges mc join actors a on a.id=mc.proposer_actor_id join actors b on b.id=mc.recipient_actor_id where mc.proposer_actor_id=? or mc.recipient_actor_id=? order by mc.id''',(aid,aid,aid))]
 out['combat_engagements']=[dict(r) for r in c.execute('''select ce.day_started,ce.day_ended,ce.engagement_kind,ce.title,ce.objective_text,ce.status,ce.outcome_json from combat_engagements ce join duel_combatants dc on dc.engagement_id=ce.id where dc.actor_id=? order by ce.day_started,ce.id''',(aid,))]
 out['households']=[dict(r) for r in c.execute('''select h.id,h.name,h.status,hm.role,hm.joined_day,hm.left_day from household_members hm join households h on h.id=hm.household_id where hm.actor_id=? order by hm.joined_day,h.id''',(aid,))]
 out['unions']=[dict(r) for r in c.execute('''select u.id,u.started_day,u.ended_day,u.status,case when u.actor_a_id=? then b.name else a.name end partner from household_unions u join actors a on a.id=u.actor_a_id join actors b on b.id=u.actor_b_id where u.actor_a_id=? or u.actor_b_id=? order by u.id''',(aid,aid,aid))]
 out['children']=[dict(r) for r in c.execute('''select a.name,alp.birth_day from kinship_links k join actors a on a.id=k.actor_b_id join actor_life_profiles alp on alp.actor_id=a.id where k.actor_a_id=? and k.kin_kind='parent' order by alp.birth_day,a.id''',(aid,))]
 out['health_conditions']=[dict(r) for r in c.execute('select condition_kind,label,severity,status,onset_day,resolved_day from health_conditions where actor_id=? order by onset_day,id',(aid,))]
 return out

def setup(key):
 cfg=SCENARIOS[key]; dst=ROOT/'diagnostics'/f'follow_{key}_latent.db'
 # A timed-out SQLite run can leave WAL/SHM sidecars. Reusing them with a fresh main DB
 # can replay stale pages into the new branch, so branch reset must remove the full SQLite set.
 for q in (dst, Path(str(dst)+'-wal'), Path(str(dst)+'-shm')):
  if q.exists(): q.unlink()
 shutil.copy2(BASE,dst)
 os.environ['CAERNESS_DB_PATH']=str(dst); init_db()
 c=open_db(dst); c.execute('update world_state set rng_seed=? where id=1',(cfg['seed'],));
 aid,latent=create_focus(c,key,cfg); c.commit()
 setup={'scenario':key,'rng_seed':cfg['seed'],'focus_actor_id':aid,'focus_actor':cfg['name'],'latent_entity_id':latent,'non_ledger':True,'campaign_only':True,'starting_location':cfg['loc']}
 (ROOT/'diagnostics'/f'follow_{key}_latent_setup.json').write_text(json.dumps(setup,indent=2),encoding='utf-8')
 c.close(); return dst,aid

def run(key, years=10):
 dst,aid=setup(key); c=open_db(dst); snaps=[snapshot(c,aid)]
 # Annual audit calls use quarterly internal checkpoints.  Information propagation is
 # intentionally summarized at the annual boundary while every other subsystem still executes
 # through the year; this is long-horizon resolution compression, not a different causal model.
 for _year in range(years):
  advance_coarse(c,365,91)
  c.commit()
  snaps.append(snapshot(c,aid))
 report={'scenario':key,'years':years,'focus_actor_id':aid,'snapshots':snaps,'final':snaps[-1]}
 rp=ROOT/'diagnostics'/f'follow_{key}_latent_report.json'; rp.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
 c.close(); print(json.dumps({'scenario':key,'db':str(dst),'report':str(rp),'actor_id':aid,'day':report['final']['day'],'decisions':len(report['final']['decisions']),'events':len(report['final']['events']),'relationships':len(report['final']['relationships']),'enterprises':len(report['final']['enterprises']),'candidates':len(report['final']['institution_candidates']),'stage':(report['final']['cultivation'] or {}).get('current_stage')},indent=2))

if __name__=='__main__':
 key=sys.argv[1] if len(sys.argv)>1 else 'underworld'; years=int(sys.argv[2]) if len(sys.argv)>2 else 3
 run(key,years)
