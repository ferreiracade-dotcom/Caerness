from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,connect,init_db,reset_db
from engine.civilian import create_enterprise,ensure_good
from engine.elixir import (
    add_batch_claim,configure_elixir_supply,consume_elixir,create_elixir_batch,
    elixir_summary,refine_batch_from_root_stock,
)
from engine.health import ensure_health_profile
from engine.cultivation import process_due_cultivation


def _actor(c,name,*,core='Open-Core',stage='First',reserve=8.0,sediment=0.0):
    c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",(name,))
    aid=int(c.execute('SELECT id FROM actors WHERE name=?',(name,)).fetchone()[0])
    c.execute("INSERT INTO actor_life_profiles(actor_id,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,'adult',0,'living',0,'{}')",(aid,))
    ensure_health_profile(c,aid,longevity_class='first')
    cap=30.0 if core=='Open-Core' else 0.0
    c.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,
              training_effort,resource_access,teacher_support,injury_constraint,core_capacity,current_reserve,sediment_burden,
              observed_stage_days,plateau_days,last_review_day,next_review_day,status,metadata_json)
              VALUES (?,?,?,?,40,22,60,60,50,0,?,?,?,100,0,0,30,'active','{}')""",
              (aid,core,stage if core=='Open-Core' else None,1 if core=='Open-Core' else 0,cap,reserve if core=='Open-Core' else 0.0,sediment))
    return aid


def run():
    assert ENGINE_VERSION in {'0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'} and SCHEMA_VERSION>=33
    reset_db(); init_db()
    with connect() as c:
        cols={r[1] for r in c.execute('PRAGMA table_info(cultivation_profiles)').fetchall()}
        assert {'core_capacity','current_reserve','sediment_burden'} <= cols
        for table in ('elixir_supply_profiles','elixir_batches','elixir_batch_claims','elixir_exposures'):
            assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone(),table

        c.execute("INSERT INTO locations(name,kind,is_canon,identity_certainty,placement_certainty,coordinate_status) VALUES ('Elixir Test Vale','district',1,'ESTABLISHED','ESTABLISHED_RELATIVE','OPEN_NOT_REQUIRED')")
        lid=int(c.execute("SELECT id FROM locations WHERE name='Elixir Test Vale'").fetchone()[0])
        producer=create_enterprise(c,'Elixir Test Refinery','workshop',location_id=lid,capital=50,cash=20)
        root=ensure_good(c,'vein-root','Vein-Root','cultivation_resource',8.0,unit='lot')
        c.execute("INSERT INTO commercial_stock(enterprise_id,location_id,good_id,quantity,updated_day,metadata_json) VALUES (?,?,?,?,0,'{}')",(producer,lid,root,10.0))
        stock_id=int(c.execute('SELECT id FROM commercial_stock WHERE enterprise_id=? AND good_id=?',(producer,root)).fetchone()[0])
        configure_elixir_supply(c,producer,'refined',refinement_quality=80,sediment_risk=2,provenance_standard=85,source_basis='test')

        # Refinement is conservation-safe: input stock is consumed once; replay cannot duplicate output.
        batch=refine_batch_from_root_stock(c,'v33-refined-1',enterprise_id=producer,stock_id=stock_id,root_units=4.0,refinement_quality=80,sediment_risk=0,
                                           actual_provenance={'root_origin':'Elixir Test Vale'})
        assert abs(float(c.execute('SELECT quantity FROM commercial_stock WHERE id=?',(stock_id,)).fetchone()[0])-6.0)<1e-9
        b=c.execute('SELECT remaining_units,actual_provenance_json FROM elixir_batches WHERE id=?',(batch,)).fetchone()
        assert abs(float(b[0])-3.2)<1e-9 and json.loads(b[1])['root_origin']=='Elixir Test Vale'
        try:
            refine_batch_from_root_stock(c,'v33-refined-1',enterprise_id=producer,stock_id=stock_id,root_units=4.0)
            raise AssertionError('replayed refinement should fail')
        except ValueError:
            pass
        assert abs(float(c.execute('SELECT quantity FROM commercial_stock WHERE id=?',(stock_id,)).fetchone()[0])-6.0)<1e-9

        clean=_actor(c,'Clean Elixir Fixture',reserve=8.0)
        before=c.execute('SELECT current_reserve,vessel_adaptation,realization_integration,sediment_burden FROM cultivation_profiles WHERE actor_id=?',(clean,)).fetchone()
        out=consume_elixir(c,clean,batch,0.5)
        after=c.execute('SELECT current_reserve,vessel_adaptation,realization_integration,sediment_burden FROM cultivation_profiles WHERE actor_id=?',(clean,)).fetchone()
        assert after[0]>before[0] and after[1]>=before[1]
        assert after[2]==before[2],(before,after)  # fuel never grants Realization
        assert after[3]==0 and out['rupture_condition_id'] is None

        # Claims never rewrite actual batch truth, including an explicitly false provenance claim.
        add_batch_claim(c,batch,'origin','This batch came from White Laurel Heights.',confidence=95,truth_status='false')
        prov=json.loads(c.execute('SELECT actual_provenance_json FROM elixir_batches WHERE id=?',(batch,)).fetchone()[0])
        assert prov['root_origin']=='Elixir Test Vale'
        assert c.execute("SELECT truth_status FROM elixir_batch_claims WHERE batch_id=? ORDER BY id DESC LIMIT 1",(batch,)).fetchone()[0]=='false'

        # Poorly refined/suspect product can leave Sediment without automatically causing Rupture.
        dirty=create_elixir_batch(c,'v33-dirty','refined',units=2,usable_current_per_unit=4,refinement_quality=45,sediment_risk=60,
                                  source_location_id=lid,producer_enterprise_id=producer,actual_provenance={'root_origin':'unknown'})
        dirty_actor=_actor(c,'Sediment Fixture',reserve=5.0)
        d=consume_elixir(c,dirty_actor,dirty,0.5)
        assert d['sediment_gain']>0 and d['rupture_condition_id'] is None
        assert c.execute('SELECT sediment_burden FROM cultivation_profiles WHERE actor_id=?',(dirty_actor,)).fetchone()[0]>0

        # Even perfectly clean product can rupture a Vessel when assimilation grossly exceeds tolerance.
        overload=create_elixir_batch(c,'v33-overload','high_grade',units=3,usable_current_per_unit=120,refinement_quality=100,sediment_risk=0,source_location_id=lid)
        fragile=_actor(c,'Overload Fixture',reserve=0.0)
        real_before=float(c.execute('SELECT realization_integration FROM cultivation_profiles WHERE actor_id=?',(fragile,)).fetchone()[0])
        o=consume_elixir(c,fragile,overload,2.0)
        assert o['rupture_condition_id'] is not None
        assert c.execute("SELECT 1 FROM health_conditions WHERE id=? AND condition_kind='rupture'",(o['rupture_condition_id'],)).fetchone()
        assert float(c.execute('SELECT realization_integration FROM cultivation_profiles WHERE actor_id=?',(fragile,)).fetchone()[0])==real_before

        # Closed Core is healthy but cannot assimilate cultivation fuel through this mechanic.
        closed=_actor(c,'Closed Core Fixture',core='Closed-Core')
        spare=create_elixir_batch(c,'v33-spare','refined',units=1,usable_current_per_unit=4,refinement_quality=90,sediment_risk=0)
        try:
            consume_elixir(c,closed,spare,0.25)
            raise AssertionError('Closed Core should not use cultivation-fuel assimilation')
        except ValueError:
            pass

        # Sediment is a later-development drag, not instant Stage loss: identical practice gains are lower with heavy burden.
        low=_actor(c,'Low Sediment Practice',reserve=5.0,sediment=0)
        high=_actor(c,'High Sediment Practice',reserve=5.0,sediment=80)
        c.execute('UPDATE world_state SET current_day=30 WHERE id=1')
        process_due_cultivation(c,30)
        lv=c.execute('SELECT vessel_adaptation,realization_integration,current_stage FROM cultivation_profiles WHERE actor_id=?',(low,)).fetchone()
        hv=c.execute('SELECT vessel_adaptation,realization_integration,current_stage FROM cultivation_profiles WHERE actor_id=?',(high,)).fetchone()
        assert lv[0]>hv[0] and lv[1]>hv[1] and lv[2]==hv[2]=='First',(lv,hv)

        s=elixir_summary(c)
        assert s['supply_profiles']==1 and s['batches']>=4 and s['claims']==1 and s['exposures']==3
        assert s['sediment_exposures']>=1 and s['ruptures']==1
        c.commit()
    print('v0.33.0 elixir/Sediment/Rupture conservation regression PASS')

if __name__=='__main__': run()
