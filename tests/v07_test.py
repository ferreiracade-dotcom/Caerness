from __future__ import annotations

import json
import threading
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

from engine.agency import assess_handoff
from engine.canon import DEFAULT_CANON, index_canon
from engine.competence import add_intention, add_obligation, add_possession, pending_attention
from engine.db import connect, init_db, reset_db
from engine.emergence import active_emergent_threads, important_memories
from engine.local_model import chat_local, runtime_config, set_runtime_config
from engine.mobile_server import CaernessHandler
from engine.model_gateway import bridge_play, run_request_local
from engine.player import build_scene_packet
from engine.router import assess_model_task
from engine.simulation import SimEvent, log_event, seed_demo
from engine.turns import play_turn


class _FakeLocalHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        payload = json.loads(self.rfile.read(length).decode('utf-8'))
        body = json.dumps({
            'choices': [{'message': {'content': json.dumps({'ok': True, 'echo_model': payload.get('model')})}}],
            'usage': {'prompt_tokens': 50, 'completion_tokens': 8},
        }).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _actor(conn, name):
    return conn.execute('SELECT * FROM actors WHERE name=?', (name,)).fetchone()


def run():
    reset_db()
    init_db()
    seed_demo()
    index_canon(DEFAULT_CANON)

    with connect() as conn:
        cfg = runtime_config(conn)
        assert cfg['device_profile'] == 'oneplus12_12gb'
        assert cfg['realtime_calendar_progression'] == 0
        assert int(cfg['local_max_context_tokens']) == 4096

        player = _actor(conn, '[DEMO] Player Wanderer')
        target = _actor(conn, '[DEMO] River Lantern Escort Company')
        assert player['current_location_id'] == target['current_location_id']

        # Character competence: the player should not need to remember an obvious delivery.
        pid = add_possession(conn, int(player['id']), 'sealed letter', item_type='letter')
        iid = add_intention(
            conn, int(player['id']), 'give the sealed letter to River Lantern when encountered',
            intention_kind='deliver_possession', target_actor_id=int(target['id']), possession_id=pid,
            trigger_kind='actor_present', auto_policy='ask_if_changed',
        )
        oid = add_obligation(
            conn, int(player['id']), 'Deliver the sealed letter to River Lantern',
            counterparty_actor_id=int(target['id']), target_actor_id=int(target['id']),
            intention_id=iid, due_day=3, importance=3,
        )
        scene = build_scene_packet(conn, 'I enter the company yard.')
        intention = conn.execute('SELECT status FROM character_intentions WHERE id=?', (iid,)).fetchone()[0]
        possession = conn.execute('SELECT holder_actor_id,status FROM possessions WHERE id=?', (pid,)).fetchone()
        obligation = conn.execute('SELECT status FROM obligations WHERE id=?', (oid,)).fetchone()[0]
        assert intention == 'fulfilled'
        assert int(possession['holder_actor_id']) == int(target['id'])
        assert possession['status'] == 'held'
        assert obligation == 'fulfilled'
        assert any(c['cue_type'] == 'automatic' for c in scene['attention_cues'])

        # Changed circumstances must hand agency back rather than auto-following the old plan.
        pid2 = add_possession(conn, int(player['id']), 'second sealed letter', item_type='letter')
        iid2 = add_intention(
            conn, int(player['id']), 'give the second sealed letter to River Lantern',
            intention_kind='deliver_possession', target_actor_id=int(target['id']), possession_id=pid2,
            trigger_kind='actor_present', auto_policy='ask_if_changed',
        )
        conn.execute(
            'INSERT OR REPLACE INTO relationships(actor_a_id,actor_b_id,stance,trust,obligation,updated_day) VALUES (?,?,?,?,?,?)',
            (int(player['id']), int(target['id']), -60, -60, 0, 1),
        )
        conn.execute('UPDATE world_state SET current_day=1 WHERE id=1')
        scene2 = build_scene_packet(conn, 'I see them again.')
        assert conn.execute('SELECT status FROM character_intentions WHERE id=?', (iid2,)).fetchone()[0] == 'blocked'
        assert any(c['cue_type'] == 'decision' for c in scene2['attention_cues'])
        assert int(conn.execute('SELECT holder_actor_id FROM possessions WHERE id=?', (pid2,)).fetchone()[0]) == int(player['id'])

        # Agency handoff: long travel can be one player-facing section with multiple internal beats.
        turn = play_turn(conn, 'I travel to Cairnholt.')
        assert turn['action_result']['action_type'] == 'travel'
        assert len(turn['segment_outline']) >= 2
        assert turn['agency_handoff']['handoff_type'] in {'open', 'hard'}
        assert 'What do you do?' not in turn['narration']
        rules = turn['narration_envelope']['narration_rules']
        assert any("Never end with generic prompts" in r for r in rules)

        # Scene router: normal work stays local; huge context recommends external AI on 12 GB profile.
        light = assess_model_task(conn, 'narration', {'scene_after': {'present_actors': [], 'known_events': [], 'known_rumours': [], 'pending_player_interactions': [], 'attention_cues': []}, 'text': 'short'}, persist=False)
        assert light.recommendation in {'local', 'rules'}
        huge = assess_model_task(conn, 'narration', {'scene_after': {'present_actors': [{'id': i} for i in range(8)], 'known_events': [{'id': i, 'severity': 5} for i in range(8)], 'known_rumours': [], 'pending_player_interactions': [{'id': i, 'stakes': 5} for i in range(5)], 'attention_cues': []}, 'canon': 'x' * 40000}, persist=False)
        assert huge.recommendation in {'external_recommended', 'external_strongly_recommended'}
        assert huge.external_reason in {'hardware', 'reasoning', 'quality'}

        # Consequences become memories and repeated consequences can be recognized as an emergent thread.
        loc = int(player['current_location_id'])
        for n in range(3):
            eid = log_event(conn, SimEvent(
                day=10+n, event_type='test:dispute', title=f'Recurring road dispute {n}',
                summary='The same road dispute between the company and its rivals escalates again.',
                severity=4, source_actor_id=int(target['id']), target_actor_ids=(int(player['id']),), location_id=loc,
                visibility='limited', rumorability=0.4,
            ))
        mems = important_memories(conn, int(player['id']))
        assert any('road dispute' in m['summary'].lower() for m in mems)
        threads = active_emergent_threads(conn)
        assert any(t['scope'] == 'emergent' for t in threads)
        conn.commit()

    # Local OpenAI-compatible adapter works without an external package/API.
    fake = ThreadingHTTPServer(('127.0.0.1', 0), _FakeLocalHandler)
    t = threading.Thread(target=fake.serve_forever, daemon=True)
    t.start()
    try:
        with connect() as conn:
            set_runtime_config(conn, local_backend='openai_compatible', local_endpoint=f'http://127.0.0.1:{fake.server_port}/v1/chat/completions', local_model='test-local')
            result = chat_local(conn, [{'role': 'user', 'content': 'hello'}], require_json=True)
            assert json.loads(result.text)['ok'] is True
            assert result.model == 'test-local'
            bridge = bridge_play(conn, 'I wait here for 2 days.', 'local')
            assert bridge['status'] == 'awaiting_narration'
            local_run = run_request_local(conn, bridge['next_request']['request_id'], force=True, apply=True)
            assert local_run['status'] == 'applied'
            assert local_run['segmented_generation'] is True
            assert local_run['segment_count'] >= 2
            conn.commit()
    finally:
        fake.shutdown(); fake.server_close(); t.join(timeout=2)

    # Mobile server can serve the phone-first state endpoint entirely on localhost.
    server = ThreadingHTTPServer(('127.0.0.1', 0), CaernessHandler)
    st = threading.Thread(target=server.serve_forever, daemon=True)
    st.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/state', timeout=4) as r:
            data = json.loads(r.read().decode('utf-8'))
            assert data['runtime']['story_time_only'] is True
            assert data['world']['name'] == 'Caerness'
    finally:
        server.shutdown(); server.server_close(); st.join(timeout=2)

    print('v07_test: PASS')


if __name__ == '__main__':
    run()
