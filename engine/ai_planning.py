"""Persistent reviewed plans, composable operations and transactional progress.

There is no parser for intelligence services, schools, bargains or any other player
idea here. AI responses are proposals. A direct player approval pins a plan digest;
each world operation then validates its own authority and causal prerequisites.
"""
from __future__ import annotations

import json
from pathlib import Path

from .world_capabilities import CAPABILITIES, check_arguments, day, digest, dump


def available(c):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_plans'").fetchone() is not None


def ensure_schema(c):
    if available(c): return
    # execute() preserves the caller's transaction; executescript() would commit it.
    for statement in Path(__file__).with_name('planning_schema.sql').read_text().split(';'):
        if statement.strip(): c.execute(statement)


def current_actor(c):
    from .player import get_player
    p = get_player(c)
    if not p: raise ValueError('Configure a player first.')
    return int(p['player_actor_id'])


def session(c, session_id=None):
    ensure_schema(c)
    owner = current_actor(c)
    if session_id is None:
        session_id = int(c.execute('INSERT INTO ai_sessions(owner_actor_id,created_day) VALUES (?,?)',(owner,day(c))).lastrowid)
    row = c.execute('SELECT * FROM ai_sessions WHERE id=? AND owner_actor_id=?',(session_id,owner)).fetchone()
    if not row: raise ValueError('This conversation does not belong to the current player.')
    return dict(row)


def message(c, session_id, role, text):
    s = session(c,session_id)
    messages = json.loads(s['messages_json'])
    messages.append({'role':role,'text':text,'day':day(c)})
    c.execute('UPDATE ai_sessions SET messages_json=? WHERE id=?',(dump(messages),session_id))


def event(c, plan_id, kind, detail):
    c.execute('INSERT INTO ai_plan_events(plan_id,day,kind,detail_json) VALUES (?,?,?,?)',(plan_id,day(c),kind,dump(detail)))


def check_spec(spec, source):
    if not isinstance(spec,dict) or set(spec) != {'source_text','summary','coverage','unresolved','steps'}:
        raise ValueError('A plan requires source_text, summary, coverage, unresolved and steps; extra fields are forbidden.')
    if spec['source_text'] != source or not isinstance(spec['summary'],str) or not spec['summary'].strip():
        raise ValueError('Preserve the complete original intention and provide a readable proposed scope.')
    if not isinstance(spec['unresolved'],list) or any(not isinstance(x,str) or not x.strip() for x in spec['unresolved']):
        raise ValueError('Unresolved conditions must be explicit text, not discarded.')
    steps = spec['steps']
    if not isinstance(steps,list) or len(steps)>32: raise ValueError('Use at most 32 steps in this planning tranche.')
    keys, outputs = set(), {}
    for step in steps:
        if not isinstance(step,dict) or set(step) != {'id','operation','arguments','depends_on'}:
            raise ValueError('Each step requires exactly id, operation, arguments and depends_on.')
        key = step['id']
        if not isinstance(key,str) or not key.isidentifier() or key in keys:
            raise ValueError('Step IDs must be unique identifiers.')
        deps = step['depends_on']
        if not isinstance(deps,list) or any(not isinstance(x,str) or x not in keys for x in deps):
            raise ValueError('Dependencies must refer to earlier steps; cycles and missing dependencies are not permitted.')
        check_arguments(step['operation'],step['arguments'],allow_refs=True)
        for arg in step['arguments'].values():
            if isinstance(arg,dict) and set(arg)=={'ref'}:
                parts = arg['ref'].split('.')
                if len(parts)!=2 or parts[0] not in deps or parts[1] not in outputs.get(parts[0],()):
                    raise ValueError('A result reference requires a dependency and a declared capability output.')
        keys.add(key); outputs[key] = CAPABILITIES[step['operation']].outputs
    # Every non-space character must be accounted for. A model cannot drop the
    # second half of a compound instruction while returning a completion boolean.
    covered = set()
    if not isinstance(spec['coverage'],list): raise ValueError('Supply explicit source coverage spans.')
    for span in spec['coverage']:
        if not isinstance(span,dict) or set(span) != {'start','end','handling','step_ids'}:
            raise ValueError('Coverage spans require start,end,handling,step_ids.')
        start,end = span['start'],span['end']
        if type(start) is not int or type(end) is not int or not 0<=start<end<=len(source):
            raise ValueError('Source coverage offsets are invalid.')
        if span['handling'] not in ('planned','unresolved','context') or not isinstance(span['step_ids'],list) or any(k not in keys for k in span['step_ids']):
            raise ValueError('Source conditions must map to real steps or explicit unresolved requirements.')
        if span['handling']=='planned' and not span['step_ids']: raise ValueError('A planned condition requires at least one operation.')
        if span['handling']=='unresolved' and not spec['unresolved']: raise ValueError('An unresolved span requires a visible unresolved condition.')
        indices=set(range(start,end))
        if covered & indices: raise ValueError('Source coverage spans must not overlap.')
        covered |= indices
    if any(i not in covered for i,ch in enumerate(source) if not ch.isspace()):
        raise ValueError('The interpretation omits part of the instruction. Nothing can be executed until those terms are accounted for.')
    if not steps and not spec['unresolved']: raise ValueError('An empty plan must explain what remains unresolved.')


