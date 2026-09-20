from __future__ import annotations
import json, os, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SOURCE=Path(os.environ.get('CAERNESS_TENYEAR_SOURCE','/mnt/data/caerness_continue/TENYEAR01_working.db'))
OUT=Path(os.environ.get('CAERNESS_TENYEAR_WAR_OUT','/mnt/data/caerness_continue'))
BRANCH=OUT/'TENYEAR01_trigger_war.db'
REPORT=OUT/'TENYEAR01_war_trigger_audit.json'

from engine.db import connect, init_db, ENGINE_VERSION, SCHEMA_VERSION
from engine.simulation import advance_connection,current_day
from engine.war import create_campaign_operation,add_campaign_force,configure_force_supply,link_operation_engagement,attach_force_to_battle_side,process_due_war
from engine.combat import create_battle,add_battle_side,add_battle_unit,resolve_battle_round
from diagnostics.oneyear01_integrated_run import hard_invariants

def main():
    if BRANCH.exists(): BRANCH.unlink()
    shutil.copy2(SOURCE,BRANCH)
    os.environ['CAERNESS_DB_PATH']=str(BRANCH); os.environ['CAERNESS_TEST_MODE']='1'
    init_db(); c=connect(); start=current_day(c)
    attacker_polity,defender_polity=3,1
    commander=int(c.execute('select ruler_actor_id from political_polities where id=?',(attacker_polity,)).fetchone()[0])
    defender_ruler=int(c.execute('select ruler_actor_id from political_polities where id=?',(defender_polity,)).fetchone()[0])
    origin,target=38,15
    route=c.execute("select id from travel_routes where ((from_location_id=? and to_location_id=?) or(from_location_id=? and to_location_id=?)) and status='open' order by id limit 1",(origin,target,target,origin)).fetchone(); assert route
    grain=int(c.execute("select id from market_goods where good_key='ordinary-grain'").fetchone()[0])
    stock=c.execute("select id,quantity from commercial_stock where enterprise_id=6 and location_id=? and good_id=?",(origin,grain)).fetchone(); assert stock and float(stock['quantity'])>=4
    stock_before=float(stock['quantity'])
    warehouse=c.execute('select id,condition from buildings where location_id=? order by id limit 1',(target,)).fetchone(); warehouse_before=float(warehouse['condition']) if warehouse else None
    op=create_campaign_operation(c,'[TENYEAR-TRIGGER] Windmere punitive march',objective_text='Bounded conditional-domain acceptance trigger after peaceful decade.',origin_location_id=origin,target_location_id=target,attacker_polity_id=attacker_polity,defender_polity_id=defender_polity,commander_actor_id=commander,objective_kind='limited',metadata={'manufactured_acceptance_trigger':True,'source':'TENYEAR-01 conditional-domain audit'})
    af=add_campaign_force(c,op,'[TENYEAR-TRIGGER] Windmere field force',personnel=360,polity_id=attacker_polity,current_location_id=origin)
    df=add_campaign_force(c,op,'[TENYEAR-TRIGGER] Toll reserve',personnel=240,polity_id=defender_polity,current_location_id=target)
    configure_force_supply(c,af,grain,supply_kind='food',source_enterprise_id=6,source_location_id=origin,weekly_need=1.2,max_on_hand=4.0,initial_on_hand=4.0)
    c.commit(); advance_connection(c,7); c.commit()
    afrow=c.execute('select * from war_campaign_forces where id=?',(af,)).fetchone(); assert int(afrow['current_location_id'])==target and afrow['status'] in {'deployed','engaged'},dict(afrow)
    stock_after_march=float(c.execute('select quantity from commercial_stock where id=?',(int(stock['id']),)).fetchone()[0])
    battle=create_battle(c,"[TENYEAR-TRIGGER] Toll's Reach engagement",location_id=target,objective='prove WAR-01 activation after naturally peaceful decade',stakes=4,metadata={'manufactured_acceptance_trigger':True})
    aside=add_battle_side(c,battle,'Windmere',controller_actor_id=commander,morale=84,cohesion=82,logistics=76,information_quality=70,reserve_capacity=70,metadata={'polity_id':attacker_polity})
    dside=add_battle_side(c,battle,'Underheaven',controller_actor_id=defender_ruler,morale=40,cohesion=38,logistics=58,information_quality=55,reserve_capacity=40,metadata={'polity_id':defender_polity})
    add_battle_unit(c,aside,'Windmere main',combat_capacity=84,morale=84,cohesion=82,readiness=82)
    add_battle_unit(c,dside,'Toll reserve',combat_capacity=45,morale=42,cohesion=40,readiness=52)
    link_operation_engagement(c,op,battle); attach_force_to_battle_side(c,af,aside); attach_force_to_battle_side(c,df,dside)
    process_due_war(c,current_day(c)); c.commit()
    for _ in range(12):
        eng=c.execute('select * from combat_engagements where id=?',(battle,)).fetchone()
        if eng['status']=='resolved': break
        resolve_battle_round(c,battle)
    eng=c.execute('select * from combat_engagements where id=?',(battle,)).fetchone(); assert eng['status']=='resolved',dict(eng)
    process_due_war(c,int(eng['day_ended'] or current_day(c))); c.commit()
    aftermath=c.execute('select * from war_battle_aftermath where engagement_id=?',(battle,)).fetchone()
    afr=c.execute('select * from war_campaign_forces where id=?',(af,)).fetchone(); dfr=c.execute('select * from war_campaign_forces where id=?',(df,)).fetchone()
    reports=int(c.execute('select count(*) from war_battle_reports where engagement_id=?',(battle,)).fetchone()[0]); damage=int(c.execute('select count(*) from war_damage_events where engagement_id=?',(battle,)).fetchone()[0])
    warehouse_after=float(c.execute('select condition from buildings where id=?',(int(warehouse['id']),)).fetchone()[0]) if warehouse else None
    inv=hard_invariants(c); aggregate_losses=int(afr['aggregate_killed'])+int(afr['aggregate_wounded'])+int(dfr['aggregate_killed'])+int(dfr['aggregate_wounded'])
    # Net commercial stock may rise during the seven-day march because the ordinary economy
    # continues trading/replenishing.  WAR-01 conservation is proved by its own physical-stock
    # ledger: mobilization/resupply entries point back to the source stock row and consumption
    # entries reduce force on-hand.
    ledger=c.execute("select entry_kind,coalesce(sum(quantity),0) qty,count(*) n from war_supply_ledger where force_id=? group by entry_kind",(af,)).fetchall()
    ledger_summary={str(r['entry_kind']):{'quantity':float(r['qty']),'entries':int(r['n'])} for r in ledger}
    physical_draw=float(c.execute("select coalesce(sum(quantity),0) from war_supply_ledger where force_id=? and source_stock_id=? and entry_kind in ('mobilized','resupplied')",(af,int(stock['id']))).fetchone()[0])
    consumed=float(c.execute("select coalesce(sum(quantity),0) from war_supply_ledger where force_id=? and entry_kind='consumed'",(af,)).fetchone()[0])
    result={'pass':bool(aftermath and aggregate_losses>0 and reports>=2 and damage>0 and physical_draw>0 and consumed>0 and inv['pass']),'engine_version':ENGINE_VERSION,'schema_version':SCHEMA_VERSION,'source_day':start,'branch_day':current_day(c),'operation_id':op,'battle_id':battle,'route_id':int(route[0]),'grain_stock_before':stock_before,'grain_stock_after_march':stock_after_march,'physical_stock_draw':physical_draw,'force_supply_consumed':consumed,'supply_ledger':ledger_summary,'attacker_killed':int(afr['aggregate_killed']),'attacker_wounded':int(afr['aggregate_wounded']),'defender_killed':int(dfr['aggregate_killed']),'defender_wounded':int(dfr['aggregate_wounded']),'battle_reports':reports,'damage_events':damage,'warehouse_condition_before':warehouse_before,'warehouse_condition_after':warehouse_after,'invariants':inv}
    REPORT.write_text(json.dumps(result,indent=2,sort_keys=True)); print(json.dumps(result,indent=2,sort_keys=True)); c.close(); assert result['pass']
if __name__=='__main__': main()
