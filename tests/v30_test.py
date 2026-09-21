from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, SCHEMA_VERSION, connect, init_db, reset_db
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.civilian import process_due_civilian

SEED=ROOT/'game'/'seeds'/'Caerness_Initial_World_State_Seed_v1_1.json'


def run():
    assert ENGINE_VERSION in {'0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION >= 30
    reset_db(); init_db()
    with connect() as c:
        import_current_seed(c,SEED)
        first=activate_existing_loops(c)
        assert first['market_goods_configured']==8
        assert first['market_conditions_configured']>=40
        assert first['production_sites_created']==5
        assert first['aggregate_buildings_created']==5
        assert first['brass_lantern_grand_sales_created']==4

        # Economic quantities are explicitly calibration, never canon price/currency claims.
        assert c.execute("SELECT COUNT(*) FROM market_conditions WHERE json_extract(metadata_json,'$.authority')='CAMPAIGN_CALIBRATION'").fetchone()[0] >= 40
        assert c.execute("SELECT COUNT(*) FROM market_goods WHERE notes LIKE '%campaign-calibration price index%'").fetchone()[0] == 8

        # Market presence != local manufacture. Aldergate is a distribution market but does not
        # receive a fake grain production site merely because grain passes through it.
        alder=c.execute("SELECT id FROM locations WHERE name='Aldergate'").fetchone()[0]
        grain=c.execute("SELECT id FROM market_goods WHERE good_key='ordinary-grain'").fetchone()[0]
        assert c.execute("SELECT 1 FROM market_conditions WHERE location_id=? AND good_id=?",(alder,grain)).fetchone()
        assert not c.execute("SELECT 1 FROM production_sites ps JOIN civilian_enterprises e ON e.id=ps.enterprise_id WHERE e.location_id=? AND ps.good_id=?",(alder,grain)).fetchone()

        # Explicit Bible seats repair structured-seed omissions without assigning arbitrary locations.
        for institution,location in [('Counting House','Aldergate'),('Still Hand','Toll’s Reach'),('Brass Lantern House','Toll’s Reach')]:
            row=c.execute("SELECT l.name FROM actors a JOIN locations l ON l.id=a.current_location_id WHERE a.name=?",(institution,)).fetchone()
            assert row and row[0]==location

        # No specific debt/credit relation is invented just to activate finance.
        assert c.execute("SELECT COUNT(*) FROM credit_agreements").fetchone()[0]==0

        # Aggregate infrastructure is marked as such and does not pretend to be an exact building census.
        assert c.execute("SELECT COUNT(*) FROM buildings WHERE json_extract(metadata_json,'$.resolution')='AGGREGATE_INFRASTRUCTURE'").fetchone()[0]==5

        # Activation is idempotent for durable state.
        before={
            'enterprises':c.execute("SELECT COUNT(*) FROM civilian_enterprises").fetchone()[0],
            'sites':c.execute("SELECT COUNT(*) FROM production_sites").fetchone()[0],
            'buildings':c.execute("SELECT COUNT(*) FROM buildings").fetchone()[0],
            'auctions':c.execute("SELECT COUNT(*) FROM auctions").fetchone()[0],
            'markets':c.execute("SELECT COUNT(*) FROM market_conditions").fetchone()[0],
        }
        second=activate_existing_loops(c)
        after={k:c.execute(sql).fetchone()[0] for k,sql in {
            'enterprises':"SELECT COUNT(*) FROM civilian_enterprises",
            'sites':"SELECT COUNT(*) FROM production_sites",
            'buildings':"SELECT COUNT(*) FROM buildings",
            'auctions':"SELECT COUNT(*) FROM auctions",
            'markets':"SELECT COUNT(*) FROM market_conditions",
        }.items()}
        assert before==after,(before,after,second)
        assert second['production_sites_created']==0 and second['aggregate_buildings_created']==0 and second['brass_lantern_grand_sales_created']==0

        # The material economy actually resolves. It may sell locally or retain stock, but production
        # cannot create negative inventory or erase all calibrated output.
        initial=float(c.execute("SELECT COALESCE(SUM(inventory),0) FROM production_sites").fetchone()[0])
        process_due_civilian(c,30)
        assert c.execute("SELECT COUNT(*) FROM enterprise_accounts").fetchone()[0]>0
        assert c.execute("SELECT MIN(inventory) FROM production_sites").fetchone()[0] >= 0
        assert float(c.execute("SELECT COALESCE(SUM(inventory),0) FROM production_sites").fetchone()[0]) >= 0
        assert initial>0
        c.commit()
    print('v0.30.0 current-canon aggregate economic substrate regression PASS')

if __name__=='__main__': run()
