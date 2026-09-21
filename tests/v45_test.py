from __future__ import annotations
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.household_life import create_union
from engine.civilian import process_due_civilian,create_enterprise,_review_latent_commercial_emergence
from engine.business import set_commercial_context,configure_enterprise_business,resolve_business_cycle


def _actor(c,name,loc):
    a=int(c.execute("INSERT INTO actors(name,actor_type,status,current_location_id,home_location_id) VALUES (?,'character','active',?,?)",(name,loc,loc)).lastrowid)
    c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,-10950,'adult',1,'living',0,'{}')",(a,))
    return a

def run():
    assert ENGINE_VERSION in {'0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=45
    reset_db();init_db()
    with connect() as c:
        loc=int(c.execute("INSERT INTO locations(name,kind) VALUES ('Fixture Market','city')").lastrowid)
        a,b,d=_actor(c,'Fixture A',loc),_actor(c,'Fixture B',loc),_actor(c,'Fixture D',loc)
        uid=create_union(c,a,b,create_new_household_name='Fixture Household AB')
        hid=int(c.execute('SELECT household_id FROM household_unions WHERE id=?',(uid,)).fetchone()[0])
        meta=c.execute('SELECT metadata_json FROM households WHERE id=?',(hid,)).fetchone()[0]
        assert 'STRUCTURAL_ONLY' in meta
        # A later accepted proposal cannot create a simultaneous second active union.
        try:
            create_union(c,a,d,create_new_household_name='Bad Duplicate Household')
            raise AssertionError('second active union should have been rejected')
        except ValueError:
            pass
        c.execute('UPDATE world_state SET current_day=30 WHERE id=1')
        process_due_civilian(c,30)
        assert c.execute('SELECT status FROM households WHERE id=?',(hid,)).fetchone()[0]=='active'
        # Operating losses never create negative cash; unfunded costs become generic liabilities.
        eid=create_enterprise(c,'Fixture Loss Firm','merchant_house',location_id=loc,capital=1,cash=0,debt=0)
        set_commercial_context(c,loc,trade_flow=0,foot_traffic=0,traveler_flow=0,security=0,disposable_income=0,credit_demand=0,craft_demand=0,health_demand=0,event_activity=0,elite_patronage=0,cultural_activity=0,military_demand=0,construction_demand=0,reputation_climate=0)
        configure_enterprise_business(c,eid,'wholesaler',capacity=100,quality=1,clientele_fit=1,service_reliability=1,price_position=1)
        c.execute('UPDATE world_state SET current_day=60 WHERE id=1')
        resolve_business_cycle(c,eid,60)
        er=c.execute('SELECT cash,debt,status FROM civilian_enterprises WHERE id=?',(eid,)).fetchone()
        assert float(er['cash'])>=0 and float(er['debt'])>0,dict(er)
        # Latent commercial emergence creates structural businesses without inventing a named adult.
        set_commercial_context(c,loc,trade_flow=99,foot_traffic=95,traveler_flow=95,security=65,disposable_income=70,credit_demand=90,craft_demand=80,health_demand=75)
        created=0
        for year in range(1,11):
            day=365*year;c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,))
            out=_review_latent_commercial_emergence(c,day);created += out['structural_enterprises_created']
        assert created>0
        assert c.execute("SELECT COUNT(*) FROM latent_entities WHERE latent_kind='person' AND archetype='merchant_operator'").fetchone()[0]>0
        assert c.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE json_extract(metadata_json,'$.emergent_business')=1").fetchone()[0]>0
        assert c.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND name LIKE '[STRUCTURAL] %'").fetchone()[0]==0
        c.commit()
    print('v0.45.0 decade integrity / latent commercial emergence regression PASS')
if __name__=='__main__':run()
