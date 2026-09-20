from __future__ import annotations
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db,init_db,connect,ENGINE_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.career_reach import (
    ensure_role_career, note_role_event, career_state, _eligibility,
    _responsibility_eligibility, career_responsibilities,
)
from engine.civilian import create_enterprise
from engine.business import configure_enterprise_business
from engine.underworld import create_underworld_organization, update_underworld_organization, maybe_deepen_gang_structure, ensure_underworld_membership_profile, derive_gang_opening_membership
from engine.role_experience import _underworld
from engine.simulation import SimEvent, log_event


def bootstrap(path='/tmp/caerness_v059.db'):
    os.environ['CAERNESS_DB_PATH']=path
    reset_db(force=True); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c)
    return c


def actor(c,name,loc='Wrenfield seat district',subtype='test professional'):
    lid=int(c.execute('select id from locations where name=?',(loc,)).fetchone()[0])
    cur=c.execute("insert into actors(name,actor_type,subtype,status,current_location_id,home_location_id) values (?,?,?,'active',?,?)",(name,'character',subtype,lid,lid))
    aid=int(cur.lastrowid)
    c.execute("insert into actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) values (?,?,'adult',1,'living',0,'{}')",(aid,-30*365))
    c.execute("insert into actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) values (?,?,?,?,?,?,?)",(aid,.4,.5,.7,.8,.7,.65))
    return aid


def cultivation(c,aid,stage='Third'):
    c.execute("insert into cultivation_profiles(actor_id,core_state,current_stage,active,status,vessel_adaptation,realization_integration,training_effort,resource_access,teacher_support,injury_constraint,last_review_day,next_review_day,metadata_json,core_capacity,current_reserve,sediment_burden) values (?,?,?,1,'active',90,65,60,60,60,0,0,30,'{}',100,60,0)",(aid,'Open-Core',stage))


