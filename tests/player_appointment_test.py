from __future__ import annotations

import json
import tempfile
from unittest.mock import patch

from engine.db import connect, init_db, reset_db
from engine.simulation import seed_demo
from engine.player import get_player, build_scene_packet, set_player
from engine.adaptive_planning import create_role
from engine.organization_agency import start_regime
from engine.relationships import ensure_reciprocal_relationship
from engine.model_gateway import bridge_play, import_response, apply_model_request, set_model_config
from engine.actions import begin_player_action
from engine.mobile_runtime import mobile_state


def fixture():
    reset_db(force=True, backup=False)
    init_db()
    seed_demo()
    c = connect()
    commander = int(get_player(c)["player_actor_id"])
    loc = int(get_player(c)["current_location_id"])
    institution = int(c.execute("SELECT id FROM actors WHERE name='[DEMO] River Lantern Escort Company'").fetchone()[0])
    c.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, institution))
    holder = int(c.execute("INSERT INTO actors(name,actor_type,subtype,current_location_id,home_location_id,status) VALUES ('Mara Vale','character','escort officer',?,?,'active')", (loc, loc)).lastrowid)
    start_regime(c, institution, leader_actor_id=commander)
    c.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,joined_day) VALUES (?,?,'service','Escort officer',0)", (institution, holder))
    ensure_reciprocal_relationship(c, commander, holder, 0, trust=85, stance=65, loyalty=70, familiarity=90)
    from engine.presence import add_presence_habit
    add_presence_habit(c, holder, loc, habit_kind='workplace', weight=1, confidence=1)
    role = create_role(c, institution, 'training_captain', 'Training Captain', 'military', role_kind='command',
                       remit={"responsibility": "Train the existing escorts", "required_resources": {"capital": 10}})
    c.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,'capital',20) ON CONFLICT(actor_id,resource_type) DO UPDATE SET amount=20", (institution,))
    packets = tempfile.mkdtemp(prefix='caerness_appointment_packets_')
    set_model_config(c, packet_dir=packets)
    return c, commander, holder, institution, role


def offer(c, text="I approach Mara Vale and offer her the Training Captain responsibility.", confirm=True, **changes):
    queued = bridge_play(c, text, 'generic')
    assert queued['status'] == 'awaiting_action_interpretation'
    p = dict(action_type='appoint', confidence=.98, target_actor_name='Mara Vale',
             institution_name='[DEMO] River Lantern Escort Company', role_title='Training Captain',
             additional_terms=False, purpose=text)
    p.update(changes)
    import_response(c, queued['request_id'], json.dumps(dict(task_type='action_interpretation', request_id=queued['request_id'], proposal=p)))
    result = apply_model_request(c, queued['request_id'])
    if confirm and result.get('turn', {}).get('action_result', {}).get('status') == 'needs_confirmation':
        from engine.actions import confirm_appointment_scope
        turn = confirm_appointment_scope(c, result['turn']['action_result']['action_id'])
        result['turn'] = turn
    return result


