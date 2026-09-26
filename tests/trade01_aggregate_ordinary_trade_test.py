from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault('CAERNESS_TEST_MODE','1')
os.environ['CAERNESS_DB_PATH']='/tmp/caerness_trade01_acceptance.db'

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.scale import scale_snapshot, settlement_tier, institution_scale_band, gang_scale_band
from engine.aggregate_trade import aggregate_trade_snapshot
from engine.merchant import process_due_merchant
from engine.growth import regional_state


def bootstrap():
    reset_db(force=True, backup=False); init_db(); c=connect(); import_current_seed(c); activated=activate_existing_loops(c); c.commit(); return c,activated


def _assert_close(a,b,tol=1e-5):
    assert abs(float(a)-float(b)) <= tol*max(1.0,abs(float(a)),abs(float(b))), (a,b)


def run():
    c, activated = bootstrap()
    try:
        # SCALE-01 denominators and classification bands.
        snap=scale_snapshot(c)
        assert snap['world_population']==52_000_000
        assert snap['urban_population']==7_172_000
        assert snap['rural_population']==44_828_000
        assert snap['named_settlement_profiles']==59
        assert snap['named_urban_population']==6_621_000
        assert snap['structural_urban_population']==551_000
        anchors=dict(c.execute('''select l.name,s.population_estimate from settlement_scale_profiles s join locations l on l.id=s.location_id
                                  where l.name in ('Crownhold','Saltmere','Aldergate','Cairnholt','Toll’s Reach')''').fetchall())
        assert anchors=={'Crownhold':520000,'Saltmere':260000,'Aldergate':210000,'Cairnholt':115000,'Toll’s Reach':110000}
        assert settlement_tier(520000)=='metropolis' and settlement_tier(210000)=='great city' and settlement_tier(115000)=='major city'
        assert institution_scale_band(24)=='nascent' and institution_scale_band(10_000)=='great'
        assert gang_scale_band(12)=='crew' and gang_scale_band(500)=='citywide criminal power'
        assert activated['aggregate_trade_profiles']==56
        assert activated['aggregate_trade_tracked_corridors']>=1

        # First unattended aggregate cycle.
        c.execute('update world_state set current_day=1 where id=1')
        result=process_due_merchant(c,1); c.commit()
        assert result['aggregate_trade_cycles']==1
        assert result['aggregate_trade_flows']>0
        trade=aggregate_trade_snapshot(c)
        assert trade['consumption_requirement']>60_000_000
        assert trade['delivered']>400_000
        # Sparse named contracts are no longer the denominator for world trade.
        tracked=int(c.execute("select count(*) from merchant_trade_contracts where status='fulfilled'").fetchone()[0])
        assert tracked < 10
        assert trade['flows'] > tracked

        # Material accounting identities hold for every region/good.
        for b in c.execute('select * from aggregate_trade_balances where period_day=1'):
            _assert_close(b['opening_reserve']+b['production_quantity'], b['local_absorption']+b['export_quantity']+b['closing_reserve'])
            _assert_close(b['consumption_requirement'], b['local_absorption']+b['import_quantity']+b['unmet_demand'])
        f=c.execute('''select coalesce(sum(dispatched_quantity),0) d,coalesce(sum(delivered_quantity),0) v,coalesce(sum(loss_quantity),0) l
                       from aggregate_trade_flows where period_day=1''').fetchone()
        _assert_close(f['d'],f['v']+f['l'])

        # Regional state now reports the scale denominator and aggregate trade rather than
        # pretending a handful of named contracts measures a whole city.
        alder=c.execute("select id from locations where name='Aldergate'").fetchone()[0]
        polity=c.execute("select p.id from political_polities p join actors a on a.id=p.institution_actor_id where a.name='Underheaven Empire'").fetchone()
        if polity is None:
            polity=c.execute("select id from political_polities order by id limit 1").fetchone()
        st=regional_state(c,int(polity[0]),int(alder),day=1)
        assert st['population_estimate']==210000
        assert st['aggregate_trade_volume_365']>0
        assert 0 <= st['aggregate_trade_coverage'] <= 1

        # Crystallized route authority beats the aggregate fallback. Force one clean test market:
        # only Windmere can export naval supplies and only Underheaven is short.
        naval=int(c.execute("select id from market_goods where good_key='naval-supplies'").fetchone()[0])
        c.execute("update aggregate_trade_profiles set production_factor=1 where good_id=?",(naval,))
        c.execute("update aggregate_trade_profiles set production_factor=.45 where good_id=? and bucket_key='underheaven'",(naval,))
        c.execute("update aggregate_trade_profiles set production_factor=3.0 where good_id=? and bucket_key='windmere'",(naval,))
        # Remove carry-over so this is a controlled material experiment.
        c.execute("update aggregate_trade_reserves set quantity=0 where good_id=?",(naval,))
        route9=c.execute('select status from travel_routes where id=9').fetchone()
        assert route9 is not None
        # The world is connected (ROUTES-01), so one closed leg just reroutes. Cut Saltmere off entirely
        # to prove a tracked corridor with no usable path blocks trade instead of teleporting it.
        saltmere=int(c.execute("select id from locations where name='Saltmere'").fetchone()[0])
        saltmere_routes=[int(r[0]) for r in c.execute("select id from travel_routes where ? in (from_location_id,to_location_id)",(saltmere,))]
        assert 9 in saltmere_routes
        c.execute(f"update travel_routes set status='closed' where id in ({','.join(map(str,saltmere_routes))})")
        c.execute("update engine_meta set value='31' where key='aggregate_trade_next_cycle_day'")
        c.execute('update world_state set current_day=31 where id=1')
        process_due_merchant(c,31); c.commit()
        blocked=float(c.execute("select unmet_demand from aggregate_trade_balances where period_day=31 and bucket_key='underheaven' and good_id=?",(naval,)).fetchone()[0])
        assert blocked>0
        assert c.execute("select count(*) from aggregate_trade_flows where period_day=31 and good_id=? and origin_bucket_key='windmere' and destination_bucket_key='underheaven'",(naval,)).fetchone()[0]==0

        # Re-open only the known Toll's Reach-Saltmere leg: the same macro need can now move over
        # the tracked corridor, and the flow records the concrete route ids rather than hiding them.
        c.execute("update travel_routes set status='open' where id=9")
        c.execute("update aggregate_trade_reserves set quantity=0 where good_id=?",(naval,))
        c.execute("update engine_meta set value='61' where key='aggregate_trade_next_cycle_day'")
        c.execute('update world_state set current_day=61 where id=1')
        process_due_merchant(c,61); c.commit()
        flow=c.execute("""select * from aggregate_trade_flows where period_day=61 and good_id=?
                          and origin_bucket_key='windmere' and destination_bucket_key='underheaven' order by id limit 1""",(naval,)).fetchone()
        assert flow is not None and flow['route_resolution']=='tracked_route'
        meta=json.loads(flow['metadata_json']); assert 9 in meta['route_ids']
        opened=float(c.execute("select unmet_demand from aggregate_trade_balances where period_day=61 and bucket_key='underheaven' and good_id=?",(naval,)).fetchone()[0])
        assert opened < blocked

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('TRADE-01 acceptance PASS', snap, trade, {'blocked_unmet':round(blocked,3),'opened_unmet':round(opened,3),'tracked_route':meta['route_ids']})
    finally:
        c.close()

if __name__=='__main__': run()
