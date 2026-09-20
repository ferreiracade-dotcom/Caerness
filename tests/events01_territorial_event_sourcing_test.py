"""EVENTS-01 acceptance: bounded event-sourcing spike for territorial sovereignty."""
from __future__ import annotations
import os, sys, tempfile, sqlite3, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.underworld import create_underworld_organization
from engine.underworld_rebuild import (
    create_zone, set_zone_adjacency, set_zone_controller, add_zone_challenger,
    grant_operating_permission, revoke_operating_permission,
)
from engine.territorial_events import (
    ensure_base_branch, event_count, replay_territorial_state, projection_state,
    authoritative_territorial_state, rebuild_territorial_projection,
    create_snapshot, replay_from_snapshot, create_branch, append_territorial_event,
)


def bootstrap():
    path = Path(tempfile.gettempdir()) / f'caerness_events01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH'] = str(path)
    os.environ['CAERNESS_TEST_MODE'] = '1'
    reset_db(force=True, backup=False); init_db()
    c = connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c, path


def run():
    assert ENGINE_VERSION == '0.60.0' and SCHEMA_VERSION >= 59
    c, path = bootstrap()
    base = ensure_base_branch(c)
    assert event_count(c, base) > 0, 'seeded territorial mutations should append domain events'

    # 1) Append -> hot projection, and replay exactly matches the current SQL owner.
    assert replay_territorial_state(c, base) == authoritative_territorial_state(c)
    assert projection_state(c, base) == authoritative_territorial_state(c)

    alder = int(c.execute("SELECT id FROM locations WHERE name='Aldergate'").fetchone()[0])
    a = create_underworld_organization(c, 'events01-a', 'gang', name='Events01 A', primary_location_id=alder, member_count_estimate=20)
    b = create_underworld_organization(c, 'events01-b', 'gang', name='Events01 B', primary_location_id=alder, member_count_estimate=15)
    z1 = create_zone(c, alder, 'events01-a', 'Events01 A Zone')
    z2 = create_zone(c, alder, 'events01-b', 'Events01 B Zone')
    set_zone_adjacency(c, z1, z2, permeability=70)
    set_zone_controller(c, z1, a, strength=61, local_support=44, fear=53)
    set_zone_controller(c, z2, b, strength=52, local_support=39, fear=48)
    add_zone_challenger(c, z2, a, strength=41)
    perm = grant_operating_permission(c, z2, b, a, 'collections', tribute_rate=.12)
    c.commit()
    assert replay_territorial_state(c, base) == authoritative_territorial_state(c)
    assert projection_state(c, base) == authoritative_territorial_state(c)

    # 2) Restart safety: close connection, open a new one, replay from SQL only.
    c.close()
    c = connect()
    assert replay_territorial_state(c, base) == authoritative_territorial_state(c)

    # 3) Projection rebuild: destroy sidecar projections and rebuild from immutable events.
    c.execute('DELETE FROM territorial_projection_permissions WHERE branch_id=?', (base,))
    c.execute('DELETE FROM territorial_projection_challengers WHERE branch_id=?', (base,))
    c.execute('DELETE FROM territorial_projection_zones WHERE branch_id=?', (base,))
    assert projection_state(c, base) != authoritative_territorial_state(c)
    rebuilt = rebuild_territorial_projection(c, base)
    assert rebuilt == authoritative_territorial_state(c)
    assert projection_state(c, base) == authoritative_territorial_state(c)

    # 4) Snapshot + tail: snapshot, mutate, then replay snapshot plus later events.
    snap = create_snapshot(c, base)
    before = replay_territorial_state(c, base)
    assert revoke_operating_permission(c, perm, reason='events01 acceptance') is True
    c.commit()
    after = replay_territorial_state(c, base)
    assert before != after
    assert replay_from_snapshot(c, snap) == after
    assert after == authoritative_territorial_state(c)

    # 5) Immutable event history: updates/deletes are rejected by schema triggers.
    latest = int(c.execute('SELECT MAX(id) FROM territorial_domain_events').fetchone()[0])
    try:
        c.execute("UPDATE territorial_domain_events SET event_type='tampered' WHERE id=?", (latest,))
        raise AssertionError('event UPDATE should be rejected')
    except sqlite3.IntegrityError:
        pass
    try:
        c.execute('DELETE FROM territorial_domain_events WHERE id=?', (latest,))
        raise AssertionError('event DELETE should be rejected')
    except sqlite3.IntegrityError:
        pass

    # 6) Branching: hypothetical territorial changes diverge without touching main/SQL truth.
    base_state = replay_territorial_state(c, base)
    branch = create_branch(c, 'events01-counterfactual', parent_branch=base)
    append_territorial_event(c, 'territory.zone_control_set', {
        'zone_id': z2, 'new_controller_organization_id': a,
        'strength': 70, 'local_support': 50, 'fear': 62, 'started_day': 999,
    }, branch=branch, day=999, cause_kind='test_counterfactual', cause_id=1)
    branch_state = replay_territorial_state(c, branch)
    assert branch_state != base_state
    assert replay_territorial_state(c, base) == base_state
    assert authoritative_territorial_state(c) == base_state
    assert branch_state['zones'][str(z2)]['controller']['organization_id'] == a

    # 7) Event-version evolution: a persisted v1 controller event replays through the v1->v2 upcaster.
    legacy_branch = create_branch(c, 'events01-v1-upcast', parent_branch=base)
    append_territorial_event(c, 'territory.zone_control_set', {
        'zone_id': z1, 'organization_id': b, 'day': 1001,
    }, branch=legacy_branch, day=1001, event_version=1, cause_kind='test_legacy_event', cause_id=2)
    legacy_state = replay_territorial_state(c, legacy_branch)
    legacy_controller = legacy_state['zones'][str(z1)]['controller']
    assert legacy_controller['organization_id'] == b
    assert legacy_controller['strength'] == 60.0 and legacy_controller['local_support'] == 45.0 and legacy_controller['fear'] == 55.0

    # 8) Migration shape itself is present and base branch is persisted.
    assert c.execute("SELECT value FROM engine_meta WHERE key='territorial_event_sourcing_spike_version'").fetchone()[0] == '1'
    assert c.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=59").fetchone()[0] == 1
    c.commit(); c.close()
    print('EVENTS-01 territorial event-sourcing tests: PASS')

if __name__ == '__main__':
    run()
