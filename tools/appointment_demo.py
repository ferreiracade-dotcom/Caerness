"""Offline, isolated gameplay demonstration: python tools/appointment_demo.py [--serve].

Uses the real interpreter contract/executor/mobile UI with a deliberately bounded
model stub. It cannot evaluate arbitrary language; real play uses the configured LLM.
Every invocation creates a fresh temporary save. The packaged opening is never opened.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile


def demo_input(conn, text, **kwargs):
    from engine.mobile_runtime import process_player_input
    from engine.model_gateway import import_response, apply_model_request
    from engine.turns import TemplateNarratorProvider
    low = text.lower()
    if not re.search(r"appoint|offer|promot|responsibilit|in charge", low):
        return process_player_input(conn, text, mode='rules')
    queued = process_player_input(conn, text, mode='chatgpt')
    req = queued['request_id']
    supported = 'mara' in low and ('training captain' in low or 'training' in low)
    proposal = {
        'action_type': 'appoint' if supported else 'attempt', 'confidence': 1,
        'target_actor_name': 'Mara Vale', 'role_title': 'Training Captain',
        'institution_name': '[DEMO] River Lantern Escort Company',
        'additional_terms': bool(re.search(r'gold|money|pay|new division|new company', low)),
        'needs_interpretation': not supported,
        'note': 'The offline demo only understands offers to Mara to lead training. Full free-form interpretation requires a configured model.',
    }
    import_response(conn, req, json.dumps(dict(task_type='action_interpretation', request_id=req, proposal=proposal)))
    applied = apply_model_request(conn, req)
    if applied['status'] == 'not_applied':
        return {'status': 'complete', 'narration': applied['summary']}
    turn = applied['turn']
    narration = TemplateNarratorProvider().narrate(turn['narration_envelope'])
    nreq = applied['next_request']['request_id']
    import_response(conn, nreq, json.dumps(dict(task_type='narration', request_id=nreq, narration=narration)))
    apply_model_request(conn, nreq)
    return {'status': 'complete', 'source': 'offline-demo-stub', 'turn': turn, 'narration': narration}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--serve', action='store_true', help='Open the existing phone-friendly UI on localhost:8765')
    ap.add_argument('--refusal', action='store_true', help='The subordinate distrusts the commander in this alternative save')
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(root), str(root / 'tests')]
    with tempfile.TemporaryDirectory(prefix='caerness_appointment_demo_') as work:
        os.environ['CAERNESS_DB_PATH'] = str(Path(work) / 'demo.db')
        os.environ['CAERNESS_BACKUP_DIR'] = str(Path(work) / 'backups')
        os.environ['CAERNESS_TEST_MODE'] = '1'
        from player_appointment_test import fixture
        from engine.db import connect
        from engine.mobile_runtime import mobile_state
        c, commander, holder, institution, role = fixture()
        if args.refusal:
            c.execute('UPDATE relationships SET trust=-100,stance=-100,obligation=-100 WHERE actor_a_id=? AND actor_b_id=?', (holder, commander))
        c.commit(); c.close()
        print('Isolated demonstration. Fictional test characters; bounded model stub, real SQLite executor.')
        if args.serve:
            from engine import mobile_server
            mobile_server.process_player_input = demo_input
            print('Open http://127.0.0.1:8765 and enter: I offer Mara Vale the Training Captain responsibility.')
            print('Then: I wait here for 7 days. Reload the page and open Matters to see the saved appointment.')
            mobile_server.serve()
            return
        for text in ('I approach Mara Vale and offer her the Training Captain responsibility.', 'I wait here for 7 days.', 'I look around.'):
            with connect() as c:
                result = demo_input(c, text)
                print('PLAYER:', text)
                print('GAME:', result['narration'])
        with connect() as c:
            state = mobile_state(c)
            print('REOPENED SAVE, DAY', state['world']['day'])
            print('MATTERS:', json.dumps(state['matters']['appointments']))


if __name__ == '__main__':
    main()
