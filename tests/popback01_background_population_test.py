from __future__ import annotations

import json
import os

os.environ.setdefault('CAERNESS_TEST_MODE', '1')
os.environ['CAERNESS_DB_PATH'] = '/tmp/caerness_popback01_acceptance.db'

from engine.db import SCHEMA_VERSION, reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.background_population import (
    create_partition,
    load_partition,
    step_partition_month,
    apply_exposure,
    promote_identity_to_latent,
    partition_summary,
)
from engine.resolution_controller import _materialize_latent_person


def bootstrap():
    reset_db(force=True, backup=False)
    init_db()
    c = connect()
    import_current_seed(c)
    activated = activate_existing_loops(c)
    c.commit()
    return c, activated


def run():
    c, activated = bootstrap()
    try:
        assert SCHEMA_VERSION >= 73
        meta = dict(c.execute("select key,value from engine_meta where key in ('schema_version','popback01_version','background_population_authority_rule')"))
        assert int(meta['schema_version']) >= 73
        assert meta['popback01_version'] == '1'
        assert meta['background_population_authority_rule'] == 'scale01_owns_population_totals_sources_are_disjoint_decomposition_partitions_preserve_identity_only'

        # The source decomposition is lossless and disjoint at the authoritative regional level.
        assert activated['background_population_sources'] == 68
        assert activated['background_population_source_total'] == 52_000_000
        assert c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0] == 52_000_000
        for b in c.execute('select bucket_key,population_estimate from population_scale_buckets order by bucket_key'):
            resolved = int(c.execute('select coalesce(sum(population_estimate),0) from background_population_sources where bucket_key=?', (b['bucket_key'],)).fetchone()[0])
            assert resolved == int(b['population_estimate']), (b['bucket_key'], resolved, b['population_estimate'])

        # Use a known named settlement so exact location continuity can be tested as well.
        source = c.execute("""select s.* from background_population_sources s
                              join locations l on l.id=s.location_id
                              where s.source_kind='settlement' and l.name='Aldergate'""").fetchone()
        assert source is not None and int(source['population_estimate']) == 210_000
        source_id = int(source['id'])
        world_before = int(c.execute('select sum(population_estimate) from population_scale_buckets').fetchone()[0])
        source_total_before = int(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0])

        existing_partition = c.execute('select id,sample_size from background_population_partitions where source_id=?', (source_id,)).fetchone()
        assert existing_partition is not None
        pid = int(existing_partition['id'])
        sample_size = int(existing_partition['sample_size'])
        baseline_summary = partition_summary(c)
        c.commit()

        # Identity resolution overlaps SCALE-01; it must never inflate headcount.
        assert int(c.execute('select population_estimate from background_population_sources where id=?', (source_id,)).fetchone()[0]) == 210_000
        assert int(c.execute('select sum(population_estimate) from population_scale_buckets').fetchone()[0]) == world_before
        assert int(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0]) == source_total_before
        try:
            create_partition(c, source_id, sample_size=100, partition_key='illegal-overlap', seed=5)
            raise AssertionError('duplicate source partition should have failed')
        except ValueError:
            pass

        row1, state1 = load_partition(c, pid)
        row2, state2 = load_partition(c, pid)
        assert state1.sample_size == sample_size
        assert state1.state_bytes < 30_000
        assert row1['state_sha256'] == row2['state_sha256']
        assert state1.uid.tolist() == state2.uid.tolist()
        assert state1.age_days.tolist() == state2.age_days.tolist()
        assert state1.active_uids.tolist() == state2.active_uids.tolist()

        # Monthly stepping preserves stable raw identity slots while active membership can shrink.
        c.execute('update world_state set current_day=30 where id=1')
        result = step_partition_month(c, pid, day=30)
        c.commit()
        assert result['aged'] == sample_size
        _, stepped = load_partition(c, pid)
        assert stepped.uid.size == sample_size
        assert stepped.active_uids.size == sample_size - result['deaths']
        assert (stepped.uid == state1.uid).all()
        assert int(c.execute('select sum(population_estimate) from population_scale_buckets').fetchone()[0]) == world_before
        assert int(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0]) == source_total_before

        # Pick a surviving adult identity. Its identity existed before any merchant/underworld significance.
        unresolved_uids = {int(r[0]) for r in c.execute(
            "select local_uid from background_person_profiles where partition_id=? and status='background' and actor_id is null", (pid,)
        ).fetchall()}
        candidates = [int(slot) for slot in stepped.active_uids.tolist()
                      if int(stepped.uid[int(slot)]) in unresolved_uids
                      and 18 * 365 <= int(stepped.age_days[int(slot)]) < 60 * 365]
        assert candidates
        slot = candidates[0]
        local_uid = int(stepped.uid[slot])
        s0 = stepped.snapshot(local_uid)
        exact_birth_day = 30 - int(s0['age_days'])
        score1 = apply_exposure(c, pid, local_uid, domain='merchant', delta=.35,
                                reason='Repeated successful market dealings', source_kind='test', source_id=1)
        score2 = apply_exposure(c, pid, local_uid, domain='underworld', delta=.40,
                                reason='Became relevant to a local protection dispute', source_kind='test', source_id=2)
        c.commit()
        assert .349 <= score1 <= .351
        assert .749 <= score2 <= .751
        assert c.execute('select count(*) from background_population_exposures where partition_id=? and local_uid=?', (pid, local_uid)).fetchone()[0] == 2

        # Background -> latent is the same identity, not a newly rolled replacement person.
        latent_id = promote_identity_to_latent(c, pid, local_uid, archetype='regional_merchant_candidate',
                                               reason='Accumulated cross-domain causal salience')
        latent_id_again = promote_identity_to_latent(c, pid, local_uid, archetype='ignored_second_archetype',
                                                     reason='Idempotency check')
        c.commit()
        assert latent_id_again == latent_id
        latent = c.execute('select * from latent_entities where id=?', (latent_id,)).fetchone()
        constraints = json.loads(latent['constraints_json'])
        history = json.loads(latent['historical_context_json'])
        assert constraints['background_partition_id'] == pid
        assert constraints['background_local_uid'] == local_uid
        assert constraints['background_source_id'] == source_id
        assert constraints['birth_day'] == exact_birth_day
        assert constraints['demographic_sex'] == s0['demographic_sex']
        assert history['background_source_key'].startswith('settlement:')
        assert history['population_bucket_key'] == 'underheaven'
        assert history['identity_existed_before_promotion'] is True
        assert history['background_identity_snapshot']['exposure_score'] >= .749

        # Latent -> named preserves the exact birth day and updates the same POPBACK link.
        actor_id = _materialize_latent_person(c, latent, day=30, score=55.0, parts={'popback_test': 55.0})
        assert actor_id is not None
        c.commit()
        life = c.execute('select * from actor_life_profiles where actor_id=?', (actor_id,)).fetchone()
        assert int(life['birth_day']) == exact_birth_day
        actor = c.execute('select current_location_id from actors where id=?', (actor_id,)).fetchone()
        assert int(actor['current_location_id']) == int(source['location_id'])
        link = c.execute('select * from background_population_identity_links where partition_id=? and local_uid=?', (pid, local_uid)).fetchone()
        assert link['status'] == 'crystallized'
        assert int(link['latent_entity_id']) == latent_id
        assert int(link['actor_id']) == actor_id

        # Resolution changes never change population authority.
        assert int(c.execute('select sum(population_estimate) from population_scale_buckets').fetchone()[0]) == world_before
        assert int(c.execute('select sum(population_estimate) from background_population_sources').fetchone()[0]) == source_total_before

        summary = partition_summary(c)
        assert summary['population_sources'] == 68
        assert summary['source_population_total'] == 52_000_000
        assert summary['active_partitions'] == 68
        assert summary['sampled_identities'] == baseline_summary['sampled_identities']
        assert summary['linked_latent'] >= baseline_summary['linked_latent'] + 1
        assert summary['linked_actors'] >= baseline_summary['linked_actors'] + 1
        assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert not c.execute('pragma foreign_key_check').fetchall()

        print('POPBACK-01 acceptance PASS', {
            'sources': 68,
            'source_total': 52_000_000,
            'partition_id': pid,
            'source_population': 210_000,
            'sample_size': sample_size,
            'sample_deaths': result['deaths'],
            'promoted_local_uid': local_uid,
            'latent_id': latent_id,
            'actor_id': actor_id,
            'exact_birth_day': exact_birth_day,
            'summary': summary,
        })
    finally:
        c.close()


if __name__ == '__main__':
    run()
