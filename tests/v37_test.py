from __future__ import annotations

import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.civilian import ensure_good,create_enterprise,add_shadow_link
from engine.ecology import add_route
from engine.underworld import (
    activate_underworld_substrate, arrange_smuggling_operation, mark_smuggling_detected,
    process_due_underworld,
)
from engine.coverage import snapshot_coverage
from engine.resolution_controller import crystallize_institution_candidate


def _institution(c,name,kind):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'institution','active')",(name,)).lastrowid)
    c.execute("INSERT INTO institution_profiles(actor_id,institution_kind) VALUES (?,?)",(aid,kind))
    return aid


def _set_day(c,day):
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(day,))


def _conserved(c,enterprise_id,good_id):
    stock=float(c.execute("SELECT COALESCE(SUM(quantity),0) FROM commercial_stock WHERE enterprise_id=? AND good_id=?",(enterprise_id,good_id)).fetchone()[0])
    cargo=float(c.execute("SELECT COALESCE(SUM(quantity),0) FROM smuggling_operations WHERE enterprise_id=? AND good_id=? AND status IN ('in_transit','stalled')",(enterprise_id,good_id)).fetchone()[0])
    return round(stock+cargo,6)


def run():
    assert ENGINE_VERSION in {'0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'} and SCHEMA_VERSION>=37
    reset_db(); init_db()
    with connect() as c:
        loc={}
        for name in ['Toll’s Reach','Cairnholt','Aldergate']:
            loc[name]=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES (?,'city',1)",(name,)).lastrowid)
        r1=add_route(c,loc['Toll’s Reach'],loc['Cairnholt'],base_days=2,reliability=90)
        r2=add_route(c,loc['Cairnholt'],loc['Aldergate'],base_days=2,reliability=90)
        tallow=_institution(c,'Tallow Family','criminal dynasty')
        greyhook=_institution(c,'Greyhook Wharf Company','smuggling power')
        cloth=ensure_good(c,'ordinary-cloth','Ordinary Cloth','ordinary_goods',1.0)
        before_actors=int(c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])

        a1=activate_underworld_substrate(c); a2=activate_underworld_substrate(c)
        assert a1['underworld_profiles']==2 and a2['underworld_fronts_created']==0,(a1,a2)
        assert int(c.execute("SELECT current_location_id FROM actors WHERE id=?",(tallow,)).fetchone()[0])==loc['Aldergate']
        assert int(c.execute("SELECT current_location_id FROM actors WHERE id=?",(greyhook,)).fetchone()[0])==loc['Toll’s Reach']
        assert int(c.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id IN (?,?)",(tallow,greyhook)).fetchone()[0])==0, 'activation must not invent bosses/members'
        assert int(c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])==before_actors
        assert int(c.execute("SELECT COUNT(*) FROM law_enforcement_profiles WHERE status='active'").fetchone()[0])==3

        ge=c.execute("SELECT * FROM civilian_enterprises WHERE institution_actor_id=? AND (json_extract(metadata_json,'$.underworld_activation_key')='v037-greyhook-front' OR json_extract(metadata_json,'$.activation_key')='v037-greyhook-front')",(greyhook,)).fetchone(); assert ge
        initial=_conserved(c,int(ge['id']),cloth); assert initial==12.0,initial

        # Conservation + idempotency: dispatch removes stock once, duplicate operation key cannot remove it twice.
        op=arrange_smuggling_operation(c,int(ge['id']),cloth,3.0,loc['Aldergate'],organizer_institution_actor_id=greyhook,concealment=100,operation_key='test-conserved')
        assert _conserved(c,int(ge['id']),cloth)==12.0
        op2=arrange_smuggling_operation(c,int(ge['id']),cloth,3.0,loc['Aldergate'],organizer_institution_actor_id=greyhook,concealment=100,operation_key='test-conserved')
        assert op2==op and _conserved(c,int(ge['id']),cloth)==12.0

        # A route closed after dispatch stalls the cargo rather than teleporting it through the edge.
        row=c.execute("SELECT * FROM smuggling_operations WHERE id=?",(op,)).fetchone(); due=int(row['segment_due_day']); route=int(row['current_route_id'])
        c.execute("UPDATE travel_routes SET status='closed' WHERE id=?",(route,)); _set_day(c,due)
        process_due_underworld(c,due)
        stalled=c.execute("SELECT * FROM smuggling_operations WHERE id=?",(op,)).fetchone(); assert stalled['status']=='stalled' and int(stalled['current_location_id'])==loc['Toll’s Reach']
        assert _conserved(c,int(ge['id']),cloth)==12.0
        c.execute("UPDATE travel_routes SET status='open' WHERE id=?",(route,))
        # Resume and traverse every leg. Detection, if any, must not destroy cargo.
        for _ in range(10):
            row=c.execute("SELECT * FROM smuggling_operations WHERE id=?",(op,)).fetchone()
            if row['status']=='delivered': break
            nd=int(row['next_review_day']); _set_day(c,nd); process_due_underworld(c,nd)
        row=c.execute("SELECT * FROM smuggling_operations WHERE id=?",(op,)).fetchone(); assert row['status']=='delivered',dict(row)
        assert _conserved(c,int(ge['id']),cloth)==12.0
        assert float(c.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(int(ge['id']),loc['Aldergate'],cloth)).fetchone()[0])>=3.0

        # Hidden criminal truth alone is not police knowledge. Sustained multi-kind evidence may form an org candidate.
        indie=create_enterprise(c,'Ordinary Carriers','service',location_id=loc['Aldergate'],capital=35,cash=20,metadata={'test':'v37'})
        s1=add_shadow_link(c,'enterprise',indie,'smuggling_risk',pressure=65,exposure=10,notes='v37-test-sustained')
        s2=add_shadow_link(c,'enterprise',indie,'corrupt_access',pressure=55,exposure=12,notes='v37-test-sustained')
        c.execute("UPDATE shadow_market_links SET status='active' WHERE id IN (?,?)",(s1,s2))
        # Prevent the canonical Greyhook autonomous calibration from adding noise to this candidate test.
        prof=json.loads(c.execute("SELECT metadata_json FROM underworld_institution_profiles WHERE institution_actor_id=?",(greyhook,)).fetchone()[0]); prof['last_smuggling_dispatch_day']=30
        c.execute("UPDATE underworld_institution_profiles SET metadata_json=? WHERE institution_actor_id=?",(json.dumps(prof,sort_keys=True),greyhook))
        _set_day(c,30); p30=process_due_underworld(c,30)
        assert not c.execute("SELECT 1 FROM emergent_institution_candidates WHERE enterprise_id=?",(indie,)).fetchone(), 'a fresh evidence snapshot is not yet durable organization formation'
        assert not c.execute("SELECT 1 FROM law_enforcement_cases WHERE subject_kind='enterprise' AND subject_id=?",(indie,)).fetchone(), 'hidden evidence must not create an omniscient police case'
        _set_day(c,60); p60=process_due_underworld(c,60)
        cand=c.execute("SELECT * FROM emergent_institution_candidates WHERE enterprise_id=? AND candidate_kind='criminal organization'",(indie,)).fetchone(); assert cand and cand['status']=='forming',p60
        _set_day(c,90); process_due_underworld(c,90)
        cand=c.execute("SELECT * FROM emergent_institution_candidates WHERE id=?",(cand['id'],)).fetchone(); assert cand['status']=='eligible',dict(cand)
        try:
            crystallize_institution_candidate(c,int(cand['id']))
            raise AssertionError('unnamed candidate must not auto-crystallize')
        except ValueError as e:
            assert 'name' in str(e).lower()
        assert int(c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])==before_actors, 'formation should remain candidate resolution until grounded identity exists'

        # Exposure creates local knowledge and therefore a local case; another city's police do not know automatically.
        c.execute("UPDATE shadow_market_links SET status='exposed',exposure=92 WHERE id=?",(s1,))
        _set_day(c,91); process_due_underworld(c,91)
        cases=c.execute("SELECT c.*,p.location_id FROM law_enforcement_cases c JOIN law_enforcement_profiles p ON p.id=c.profile_id WHERE c.subject_kind='enterprise' AND c.subject_id=?",(indie,)).fetchall()
        assert len(cases)==1 and int(cases[0]['location_id'])==loc['Aldergate'],[dict(x) for x in cases]

        # Explicitly detected smuggling opens a case only where detection happened and preserves the cargo record.
        _set_day(c,92)
        opx=arrange_smuggling_operation(c,int(ge['id']),cloth,2.0,loc['Aldergate'],organizer_institution_actor_id=greyhook,concealment=70,operation_key='test-detected')
        mark_smuggling_detected(c,opx,loc['Toll’s Reach'],strength=75,day=92,source='test')
        before_qty=_conserved(c,int(ge['id']),cloth)
        process_due_underworld(c,92)
        scases=c.execute("SELECT c.*,p.location_id FROM law_enforcement_cases c JOIN law_enforcement_profiles p ON p.id=c.profile_id WHERE c.subject_kind='smuggling_operation' AND c.subject_id=?",(opx,)).fetchall()
        assert len(scases)==1 and int(scases[0]['location_id'])==loc['Toll’s Reach']
        assert _conserved(c,int(ge['id']),cloth)==before_qty

        # Corruption can slow a case, but never erase or rewrite the evidence that caused it.
        case_id=int(scases[0]['id']); evidence_before=float(c.execute("SELECT strength FROM underworld_evidence WHERE subject_kind='smuggling_operation' AND subject_id=?",(opx,)).fetchone()[0])
        c.execute("UPDATE law_enforcement_profiles SET corruption_pressure=95 WHERE id=?",(scases[0]['profile_id'],))
        _set_day(c,106); process_due_underworld(c,106)
        score1=float(c.execute("SELECT evidence_score FROM law_enforcement_cases WHERE id=?",(case_id,)).fetchone()[0])
        c.execute("UPDATE law_enforcement_profiles SET corruption_pressure=0 WHERE id=?",(scases[0]['profile_id'],))
        _set_day(c,120); process_due_underworld(c,120)
        score2=float(c.execute("SELECT evidence_score FROM law_enforcement_cases WHERE id=?",(case_id,)).fetchone()[0])
        evidence_after=float(c.execute("SELECT strength FROM underworld_evidence WHERE subject_kind='smuggling_operation' AND subject_id=?",(opx,)).fetchone()[0])
        assert score2>=score1 and evidence_after==evidence_before

        cov={x['domain_key']:x for x in snapshot_coverage(c,None,phase='v37-test')}
        for key in ['37_crime_orgs','38_smuggling','39_policing']:
            assert cov[key]['mechanism_status']=='RUNNABLE' and cov[key]['populated_count']>=1,(key,cov[key])
        assert cov['42_exploitation_medicine']['mechanism_status']==('RUNNABLE' if SCHEMA_VERSION>=40 else 'PARTIAL')
        c.commit()
    print('v0.37.0 underworld-ecology regression PASS')

if __name__=='__main__': run()