def run():
    assert ENGINE_VERSION=='0.59.0'
    c=bootstrap()

    # Third-stage junior disciple: Stage widens responsibilities, but does not force standing advancement.
    a=actor(c,'[TEST] Career Reach Disciple',subtype='martial disciple')
    w=int(c.execute("select id from actors where name='Wrenfield Sect'").fetchone()[0])
    c.execute("insert into institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json,metadata_json) values (?,?, 'member','ordinary junior spear disciple','active',0,'[]','{}')",(w,a))
    cultivation(c,a,'Third')
    ctx=c.execute("select im.*,ia.name institution_name from institution_memberships im join actors ia on ia.id=im.institution_actor_id where im.member_actor_id=?",(a,)).fetchone()
    st=ensure_role_career(c,a,'martial_institution',ctx); assert st['stage_key']=='junior'
    for _ in range(7): note_role_event(c,a,'martial_institution',ctx)
    # Assistant teaching and patrol leadership are independently possible while still Junior.
    ok,reasons,_=_responsibility_eligibility(c,a,'martial_institution','assistant_instructor',7,'junior')
    assert ok and any('Third-stage' in x for x in reasons)
    ok2,_,_=_responsibility_eligibility(c,a,'martial_institution','patrol_lead',7,'junior')
    assert ok2
    assert career_state(c,a,'martial_institution',ctx)['stage_key']=='junior'
    assert career_responsibilities(c,a,'martial_institution',ctx)==set()
    # Standing itself is separately eligible; neither responsibility nor standing is automatic.
    ok3,_,_=_eligibility(c,a,'martial_institution','junior','established',7)
    assert ok3

    # Wealth can open larger commercial responsibilities while formal commercial standing remains local-scale.
    m=actor(c,'[TEST] Growing Merchant',loc='Saltmere',subtype='independent merchant')
    eid=create_enterprise(c,'[TEST] Growing Concern','merchant_house',owner_actor_id=m,location_id=int(c.execute("select id from locations where name='Saltmere'").fetchone()[0]),capital=40,cash=170,debt=4,reputation=61,admin_quality=60,labor_capacity=50,risk_tolerance=55)
    configure_enterprise_business(c,eid,'wholesaler',capacity=40)
    mst=ensure_role_career(c,m,'merchant',c.execute('select * from civilian_enterprises where id=?',(eid,)).fetchone()); assert mst['stage_key']=='small_operator'
    for _ in range(8): note_role_event(c,m,'merchant')
    ok,reasons,_=_responsibility_eligibility(c,m,'merchant','factor_coordinator',8,'small_operator')
    assert ok and any('business resources' in x for x in reasons)
    ok,_,_=_responsibility_eligibility(c,m,'merchant','regional_contractor',8,'small_operator')
    assert ok
    assert career_state(c,m,'merchant')['stage_key']=='small_operator'

    # Retainer specialization is not equivalent to hierarchy: horse expertise can open without captaincy.
    r=actor(c,'[TEST] Horse Retainer',loc='Northwatch',subtype='estate retainer')
    cultivation(c,r,'Temper')
    c.execute("insert into resources(actor_id,resource_type,amount,unit,updated_day) values (?,?,?,'index',0)",(r,'horse_access',14))
    ensure_role_career(c,r,'retainer')
    for _ in range(5): note_role_event(c,r,'retainer')
    ok,_,_=_responsibility_eligibility(c,r,'retainer','horsemaster',5,'retainer')
    assert ok
    ok_captain,_,_=_responsibility_eligibility(c,r,'retainer','retainer_captain',5,'retainer')
    assert not ok_captain

    # Opening gang scale is resolved from operational footprint, not from a universal 'small gang'
    # headcount.  This specific ward-level footprint (front + two recurring rackets + enforcement
    # + targeted-violence capacity) should resolve into personnel in the tens, with material seed
    # variation. Tiny 4-10 person crews remain possible under a lighter footprint elsewhere.
    import random
    openings=[]
    for seed in (101,202,303,404,505,606):
        x=derive_gang_opening_membership(random.Random(seed),racket_breadth=24,territorial_presence=22,front_depth=28,violence_capacity=28,command_depth=2,recurring_rackets=2,has_operating_front=True,can_mount_group_violence=True,can_commission_targeted_killing=True)
        openings.append(int(x['full_members']))
    assert min(openings)>=20 and max(openings)-min(openings)>=8 and len(set(openings))>=4, openings

    # Underworld organization form is not a career rank. A gang can become large and layered while remaining a gang.
    g=actor(c,'[TEST] Independent Gang Boss',loc='Aldergate',subtype='boss of an independent gang')
    gloc=int(c.execute("select id from locations where name='Aldergate'").fetchone()[0])
    ge=create_enterprise(c,'[TEST] Gang Cartage Yard','service',owner_actor_id=g,location_id=gloc,capital=20,cash=35,debt=0,reputation=50,admin_quality=50,labor_capacity=40,risk_tolerance=70,metadata={'front_for_minor_crew':True})
    oid=create_underworld_organization(c,'test-independent-gang','gang',founder_actor_id=g,anchor_enterprise_id=ge,primary_location_id=gloc,member_count_estimate=8,command_depth=1,territorial_presence=15,racket_breadth=20,front_depth=20,reputation_deterrence=15,violence_capacity=20,cohesion=60,membership_stability=55)
    update_underworld_organization(c,oid,member_delta=32,dimension_deltas={'racket_breadth':40,'territorial_presence':40,'reputation_deterrence':45,'violence_capacity':35,'cohesion':5})
    grown=maybe_deepen_gang_structure(c,oid)
    assert grown['organization_type']=='gang' and grown['command_depth']>=3 and float(grown['member_count_estimate'])>=40
    # Recruitment has no old small-gang ceiling: a 40-member gang can still make a deliberate
    # recruitment push if its money/organization supports it. This guards against silently
    # preserving the earlier 8->12 calibration or the superseded member_count<18 gate.
    ensure_underworld_membership_profile(c,oid,core_members=12,active_members=28,peripheral_associates=4)
    c.execute('update civilian_enterprises set cash=260 where id=?',(ge,))
    c.execute('update actor_drives set ambition=.85 where actor_id=?',(g,))
    class LowRng:
        def random(self): return 0.0
        def randrange(self,n): return 0
    def elog(**kw):
        return log_event(c,SimEvent(
            day=kw['day'],event_type=kw['event_type'],title=kw['title'],summary=kw['summary'],
            severity=kw.get('severity',1),source_actor_id=kw.get('source_actor_id'),
            target_actor_ids=tuple(kw.get('target_actor_ids') or ()),location_id=kw.get('location_id'),
            visibility=kw.get('visibility'),secrecy=kw.get('secrecy'),rumorability=kw.get('rumorability'),reliability=kw.get('reliability')))
    ent=c.execute('select * from civilian_enterprises where id=?',(ge,)).fetchone()
    before=c.execute('select peripheral_associates from underworld_membership_profiles where organization_id=?',(oid,)).fetchone()[0]
    _underworld(c,g,ent,LowRng(),elog)
    after=c.execute('select peripheral_associates from underworld_membership_profiles where organization_id=?',(oid,)).fetchone()[0]
    assert after > before
    assert c.execute("select organization_type from underworld_organizations where id=?",(oid,)).fetchone()[0]=='gang'

    # A smaller Mafia-style family is still a different form, not a lower/higher score on the same ladder.
    mid=create_underworld_organization(c,'test-mafia-family','mafia_family',name='[TEST] Family',primary_location_id=gloc,member_count_estimate=18,command_depth=3,territorial_presence=20,racket_breadth=35,front_depth=45,corrupt_access=40,reputation_deterrence=35,violence_capacity=25,cohesion=70,membership_stability=80,succession_depth=65)
    maf=c.execute('select * from underworld_organizations where id=?',(mid,)).fetchone()
    assert maf['organization_type']=='mafia_family' and float(maf['member_count_estimate']) < float(grown['member_count_estimate'])
    # There is no underworld career track to auto-promote the gang boss into another organization type.
    assert c.execute("select count(*) from actor_careers where actor_id=?",(g,)).fetchone()[0]==0

    # A quiet service worker can remain in place even while individual supervisory roles become possible later.
    wkr=actor(c,'[TEST] Parish Worker',loc='Eldenfell',subtype='Witness parish clerk')
    c.execute("insert into resources(actor_id,resource_type,amount,unit,updated_day) values (?,?,?,'index',0)",(wkr,'local_trust',18))
    ensure_role_career(c,wkr,'witness')
    ok,_,_=_eligibility(c,wkr,'witness','parish_worker','trusted_worker',0)
    assert not ok
    ok,_,_=_responsibility_eligibility(c,wkr,'witness','records_supervisor',0,'parish_worker')
    assert not ok

    c.close()
    print('v0.59 flexible career/reach regression PASS: standing and branching responsibilities are independent')

if __name__=='__main__': run()
