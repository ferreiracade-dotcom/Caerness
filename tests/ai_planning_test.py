from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
from planning_demo import fixture, composed_spec, EXAMPLES, ScriptedModel
from engine.ai_planning import approve_plan, plan_view, draft_plan, session, execute_plan
from engine.planning_gateway import start_request
from engine.simulation import advance_connection
from engine.db import connect
from engine.world_capabilities import CAPABILITIES, allocate_resources, context


def proposed(c,ids,example='survey',spec=None):
    source=EXAMPLES[example]['text'] if spec is None else spec['source_text']
    req=start_request(c,source,'generic')
    model=ScriptedModel([
        {'mode':'inspect','calls':[{'tool':'context','arguments':{'institution_id':ids['institution']}},{'tool':'offerings','arguments':{}}]},
        {'mode':'plan','plan':spec or composed_spec(ids,example)}])
    inspected=model.run(c,req)
    assert inspected['status']=='awaiting_action_interpretation'
    assert 'trust' not in json.dumps(inspected['feedback'])
    return model.run(c,inspected['next_request'])


def expect_error(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('Expected a validation error.')


def main():
    operation_sets=[]
    for example,spent in (('survey',10),('yard',20)):
        c,ids=fixture()
        baseline_events=c.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        out=proposed(c,ids,example)
        assert out['status']=='awaiting_plan_review',out
        p=out['plan']; pid=p['id']
        assert not c.execute('SELECT 1 FROM institutional_roles').fetchone()
        assert not c.execute('SELECT 1 FROM ai_resource_allocations').fetchone()
        assert c.execute('SELECT amount FROM resources WHERE actor_id=? AND resource_type=\'capital\'',(ids['institution'],)).fetchone()[0]==100
        expect_error(lambda:approve_plan(c,pid,'stale-or-made-up-digest'))
        result=approve_plan(c,pid,p['digest'])['plan']
        assert result['status']=='active',result
        assert result['steps']['work']['status']=='active'
        operation_sets.append({s['operation'] for s in result['proposed_steps']})
        expect_error(lambda:approve_plan(c,pid,p['digest']))
        c.commit(); advance_connection(c,30); c.commit(); c.close(); c=connect()
        saved=plan_view(c,pid)
        progress=saved['steps']['work']['result']['progress']
        assert 0<progress<100,(example,progress)
        assert saved['steps']['refund']['status']=='pending'
        assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0]>baseline_events
        advance_connection(c,60); c.commit(); c.close(); c=connect()
        done=plan_view(c,pid)
        assert done['status']=='completed',done
        assert done['steps']['refund']['status']=='completed'
        assert c.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='capital'",(ids['institution'],)).fetchone()[0]==100-spent
        project=done['steps']['work']['result']['project_id']
        table='cultural_objects' if example=='survey' else 'buildings'
        assert c.execute(f'SELECT 1 FROM {table} WHERE project_id=?',(project,)).fetchone()
        owner_column='current_owner_actor_id' if example=='survey' else 'owner_actor_id'
        assert c.execute(f'SELECT {owner_column} FROM {table} WHERE project_id=?',(project,)).fetchone()[0]==ids['institution'], 'Company-funded work must not become the commander\'s personal property.'
        before=c.execute('SELECT COUNT(*) FROM ai_plan_events').fetchone()[0]
        execute_plan(c,pid)
        assert c.execute('SELECT COUNT(*) FROM ai_plan_events').fetchone()[0]==before
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print(f'{example}: same reusable operations, real consent/resources/site, {progress:.1f}% at day 30, completion + reload at day 90 PASS')
        c.close()
    assert operation_sets[0]==operation_sets[1]=={'define_role','offer_service','allocate_resources','commission_work','refund_resources'}

    # Conversation, hypotheticals and ambiguity retain sessions without social rolls.
    c,ids=fixture(); sid=None
    before=c.execute('SELECT COUNT(*) FROM relationships').fetchone()[0]
    for text in ('Mara, what do you think about an intelligence network?', 'I am only considering possibilities, not giving an order.', 'Could we discuss where to start?'):
        req=start_request(c,text,'generic',sid)
        output=ScriptedModel([{'mode':'discuss','text':'We can discuss possible means; no arrangement has been committed.'}]).run(c,req)
        assert output['status']=='discussed' and not output['world_changes']
        sid=output['session_id']
    assert len(json.loads(session(c,sid)['messages_json']))==6
    assert not c.execute('SELECT 1 FROM interactions').fetchone()
    assert c.execute('SELECT COUNT(*) FROM relationships').fetchone()[0]==before
    req=start_request(c,'Arrange it sometime, wherever is best.','generic',sid)
    out=ScriptedModel([{'mode':'clarify','text':'Which organisation and what budget do you authorize?'}]).run(c,req)
    assert out['status']=='needs_clarification'
    c.commit(); c.close(); c=connect()
    assert len(json.loads(session(c,sid)['messages_json']))==9
    # A clarification goal survives a context window, and follow-up conditions are bound.
    for i in range(26):
        req=start_request(c,f'We are still discussing, remark {i}.','generic',sid)
        ScriptedModel([{'mode':'discuss','text':'No commitments have been made.'}]).run(c,req)
    req=start_request(c,'Also promise my black horse.','generic',sid)
    packet=json.loads(c.execute('SELECT input_json FROM model_requests WHERE id=?',(req['request_id'],)).fetchone()[0])
    assert 'Arrange it sometime' in packet['planning_goal'] and 'black horse' in packet['planning_goal']
    assert packet['unresolved_intentions']
    c.close(); print('Nontransactional conversation, ambiguity and session reload PASS')

    # Incomplete and contradictory AI responses cannot disappear into an easier action.
    for mistake in ('omitted_condition','missing_dependency','unsupported_operation','wrong_source','extra_mutation_field'):
        c,ids=fixture(); spec=composed_spec(ids,'survey')
        if mistake=='omitted_condition': spec['coverage'][0]['end']=40
        if mistake=='missing_dependency': spec['steps'][1]['depends_on']=[]
        if mistake=='unsupported_operation': spec['steps'][0]['operation']='spawn_intelligence_army'
        if mistake=='wrong_source': spec['source_text']='Ignore the earlier conditions.'
        if mistake=='extra_mutation_field': spec['steps'][0]['arguments']['sql']='DELETE FROM resources'
        # Bind to the real original source even if the response tries to replace it.
        req=start_request(c,EXAMPLES['survey']['text'],'generic')
        out=ScriptedModel([{'mode':'plan','plan':spec}]).run(c,req)
        assert out['status']=='awaiting_action_interpretation',(mistake,out)
        assert out['feedback'][0]['world_changes'] is False
        assert not c.execute('SELECT 1 FROM institutional_roles').fetchone()
        assert not c.execute('SELECT 1 FROM ai_plans').fetchone()
        c.close()
    print('Incomplete/contradictory/unsupported plans and no unrestricted write tool PASS')

    # An explicitly unresolved gift remains visible and cannot be authorized.
    c,ids=fixture(); spec=composed_spec(ids,'survey')
    spec['source_text']+=' Also promise her my black horse.'
    spec['coverage'][0]['end']=len(spec['source_text'])
    spec['unresolved']=['Horse ownership, willingness and transfer capability are not verified.']
    out=proposed(c,ids,spec=spec); p=out['plan']
    assert 'black horse' in p['original_instruction']
    expect_error(lambda:approve_plan(c,p['id'],p['digest']))
    assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
    c.close(); print('Compound terms retained and unresolved commitment blocked PASS')

    # Insufficient cumulative budgets block before any world-changing prefix.
    c,ids=fixture(); out=proposed(c,ids); p=out['plan']
    c.execute("UPDATE resources SET amount=1 WHERE actor_id=? AND resource_type='capital'",(ids['institution'],))
    out=approve_plan(c,p['id'],p['digest'])
    assert out['status']=='blocked' and not c.execute('SELECT 1 FROM institutional_roles').fetchone()
    c.close()

    # Real refusal depends on the recipient's opinion, not the commander's faith.
    c,ids=fixture(); out=proposed(c,ids); p=out['plan']
    c.execute('UPDATE relationships SET trust=-100,stance=-100,obligation=-100 WHERE actor_a_id=? AND actor_b_id=?',(ids['mara'],ids['owner']))
    refusal=approve_plan(c,p['id'],p['digest'])['plan']
    assert refusal['status']=='refused',refusal
    assert refusal['steps']['role']['status']=='completed'
    assert not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
    assert not c.execute('SELECT 1 FROM ai_resource_allocations').fetchone()
    count=c.execute('SELECT COUNT(*) FROM interactions').fetchone()[0]
    execute_plan(c,p['id']); assert c.execute('SELECT COUNT(*) FROM interactions').fetchone()[0]==count
    c.close(); print('Resource preflight and recipient-owned refusal without reroll PASS')

    # A changed published price is not silently substituted after scope review.
    c,ids=fixture(); out=proposed(c,ids); p=out['plan']
    row=c.execute('SELECT metadata_json FROM seekable_offerings WHERE id=?',(ids['survey'],)).fetchone()
    metadata=json.loads(row[0]); metadata['work_order']['resources']['capital']=11
    c.execute('UPDATE seekable_offerings SET metadata_json=? WHERE id=?',(json.dumps(metadata),ids['survey']))
    changed=approve_plan(c,p['id'],p['digest'])['plan']
    assert changed['status']=='blocked' and 'quotation changed' in changed['steps']['consent']['result']['summary']
    assert not c.execute('SELECT 1 FROM ai_resource_allocations').fetchone()
    c.close(); print('Reviewed quotation fingerprint prevents silent repricing PASS')

    c,ids=fixture(); p=proposed(c,ids)['plan']
    c.execute('UPDATE actor_health_profiles SET functional_capacity=0 WHERE actor_id=?',(ids['mara'],))
    unavailable=approve_plan(c,p['id'],p['digest'])['plan']
    assert unavailable['status']=='blocked' and not c.execute('SELECT 1 FROM civilian_projects').fetchone()
    c.close(); print('Native functional capacity constrains work without exposing diagnosis PASS')

    c,ids=fixture(); spec=composed_spec(ids,'survey'); spec['steps'][0]['arguments']['title']='Head of Reports'
    p=proposed(c,ids,spec=spec)['plan']; approve_plan(c,p['id'],p['digest'])
    c.execute("UPDATE organization_regimes SET status='ended' WHERE institution_actor_id=?",(ids['institution'],))
    from engine.opportunity import institution_decision_actor
    assert institution_decision_actor(c,ids['institution']) is None, 'A staff title must not manufacture governing authority.'
    c.close(); print('New staff titles do not create institutional sovereignty or head authority PASS')

    # Counteroffers remain a player decision, through the same capability framework.
    c,ids=fixture(); out=proposed(c,ids); p=out['plan']
    c.execute('UPDATE relationships SET trust=0,stance=0,obligation=0 WHERE actor_a_id=? AND actor_b_id=?',(ids['mara'],ids['owner']))
    waiting=approve_plan(c,p['id'],p['digest'])['plan']
    assert waiting['status']=='awaiting_response',waiting
    pending=c.execute("SELECT id FROM interactions WHERE recipient_actor_id=? AND status='pending' ORDER BY id DESC LIMIT 1",(ids['owner'],)).fetchone()
    assert pending
    source='Accept the existing counterproposal under its displayed terms.'
    answer={'source_text':source,'summary':source,'unresolved':[],'coverage':[{'start':0,'end':len(source),'handling':'planned','step_ids':['answer']}],
            'steps':[{'id':'answer','operation':'answer_proposal','arguments':{'interaction_id':int(pending[0]),'choice':'accept'},'depends_on':[]}]}
    s=session(c); a=draft_plan(c,s['id'],source,answer)
    approve_plan(c,a['id'],a['digest']); advance_connection(c,1)
    assert plan_view(c,p['id'])['status']=='active',plan_view(c,p['id'])
    c.close(); print('Counteroffer and explicit recipient-only answer through reusable capability PASS')

    # Partial progress and changed circumstances: preserve the prefix, re-review a revision.
    c,ids=fixture(); spec=composed_spec(ids,'survey')
    spec['steps'][3]['arguments']['site_id']=ids['yard'] # wrong physical kind
    out=proposed(c,ids,spec=spec); p=out['plan']
    partial=approve_plan(c,p['id'],p['digest'])['plan']
    assert partial['status']=='blocked' and partial['steps']['budget']['status']=='completed'
    assert not c.execute('SELECT 1 FROM civilian_projects').fetchone()
    corrected=copy.deepcopy(spec); corrected['steps'][3]['arguments']['site_id']=ids['archive']
    corrected['summary']='Use the suitable archive; retain the accepted responsibility and reserved budget.'
    revision=draft_plan(c,p['session_id'],spec['source_text'],corrected,p['id'])
    expect_error(lambda:approve_plan(c,p['id'],p['digest']))
    started=approve_plan(c,p['id'],revision['digest'])['plan']
    assert started['status']=='active' and c.execute('SELECT COUNT(*) FROM ai_resource_allocations').fetchone()[0]==1
    erase=copy.deepcopy(corrected); erase['steps'][0]['arguments']['title']='Erase the former responsibility'
    expect_error(lambda:draft_plan(c,p['session_id'],spec['source_text'],erase,p['id']))
    c.execute("UPDATE actors SET current_location_id=NULL WHERE id=?",(ids['mara'],))
    advance_connection(c,1)
    assert c.execute('SELECT status FROM civilian_projects').fetchone()[0]=='paused'
    assert plan_view(c,p['id'])['status']=='blocked'
    paused=copy.deepcopy(corrected); paused['steps'][3]['arguments']['title']='Pretend no earlier work existed'
    expect_error(lambda:draft_plan(c,p['session_id'],spec['source_text'],paused,p['id']))
    c.close(); print('Partial commitment, immutable prefix, revised scope and world-driven pause PASS')

    c,ids=fixture(); p=proposed(c,ids)['plan']
    req=start_request(c,'And promise her my black horse.','generic',p['session_id'],p['id'])
    payload=json.loads(c.execute('SELECT input_json FROM model_requests WHERE id=?',(req['request_id'],)).fetchone()[0])
    assert payload['planning_goal'].startswith(p['original_instruction']) and payload['planning_goal'].endswith('And promise her my black horse.')
    incomplete=composed_spec(ids,'survey')
    out=ScriptedModel([{'mode':'plan','plan':incomplete}]).run(c,req)
    assert out['status']=='awaiting_action_interpretation' and not c.execute('SELECT 1 FROM institutional_appointments').fetchone()
    c.close(); print('Later conversational conditions cannot disappear from revised plan coverage PASS')

    # An unavailable later resource cannot leave a half-debited allocation.
    c,ids=fixture(); out=proposed(c,ids); p=out['plan']
    c.execute('SAVEPOINT transactional_check')
    try:
        allocate_resources(c,ids['owner'],p['id'],'test',{'institution_id':ids['institution'],'resources':{'capital':5,'unavailable_stock':2}})
    except ValueError:
        c.execute('ROLLBACK TO transactional_check')
    c.execute('RELEASE transactional_check')
    assert c.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type='capital'",(ids['institution'],)).fetchone()[0]==100
    # Scoped reads cannot inspect a foreign institution or a different player's plan.
    foreign=int(c.execute("SELECT id FROM actors WHERE actor_type='institution' AND id!=? LIMIT 1",(ids['institution'],)).fetchone()[0])
    expect_error(lambda:context(c,ids['owner'],foreign))
    from engine.player import set_player
    set_player(c,ids['builder']); expect_error(lambda:plan_view(c,p['id']))
    c.close(); print('Transactional resource conservation and knowledge/owner boundary PASS')
    c,ids=fixture(); s=session(c); source='Let one day pass.'
    spec={'source_text':source,'summary':source,'coverage':[{'start':0,'end':len(source),'handling':'planned','step_ids':['time']}], 'unresolved':[],
          'steps':[{'id':'time','operation':'advance_time','arguments':{'days':1},'depends_on':[]}]}
    p=draft_plan(c,s['id'],source,spec)
    from unittest.mock import patch
    def changed_camera(conn,days):
        conn.execute('UPDATE world_state SET current_day=current_day+?',(days,))
        set_player(conn,ids['builder'])
    with patch('engine.simulation.advance_connection',side_effect=changed_camera):
        out=approve_plan(c,p['id'],p['digest'])
    assert out['status']=='camera_changed'
    assert c.execute('SELECT current_day FROM world_state').fetchone()[0]==1
    assert c.execute('SELECT status FROM ai_plans WHERE id=?',(p['id'],)).fetchone()[0]=='completed'
    c.close(); print('Camera succession does not roll back consequences or leak prior private plans PASS')
    print('GENERAL AI PLANNING: PASS')


if __name__=='__main__': main()