def draft_plan(c, session_id, source, spec, plan_id=None):
    s = session(c,session_id)
    check_spec(spec,source)
    hashed = digest(spec)
    if plan_id is None:
        plan_id = int(c.execute('INSERT INTO ai_plans(session_id,owner_actor_id,source_text,spec_json,digest,created_day,updated_day) VALUES (?,?,?,?,?,?,?)',
            (session_id,s['owner_actor_id'],source,dump(spec),hashed,day(c),day(c))).lastrowid)
    else:
        old = owned_plan(c,plan_id)
        if old['session_id'] != session_id or (old['source_text'] != source and not source.startswith(old['source_text']+'\nFollow-up: ')):
            raise ValueError('A revision must preserve the plan owner, conversation and complete prior intention. Amendments are appended, never substituted.')
        steps = {x['id']:x for x in spec['steps']}
        for r in c.execute('SELECT * FROM ai_plan_steps WHERE plan_id=?',(plan_id,)):
            result=json.loads(r['result_json'])
            has_effects=any(result.get(k) for k in ('project_id','allocation_id','appointment_id','engagement_id'))
            if (has_effects or r['status'] in ('completed','active','awaiting_response')) and steps.get(r['step_key']) != json.loads(r['spec_json']):
                raise ValueError('A revision cannot erase or reroll committed work, spending or an unresolved proposal. Preserve it and append/revise unexecuted steps.')
        for r in c.execute("SELECT step_key,result_json FROM ai_plan_steps WHERE plan_id=? AND status IN ('pending','blocked','refused')",(plan_id,)).fetchall():
            result=json.loads(r['result_json'])
            if not any(result.get(k) for k in ('project_id','allocation_id','appointment_id','engagement_id')):
                c.execute('DELETE FROM ai_plan_steps WHERE plan_id=? AND step_key=?',(plan_id,r['step_key']))
        c.execute("UPDATE ai_plans SET revision=revision+1,source_text=?,spec_json=?,digest=?,approved_digest=NULL,status='draft',updated_day=? WHERE id=?",(source,dump(spec),hashed,day(c),plan_id))
    for step in spec['steps']:
        c.execute('INSERT OR IGNORE INTO ai_plan_steps(plan_id,step_key,spec_json) VALUES (?,?,?)',(plan_id,step['id'],dump(step)))
    event(c,plan_id,'drafted',{'spec':spec,'digest':hashed})
    return plan_view(c,plan_id)


def owned_plan(c,plan_id):
    ensure_schema(c)
    row=c.execute('SELECT * FROM ai_plans WHERE id=? AND owner_actor_id=?',(plan_id,current_actor(c))).fetchone()
    if not row: raise ValueError('This plan is not available to the current player.')
    return dict(row)


def plan_view(c,plan_id,check_owner=True):
    row=owned_plan(c,plan_id) if check_owner else dict(c.execute('SELECT * FROM ai_plans WHERE id=?',(plan_id,)).fetchone())
    spec=json.loads(row['spec_json'])
    steps={r['step_key']:{'status':r['status'],'result':json.loads(r['result_json'])} for r in c.execute('SELECT * FROM ai_plan_steps WHERE plan_id=?',(plan_id,))}
    from .world_capabilities import describe_scope
    return {'id':row['id'],'session_id':row['session_id'],'revision':row['revision'],'digest':row['digest'],
        'status':row['status'],'original_instruction':row['source_text'],'summary':spec['summary'],
        'unresolved':spec['unresolved'],'proposed_steps':spec['steps'],'steps':steps,
        'review_scope':[describe_scope(c,row['owner_actor_id'],s) for s in spec['steps']],
        'authorization_notice':'Authorize only the engine-listed operations below, not an unlisted consequence. If this scope omits a condition from your original instruction, discuss/revise it before authorizing.'}


