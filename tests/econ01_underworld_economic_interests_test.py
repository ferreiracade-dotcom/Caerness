"""ECON-01 acceptance: explicit economic interests/flows and protection-as-racket."""
from __future__ import annotations
import os, sys, tempfile, random
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.underworld import create_underworld_organization
from engine.civilian import create_enterprise, create_household, add_household_member
from engine.underworld_rebuild import (
    create_zone, set_zone_controller, protect_business, create_racket_site, create_crew,
    create_front, attach_front_use, seize_front, pay_bribe, pay_member_household_support,
    ensure_heat_profile, set_racket_status, absorb_organization,
)


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_econ01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path)
    os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db()
    c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=59
    c=bootstrap()
    alder=int(c.execute("SELECT id FROM locations WHERE name='Aldergate'").fetchone()[0])

    # Firewall correction: current World Bible institutions are not rejected merely for being old.
    for name in ('Painted Veil','The Hush','The Reckoning','Cormorants','Red Board'):
        row=c.execute("SELECT id,status FROM actors WHERE name=? AND actor_type='institution'",(name,)).fetchone()
        if row:
            assert row['status']!='retired', (name,row['status'])
            assert not c.execute("SELECT 1 FROM underworld_rebuild_quarry WHERE actor_id=?",(int(row['id']),)).fetchone(), name

    org=create_underworld_organization(c,'econ01-org','mafia_family',name='ECON-01 Family',primary_location_id=alder,
                                       member_count_estimate=35,command_depth=2)
    c.execute("UPDATE underworld_organizations SET treasury=100 WHERE id=?",(org,))
    z=create_zone(c,alder,'econ01-zone','ECON-01 Ward')
    set_zone_controller(c,z,org)

    # Protection is a racket with multiple account/client rows beneath it.
    e1=create_enterprise(c,'Protection Client A','service',location_id=alder,capital=5,cash=4)
    e2=create_enterprise(c,'Protection Client B','service',location_id=alder,capital=5,cash=4)
    p1=protect_business(c,org,e1,z,payment_per_30=1.0); p2=protect_business(c,org,e2,z,payment_per_30=1.2)
    assert p1['created'] and p2['created'] and p1['racket_id']==p2['racket_id']
    rid=int(p1['racket_id'])
    rr=c.execute("SELECT * FROM underworld_racket_sites WHERE id=?",(rid,)).fetchone()
    assert rr and rr['racket_kind']=='protection collections'
    assert c.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE racket_id=? AND status='active'",(rid,)).fetchone()[0]==2
    # The default one-book-per-org/zone behavior is not a schema uniqueness rule.
    rid2=create_racket_site(c,org,'protection collections',zone_id=z,gross_income_per_30=0,metadata={'second_book_for_test':True})
    assert rid2!=rid

    # Individual/crew operation is separate from organizational affiliation/control.
    operator=int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id LIMIT 1").fetchone()[0])
    debt=create_racket_site(c,org,'high-risk debt',zone_id=z,operator_actor_id=operator,gross_income_per_30=2)
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_actor_id=? AND target_racket_id=? AND interest_kind='operator' AND status='active'",(operator,debt)).fetchone()
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_actor_id=? AND target_racket_id=? AND interest_kind='beneficial_controller' AND status='active'",(operator,debt)).fetchone()
    assert not c.execute("SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_racket_id=? AND interest_kind='beneficial_controller' AND status='active'",(org,debt)).fetchone()
    independent=create_racket_site(c,None,'stolen goods',operator_actor_id=operator,gross_income_per_30=1)
    assert c.execute("SELECT organization_id FROM underworld_racket_sites WHERE id=?",(independent,)).fetchone()[0] is None

    # Front is a criminal use/status, not a synonym for the boss personally owning a business.
    f1=create_front(c,org,'Organization-owned Cover','service',zone_id=z)
    ent1=c.execute("SELECT * FROM civilian_enterprises WHERE id=?",(f1,)).fetchone()
    assert ent1['owner_actor_id'] is None
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_enterprise_id=? AND interest_kind='legal_owner' AND status='active'",(org,f1)).fetchone()

    f2=create_front(c,org,'Actor-owned Controlled Cover','service',zone_id=z,organization_legal_owner=False,legal_owner_actor_id=operator,operator_actor_id=operator)
    link2=c.execute("SELECT id,link_kind FROM underworld_business_links WHERE enterprise_id=? AND status='active'",(f2,)).fetchone()
    assert link2['link_kind']=='controlled_front'
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_actor_id=? AND target_enterprise_id=? AND interest_kind='legal_owner' AND status='active'",(operator,f2)).fetchone()
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_enterprise_id=? AND interest_kind='beneficial_controller' AND status='active'",(org,f2)).fetchone()
    assert seize_front(c,int(link2['id']),reason='test-controlled')
    # Seizing criminal use/control does not automatically destroy someone else's legitimate enterprise.
    assert c.execute("SELECT status FROM civilian_enterprises WHERE id=?",(f2,)).fetchone()[0]=='active'

    # Front-use can attach to an already-existing ordinary enterprise without changing its legal owner.
    existing_eid=create_enterprise(c,'Existing Family Tavern','service',owner_actor_id=operator,location_id=alder,capital=12,cash=4)
    attach_front_use(c,org,existing_eid,zone_id=z,organization_legal_owner=False,legal_owner_actor_id=operator)
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_actor_id=? AND target_enterprise_id=? AND interest_kind='legal_owner' AND status='active'",(operator,existing_eid)).fetchone()
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_organization_id=? AND target_enterprise_id=? AND interest_kind='beneficial_controller' AND status='active'",(org,existing_eid)).fetchone()

    # Multiple protection books may coexist in one org/zone, and callers can target one explicitly.
    crew_id=create_crew(c,org,'ECON-01 Collections Crew',home_zone_id=z,size_estimate=8)
    second_book=create_racket_site(c,org,'protection collections',zone_id=z,gross_income_per_30=0,operator_crew_id=crew_id)
    e3=create_enterprise(c,'Protection Client C','service',location_id=alder,capital=5,cash=4)
    p3=protect_business(c,org,e3,z,payment_per_30=1.4,racket_id=second_book)
    assert int(p3['racket_id'])==second_book
    assert c.execute("SELECT 1 FROM economic_interests WHERE holder_crew_id=? AND target_racket_id=? AND interest_kind='beneficial_controller' AND status='active'",(crew_id,second_book)).fetchone()

    # Treasury money paths are explicit and real.
    bribe_target=int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND id<>? AND status='active' ORDER BY id LIMIT 1",(operator,)).fetchone()[0])
    before=float(c.execute("SELECT treasury FROM underworld_organizations WHERE id=?",(org,)).fetchone()[0])
    cover_before=float(ensure_heat_profile(c,org)['corruption_cover'])
    flow_bribe=pay_bribe(c,org,bribe_target,5)
    after=float(c.execute("SELECT treasury FROM underworld_organizations WHERE id=?",(org,)).fetchone()[0])
    assert abs((before-5)-after)<1e-9
    assert float(ensure_heat_profile(c,org)['corruption_cover'])>cover_before
    assert c.execute("SELECT flow_kind,amount FROM economic_flows WHERE id=?",(flow_bribe,)).fetchone()['flow_kind']=='bribe'

    hh=create_household(c,'Supported Household',head_actor_id=operator,location_id=alder,wealth=2,liquidity=1)
    # create_household already inserts the head membership; add is idempotent enough for test intent.
    before_t=float(c.execute("SELECT treasury FROM underworld_organizations WHERE id=?",(org,)).fetchone()[0])
    before_l=float(c.execute("SELECT liquidity FROM households WHERE id=?",(hh,)).fetchone()[0])
    flow_support=pay_member_household_support(c,org,operator,7,metadata={'reason':'member incapacitated'})
    assert abs(float(c.execute("SELECT treasury FROM underworld_organizations WHERE id=?",(org,)).fetchone()[0])-(before_t-7))<1e-9
    assert abs(float(c.execute("SELECT liquidity FROM households WHERE id=?",(hh,)).fetchone()[0])-(before_l+7))<1e-9
    assert c.execute("SELECT flow_kind,target_household_id FROM economic_flows WHERE id=?",(flow_support,)).fetchone()['target_household_id']==hh

    # Organization absorption transfers protection and racket affiliation together, never creating
    # a winner-side account that still points at the defeated organization's protection book.
    loser=create_underworld_organization(c,'econ01-loser','gang',name='ECON-01 Loser',primary_location_id=alder,member_count_estimate=4,command_depth=1)
    c.execute("UPDATE underworld_organizations SET treasury=5 WHERE id=?",(loser,))
    lz=create_zone(c,alder,'econ01-loser-zone','ECON-01 Loser Ward'); set_zone_controller(c,lz,loser)
    le=create_enterprise(c,'Loser Protected Shop','service',location_id=alder,capital=4,cash=2)
    lp=protect_business(c,loser,le,lz,payment_per_30=1.0); lrid=int(lp['racket_id'])
    absorb_organization(c,org,loser)
    moved=c.execute("SELECT protector_organization_id,racket_id FROM underworld_protection_accounts WHERE enterprise_id=? AND status='active'",(le,)).fetchone()
    assert int(moved['protector_organization_id'])==org and int(moved['racket_id'])==lrid
    assert int(c.execute("SELECT organization_id FROM underworld_racket_sites WHERE id=?",(lrid,)).fetchone()[0])==org

    # Suppressing a protection racket cannot leave its client accounts silently active.
    assert set_racket_status(c,rid,'suppressed')
    assert c.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE racket_id=? AND status='active'",(rid,)).fetchone()[0]==0

    # Every remaining active protection account, including seeded accounts, must have a real parent racket.
    dangling=int(c.execute("SELECT COUNT(*) FROM underworld_protection_accounts WHERE status='active' AND racket_id IS NULL").fetchone()[0])
    assert dangling==0, dangling

    c.commit(); print('ECON-01 underworld economic interests tests: PASS')


if __name__=='__main__':
    run()
