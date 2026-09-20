"""Acceptance tests for v0.60 Phase 2A (foundation adjustment).

Covers plan sections 6.2 (shared geography), 6.3 (zone graph), 6.4 (concrete candidate
generation), 6.5 (event-shaped mutation) and 6.6 (cross-system readiness). 6.1 (existing
Phase 1 semantics) and most of 6.7/6.8 (off-camera parity, no perfect-map invention) are
exercised by tests/v60_underworld_rebuild_test.py and the Phase 2A status note; this file
adds only what that suite does not already cover, per the plan's instruction not to alter
old expectations just to make failures disappear.
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.simulation import SimEvent, log_event
from engine.underworld import create_underworld_organization
from engine.underworld_rebuild import (
    UnderworldZoneGraph, UnderworldCandidateAction, underworld_candidate_actions,
    ensure_zone_anchor_locations, attempt_local_activity, autonomous_organization_turn,
    _territorial_attack, _org_controlled_zones, create_zone, set_zone_adjacency,
    set_zone_controller, create_crew, change_relation,
)
import inspect
import engine.underworld_rebuild as underworld_rebuild


def bootstrap():
    path = Path(tempfile.gettempdir()) / f'caerness_v060_phase2a_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH'] = str(path)
    os.environ['CAERNESS_TEST_MODE'] = '1'
    reset_db(force=True, backup=False); init_db()
    c = connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def make_event_logger(conn):
    def _logger(*, day, event_type, title, summary, severity=1, source_actor_id=None,
                target_actor_ids=(), location_id=None, visibility=None, **_ignored):
        return log_event(conn, SimEvent(
            day=day, event_type=event_type, title=title, summary=summary, severity=severity,
            source_actor_id=source_actor_id, target_actor_ids=tuple(target_actor_ids or ()),
            location_id=location_id, visibility=visibility,
        ))
    return _logger


def run():
    assert ENGINE_VERSION == '0.60.0' and SCHEMA_VERSION >= 59
    c = bootstrap()
    alder = int(c.execute("select id from locations where name='Aldergate'").fetchone()[0])

    # --- 6.2 shared geography: zone -> anchor location -> city, resolvable without
    # parsing zone_key strings. Backfilling is opt-in and additive; existing zones start
    # unanchored (verified) and become resolvable once anchored.
    zones_before = c.execute("select id,anchor_location_id from underworld_zones where city_location_id=?", (alder,)).fetchall()
    assert zones_before, "expected seeded Aldergate zones"
    assert all(z['anchor_location_id'] is None for z in zones_before), "zones should start unanchored"
    linked = ensure_zone_anchor_locations(c, alder)
    assert len(linked) == len(zones_before)
    for zkey, loc_id in linked.items():
        loc = c.execute("select parent_location_id,is_canon from locations where id=?", (loc_id,)).fetchone()
        assert loc is not None and int(loc['parent_location_id']) == alder
        assert int(loc['is_canon']) == 0, "procedural zone anchors must not assert new canon"
    zid_sample = int(zones_before[0]['id'])
    resolved_loc = c.execute("select anchor_location_id from underworld_zones where id=?", (zid_sample,)).fetchone()[0]
    assert resolved_loc is not None
    # idempotent: re-running does not create duplicate locations or re-touch anchored zones.
    loc_count_before = int(c.execute("select count(*) from locations").fetchone()[0])
    linked_again = ensure_zone_anchor_locations(c, alder)
    assert linked_again == {}, "already-anchored zones must not be re-processed"
    assert int(c.execute("select count(*) from locations").fetchone()[0]) == loc_count_before

    # --- 6.3 zone graph: adjacency, neighbors, permeability, no self-edge, deterministic.
    graph = UnderworldZoneGraph(c)
    zone_ids = [int(z['id']) for z in zones_before]
    z0, z1 = zone_ids[0], zone_ids[1]
    neighbors_z0_a = graph.neighbors(z0)
    neighbors_z0_b = graph.neighbors(z0)
    assert neighbors_z0_a == neighbors_z0_b, "neighbor order must be deterministic"
    assert z0 not in neighbors_z0_a, "no self-edge"
    for other in neighbors_z0_a:
        assert graph.are_adjacent(z0, other)
        assert graph.permeability(z0, other) is not None
    assert graph.are_adjacent(z0, z0) is False
    assert graph.permeability(z0, z0) is None
    reachable = graph.reachable_from([z0], max_depth=1)
    assert set(reachable) == set(neighbors_z0_a)
    assert z0 not in reachable

    # --- 6.4 concrete candidate generation: real targets only, no impossible conquest,
    # reflects manpower/territorial facts, always allows hold, and does not mutate state.
    org_row = c.execute(
        "select organization_id from underworld_zone_claims where zone_id=? and claim_kind='controller' and status='active'", (z0,)
    ).fetchone()
    assert org_row, "expected a controller on the sampled zone"
    org_id = int(org_row['organization_id'])
    claims_before = int(c.execute("select count(*) from underworld_zone_claims").fetchone()[0])
    relations_before = int(c.execute("select count(*) from underworld_relations").fetchone()[0])
    candidates = underworld_candidate_actions(c, org_id)
    claims_after = int(c.execute("select count(*) from underworld_zone_claims").fetchone()[0])
    relations_after = int(c.execute("select count(*) from underworld_relations").fetchone()[0])
    assert claims_before == claims_after and relations_before == relations_after, "candidate generation must not mutate state"
    kinds = {cand.action_kind for cand in candidates}
    assert 'hold' in kinds, "hold/no-action must always be a candidate"
    own_zones = set(_org_controlled_zones(c, org_id))
    for cand in candidates:
        if cand.action_kind == 'occupy_vacant_turf':
            assert cand.target_zone_id is not None
            assert any(graph.are_adjacent(z, cand.target_zone_id) for z in own_zones), "vacant target must be adjacent to owned territory"
        if cand.action_kind == 'challenge_organization':
            assert cand.target_zone_id is not None and cand.target_organization_id is not None
            assert any(graph.are_adjacent(z, cand.target_zone_id) for z in own_zones), "conquest target must be reachable, not invented"
            assert cand.target_organization_id != org_id
        if cand.action_kind == 'patrol_zone':
            assert cand.target_zone_id in own_zones

    # --- 6.5 event-shaped mutation: an encroachment attempt must be reconstructible as a
    # machine-readable occurrence with clean causal links, not just prose.
    logger = make_event_logger(c)
    rival_row = c.execute(
        "select id from underworld_organizations where primary_location_id=? and id<>? and status='active' order by id limit 1",
        (alder, org_id),
    ).fetchone()
    assert rival_row, "expected a second organization to test encroachment"
    rival_id = int(rival_row[0])
    events_before = int(c.execute("select count(*) from events").fetchone()[0])
    result = attempt_local_activity(c, z0, rival_id, 'patrol', severity=40, event_logger=logger)
    assert result['authorized'] is False and result['incident_id'] is not None
    events_after = int(c.execute("select count(*) from events").fetchone()[0])
    assert events_after > events_before, "encroachment must produce a machine-readable event"
    ev = c.execute("select * from events where event_type='underworld_encroachment_attempted' order by id desc limit 1").fetchone()
    assert ev is not None
    link = c.execute(
        "select * from causal_links where target_kind='event' and target_id=? and relation='underworld_incident'", (int(ev['id']),)
    ).fetchone()
    assert link is not None and int(link['source_id']) == int(result['incident_id'])
    incident = c.execute("select * from underworld_incidents where id=?", (int(result['incident_id']),)).fetchone()
    assert incident is not None and int(incident['zone_id']) == z0 and int(incident['source_organization_id']) == rival_id
    # who/where/what is answerable end to end: event -> causal link -> incident -> zone/orgs.
    assert int(incident['target_organization_id']) == org_id

    # --- 6.6 cross-system readiness: a violent territorial attack preserves structured
    # facts (location, organizations, violence flag, losses) reachable from its event.
    # Built as a self-contained scenario (fresh orgs/zones/crews/hostility) rather than
    # relying on the natural seed to happen to produce an eligible attack, so the test is
    # deterministic about the attack actually firing rather than merely being attempted.
    atk_org = create_underworld_organization(c, 'test-2a-attacker', 'gang', name='Test 2A Attacker', primary_location_id=alder, member_count_estimate=30, command_depth=1)
    def_org = create_underworld_organization(c, 'test-2a-defender', 'gang', name='Test 2A Defender', primary_location_id=alder, member_count_estimate=20, command_depth=1)
    za = create_zone(c, alder, 'test-2a-zone-a', 'Test 2A Zone A')
    zb = create_zone(c, alder, 'test-2a-zone-b', 'Test 2A Zone B')
    set_zone_adjacency(c, za, zb, permeability=60)
    set_zone_controller(c, za, atk_org, strength=60)
    set_zone_controller(c, zb, def_org, strength=40)
    create_crew(c, atk_org, 'Test 2A Attacker Crew', size_estimate=40, rng=__import__('random').Random(1))
    create_crew(c, def_org, 'Test 2A Defender Crew', size_estimate=10, rng=__import__('random').Random(2))
    change_relation(c, atk_org, def_org, hostility_delta=70)  # comfortably clears the score>=42 attack threshold
    events_before2 = int(c.execute("select count(*) from events").fetchone()[0])
    ops_before2 = int(c.execute("select count(*) from underworld_operations where operation_kind='territorial_attack'").fetchone()[0])
    attacked = _territorial_attack(c, atk_org, __import__('random').Random(9001), event_logger=logger)
    assert attacked is True, "deterministic scenario must produce an actual attack, not just an attempt to attack"
    events_after2 = int(c.execute("select count(*) from events").fetchone()[0])
    ops_after2 = int(c.execute("select count(*) from underworld_operations where operation_kind='territorial_attack'").fetchone()[0])
    assert events_after2 >= events_before2 + 2, "attack must log both a declared and a resolved occurrence"
    assert ops_after2 == ops_before2 + 1, "exactly one operations row per attack, unchanged from pre-Phase-2A behavior"
    resolved_ev = c.execute("select * from events where event_type='underworld_territorial_attack_resolved' order by id desc limit 1").fetchone()
    assert resolved_ev is not None
    op_link = c.execute(
        "select * from causal_links where target_kind='event' and target_id=? and relation='underworld_operation'", (int(resolved_ev['id']),)
    ).fetchone()
    assert op_link is not None
    op = c.execute("select * from underworld_operations where id=?", (int(op_link['source_id']),)).fetchone()
    assert op is not None and str(op['operation_kind']) == 'territorial_attack'
    assert 'attacker_losses' in op['metadata_json'] and 'defender_losses' in op['metadata_json']

    # --- 6.7 off-camera parity (structural + functional): no branch anywhere in the
    # autonomous-turn call chain keys behavior off "player" / "followed" / "protagonist"
    # identity, and the same function runs cleanly for a non-followed rival organization.
    turn_source = inspect.getsource(underworld_rebuild)
    for banned in ('is_player', 'is_focus_org', 'followed_organization', 'protagonist_org', 'player_organization_id'):
        assert banned not in turn_source, f"found protagonist-privileged branching: {banned}"
    outcome = autonomous_organization_turn(c, rival_id, rng=__import__('random').Random(4242), event_logger=logger)
    assert 'action' in outcome and outcome['action'] in {
        'decision_runtime_owned',
    }

    # --- 6.8 no perfect-map invention: the five zones whose theme (not name, count, or
    # boundary) is confirmed in the World Bible get an honest citation; the other seven
    # stay purely procedural, and nothing about zone identity/count/adjacency changes.
    from engine.underworld_rebuild import apply_world_bible_zone_theme_citations, ALDERGATE_WORLD_BIBLE_ZONE_THEMES
    zone_count_before = int(c.execute("select count(*) from underworld_zones where city_location_id=?", (alder,)).fetchone()[0])
    touched = apply_world_bible_zone_theme_citations(c, alder)
    zone_count_after = int(c.execute("select count(*) from underworld_zones where city_location_id=?", (alder,)).fetchone()[0])
    assert zone_count_after == zone_count_before, "citation pass must not seed, remove, or rename zones"
    assert set(touched) == set(ALDERGATE_WORLD_BIBLE_ZONE_THEMES.keys())
    themed_rows = c.execute(
        "select metadata_json from underworld_zones where city_location_id=? and json_extract(metadata_json,'$.world_bible_theme_grounded')=1",
        (alder,),
    ).fetchall()
    assert len(themed_rows) == 5
    untouched_rows = c.execute(
        "select count(*) from underworld_zones where city_location_id=? and (json_extract(metadata_json,'$.world_bible_theme_grounded') is null)",
        (alder,),
    ).fetchone()[0]
    assert int(untouched_rows) == zone_count_before - 5, "the other seven zones must remain unannotated/procedural"
    # idempotent, and never claims full canon for a procedurally-bounded zone.
    touched_again = apply_world_bible_zone_theme_citations(c, alder)
    assert touched_again == []
    for row in themed_rows:
        meta = __import__('json').loads(row['metadata_json'])
        assert meta.get('not_world_bible_canon') is True, "theme citation must not silently upgrade the zone itself to canon"

    c.commit(); c.close(); print('v0.60 Phase 2A tests: PASS')


if __name__ == '__main__':
    run()
