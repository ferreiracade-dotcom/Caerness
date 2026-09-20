"""CRAFT-01 acceptance: real recipe -> bounded procurement -> conserved input -> finished stock -> sale."""
from __future__ import annotations
import os, sys, tempfile, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.civilian import create_enterprise, ensure_good, set_market_condition, add_production_site
from engine.ecology import add_route
from engine.expertise import set_actor_competence
from engine.merchant import (add_enterprise_staff, create_trade_offer, observe_trade_offer, record_market_observation,
                             apply_supply_shock, create_trade_contract, dispatch_trade_contract)
from engine.logistics import process_due_logistics
from engine.craft import (create_recipe, add_recipe_input, add_recipe_facility_requirement, add_facility,
                          bind_recipe_to_site, assign_site_worker, validate_recipe_dependency_closure,
                          create_production_order, process_due_craft, craft_summary)
from engine.decisions import build_actor_context, candidate_to_proposal, apply_decision
from engine.decision_runtime import generate_candidates


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_craft01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(conn,name,loc):
    aid=int(conn.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)",(name,loc,loc)).lastrowid)
    conn.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,last_review_day,next_review_day) VALUES (?,'STRATEGIC',30,0,30)",(aid,))
    return aid


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=65
    c,path=bootstrap()
    assert c.execute("SELECT value FROM engine_meta WHERE key='craft_vertical_slice_version'").fetchone()[0]=='1'
    assert c.execute("SELECT value FROM engine_meta WHERE key='craft_stock_rule'").fetchone()[0]=='commercial_stock_conserved'

    steelport=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[CRAFT01] Steelport','city')").lastrowid)
    forgecity=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[CRAFT01] Forgecity','city')").lastrowid)
    add_route(c,steelport,forgecity,base_days=2,reliability=100)

    seller_actor=actor(c,'[CRAFT01] Steel Merchant',steelport)
    smith_actor=actor(c,'[CRAFT01] Master Smith',forgecity)
    seller=create_enterprise(c,'[CRAFT01] Steel House','merchant_house',owner_actor_id=seller_actor,location_id=steelport,cash=200,capital=100)
    workshop=create_enterprise(c,'[CRAFT01] Forge Works','workshop',owner_actor_id=smith_actor,location_id=forgecity,cash=300,capital=150,labor_capacity=85)
    add_enterprise_staff(c,workshop,smith_actor,role='master_smith',authority=90,specialty='craft')
    set_actor_competence(c,smith_actor,'commerce',60,source_kind='campaign')
    set_actor_competence(c,smith_actor,'craft',82,specialty='metalworking',source_kind='career')
    set_actor_competence(c,seller_actor,'craft',68,specialty='smelting',source_kind='career')

    ore=ensure_good(c,'craft01_ore','Iron Ore','ore',3)
    steel=ensure_good(c,'craft01_steel','Steel','metal',10)
    copper=ensure_good(c,'craft01_copper','Copper','metal',10)
    charcoal=ensure_good(c,'craft01_charcoal','Charcoal','fuel',4)
    wares=ensure_good(c,'craft01_tools','Metal Tools','craft',30)
    impossible=ensure_good(c,'craft01_impossible_flux','Impossible Flux','material',50)
    for loc in (steelport,forgecity):
        set_market_condition(c,loc,ore,supply=60,demand=50)
        set_market_condition(c,loc,steel,supply=45,demand=55)
        set_market_condition(c,loc,copper,supply=35,demand=65)
        set_market_condition(c,loc,charcoal,supply=60,demand=45)
        set_market_condition(c,loc,wares,supply=35,demand=70)

    # First tracked production layer: ore + charcoal + furnace + craft labor -> real steel intermediate.
    steel_site=add_production_site(c,seller,steel,capacity_per_30=60,efficiency=90,material_access=99,skilled_labor=68,inventory=0)
    steel_recipe=create_recipe(c,'craft01_smelting','Smelt Steel',steel,output_quantity=1,base_duration_days=.25,
                               skill_domain='craft',min_skill=45)
    add_recipe_input(c,steel_recipe,ore,group_key='ore_charge',units_per_batch=1.2)
    add_recipe_input(c,steel_recipe,charcoal,group_key='smelting_fuel',units_per_batch=.8)
    add_recipe_facility_requirement(c,steel_recipe,'furnace',minimum_capacity=1,minimum_condition=50)
    bind_recipe_to_site(c,steel_site,steel_recipe); assign_site_worker(c,steel_site,seller_actor,role='smelter')
    add_facility(c,seller,steelport,'furnace','[CRAFT01] Steel Furnace',capacity=3,condition=90)
    c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(seller,steelport,ore,40))
    c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(seller,steelport,charcoal,30))
    steel_order=create_production_order(c,steel_site,20,recipe_id=steel_recipe,priority=90)
    c.execute("UPDATE world_state SET current_day=1 WHERE id=1"); process_due_craft(c,1)
    steel_started=c.execute("SELECT * FROM craft_production_orders WHERE id=?",(steel_order,)).fetchone()
    assert steel_started['status']=='in_progress'
    steel_done_day=int(steel_started['next_review_day'])
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(steel_done_day,)); process_due_craft(c,steel_done_day)
    assert c.execute("SELECT status FROM craft_production_orders WHERE id=?",(steel_order,)).fetchone()[0]=='completed'
    produced_steel=c.execute("SELECT * FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(seller,steelport,steel)).fetchone()
    assert produced_steel and abs(float(produced_steel['quantity'])-20)<1e-9

    site=add_production_site(c,workshop,wares,capacity_per_30=30,efficiency=84,material_access=99,skilled_labor=70,inventory=0)
    recipe=create_recipe(c,'craft01_metal_tools','Forged Metal Tools',wares,output_quantity=1,base_duration_days=1,
                         skill_domain='craft',min_skill=55)
    add_recipe_input(c,recipe,steel,group_key='working_metal',units_per_batch=1.0)
    add_recipe_input(c,recipe,copper,group_key='working_metal',units_per_batch=1.2)
    add_recipe_input(c,recipe,charcoal,group_key='fuel',units_per_batch=.5)
    add_recipe_facility_requirement(c,recipe,'forge',minimum_capacity=1,minimum_condition=50)
    bind_recipe_to_site(c,site,recipe)
    assign_site_worker(c,site,smith_actor,role='master_smith')
    assert c.execute("SELECT production_mode FROM production_sites WHERE id=?",(site,)).fetchone()[0]=='tracked'

    # Closure fails inspectably before a required facility exists.
    closure=validate_recipe_dependency_closure(c,recipe,workshop)
    assert not closure['closed'] and 'facility:forge' in closure['missing']
    forge=add_facility(c,workshop,forgecity,'forge','[CRAFT01] Main Forge',capacity=2,condition=92)

    # A separate recipe with a material that has no stock, offer, producer or route-source fails closure.
    impossible_recipe=create_recipe(c,'craft01_impossible','Impossible Demonstrator',wares,skill_domain='craft')
    add_recipe_input(c,impossible_recipe,impossible,group_key='mystery_input',units_per_batch=1)
    bad=validate_recipe_dependency_closure(c,impossible_recipe,workshop)
    assert not bad['closed'] and 'input_group:mystery_input:no_source_path' in bad['missing']

    # Real local stock exists for charcoal and for the now-expensive technically-valid copper alternative.
    c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(workshop,forgecity,charcoal,20))
    copper_stock=int(c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(workshop,forgecity,copper,20)).lastrowid)

    # The MERCHANT-01 steel supply shock makes steel the preferred valid material; the enterprise receives that information.
    shock=apply_supply_shock(c,forgecity,steel,90,source='craft01_test')
    assert shock['price_after'] < shock['price_before']
    record_market_observation(c,workshop,forgecity,steel,observer_actor_id=smith_actor,price=shock['price_after'],source_kind='local_market_sheet')
    record_market_observation(c,workshop,forgecity,copper,observer_actor_id=smith_actor,price=18.0,source_kind='local_market_sheet')

    # Steel is physically available from a real seller and the workshop actually receives the specific offer.
    seller_stock=int(produced_steel['id'])
    offer=create_trade_offer(c,seller,seller_stock,20,5.0,expires_day=steel_done_day+90)
    observe_trade_offer(c,workshop,smith_actor,offer)
    closure=validate_recipe_dependency_closure(c,recipe,workshop)
    assert closure['closed'], closure

    order=create_production_order(c,site,4,recipe_id=recipe,priority=85)
    first_review=steel_done_day+1
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(first_review,))
    process_due_craft(c,first_review)
    o=c.execute("SELECT * FROM craft_production_orders WHERE id=?",(order,)).fetchone()
    assert o['status']=='waiting_input' and o['blocked_reason']=='missing_input'
    detail=json.loads(o['blocked_detail_json'])
    metal=next(g for g in detail['missing'] if g['group_key']=='working_metal')
    assert int(metal['preferred_input_good_id'])==steel
    assert copper in [int(x) for x in metal['technically_valid_alternatives']]
    # Copper remained untouched: price-aware choice created a steel shortage instead of silently consuming copper.
    assert abs(float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(copper_stock,)).fetchone()[0])-20)<1e-9

    # The shortage creates a concrete, belief-bounded procurement candidate tied to this exact order and observed offer.
    envelope=build_actor_context(c,smith_actor,first_review)
    candidates=generate_candidates(c,smith_actor,'STRATEGIC',first_review,envelope)
    procurement=next(x for x in candidates if x.provider_key=='craft' and x.action_kind=='accept_trade_offer')
    assert int(procurement.payload['production_order_id'])==order and int(procurement.payload['offer_id'])==offer
    assert int(procurement.information_basis['production_order_id'])==order
    apply_decision(c,smith_actor,'STRATEGIC',first_review,candidate_to_proposal(procurement))
    contract=c.execute("SELECT * FROM merchant_trade_contracts ORDER BY id DESC LIMIT 1").fetchone()
    shipment=c.execute("SELECT * FROM commercial_shipments WHERE trade_contract_id=?",(int(contract['id']),)).fetchone()
    assert contract['status']=='in_transit' and shipment['status']=='in_transit'

    # Cargo must physically arrive before the order can start.
    arrival=int(shipment['segment_due_day'])
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(arrival,)); process_due_logistics(c,arrival)
    assert c.execute("SELECT status FROM merchant_trade_contracts WHERE id=?",(int(contract['id']),)).fetchone()[0]=='fulfilled'
    arrived=float(c.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(workshop,forgecity,steel)).fetchone()[0])
    assert arrived>=4
    review=max(arrival,int(c.execute("SELECT next_review_day FROM craft_production_orders WHERE id=?",(order,)).fetchone()[0]))
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(review,)); process_due_craft(c,review)
    started=c.execute("SELECT * FROM craft_production_orders WHERE id=?",(order,)).fetchone()
    assert started['status']=='in_progress'
    # Reservation/consumption is physical: exactly 4 steel and 2 charcoal have left commercial stock.
    consumed={int(r['good_id']):float(r['quantity_consumed']) for r in c.execute("SELECT * FROM craft_input_reservations WHERE order_id=?",(order,)).fetchall()}
    assert abs(consumed[steel]-4)<1e-9 and abs(consumed[charcoal]-2)<1e-9 and copper not in consumed

    completion=int(started['next_review_day'])
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(completion,)); process_due_craft(c,completion)
    done=c.execute("SELECT * FROM craft_production_orders WHERE id=?",(order,)).fetchone()
    assert done['status']=='completed' and 0<float(done['quality'])<=100
    output_stock=c.execute("SELECT * FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(workshop,forgecity,wares)).fetchone()
    assert output_stock and abs(float(output_stock['quantity'])-4)<1e-9
    assert abs(float(c.execute("SELECT quantity FROM craft_output_lots WHERE order_id=?",(order,)).fetchone()[0])-4)<1e-9
    # Legacy aggregate inventory did not mint a parallel copy for the tracked site.
    assert abs(float(c.execute("SELECT inventory FROM production_sites WHERE id=?",(site,)).fetchone()[0]))<1e-9

    # Finished goods can immediately re-enter MERCHANT-01 and create real sale revenue/margin records.
    finished_offer=create_trade_offer(c,workshop,int(output_stock['id']),4,25.0,expires_day=completion+60)
    sale=create_trade_contract(c,seller,finished_offer,4,settlement_kind='cash_on_delivery')
    sale_shipment=dispatch_trade_contract(c,sale)
    sale_row=c.execute("SELECT * FROM commercial_shipments WHERE id=?",(sale_shipment,)).fetchone()
    sale_arrival=int(sale_row['segment_due_day'])
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(sale_arrival,)); process_due_logistics(c,sale_arrival)
    assert c.execute("SELECT status FROM merchant_trade_contracts WHERE id=?",(sale,)).fetchone()[0]=='fulfilled'
    purchase_total=float(c.execute("SELECT COALESCE(SUM(amount),0) FROM enterprise_accounts WHERE enterprise_id=? AND account_kind='purchase'",(workshop,)).fetchone()[0])
    revenue_total=float(c.execute("SELECT COALESCE(SUM(amount),0) FROM enterprise_accounts WHERE enterprise_id=? AND account_kind='revenue'",(workshop,)).fetchone()[0])
    assert purchase_total>0 and revenue_total>=100

    summary=craft_summary(c)
    assert summary['completed_orders']>=2 and abs(summary['output_quantity']-24)<1e-9
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close();
    try: path.unlink()
    except FileNotFoundError: pass
    print('CRAFT-01 production dependency closure acceptance: PASS')

if __name__=='__main__': run()
