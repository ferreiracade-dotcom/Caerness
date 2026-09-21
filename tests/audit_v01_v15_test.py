from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.battlefield import add_battle_zone, assign_unit_to_zone
from engine.battle_tactics import add_vein_asset, submit_tactical_choice
from engine.combat import (
    add_battle_side, add_battle_unit, create_battle, create_duel, link_duel_to_battle,
    resolve_battle_round, resolve_duel_exchange, submit_battle_intent, submit_duel_intent,
)
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.player import set_player
from engine.simulation import seed_demo

EXPECTED_TABLES = {
    # v0.1-v0.4 living world / decisions / interactions / information
    'world_state','locations','actors','simulation_profiles','metrics','goals','pressures','threads','clocks',
    'background_processes','events','relationships','resources','knowledge','rumours','canon_sources','canon_chunks',
    'decisions','interactions','agreements','causal_links','event_information','information_channels','scene_packets',
    # v0.5-v0.7 player/runtime/model/competence/emergence
    'world_processes','player_actions','turns','model_requests','runtime_config','possessions','character_intentions',
    'obligations','attention_cues','actor_memories','thread_evidence','narrative_segments','agency_checkpoints',
    # v0.8-v0.12 continuity/crystallization/embodiment/expertise/time skip
    'continuity_cores','historical_anchors','public_narratives','documentary_records','cohorts','career_tracks',
    'institution_profiles','entity_resolution','latent_entities','crystallization_runs','character_embodiment',
    'speech_mediations','competence_domains','actor_competence','professional_readings','advisor_judgments',
    'time_skip_runs','time_skip_interruptions',
    # v0.13-v0.15 combat stack
    'combat_engagements','battle_sides','battle_units','battle_rounds','duel_combatants','duel_exchanges','battle_zones',
    'battle_command_links','battle_orders','battle_reports','battle_turning_points','battle_command_profiles',
    'battle_doctrines','battle_tactical_choices','battle_zone_current','battle_vein_assets','battle_tactical_effects',
    'battle_personal_consequences','duel_battle_links',
}


def _fresh():
    reset_db(); init_db(); seed_demo(); init_db()


def _actor(conn, name: str):
    return conn.execute('SELECT * FROM actors WHERE name=?', (name,)).fetchone()


def _tactic_swing(family: str) -> float:
    _fresh()
    with connect() as conn:
        player = _actor(conn, '[DEMO] Player Wanderer')
        foe = _actor(conn, '[DEMO] North Road Brotherhood')
        set_player(conn, int(player['id']), 'audit tactics')
        eid = create_battle(conn, '[AUDIT] Same-round tactic causality', player_actor_id=int(player['id']))
        a = add_battle_side(conn, eid, 'A', controller_actor_id=int(player['id']))
        b = add_battle_side(conn, eid, 'B', controller_actor_id=int(foe['id']))
        z = add_battle_zone(conn, eid, 'Decision Front', importance=90)
        ua = add_battle_unit(conn, a, 'A line', commander_actor_id=int(player['id']), combat_capacity=70)
        ub = add_battle_unit(conn, b, 'B line', commander_actor_id=int(foe['id']), combat_capacity=70)
        assign_unit_to_zone(conn, ua, z); assign_unit_to_zone(conn, ub, z)
        submit_battle_intent(conn, eid, int(player['id']), 'hold', commitment=0.5)
        submit_tactical_choice(conn, eid, a, family, actor_id=int(player['id']), focus_zone_id=z, commitment=1.0)
        out = resolve_battle_round(conn, eid)
        side = next(x for x in out['sides'] if x['side_id'] == a)
        return float(side['swing'])


def run():
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {'0.15.1','0.16.0','0.17.0','0.18.0','0.19.0','0.19.1','0.20.0','0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = sorted(EXPECTED_TABLES - tables)
        assert not missing, f'Missing claimed persistence tables: {missing}'

    # v0.15.1 hardening: tactics/front pressure must participate in the authoritative same round,
    # not merely be appended to its summary after resolution.
    pressure_swing = _tactic_swing('pressure')
    depth_swing = _tactic_swing('depth')
    assert pressure_swing != depth_swing, 'Different tactical families must causally alter same-round authoritative resolution.'

    # v0.15.1 hardening: a linked duel must automatically feed the contextual personal-combat
    # consequence resolver rather than requiring a manual second call.
    _fresh()
    with connect() as conn:
        player = _actor(conn, '[DEMO] Player Wanderer')
        foe = _actor(conn, '[DEMO] North Road Brotherhood')
        battle = create_battle(conn, '[AUDIT] Linked duel battle')
        a = add_battle_side(conn, battle, 'A')
        b = add_battle_side(conn, battle, 'B')
        zone = add_battle_zone(conn, battle, 'Critical Front', importance=95)
        aa = add_vein_asset(conn, battle, a, 'Fifth', actor_id=int(player['id']), zone_id=zone,
                            metadata={'command_role':'critical_command','replacement_depth':0.5})
        bb = add_vein_asset(conn, battle, b, 'Fifth', actor_id=int(foe['id']), zone_id=zone,
                            metadata={'command_role':'critical_command','replacement_depth':0.5})
        duel = create_duel(conn, '[AUDIT] Embedded duel', int(player['id']), int(foe['id']),
                           player_actor_id=int(player['id']), capability_a=100, capability_b=1)
        link_duel_to_battle(conn, duel, battle, zone, aa, bb)
        conn.execute('UPDATE duel_combatants SET readiness=12,composure=12 WHERE engagement_id=? AND actor_id=?', (duel, int(foe['id'])))
        submit_duel_intent(conn, duel, int(player['id']), 'commit', risk_level='high', reserve_commitment=1.0)
        out = resolve_duel_exchange(conn, duel)
        assert out['status'] == 'resolved'
        assert out['battle_consequence'] is not None, 'Resolved linked duel must feed battlefield consequence automatically.'
        link = conn.execute('SELECT consequence_id FROM duel_battle_links WHERE duel_engagement_id=?', (duel,)).fetchone()
        assert link and link[0] is not None

    # Stale release labels were one of the audit findings; keep them from recurring.
    assert 'v0.13' not in (ROOT / 'run.py').read_text(encoding='utf-8').split('description=',1)[1].split(')',1)[0]
    mobile_text = (ROOT / 'engine' / 'mobile_server.py').read_text(encoding='utf-8')
    assert 'Caerness v0.13 mobile UI' not in mobile_text

    print('audit_v01_v15_test: PASS')


if __name__ == '__main__':
    run()