def resolve_arguments(step, results):
    args={}
    for key,value in step['arguments'].items():
        if isinstance(value,dict) and set(value)=={'ref'}:
            prior,field=value['ref'].split('.')
            value=results[prior].get(field)
        args[key]=value
    check_arguments(step['operation'],args)
    return args


def approve_plan(c,plan_id,expected_digest):
    row=owned_plan(c,plan_id)
    if row['status']!='draft' or expected_digest!=row['digest']: raise ValueError('The reviewed plan changed or was already approved. Review its current version.')
    spec=json.loads(row['spec_json']); check_spec(spec,row['source_text'])
    if spec['unresolved']: raise ValueError('Unresolved conditions need clarification or an explicit revised scope before authorization.')
    # Preflight cumulative material reservations before any operation commits.
    from .world_capabilities import authority
    budgets={}
    for step in spec['steps']:
        prior=c.execute('SELECT status FROM ai_plan_steps WHERE plan_id=? AND step_key=?',(plan_id,step['id'])).fetchone()
        if prior and prior[0] in ('completed','active','awaiting_response'): continue
        if step['operation']=='allocate_resources' and type(step['arguments']['institution_id']) is int:
            inst=step['arguments']['institution_id']; authority(c,row['owner_actor_id'],inst)
            for resource,amount in step['arguments']['resources'].items(): budgets[(inst,resource)]=budgets.get((inst,resource),0)+amount
    for (inst,resource),amount in budgets.items():
        stock=c.execute('SELECT amount FROM resources WHERE actor_id=? AND resource_type=?',(inst,resource)).fetchone()
        if not stock or float(stock[0])<amount:
            event(c,plan_id,'preflight_blocked',{'summary':f'Insufficient {resource} for the proposed allocations.'})
            return {'status':'blocked','summary':f'Insufficient {resource}. No plan operations were committed.','plan':plan_view(c,plan_id)}
    c.execute("UPDATE ai_plans SET approved_digest=?,status='approved',updated_day=? WHERE id=?",(expected_digest,day(c),plan_id))
    event(c,plan_id,'player_authorized',{'digest':expected_digest})
    execute_plan(c,plan_id)
    if current_actor(c)!=row['owner_actor_id']:
        return {'status':'camera_changed','summary':'The camera character changed during world time. Consequences remain saved; the new character does not automatically inherit the old private plan context.'}
    return {'status':'resolved','plan':plan_view(c,plan_id)}


