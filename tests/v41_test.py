from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.ecology import add_route,add_route_condition
from engine.combat import create_battle,add_battle_side,add_battle_unit
from engine.war import configure_military_logistics_profile,register_campaign_for_battle,process_due_war
from engine.coverage import snapshot_coverage

def run():
    assert ENGINE_VERSION in {'0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=41
    reset_db();init_db()
    with connect() as c:
        src=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('War Supply City','city',0)").lastrowid)
        mid=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('War Pass','pass',0)").lastrowid)
        front=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('War Front','fort',0)").lastrowid)
        r1=add_route(c,src,mid,route_kind='road',base_days=2,reliability=90);r2=add_route(c,mid,front,route_kind='road',base_days=2,reliability=90)
        inst=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES ('Fixture Polity','institution',?,'active')",(src,)).lastrowid)
        c.execute("INSERT INTO institution_profiles(actor_id,institution_kind) VALUES (?,'state')",(inst,))
        pid=int(c.execute("INSERT INTO political_polities(institution_actor_id,polity_kind,military_capacity,administrative_capacity,status,next_review_day) VALUES (?,'test polity',60,60,'active',30)",(inst,)).lastrowid)
        configure_military_logistics_profile(c,pid,source_location_id=src,food_fodder_capacity=70,medical_capacity=65,equipment_capacity=65,elixir_reserve_capacity=40,transport_capacity=70,readiness=70,metadata={'authority':'TEST'})
        # Peace readiness is populated but does not manufacture a campaign.
        out=process_due_war(c,30);assert out['campaigns_created']==0 and c.execute("SELECT COUNT(*) FROM military_campaigns").fetchone()[0]==0
        # A tournament/duel cannot become a military campaign.
        c.execute("INSERT INTO combat_engagements(engagement_kind,title,location_id,status,phase,round_index,day_started) VALUES ('duel','Fixture Duel',?,'active','opening',0,30)",(front,))
        process_due_war(c,30);assert c.execute("SELECT COUNT(*) FROM military_campaigns").fetchone()[0]==0
        # A real battle creates campaign logistics. Side metadata identifies polity and cultivated share.
        c.execute("UPDATE world_state SET current_day=31 WHERE id=1")
        battle=create_battle(c,'Fixture Border Battle',location_id=front,metadata={'cause':'test'})
        side=add_battle_side(c,battle,'Fixture Side',logistics=70,reserve_capacity=60,metadata={'polity_id':pid,'cultivated_share':0.5})
        foe=add_battle_side(c,battle,'Opponent',logistics=70,reserve_capacity=50,metadata={'cultivated_share':0.0})
        add_battle_unit(c,side,'Fixture Line',readiness=80,fatigue=10);add_battle_unit(c,foe,'Opponent Line',readiness=80,fatigue=10)
        cid=register_campaign_for_battle(c,battle)
        sl=c.execute("SELECT * FROM campaign_side_logistics WHERE battle_side_id=?",(side,)).fetchone(); assert sl and float(sl['elixir_reserve'])==40
        # One active review consumes ordinary supply and some elixir only because this force has cultivated share.
        c.execute("UPDATE world_state SET current_day=38 WHERE id=1");process_due_war(c,38)
        sl2=c.execute("SELECT * FROM campaign_side_logistics WHERE battle_side_id=?",(side,)).fetchone()
        assert float(sl2['food_fodder'])<float(sl['food_fodder']) and float(sl2['elixir_reserve'])<float(sl['elixir_reserve'])
        foe_sl=c.execute("SELECT * FROM campaign_side_logistics WHERE battle_side_id=?",(foe,)).fetchone(); assert float(foe_sl['elixir_reserve'])==25.0
        # Close the sole route chain: no teleporting supply; shortage degrades logistics/readiness, never Stage/office.
        add_route_condition(c,r2,'closure','front road cut',39,end_day=60,accessibility=0,delay_factor=1,hazard_pressure=0)
        before_ready=float(c.execute("SELECT readiness FROM battle_units WHERE side_id=?",(side,)).fetchone()[0])
        c.execute("UPDATE world_state SET current_day=45 WHERE id=1");process_due_war(c,45)
        sl3=c.execute("SELECT * FROM campaign_side_logistics WHERE battle_side_id=?",(side,)).fetchone(); assert float(sl3['route_access'])==0 and float(sl3['shortage_pressure'])>0
        after_ready=float(c.execute("SELECT readiness FROM battle_units WHERE side_id=?",(side,)).fetchone()[0]); assert after_ready<before_ready
        # Resolution enters an aftermath interval, not instant normality.
        c.execute("UPDATE combat_engagements SET status='resolved',phase='aftermath',day_ended=46,outcome_json='{}' WHERE id=?",(battle,))
        c.execute("UPDATE world_state SET current_day=52 WHERE id=1");process_due_war(c,52)
        camp=c.execute("SELECT * FROM military_campaigns WHERE id=?",(cid,)).fetchone(); assert camp['status']=='aftermath' and int(camp['next_review_day'])>52
        assert c.execute("SELECT COUNT(*) FROM war_logistics_events WHERE campaign_id=? AND event_kind='demobilization_started'",(cid,)).fetchone()[0]==1
        # Aftermath later closes and polity readiness remains carrying burden through recovery.
        c.execute("UPDATE world_state SET current_day=? WHERE id=1",(int(camp['next_review_day']),));process_due_war(c,int(camp['next_review_day']))
        assert c.execute("SELECT status FROM military_campaigns WHERE id=?",(cid,)).fetchone()[0]=='closed'
        assert c.execute("SELECT status FROM military_logistics_profiles WHERE polity_id=?",(pid,)).fetchone()[0]=='recovering'
        cov={x['domain_key']:x for x in snapshot_coverage(c,None,phase='v41-test')}
        assert cov['47_war_logistics']['mechanism_status']=='RUNNABLE' and cov['47_war_logistics']['populated_count']>=1,cov['47_war_logistics']
        c.commit()
    print('v0.41.0 war logistics / aftermath regression PASS')
if __name__=='__main__':run()
