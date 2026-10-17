from __future__ import annotations
import os, sys, tempfile, random
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.underworld import create_underworld_organization
from engine.underworld_rebuild import (
    city_underworld_snapshot, organization_snapshot, ensure_organization_culture,
    create_personnel, create_crew, create_zone, set_zone_controller, protect_business,
    grant_operating_permission, attempt_local_activity, ensure_organization_leader,
    collect_monthly_income, make_tributary, make_truce, absorb_organization, ensure_crew_leadership, ensure_zone_staffing, resolve_defeated_organization, reconcile_crews_to_membership,
)
from engine.civilian import create_enterprise
from engine.household_life import mark_actor_deceased


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_v060_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path)
    os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db()
    c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=59
    c=bootstrap()
    # Gap 4a: the World Bible outfits are re-adopted at their canon places, no longer quarry.
    for name in ('Tallow Family','Greyhook Wharf Company','Saltwake Combine'):
        r=c.execute("select id,status from actors where name=?",(name,)).fetchone()
        if r:
            assert r['status']=='active', (name,r['status'])
            assert not c.execute('select 1 from underworld_rebuild_quarry where actor_id=?',(int(r['id']),)).fetchone()
    # Current World Bible independently retains these institutions/ecologies; anti-grandfathering
    # targets the old city-assigned criminal organizations, not all older underworld-adjacent facts.
    for name in ('Painted Veil','The Hush','The Reckoning','Cormorants','Red Board'):
        row=c.execute("select id,status from actors where name=?",(name,)).fetchone()
        if row:
            assert row['status']!='retired', (name,row['status'])
            assert not c.execute('select 1 from underworld_rebuild_quarry where actor_id=?',(int(row['id']),)).fetchone(), name

    alder=int(c.execute("select id from locations where name='Aldergate'").fetchone()[0])
    snap=city_underworld_snapshot(c,alder)
    assert snap['zones']==10, snap  # canon-shaped Aldergate: money and paperwork, few street gangs
    assert snap['organizations']>=8 and 1<=snap['forms'].get('gang',0)<=3, snap
    assert snap['crews']>=snap['organizations']-1, snap  # Tallow holds fronts, not crews, until it needs them
    assert snap['rackets']>=snap['organizations'], snap
    assert snap['crew_manpower_estimate']>0 and snap['open_core_manpower_estimate']>0
    overall=snap['open_core_manpower_estimate']/snap['crew_manpower_estimate']
    command=snap['open_core_command_figures']/max(1,snap['command_figures'])
    assert overall < .22, (overall,snap)
    assert command > .70 and command > overall*3, (command,overall,snap)

    # Gang/Mafia/dynasty are forms, not ranks; culture derives from institutional grammar.
    gid=int(c.execute("select id from underworld_organizations where primary_location_id=? and organization_type='gang' order by id limit 1",(alder,)).fetchone()[0])
    gs=organization_snapshot(c,gid); assert gs['form']=='gang' and gs['culture']['membership_model']=='fluid'
    mafia=create_underworld_organization(c,'test-v060-mafia','mafia_family',name='Test Sworn Family',primary_location_id=alder,member_count_estimate=45,command_depth=2)
    mc=ensure_organization_culture(c,mafia,rng=random.Random(100)); assert mc['membership_model']=='sworn' and int(mc['induction_required'])==1
    dyn=create_underworld_organization(c,'test-v060-dynasty','criminal_dynasty',name='Test Blood House',primary_location_id=alder,member_count_estimate=45,command_depth=2)
    dc=ensure_organization_culture(c,dyn,rng=random.Random(101)); assert dc['membership_model']=='blood_household' and float(dc['hereditary_headship_preference'])>=80

    # Territorial sovereignty: rival protection is an encroachment, not a second stable account.
    zone=c.execute("""select z.id,c.organization_id from underworld_zones z join underworld_zone_claims c on c.zone_id=z.id
                      where z.city_location_id=? and c.claim_kind='controller' and c.status='active' order by z.id limit 1""",(alder,)).fetchone()
    zid,controller=int(zone['id']),int(zone['organization_id'])
    ent=create_enterprise(c,'[TEST] Sovereignty Tavern','service',location_id=alder,capital=8,cash=3,reputation=45,admin_quality=45,labor_capacity=35,risk_tolerance=50)
    a=protect_business(c,controller,ent,zid,payment_per_30=1); assert a['created']
    rival=int(c.execute("select id from underworld_organizations where primary_location_id=? and id<>? and status='active' order by id limit 1",(alder,controller)).fetchone()[0])
    b=protect_business(c,rival,ent,zid,payment_per_30=1.2); assert not b['created'] and b['disputed']
    assert int(c.execute("select count(*) from underworld_protection_accounts where enterprise_id=? and status='active'",(ent,)).fetchone()[0])==1
    assert c.execute("select 1 from underworld_incidents where incident_kind='protection_poach' and source_organization_id=? and target_organization_id=?",(rival,controller)).fetchone()
    # Explicit permission makes an otherwise territorial activity legitimate within the underworld arrangement.
    grant_operating_permission(c,zid,controller,rival,'street_gambling',tribute_rate=.15)
    assert attempt_local_activity(c,zid,rival,'street_gambling')['authorized'] is True
    assert attempt_local_activity(c,zid,rival,'patrol')['authorized'] is False

    # Sworn-family succession must select a sworn member, not merely the strongest outsider.
    boss=create_personnel(c,mafia,role_kind='boss',membership_status='sworn_member',rng=random.Random(4))
    crew=create_crew(c,mafia,'Test Mafia Crew',home_zone_id=None,size_estimate=20,rng=random.Random(5))
    sworn=create_personnel(c,mafia,role_kind='lieutenant',crew_id=crew,membership_status='sworn_member',rng=random.Random(6))
    outsider=create_personnel(c,mafia,role_kind='lieutenant',crew_id=crew,membership_status='member',rng=random.Random(7))
    c.execute('update underworld_personnel set authority=99 where actor_id=?',(outsider,))
    mark_actor_deceased(c,boss,reason='test death'); c.execute("update underworld_personnel set status='dead' where actor_id=?",(boss,))
    successor=ensure_organization_leader(c,mafia,random.Random(8)); assert successor==sworn, (successor,sworn,outsider)


    # Command vacancies crystallize replacements from the existing organization rather than leaving leaderless counters.
    gang_crew=int(c.execute("select id from underworld_crews where organization_id=? order by id limit 1",(gid,)).fetchone()[0])
    old_leader=c.execute("select leader_actor_id from underworld_crews where id=?",(gang_crew,)).fetchone()[0]
    if old_leader is not None:
        mark_actor_deceased(c,int(old_leader),reason='test crew leader death'); c.execute("update underworld_personnel set status='dead' where actor_id=?",(int(old_leader),))
    repaired=ensure_crew_leadership(c,gid,rng=random.Random(19)); assert repaired>=1
    new_leader=c.execute("select leader_actor_id from underworld_crews where id=?",(gang_crew,)).fetchone()[0]
    assert new_leader is not None and new_leader!=old_leader

    # Absorption transfers concrete assets while preserving the winner's form. Conquered outsiders
    # are not magically sworn into a Mafia family.
    loser=create_underworld_organization(c,'test-v060-loser','gang',name='Test Loser Gang',primary_location_id=alder,member_count_estimate=12,command_depth=1)
    ensure_organization_culture(c,loser,rng=random.Random(22))
    lb=create_personnel(c,loser,role_kind='boss',membership_status='member',rng=random.Random(23))
    lc=create_crew(c,loser,'Loser Crew',size_estimate=12,rng=random.Random(24))
    c.execute("insert into underworld_membership_profiles(organization_id,core_members,active_members,peripheral_associates,lifetime_entries,lifetime_exits,last_review_day,metadata_json) values (?,?,?,?,0,0,0,'{}')",(loser,4,8,3))
    az=create_zone(c,alder,'test-absorb-zone','Test Absorb Zone'); set_zone_controller(c,az,loser)
    before_form=organization_snapshot(c,mafia)['form']
    absorb_organization(c,mafia,loser)
    assert organization_snapshot(c,mafia)['form']==before_form=='mafia_family'
    assert c.execute("select status from underworld_organizations where id=?",(loser,)).fetchone()[0]=='merged'
    assert c.execute("select membership_status from underworld_personnel where actor_id=?",(lb,)).fetchone()[0]=='associate'
    assert int(zone_controller:=c.execute("select organization_id from underworld_zone_claims where zone_id=? and claim_kind='controller' and status='active'",(az,)).fetchone()[0])==mafia

    # Territory consumes real crew capacity; staffing repair never creates phantom size out of nothing.
    crew_total_before=float(c.execute("select coalesce(sum(size_estimate),0) from underworld_crews where organization_id=? and status='active'",(gid,)).fetchone()[0])
    staffing=ensure_zone_staffing(c,gid,rng=random.Random(31))
    crew_total_after=float(c.execute("select coalesce(sum(size_estimate),0) from underworld_crews where organization_id=? and status='active'",(gid,)).fetchone()[0])
    assert abs(crew_total_before-crew_total_after)<1e-6, (crew_total_before,crew_total_after,staffing)

    # Aggregate membership changes must become concrete crew manpower and command structure.
    prof=c.execute("select * from underworld_membership_profiles where organization_id=?",(gid,)).fetchone()
    c.execute("update underworld_membership_profiles set active_members=active_members+35 where organization_id=?",(gid,))
    c.execute("update underworld_organizations set member_count_estimate=member_count_estimate+35 where id=?",(gid,))
    rec=reconcile_crews_to_membership(c,gid,rng=random.Random(41))
    full=float(c.execute("select core_members+active_members from underworld_membership_profiles where organization_id=?",(gid,)).fetchone()[0])
    crew=float(c.execute("select coalesce(sum(size_estimate),0) from underworld_crews where organization_id=? and status='active'",(gid,)).fetchone()[0])
    assert abs(full-crew)<1e-6, (full,crew,rec)

    # Money is kicked upward from concrete rackets/protection; central treasury does not salary every member.
    c.execute('update underworld_organizations set treasury=0 where id=?',(controller,))
    before=float(c.execute('select treasury from underworld_organizations where id=?',(controller,)).fetchone()[0])
    cash=collect_monthly_income(c,controller)
    after=float(c.execute('select treasury from underworld_organizations where id=?',(controller,)).fetchone()[0])
    assert cash['gross']>=0 and after>=before
    assert c.execute("select 1 from underworld_finance_transactions where organization_id=? and transaction_kind='criminal_income_kickup'",(controller,)).fetchone()

    c.commit(); c.close(); print('v0.60 underworld rebuild tests: PASS')

if __name__=='__main__': run()