def execute_plan(c,plan_id):
    from .world_capabilities import service_result
    row=c.execute('SELECT * FROM ai_plans WHERE id=?',(plan_id,)).fetchone()
    if not row or row['approved_digest']!=row['digest'] or row['status'] in ('draft','blocked','completed','executing'):
        return
    c.execute("UPDATE ai_plans SET status='executing' WHERE id=?",(plan_id,))
    spec=json.loads(row['spec_json']); results={}
    for step in spec['steps']:
        stored=c.execute('SELECT * FROM ai_plan_steps WHERE plan_id=? AND step_key=?',(plan_id,step['id'])).fetchone()
        state=stored['status']; result=json.loads(stored['result_json'])
        if state=='awaiting_response':
            result=service_result(c,result['proposal_id'],result['interaction_id'])
            state=result['state']
            # Follow accepted native counterproposals, preserving the original terms guard.
            if state=='awaiting_response':
                from .opportunity import _proposal_interaction
                child=c.execute("SELECT id,status FROM opportunity_proposals WHERE parent_proposal_id=? ORDER BY id DESC LIMIT 1",(result['proposal_id'],)).fetchone()
                if child and child['status']=='accepted':
                    ir=_proposal_interaction(c,int(child['id']))
                    if ir: result=service_result(c,int(child['id']),int(ir['id'])); state=result['state']
            c.execute('UPDATE ai_plan_steps SET status=?,result_json=? WHERE plan_id=? AND step_key=?',(state,dump(result),plan_id,step['id']))
        if state=='active':
            project=c.execute('SELECT status,progress FROM civilian_projects WHERE id=?',(result['project_id'],)).fetchone()
            result['progress']=float(project['progress']) if project else 0
            if not project or project['status'] in ('paused','failed','abandoned'):
                state='blocked'; result['summary']='The delegated work is paused or unavailable; investigate its prerequisites before revising the plan.'
            elif project['status']=='completed':
                state='completed'; result['state']=state; result['summary']='The native world simulation completed the delegated work.'
            c.execute('UPDATE ai_plan_steps SET status=?,result_json=? WHERE plan_id=? AND step_key=?',(state,dump(result),plan_id,step['id']))
        if state in ('completed','active'):
            results[step['id']]=result; continue
        if state in ('refused','blocked','awaiting_response'):
            c.execute('UPDATE ai_plans SET status=?,updated_day=? WHERE id=?',(state,day(c),plan_id)); return
        if any(dep not in results or results[dep].get('state')!='completed' for dep in step['depends_on']):
            c.execute("UPDATE ai_plans SET status='active',updated_day=? WHERE id=?",(day(c),plan_id)); return
        c.execute('SAVEPOINT ai_world_step')
        try:
            args=resolve_arguments(step,results)
            result=CAPABILITIES[step['operation']].execute(c,int(row['owner_actor_id']),plan_id,step['id'],args)
            state=result['state']
            c.execute('RELEASE ai_world_step')
        except (ValueError,KeyError,TypeError) as exc:
            c.execute('ROLLBACK TO ai_world_step'); c.execute('RELEASE ai_world_step')
            state='blocked'; result={'state':state,'summary':str(exc)}
        c.execute('UPDATE ai_plan_steps SET status=?,result_json=? WHERE plan_id=? AND step_key=?',(state,dump(result),plan_id,step['id']))
        event(c,plan_id,'step_'+state,{'step':step['id'],'result':result})
        results[step['id']]=result
        if state not in ('completed','active'):
            c.execute('UPDATE ai_plans SET status=?,updated_day=? WHERE id=?',(state,day(c),plan_id)); return
    status='completed' if all(r.get('state')=='completed' for r in results.values()) else 'active'
    c.execute('UPDATE ai_plans SET status=?,updated_day=? WHERE id=?',(status,day(c),plan_id))


def next_planning_due_day(c,after_day,end_day):
    if not available(c): return None
    active=c.execute("SELECT 1 FROM ai_plans WHERE approved_digest=digest AND status IN ('approved','active','awaiting_response') LIMIT 1").fetchone()
    return min(end_day,after_day+1) if active and after_day<end_day else None


def process_due_planning(c,today,**kwargs):
    if not available(c): return {'plans_reviewed':0}
    # Native projects must not keep progressing after their actual means vanish.
    for work in c.execute("SELECT w.*,p.status FROM ai_work_links w JOIN civilian_projects p ON p.id=w.project_id WHERE p.status='active'").fetchall():
        from .world_capabilities import work_capacity, skill
        engagement=c.execute("SELECT s.provider_id,s.status,a.status actor_status,a.current_location_id,s.client_institution_actor_id FROM service_engagements s JOIN actors a ON a.id=s.provider_id WHERE s.id=?",(work['service_engagement_id'],)).fetchone()
        site=c.execute('SELECT status,location_id,owner_institution_actor_id FROM strategic_assets WHERE id=?',(work['site_id'],)).fetchone()
        if not engagement or not site or engagement['status']!='active' or engagement['actor_status']!='active' or work_capacity(c,int(engagement['provider_id']))<=0 or site['status']!='active' or engagement['current_location_id']!=site['location_id'] or site['owner_institution_actor_id']!=engagement['client_institution_actor_id']:
            c.execute("UPDATE civilian_projects SET status='paused' WHERE id=?",(work['project_id'],))
            event(c,work['plan_id'],'work_paused',{'project_id':work['project_id'],'summary':'The established personnel or site prerequisite is no longer satisfied.'})
        else:
            domain=c.execute('SELECT domain_key FROM service_engagements WHERE id=?',(work['service_engagement_id'],)).fetchone()[0]
            labor=skill(c,int(engagement['provider_id']),domain)*work_capacity(c,int(engagement['provider_id']))/100
            c.execute('UPDATE civilian_projects SET skilled_labor=? WHERE id=?',(labor,work['project_id']))
    rows=c.execute("SELECT id FROM ai_plans WHERE approved_digest=digest AND status IN ('approved','active','awaiting_response')").fetchall()
    for row in rows: execute_plan(c,int(row[0]))
    return {'plans_reviewed':len(rows)}
