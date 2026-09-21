from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.civilian import (
    add_auction_lot, add_production_site, add_shadow_link, civilian_summary,
    create_auction, create_cultural_object, create_enterprise, create_household, create_project,
    ensure_career_track, ensure_good, set_auction_interest, set_market_condition, start_career,
)
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.expertise import set_actor_competence
from engine.simulation import advance_connection, seed_demo


def _fresh():
    reset_db(); init_db(); seed_demo(); init_db()


def _actor(conn, name):
    return conn.execute('SELECT * FROM actors WHERE name=?', (name,)).fetchone()


def run():
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {'0.16.0','0.17.0','0.18.0','0.19.0','0.19.1','0.20.0','0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
        merchant = _actor(conn, '[DEMO] House of Seven Ledgers')
        player = _actor(conn, '[DEMO] Player Wanderer')
        cairn = conn.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0]
        toll = conn.execute("SELECT id FROM locations WHERE name=\"Toll's Reach\"").fetchone()[0]

        hh = create_household(conn, '[DEMO] Seven Ledgers Household', head_actor_id=int(merchant['id']),
                              location_id=int(cairn), wealth=120, liquidity=15, staff_capacity=70, hospitality=60)
        ent = create_enterprise(conn, '[DEMO] Seven Ledgers Fine Cloth', 'merchant_house',
                                institution_actor_id=int(merchant['id']), household_id=hh, location_id=int(cairn),
                                capital=100, cash=20, debt=10, reputation=70, admin_quality=75, labor_capacity=70)
        cloth = ensure_good(conn, 'fine_cloth', 'Fine Cloth', 'textile', 4.0, unit='bolt', luxury=0.65, skill_intensity=0.75)
        set_market_condition(conn, int(cairn), cloth, supply=35, demand=72, transport_pressure=15, risk_pressure=8,
                             metadata={'supply_trend_per_30': 1.5, 'demand_trend_per_30': 0.5, 'cadence_days': 30})
        site = add_production_site(conn, ent, cloth, capacity_per_30=20, efficiency=72, material_access=66, skilled_labor=80)

        # Career progression is actual persisted simulation, with auto-advance only where the track explicitly allows it.
        track = ensure_career_track(conn, 'merchant_demo', 'Merchant Career', 'commerce', stages=[
            {'key':'apprentice','name':'Apprentice','sequence':0},
            {'key':'factor','name':'Factor','sequence':1,'requirements':{'min_days_in_stage':30,'competence_domain':'commerce','min_competence':45,'auto_advance':True}},
            {'key':'partner','name':'Partner','sequence':2,'requirements':{'min_days_in_stage':120,'competence_domain':'commerce','min_competence':70,'auto_advance':False}},
        ])
        set_actor_competence(conn, int(player['id']), 'commerce', 55, source_kind='campaign')
        career = start_career(conn, int(player['id']), track, stage_key='apprentice', institution_actor_id=int(merchant['id']))

        # Culture / patronage / provenance.
        proj = create_project(conn, '[DEMO] Indigo Court Hanging', 'textile', patron_actor_id=int(merchant['id']),
                              creator_actor_id=int(player['id']), enterprise_id=ent, location_id=int(cairn),
                              target_day=45, quality_potential=82, funding=82, material_access=78, skilled_labor=84)

        old_obj = create_cultural_object(conn, '[DEMO] Old River Panel', 'painting', creator_actor_id=int(player['id']),
                                         owner_actor_id=int(merchant['id']), location_id=int(toll), quality=76,
                                         market_value=95, significance='valuable')
        auc = create_auction(conn, '[DEMO] Cairnholt Estate Sale', 35, location_id=int(cairn), prestige=65)
        lot = add_auction_lot(conn, auc, old_obj, seller_actor_id=int(merchant['id']), reserve_price=80, estimate_low=90, estimate_high=130)
        set_auction_interest(conn, lot, int(player['id']), budget=140, interest=80, taste_fit=85, status_motive=10)

        shadow = add_shadow_link(conn, 'object', old_obj, 'disputed_provenance', pressure=35, exposure=12,
                                 notes='Abstract provenance risk only; no operational crime detail.')
        conn.commit()

        before_price = float(conn.execute('SELECT current_price FROM market_conditions WHERE location_id=? AND good_id=?',(cairn,cloth)).fetchone()[0])
        advance_connection(conn, 60)
        conn.commit()

        # Market and production actually moved through the shared world clock.
        market = conn.execute('SELECT * FROM market_conditions WHERE location_id=? AND good_id=?',(cairn,cloth)).fetchone()
        assert int(market['last_review_day']) >= 60
        assert float(market['current_price']) > 0
        production = conn.execute('SELECT * FROM production_sites WHERE id=?',(site,)).fetchone()
        assert int(production['last_resolved_day']) == 60
        assert conn.execute("SELECT COUNT(*) FROM enterprise_accounts WHERE enterprise_id=? AND account_kind IN ('revenue','expense')",(ent,)).fetchone()[0] > 0

        # Career advanced because the track explicitly allowed routine advancement.
        c = conn.execute('SELECT ac.*,cs.stage_key FROM actor_careers ac LEFT JOIN career_stages cs ON cs.id=ac.current_stage_id WHERE ac.id=?',(career,)).fetchone()
        assert c['stage_key'] == 'factor'

        # Project completed and became a persistent cultural object with provenance.
        p = conn.execute('SELECT * FROM civilian_projects WHERE id=?',(proj,)).fetchone()
        assert p['status'] == 'completed'
        created = conn.execute('SELECT * FROM cultural_objects WHERE project_id=?',(proj,)).fetchone()
        assert created is not None and created['object_kind'] == 'textile'
        assert conn.execute('SELECT COUNT(*) FROM object_provenance WHERE object_id=?',(created['id'],)).fetchone()[0] >= 2

        # Auction resolved through simulation and ownership/provenance changed authoritatively.
        a = conn.execute('SELECT * FROM auctions WHERE id=?',(auc,)).fetchone()
        assert a['status'] == 'resolved'
        l = conn.execute('SELECT * FROM auction_lots WHERE id=?',(lot,)).fetchone()
        assert l['status'] == 'sold' and int(l['winning_actor_id']) == int(player['id'])
        obj = conn.execute('SELECT * FROM cultural_objects WHERE id=?',(old_obj,)).fetchone()
        assert int(obj['current_owner_actor_id']) == int(player['id'])
        assert conn.execute("SELECT COUNT(*) FROM object_provenance WHERE object_id=? AND provenance_kind='sold'",(old_obj,)).fetchone()[0] == 1

        # Shadow-market overlap evolves as abstract risk/exposure, not a procedural crime simulator.
        sh = conn.execute('SELECT * FROM shadow_market_links WHERE id=?',(shadow,)).fetchone()
        assert float(sh['exposure']) != 12

        # Household has persistent economic state and the subsystem is visible in aggregate.
        household = conn.execute('SELECT * FROM households WHERE id=?',(hh,)).fetchone()
        assert int(household['updated_day']) == 60
        summary = civilian_summary(conn)
        assert summary['households'] >= 1 and summary['enterprises'] >= 1 and summary['cultural_objects'] >= 2

    print('v16_test: PASS')


if __name__ == '__main__':
    run()
