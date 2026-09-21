from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.business import (
    business_catalog, business_ecology_summary, business_profile,
    configure_enterprise_business, set_commercial_context,
)
from engine.civilian import create_enterprise, civilian_summary
from engine.civilian_life import create_credit_agreement
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.simulation import advance_connection, seed_demo


def _fresh():
    reset_db(); init_db(); seed_demo(); init_db()


def run():
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {'0.18.0','0.19.0','0.19.1','0.20.0','0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'},'0.19.0'
        cairn = int(conn.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0])
        merchant = int(conn.execute("SELECT id FROM actors WHERE name='[DEMO] House of Seven Ledgers'").fetchone()[0])

        catalog = {x['archetype_key']: x for x in business_catalog(conn)}
        # The engine now knows the requested business forms as behavior archetypes rather than cosmetic labels.
        for key in ['inn','gambling_house','pleasure_house','loan_house','smithy','tailor','theatre','physician_practice','warehouse']:
            assert key in catalog

        theatre = create_enterprise(conn, '[DEMO] Lantern Theatre', 'other', owner_actor_id=merchant,
                                    location_id=cairn, capital=100, cash=50, reputation=70, admin_quality=70, labor_capacity=70)
        smithy = create_enterprise(conn, '[DEMO] Blue Iron Smithy', 'other', owner_actor_id=merchant,
                                   location_id=cairn, capital=100, cash=50, reputation=70, admin_quality=70, labor_capacity=70)
        gaming = create_enterprise(conn, '[DEMO] River Dice House', 'other', owner_actor_id=merchant,
                                   location_id=cairn, capital=100, cash=50, reputation=70, admin_quality=70, labor_capacity=70)
        lender = create_enterprise(conn, '[DEMO] Narrow Door Loans', 'other', owner_actor_id=merchant,
                                   location_id=cairn, capital=500, cash=300, reputation=70, admin_quality=75, labor_capacity=55)
        borrower = create_enterprise(conn, '[DEMO] Small Cloth Shop', 'shop', owner_actor_id=merchant,
                                     location_id=cairn, capital=40, cash=10, reputation=50, admin_quality=50, labor_capacity=50)

        configure_enterprise_business(conn, theatre, 'theatre', quality=75, capacity=70, clientele_fit=75, service_reliability=70)
        configure_enterprise_business(conn, smithy, 'smithy', quality=75, capacity=70, clientele_fit=75, service_reliability=70)
        configure_enterprise_business(conn, gaming, 'gambling_house', quality=75, capacity=70, clientele_fit=75, service_reliability=70)
        configure_enterprise_business(conn, lender, 'loan_house', quality=75, capacity=70, clientele_fit=75, service_reliability=70)
        create_credit_agreement(conn, principal=100, lender_enterprise_id=lender, borrower_enterprise_id=borrower,
                                interest_rate_per_30=0.02, due_day=120, risk=35)

        # A wealthy festival district should favor cultural/entertainment businesses while regulation suppresses a regulated venue.
        set_commercial_context(
            conn, cairn,
            foot_traffic=80, traveler_flow=70, disposable_income=85, trade_flow=55, elite_patronage=80,
            cultural_activity=95, credit_demand=90, military_demand=15, health_demand=40, craft_demand=25,
            construction_demand=30, regulation=95, security=80, event_activity=95, reputation_climate=80,
        )
        conn.commit()
        advance_connection(conn, 30)
        conn.commit()

        t1 = conn.execute('SELECT * FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1', (theatre,)).fetchone()
        s1 = conn.execute('SELECT * FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1', (smithy,)).fetchone()
        g1 = conn.execute('SELECT * FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1', (gaming,)).fetchone()
        l1 = conn.execute('SELECT * FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1', (lender,)).fetchone()
        assert t1 and s1 and g1 and l1
        assert float(t1['demand_index']) > float(s1['demand_index'])
        assert float(g1['utilization']) < float(t1['utilization'])  # high regulation matters to this archetype
        assert float(l1['gross_revenue']) > 0
        assert conn.execute("SELECT COUNT(*) FROM enterprise_accounts WHERE enterprise_id=? AND source_kind='business_cycle'", (theatre,)).fetchone()[0] >= 2

        # Change the same city rather than changing the businesses: military/craft demand now favors the smithy,
        # while relaxed regulation materially improves the gambling-house utilization.
        g1_util = float(g1['utilization'])
        set_commercial_context(
            conn, cairn,
            foot_traffic=55, traveler_flow=45, disposable_income=45, trade_flow=75, elite_patronage=30,
            cultural_activity=15, credit_demand=55, military_demand=95, health_demand=40, craft_demand=95,
            construction_demand=70, regulation=10, security=65, event_activity=20, reputation_climate=60,
        )
        conn.commit()
        advance_connection(conn, 30)
        conn.commit()

        t2 = conn.execute('SELECT * FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1', (theatre,)).fetchone()
        s2 = conn.execute('SELECT * FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1', (smithy,)).fetchone()
        g2 = conn.execute('SELECT * FROM business_cycles WHERE enterprise_id=? ORDER BY id DESC LIMIT 1', (gaming,)).fetchone()
        assert float(s2['demand_index']) > float(s1['demand_index'])
        assert float(t2['demand_index']) < float(t1['demand_index'])
        assert float(g2['utilization']) > g1_util

        # Broad enterprise kinds are still present for compatibility, but the archetype is authoritative for business behavior.
        assert conn.execute('SELECT enterprise_kind FROM civilian_enterprises WHERE id=?', (theatre,)).fetchone()[0] == 'service'
        prof = business_profile(conn, theatre)
        assert prof and prof['archetype_key'] == 'theatre' and len(prof['recent_cycles']) >= 2
        summary = business_ecology_summary(conn)
        assert summary['configured_businesses'] >= 4 and summary['business_cycles'] >= 8
        civ = civilian_summary(conn)
        assert civ['business_ecology']['configured_businesses'] >= 4

    print('v18_test: PASS')


if __name__ == '__main__':
    run()
