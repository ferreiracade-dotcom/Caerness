from __future__ import annotations
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, SCHEMA_VERSION, connect, init_db, reset_db
from engine.current_seed import import_current_seed, SOURCE_NAMESPACE
from engine.coverage import start_coverage_run, snapshot_coverage, ten_year_gate
from engine.resolution_controller import review_entity, create_institution_candidate, update_institution_candidate, crystallize_institution_candidate
from engine.activation import activate_existing_loops
from engine.civilian import process_due_civilian

SEED=ROOT/'game'/'seeds'/'Caerness_Initial_World_State_Seed_v1_1.json'

def run():
    assert ENGINE_VERSION in {'0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    assert SCHEMA_VERSION >= 27
    reset_db(); init_db()
    with connect() as c:
        first=import_current_seed(c,SEED)
        assert first['places']==101 and first['routes']==11 and first['institutions']==91 and first['persons']==464
        assert first['households']==8 and first['cohorts']==14 and first['claims']==12 and first['latent_scopes']==54
        assert c.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character'").fetchone()[0]==464
        assert c.execute("SELECT COUNT(*) FROM actors WHERE actor_type='institution'").fetchone()[0]==91
        assert c.execute("SELECT COUNT(*) FROM actors WHERE lower(name)='malcolm vane'").fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM coverage_registry").fetchone()[0]==52
        assert c.execute("SELECT COUNT(*) FROM latent_population_scopes WHERE population_estimate IS NOT NULL").fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM actor_life_profiles WHERE birth_day IS NULL").fetchone()[0]==21
        unknown_loc=c.execute("""SELECT COUNT(*) FROM source_identity_map m JOIN actors a ON a.id=m.entity_id
                                  WHERE m.source_namespace=? AND m.entity_kind='actor' AND a.current_location_id IS NULL""",(SOURCE_NAMESPACE,)).fetchone()[0]
        assert unknown_loc>0
        # Current named lives are persistent but may later lower resolution without being deleted.
        assert c.execute("SELECT COUNT(*) FROM entity_resolution WHERE entity_kind='actor' AND resolution_level='TRACKED'").fetchone()[0] >= 460
        source_before=c.execute("SELECT COUNT(*) FROM source_identity_map WHERE source_namespace=?",(SOURCE_NAMESPACE,)).fetchone()[0]
        actor_before=c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        import_current_seed(c,SEED)
        assert c.execute("SELECT COUNT(*) FROM source_identity_map WHERE source_namespace=?",(SOURCE_NAMESPACE,)).fetchone()[0]==source_before
        assert c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]==actor_before

        run_id=start_coverage_run(c,'v27 current-canon import',source_seed_namespace=SOURCE_NAMESPACE)
        snap=snapshot_coverage(c,run_id,phase='post_import')
        assert len(snap)==52
        gate=ten_year_gate(c,run_id)
        assert gate['pass'] is False and gate['failure_count']>0

        activated=activate_existing_loops(c)
        assert activated['explicit_teaching_relationships_created']==54
        assert activated['training_programs_created']>0 and activated['training_enrollments_created']>0
        assert activated['aggregate_enterprises_created']>0
        assert c.execute("SELECT COUNT(*) FROM enterprise_business_profiles").fetchone()[0]>0
        # Unknown household finances are not literal zero-money budgets. Structural households must not
        # dissolve merely because canon deliberately leaves their economic state unquantified.
        process_due_civilian(c, 30)
        assert c.execute("SELECT COUNT(*) FROM households WHERE status='active'").fetchone()[0]==8
        coverage_now={x['domain_key']:x for x in snapshot_coverage(c,None,phase='regression')}
        assert coverage_now['23_population_resolution']['eligible_count']==54
        if ENGINE_VERSION in {'0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'}:
            assert coverage_now['17_tournament']['populated_count']>=1
            assert coverage_now['17_tournament']['mechanism_status']=='PARTIAL'
        else:
            assert coverage_now['17_tournament']['populated_count']==0

        # Objective consequence can promote; attention/camera cannot.
        aid=c.execute("SELECT id FROM actors WHERE actor_type='character' AND name='Carter Oswin'").fetchone()[0]
        before=c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        result=review_entity(c,'actor',aid,signals={'regional_market_share':40,'camera':40})
        assert result['applied_level'] in ('TRACKED','ACTIVE')
        assert 'signal:camera' not in result['score_parts']
        assert c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]==before

        # Demotion is hysteretic and preserves identity/history rather than deleting the actor.
        c.execute("UPDATE simulation_profiles SET tier='DORMANT' WHERE actor_id=?",(aid,))
        r1=review_entity(c,'actor',aid,signals={},day=180)
        r2=review_entity(c,'actor',aid,signals={},day=360)
        assert r1['action'] in ('defer','none')
        assert r2['applied_level']=='STRUCTURAL'
        assert c.execute("SELECT 1 FROM actors WHERE id=?",(aid,)).fetchone()
        assert c.execute("SELECT 1 FROM continuity_cores WHERE entity_kind='actor' AND entity_id=?",(aid,)).fetchone()

        # Organization formation is causal, then crystallized; it is not random resolution spawning.
        loc=c.execute("SELECT id FROM locations WHERE name='Aldergate'").fetchone()[0]
        founder=c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id LIMIT 1").fetchone()[0]
        candidate=create_institution_candidate(c,'crime_family',location_id=loc,founder_actor_id=founder,
            proposed_name='Regression Test Family',significance_score=10,participants=[founder],
            evidence=[{'kind':'sustained_joint_activity','duration_days':180}])
        try:
            crystallize_institution_candidate(c,candidate)
            raise AssertionError('low-significance candidate crystallized')
        except ValueError:
            pass
        update_institution_candidate(c,candidate,significance_score=45,evidence_append={'kind':'durable_asset','asset':'warehouse'})
        iid=crystallize_institution_candidate(c,candidate)
        assert c.execute("SELECT actor_type FROM actors WHERE id=?",(iid,)).fetchone()[0]=='institution'
        assert c.execute("SELECT status FROM emergent_institution_candidates WHERE id=?",(candidate,)).fetchone()[0]=='crystallized'
        assert c.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=?",(iid,)).fetchone()[0]>=1
        c.commit()
    print('v0.27.1 current-canon bridge/coverage/two-way-resolution regression PASS')

if __name__=='__main__': run()
