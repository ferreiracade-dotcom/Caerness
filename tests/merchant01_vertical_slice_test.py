"""MERCHANT-01 acceptance: bounded merchant records -> concrete contract -> conserved cargo/cash + steel/copper substitution."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.civilian import create_enterprise, ensure_good, set_market_condition, add_production_site
from engine.expertise import set_actor_competence
from engine.ecology import add_route
from engine.merchant import (
    add_enterprise_staff, record_market_observation, commission_market_report,
    create_trade_offer, observe_trade_offer, create_trade_contract, dispatch_trade_contract,
    add_production_input_option, apply_supply_shock, resolve_input_substitution,
)
from engine.decisions import build_actor_context, candidate_to_proposal, apply_decision
from engine.decision_runtime import generate_candidates
from engine.logistics import process_due_logistics


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_merchant01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(conn,name,loc):
    aid=int(conn.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)",(name,loc,loc)).lastrowid)
    conn.execute("INSERT INTO simulation_profiles(actor_id,tier,cadence_days,last_review_day,next_review_day) VALUES (?,'STRATEGIC',30,0,30)",(aid,))
    return aid


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=64
    c,path=bootstrap()
    assert c.execute("SELECT value FROM engine_meta WHERE key='merchant_vertical_slice_version'").fetchone()[0]=='1'
    assert c.execute("SELECT value FROM engine_meta WHERE key='merchant_information_rule'").fetchone()[0]=='enterprise_records_only'

    origin=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[MERCHANT01] Forgeport','city')").lastrowid)
    dest=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[MERCHANT01] Coppermarket','city')").lastrowid)
    add_route(c,origin,dest,base_days=2,reliability=100)
    seller_actor=actor(c,'[MERCHANT01] Steel Factor',origin)
    buyer_actor=actor(c,'[MERCHANT01] Copper Factor',dest)
    seller=create_enterprise(c,'[MERCHANT01] Steel House','merchant_house',owner_actor_id=seller_actor,location_id=origin,cash=0,capital=80)
    buyer=create_enterprise(c,'[MERCHANT01] Metalware House','merchant_house',owner_actor_id=buyer_actor,location_id=dest,cash=200,capital=100)
    add_enterprise_staff(c,buyer,buyer_actor,role='master_factor',authority=90)
    set_actor_competence(c,buyer_actor,'commerce',72,source_kind='campaign')

    steel=ensure_good(c,'merchant01_steel','Steel','metal',10)
    copper=ensure_good(c,'merchant01_copper','Copper','metal',10)
    wares=ensure_good(c,'merchant01_wares','Metalwares','craft',20)
    for loc in (origin,dest):
        set_market_condition(c,loc,steel,supply=50,demand=50)
        set_market_condition(c,loc,copper,supply=50,demand=50)
    set_market_condition(c,dest,wares,supply=40,demand=60)

    # Real owned stock backs the public offer; a second hidden offer proves unobserved opportunities do not leak into DEC-01.
    stock_id=int(c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day) VALUES (?,?,?,?,0)",(seller,origin,steel,50)).lastrowid)
    offer=create_trade_offer(c,seller,stock_id,20,5.0,expires_day=60)
    hidden_offer=create_trade_offer(c,seller,stock_id,5,4.0,expires_day=60)
    observe_trade_offer(c,buyer,buyer_actor,offer)
    record_market_observation(c,buyer,origin,steel,observer_actor_id=buyer_actor,observed_day=0,received_day=0,price=8.0,source_kind='factor_report')

    # Remote reports have a travel-time information lag and are unavailable before receipt.
    remote_obs=commission_market_report(c,buyer,buyer_actor,origin,copper)
    remote=c.execute("SELECT * FROM merchant_market_observations WHERE id=?",(remote_obs,)).fetchone()
    assert int(remote['received_day'])>0

    envelope=build_actor_context(c,buyer_actor,0)
    candidates=generate_candidates(c,buyer_actor,'STRATEGIC',0,envelope)
    merchant=[x for x in candidates if x.provider_key=='merchant']
    buy=next(x for x in merchant if x.action_kind=='accept_trade_offer')
    assert int(buy.payload['offer_id'])==offer
    assert all(int(x.payload.get('offer_id',-1))!=hidden_offer for x in merchant)
    assert int(buy.information_basis['offer_awareness_received_day'])<=0
    assert int(buy.information_basis['market_observation_id'])>0
    assert float(buy.information_basis['commerce_competence'])==72.0

    # Execute the concrete merchant candidate through the same decision application boundary used by DEC-01.
    proposal=candidate_to_proposal(buy)
    did=apply_decision(c,buyer_actor,'STRATEGIC',0,proposal)
    decision=c.execute("SELECT * FROM decisions WHERE id=?",(did,)).fetchone()
    assert decision['action_type']=='merchant_action'
    contract=c.execute("SELECT * FROM merchant_trade_contracts ORDER BY id DESC LIMIT 1").fetchone()
    shipment=c.execute("SELECT * FROM commercial_shipments WHERE trade_contract_id=?",(int(contract['id']),)).fetchone()
    assert contract['status']=='in_transit' and shipment['status']=='in_transit'
    q=float(contract['quantity'])
    assert abs(float(c.execute("SELECT quantity FROM commercial_stock WHERE id=?",(stock_id,)).fetchone()[0])-(50-q))<1e-6
    assert abs(float(c.execute("SELECT COALESCE(SUM(quantity),0) FROM commercial_shipments WHERE status IN ('in_transit','stalled')").fetchone()[0])-q)<1e-6

    # Delivery moves the same physical quantity to the buyer and settles the exact contractual cash transfer.
    due=int(shipment['segment_due_day']); c.execute("UPDATE world_state SET current_day=? WHERE id=1",(due,))
    process_due_logistics(c,due)
    contract=c.execute("SELECT * FROM merchant_trade_contracts WHERE id=?",(int(contract['id']),)).fetchone()
    assert contract['status']=='fulfilled' and abs(float(contract['delivered_quantity'])-q)<1e-6
    buyer_stock=float(c.execute("SELECT quantity FROM commercial_stock WHERE enterprise_id=? AND location_id=? AND good_id=?",(buyer,dest,steel)).fetchone()[0])
    assert abs(buyer_stock-q)<1e-6
    amount=q*5.0
    assert abs(float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(buyer,)).fetchone()[0])-(200-amount))<1e-6
    assert abs(float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(seller,)).fetchone()[0])-amount)<1e-6
    assert abs(float(c.execute("SELECT amount FROM commercial_cash_transfers WHERE trade_contract_id=?",(int(contract['id']),)).fetchone()[0])-amount)<1e-6

    # The same contract/transport path can create a real seller receivable instead of magic liquidity.
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(due,))
    credit_offer=create_trade_offer(c,seller,stock_id,4,6.0,expires_day=90)
    credit_contract=create_trade_contract(c,buyer,credit_offer,4,settlement_kind='seller_credit',due_day=due+30)
    credit_shipment=dispatch_trade_contract(c,credit_contract)
    credit_due=int(c.execute("SELECT segment_due_day FROM commercial_shipments WHERE id=?",(credit_shipment,)).fetchone()[0])
    c.execute("UPDATE world_state SET current_day=? WHERE id=1",(credit_due,)); process_due_logistics(c,credit_due)
    cr=c.execute("SELECT * FROM credit_agreements WHERE json_extract(metadata_json,'$.merchant01_contract_id')=?",(credit_contract,)).fetchone()
    assert cr and abs(float(cr['outstanding'])-24.0)<1e-6 and int(cr['lender_enterprise_id'])==seller and int(cr['borrower_enterprise_id'])==buyer
    assert c.execute("SELECT status FROM merchant_trade_contracts WHERE id=?",(credit_contract,)).fetchone()[0]=='fulfilled'

    # Steel-vs-copper shock: a real supply increase lowers steel price, and a workshop with two valid material options shifts demand toward steel.
    workshop=create_enterprise(c,'[MERCHANT01] Tool Workshop','workshop',location_id=dest,cash=30,capital=40)
    site=add_production_site(c,workshop,wares,capacity_per_30=20,inventory=0)
    add_production_input_option(c,site,copper,units_per_output=1,substitution_group='work_metal',preference_weight=1,initial_share=.5)
    add_production_input_option(c,site,steel,units_per_output=1,substitution_group='work_metal',preference_weight=1,initial_share=.5)
    copper_d0=float(c.execute("SELECT demand FROM market_conditions WHERE location_id=? AND good_id=?",(dest,copper)).fetchone()[0])
    steel_d0=float(c.execute("SELECT demand FROM market_conditions WHERE location_id=? AND good_id=?",(dest,steel)).fetchone()[0])
    shock=apply_supply_shock(c,dest,steel,100,source='merchant01_acceptance')
    assert shock['price_after']<shock['price_before']
    sub=resolve_input_substitution(c,site,due)
    shares={int(x['good_id']):float(x['new_share']) for x in sub['changes']}
    assert shares[steel]>shares[copper]
    steel_d1=float(c.execute("SELECT demand FROM market_conditions WHERE location_id=? AND good_id=?",(dest,steel)).fetchone()[0])
    copper_d1=float(c.execute("SELECT demand FROM market_conditions WHERE location_id=? AND good_id=?",(dest,copper)).fetchone()[0])
    assert steel_d1>steel_d0 and copper_d1<copper_d0

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    c.close()
    print('MERCHANT-01 merchant-house / market vertical slice tests: PASS')

if __name__=='__main__': run()
