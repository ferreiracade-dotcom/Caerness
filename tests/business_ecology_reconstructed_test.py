from __future__ import annotations
import os,json
os.environ['CAERNESS_TEST_MODE']='1'
os.environ['CAERNESS_DB_PATH']='/tmp/caerness_business_ecology_reconstructed.db'
from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import create_enterprise,_review_latent_commercial_emergence
from engine.business import configure_enterprise_business,resolve_business_cycle,set_commercial_context


def run():
    reset_db(force=True,backup=False);init_db();c=connect();import_current_seed(c);activate_existing_loops(c);c.commit()
    try:
        pop0=int(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0])
        alder=int(c.execute("select id from locations where name='Aldergate'").fetchone()[0])
        set_commercial_context(c,alder,trade_flow=100,foot_traffic=100,traveler_flow=100,credit_demand=100,health_demand=100,craft_demand=100)
        created=0
        for y in range(1,21):
            c.execute('update world_state set current_day=? where id=1',(365*y,))
            r=_review_latent_commercial_emergence(c,365*y);created+=int(r['structural_enterprises_created'])
            if created:break
        assert created>0
        emergent=c.execute("select * from civilian_enterprises where json_extract(metadata_json,'$.emergent_business')=1 order by id desc limit 1").fetchone()
        assert emergent is not None and emergent['owner_actor_id'] is not None
        meta=json.loads(emergent['metadata_json'] or '{}')
        assert meta.get('background_operator_actor_id')==int(emergent['owner_actor_id'])
        assert meta.get('institutional_form')=='ordinary_firm' and meta.get('latent_owner_entity_id') is None
        assert int(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0])==pop0
        assert c.execute('select 1 from person_resolution_provenance where actor_id=?',(int(emergent['owner_actor_id']),)).fetchone()

        # Persistent insolvency closes a firm without deleting its accounting history.
        base_day=int(c.execute('select current_day from world_state where id=1').fetchone()[0])
        eid=create_enterprise(c,'[TEST] Insolvency Firm','other',location_id=alder,capital=0,cash=0,debt=100,reputation=30,admin_quality=30,labor_capacity=20,risk_tolerance=50)
        configure_enterprise_business(c,eid,'food_shop',quality=30,capacity=30,clientele_fit=20,service_reliability=30)
        for offset in (30,60,90,120,150,180,210,240):
            day=base_day+offset
            c.execute('update world_state set current_day=? where id=1',(day,)); resolve_business_cycle(c,eid,day)
            if c.execute('select status from civilian_enterprises where id=?',(eid,)).fetchone()[0]=='closed':break
        e=c.execute('select status from civilian_enterprises where id=?',(eid,)).fetchone(); eco=c.execute('select * from enterprise_ecology_state where enterprise_id=?',(eid,)).fetchone()
        assert e[0]=='closed',e[0]
        assert eco['closure_reason']=='sustained_insolvency' and eco['closed_day'] is not None
        assert c.execute('select count(*) from enterprise_accounts where enterprise_id=?',(eid,)).fetchone()[0]>0
        print('BUSINESS ecology reconstructed PASS',{'emergent_real_operator':int(emergent['owner_actor_id']),'population_delta':0,'insolvency_closed_day':int(eco['closed_day'])})
    finally:c.close()
if __name__=='__main__':run()