def main():
    c, commander, holder, institution, role = fixture()
    output = offer(c)
    result = output['turn']['action_result']
    assert result['status'] == 'applied', result
    assert result['detail']['consent'] == 'accept' and result['detail']['committed']
    assert c.execute('SELECT COUNT(*) FROM institutional_appointments WHERE role_id=?', (role,)).fetchone()[0] == 1
    print('PLAYER: I approach Mara Vale and offer her the Training Captain responsibility.')
    print('ENGINE:', result['summary'])
    # The narrator receives facts, never private reasons or social score inputs.
    envelope = output['turn']['narration_envelope']
    assert 'burden' not in json.dumps(envelope['action_result'])
    assert 'trust' not in json.dumps(envelope['action_result'])
    # Narrator prose cannot create a second role or appointment.
    req = output['next_request']['request_id']
    import_response(c, req, json.dumps(dict(task_type='narration', request_id=req, narration=result['summary'])))
    apply_model_request(c, req)
    c.commit(); c.close()
    c = connect()
    from engine.turns import play_turn
    play_turn(c, 'I wait here for 7 days.')
    c.commit(); c.close(); c = connect()
    offices = mobile_state(c)['matters']['appointments']
    assert any(x['holder_name']=='Mara Vale' and x['title']=='Training Captain' for x in offices)
    assert build_scene_packet(c)['matters']['appointments']
    print('AFTER 7 DAYS + SAVE/RELOAD:', offices)
    repeated = offer(c)['turn']['action_result']
    assert repeated['status'] == 'blocked'
    assert c.execute('SELECT COUNT(*) FROM institutional_appointments WHERE role_id=?', (role,)).fetchone()[0] == 1
    c.close()

    # Grounded refusal despite authority and resources, using the existing social resolver.
    c, commander, holder, institution, role = fixture()
    c.execute('UPDATE relationships SET trust=-100,stance=-100,obligation=-100 WHERE actor_a_id=? AND actor_b_id=?', (holder, commander))
    result = offer(c)['turn']['action_result']
    assert result['status'] == 'refused', result
    assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
    print('REFUSAL:', result['summary'])
    c.close()

    c, commander, holder, institution, role = fixture()
    c.execute('UPDATE relationships SET trust=0,stance=0,obligation=0 WHERE actor_a_id=? AND actor_b_id=?', (holder, commander))
    output = offer(c)
    result = output['turn']['action_result']
    assert result['status'] == 'countered', result
    assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
    pending = output['turn']['narration_envelope']['scene_after']['pending_player_interactions']
    assert pending and all('burden' not in x['terms'] for x in pending)
    from engine.turns import play_turn
    agreed = play_turn(c, 'I accept the offer.')
    assert c.execute('SELECT 1 FROM institutional_appointments WHERE holder_actor_id=? AND role_id=?', (holder, role)).fetchone()
    print('COUNTERPROPOSAL:', result['summary'])
    c.close()

    for interpretation in ('observe', 'speak', 'wait'):
        c, *_ = fixture()
        outcome = offer(c, action_type=interpretation)
        assert outcome['status'] == 'not_applied'
        assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
        c.close()
    c, *_ = fixture()
    result = offer(c, text='I offer Mara Vale the Training Captain responsibility and pay her 100 gold.')['turn']['action_result']
    assert result['status'] == 'blocked' and not result['detail']['committed']
    c.close()
    c, *_ = fixture()
    incomplete = offer(c, text='I offer Mara Vale Training Captain and promise her my black horse.', confirm=False)
    assert incomplete['turn']['action_result']['status'] == 'needs_confirmation'
    assert 'black horse' in incomplete['turn']['action_result']['detail']['original_instruction']
    assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
    from engine.actions import HeuristicPlayerActionProvider
    from engine.model_gateway import proposal_from_action_response
    for text in ('I approach Mara Vale and offer her a seat.', 'I ask Mara Vale about the merchant offer.', 'I wait for the offer to arrive.'):
        p = HeuristicPlayerActionProvider().propose(c, text)
        assert not p.needs_interpretation, (text, p)
        interpreted = proposal_from_action_response(c, text, {'proposal': {'action_type': p.action_type, 'target_actor_name':'Mara Vale'}})
        assert not interpreted.needs_interpretation, interpreted
    c.close()

    for constraint in ('authority', 'resources', 'membership', 'competence', 'absent', 'unknown_role', 'extra_terms'):
        c, commander, holder, institution, role = fixture()
        changes = {}
        if constraint == 'authority': c.execute('UPDATE organization_regimes SET leader_actor_id=?', (holder,))
        if constraint == 'resources': c.execute("UPDATE resources SET amount=0 WHERE actor_id=?", (institution,))
        if constraint == 'membership': c.execute('DELETE FROM institution_memberships WHERE member_actor_id=?', (holder,))
        if constraint == 'competence': c.execute('UPDATE institutional_roles SET minimum_candidate_quality=80 WHERE id=?', (role,))
        if constraint == 'absent':
            c.execute('UPDATE actors SET current_location_id=NULL,home_location_id=NULL WHERE id=?', (holder,))
            c.execute('DELETE FROM actor_presence_habits WHERE actor_id=?', (holder,))
            c.execute('UPDATE actor_presence_profiles SET base_location_id=NULL WHERE actor_id=?', (holder,))
        if constraint == 'unknown_role': changes['role_title'] = 'Commander of an invented division'
        if constraint == 'extra_terms': changes['additional_terms'] = True
        result = offer(c, **changes)['turn']['action_result']
        assert result['status'] == 'blocked', (constraint, result)
        assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
        assert not c.execute('SELECT 1 FROM opportunity_proposals').fetchone()
        print(constraint.upper()+':', result['summary'])
        c.close()

    # Revalidate inside the domain executor even if state changes after consent.
    c, commander, holder, institution, role = fixture()
    from engine import player_appointments
    original = player_appointments.validate_appointment
    calls = 0
    def changed(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            c.execute("UPDATE resources SET amount=0 WHERE actor_id=?", (institution,))
        return original(*args)
    with patch.object(player_appointments, 'validate_appointment', side_effect=changed):
        result = offer(c)['turn']['action_result']
    assert result['status'] == 'blocked' and result['detail']['consent'] == 'accept'
    assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
    print('CONSENT WITHOUT COMMIT:', result['summary'])
    # Unsupported intent stays an attempt; no successful observation substituted.
    _, unsupported = begin_player_action(c, 'I conjure a golden palace from nothing.')
    assert unsupported.status == 'needs_interpretation'
    assert unsupported.action_type == 'attempt'
    set_player(c, holder)
    assert not mobile_state(c)['matters']['appointments']
    assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
    assert not c.execute('pragma foreign_key_check').fetchall()
    c.close()
    print('PLAYER APPOINTMENT: PASS')


if __name__ == '__main__':
    main()
