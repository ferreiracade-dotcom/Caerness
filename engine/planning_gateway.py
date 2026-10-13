"""General tool/plan protocol over Caerness's existing local/manual model gateway."""
from __future__ import annotations

import json
import threading
import time

_LOCAL_RUN_LOCK=threading.Lock()

from . import ai_planning as plans
from .world_capabilities import CAPABILITIES, context, known_offerings


PROTOCOL = 'world_plan_v1'
READ_TOOLS = [
    {'name':'context','arguments':{'institution_id':'optional integer'},'description':'Read ordinary player perception or records of an organisation you actually command.'},
    {'name':'offerings','arguments':{},'description':'Read accessible published quotations from present providers; never global hidden talent.'},
    {'name':'plan_status','arguments':{'plan_id':'integer'},'description':'Inspect your own persisted plan and authoritative progress.'},
]


def contract(request_id):
    return {'task_type':'action_interpretation','request_id':request_id,'proposal':{
        'mode':'inspect|plan|discuss|clarify',
        'calls':'For inspect only: [{tool: one discovered read tool, arguments: object}]',
        'text':'For discuss/clarify: natural dialogue or a question. Neither creates consent or commitments.',
        'plan':'For plan only: {source_text: EXACT planning_goal, summary: proposed scope, coverage: [{start:0,end:length,handling:planned|unresolved|context,step_ids:[ids]}], unresolved:[conditions not yet executable], steps:[{id:identifier,operation:discovered capability,arguments:typed object,depends_on:[prior IDs]}]}',
    }}


def response_schema(request_id, payload):
    """Syntax for the existing protocol, dynamically scoped to advertised tools/operations.

    Grammar constrains shape, never consent, source coverage or feasibility. Those
    remain independently checked by the existing engine executors and scope review.
    """
    def obj(properties, required=None):
        return {'type':'object','properties':properties,'required':required or list(properties),'additionalProperties':False}
    def array(items, **limits): return {'type':'array','items':items,**limits}
    string={'type':'string'}
    span=obj({'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':0}})
    if payload.get('protocol')=='narrative_authoring_review_v1':
        proposal=obj({'compatible':{'type':'boolean'},'independent':{'type':'boolean'},'issues':array(string),'reason':string})
    elif payload.get('protocol')=='narrative_scope_v1':
        proposal=obj({'authorized':{'type':'boolean'},'complete':{'type':'boolean'},
            'evidence':array(span),'omissions':array(string),'reason':string})
    else:
        tools=[t['name'] for t in payload.get('read_tools',[]) if t.get('name')]
        if payload.get('protocol')=='narrative_play_v1' and payload.get('context',{}).get('scene'):
            tools=[tool for tool in tools if tool!='scene']
        if payload.get('protocol')=='narrative_play_v1' and 'read_result' not in tools and any(len(json.dumps(item.get('result'),ensure_ascii=False))>6000 for item in payload.get('feedback',[])):tools.append('read_result')
        operations=[t['name'] for t in payload.get('capabilities',[]) if t.get('name')]
        # Arguments remain engine-validated against dynamically discoverable domain
        # schemas; a syntactically valid arbitrary object has no mutation authority.
        arguments={'type':'object','additionalProperties':True}
        call=obj({'tool':{'type':'string','enum':tools},'arguments':arguments})
        if payload.get('protocol')=='narrative_play_v1' and 'context' in tools:
            remaining=[tool for tool in tools if tool!='context']
            variants=[obj({'tool':{'const':'context'},'arguments':obj({'institution_id':{'type':'integer','minimum':1}})})]
            if remaining:variants.append(obj({'tool':{'type':'string','enum':remaining},'arguments':arguments}))
            call={'anyOf':variants}
        step=obj({'id':string,'operation':{'type':'string','enum':operations},'arguments':arguments,'depends_on':array(string)})
        coverage=obj({'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':0},
            'handling':{'type':'string','enum':['planned','unresolved','context']},'step_ids':array(string)})
        plan=obj({'source_text':string,'summary':string,'coverage':array(coverage),'unresolved':array(string),'steps':array(step)})
        discussion=obj({'mode':{'type':'string','enum':['discuss','clarify']},'text':{'type':'string','minLength':1}})
        modes=[discussion]
        if payload.get('protocol')=='narrative_play_v1' and payload.get('phase')!='consequences':
            # Discover detailed authoring fields only when needed. The engine always
            # validates them; repeating every nested field burdens ordinary dialogue.
            authorship={'entities':array(arguments,maxItems=4),'details':array(arguments,maxItems=8)}
            modes.append(obj({'mode':{'const':'discuss'},'text':{'type':'string','minLength':1},'details':authorship['details']}))
            modes.append(obj({'mode':{'const':'author'},'authorship':obj(authorship)}))
        if payload.get('phase')!='consequences':
            if tools:modes.append(obj({'mode':{'const':'inspect'},'calls':array(call,minItems=1,maxItems=8)}))
            if operations:modes.append(obj({'mode':{'const':'plan'},'plan':plan}))
        proposal={'anyOf':modes}
    return obj({'task_type':{'const':'action_interpretation'},'request_id':{'const':request_id},'proposal':proposal})


def start_request(c, text, provider='chatgpt', session_id=None, plan_id=None, feedback=None, record_input=True, rounds=0, goal_override=None, narrative=False):
    from .model_gateway import create_request
    s=plans.session(c,session_id); sid=s['id']
    if record_input: plans.message(c,sid,'player',text)
    existing=plans.plan_view(c,plan_id) if plan_id is not None else None
    if existing and existing['session_id']!=sid: raise ValueError('Resume the conversation that owns this plan.')
    memory=json.loads(plans.session(c,sid)['messages_json'])
    handled={m['text']['planned_intention'] for m in memory if isinstance(m['text'],dict) and 'planned_intention' in m['text']}
    all_pending=list(dict.fromkeys(m['text']['unresolved_intention'] for m in memory if isinstance(m['text'],dict) and 'unresolved_intention' in m['text']))
    pending=[x for x in all_pending if not any(y==x or y.startswith(x+'\nFollow-up: ') for y in handled)
             and not any(y!=x and y.startswith(x+'\nFollow-up: ') for y in all_pending)]
    prior=existing['original_instruction'] if existing else (pending[-1] if pending else None)
    if existing and pending and pending[-1].startswith(existing['original_instruction']+'\nFollow-up: '): prior=pending[-1]
    goal=goal_override or (prior+'\nFollow-up: '+text if prior and record_input else prior or text)
    if prior and record_input:
        # Bind follow-up conditions before the model can misclassify them as chat.
        plans.message(c,sid,'system',{'unresolved_intention':goal})
        pending=[goal]
    payload={'protocol':PROTOCOL,'raw_player_input':text,'planning_goal':goal,
        'session_id':sid,'plan_id':plan_id,'rounds':rounds,'conversation':json.loads(plans.session(c,sid)['messages_json'])[-24:],
        'context':{} if narrative else context(c,s['owner_actor_id']), 'current_plan':existing,
        'read_tools':list(READ_TOOLS),'capabilities':[cap.schema() for cap in CAPABILITIES.values()],
        'feedback':feedback or [],
        'unresolved_intentions':pending,
        'rules':[
            'Understand the whole intention, including unusual arrangements. Compose capabilities; do not look for a predefined gameplay verb.',
            'Inspect relevant permissions, people, quotations, resources and sites before planning. Unknown is not available.',
            'Distinguish discussion, hypotheticals, desired plans, player authorization, NPC consent and committed outcomes.',
            'Ordinary conversation must remain discussion, without automatic offers, social rolls or time advancement.',
            'Every non-whitespace character of planning_goal needs non-overlapping source coverage. Retain all unhandled conditions in unresolved.',
            'Use {ref:"prior_step.declared_output"} for operation outputs and declare dependencies. Do not invent future IDs.',
            'Models never authorize or execute. All new commitments require the player to review the proposed scope against the original intention.',
            'Only declared capabilities can mutate world state. Never claim creation, consent, expenditure or completion without an engine result.',
            'A missing operation remains an explicit limitation or longer process. Do not substitute observation or an easier unstated goal.',
            'On refusal/failure use the engine feedback to revise unexecuted steps or propose an alternative. Preserve committed prefixes and the original goal.',
            'Quotes are native published terms, not permission to invent price, personnel, equipment, property, travel, sovereignty or mastery.',
            'No future fortune/director system is implemented by this protocol. Follow the owner narrative-direction qualifications, not absolute survival prohibitions.',
        ]}
    payload['open_plans']=[plans.plan_view(c,int(r[0])) for r in c.execute("SELECT id FROM ai_plans WHERE owner_actor_id=? AND status!='completed' ORDER BY id DESC LIMIT 4",(s['owner_actor_id'],))]
    if narrative:
        from .narrative_runtime import enrich
        enrich(c,payload)
    return create_request(c,'action_interpretation',payload,provider=provider,target_kind='ai_session',target_id=sid)


def apply_response(c, row, response, payload):
    p=response['proposal']; mode=p.get('mode')
    sid=int(payload['session_id']); s=plans.session(c,sid)
    if mode=='inspect' and isinstance(p.get('calls'),list) and any(isinstance(call,dict) and {'tool':call.get('tool'),'arguments':call.get('arguments')} in payload.get('completed_reads',[]) for call in p['calls']):
        error=RuntimeError('The model repeated an unchanged read instead of using its result.');error.code='repeated_read'
        raise error
    def follow(feedback):
        rounds=int(payload.get('rounds',0))+1
        if rounds>6:
            plans.message(c,sid,'system','The planning round limit was reached. The original goal remains unresolved; no world operation was executed.')
            return {'status':'needs_clarification','session_id':sid,'summary':'The planning round limit was reached; the goal remains unresolved.'}
        req=start_request(c,payload['raw_player_input'],row['provider'],sid,payload.get('plan_id'),feedback,False,rounds,goal_override=payload['planning_goal'],narrative=payload.get('protocol')=='narrative_play_v1')
        return {'status':'awaiting_action_interpretation','session_id':sid,'feedback':feedback,'next_request':req}
    try:
        if mode=='inspect':
            if set(p)!={'mode','calls'} or not isinstance(p['calls'],list) or not 1<=len(p['calls'])<=8:
                raise ValueError('Inspect mode requires one to eight scoped read calls only.')
            results=[]
            for call in p['calls']:
                if not isinstance(call,dict) or set(call)!={'tool','arguments'} or not isinstance(call['arguments'],dict): raise ValueError('Invalid read call.')
                tool,args=call['tool'],call['arguments']
                if tool=='context' and set(args)<= {'institution_id'}:
                    inst=args.get('institution_id')
                    if inst is not None and (type(inst)is not int or inst<1): raise ValueError('Invalid organisation ID.')
                    if payload.get('protocol')=='narrative_play_v1' and inst is None:
                        # Narrative scene is already current and scoped. The legacy
                        # planner scene includes a large roster/policy/ledger dump.
                        value={'scene':{'from':'context.scene','unchanged':True},'organisations':payload['context'].get('organisations',[]),
                            'competence_domains':[r[0] for r in c.execute('SELECT domain_key FROM competence_domains ORDER BY domain_key')]}
                    else:value=context(c,s['owner_actor_id'],inst)
                elif tool=='offerings' and not args: value=known_offerings(c,s['owner_actor_id'])
                elif tool=='plan_status' and set(args)=={'plan_id'} and type(args['plan_id'])is int:
                    value=plans.plan_view(c,args['plan_id'])
                elif payload.get('protocol')=='narrative_play_v1':
                    from .narrative_runtime import read
                    value=read(c,sid,tool,args)
                else: raise ValueError('Read tool or arguments unavailable; unrestricted database access is forbidden.')
                results.append({'tool':tool,'arguments':args,'result':value})
            plans.message(c,sid,'tool',results)
            output=follow(results)
        elif mode in ('discuss','clarify'):
            if set(p)!={'mode','text'} or not isinstance(p['text'],str) or not p['text'].strip(): raise ValueError('Discussion/clarification requires text only, without operations.')
            plans.message(c,sid,'assistant',p['text'])
            if mode=='clarify': plans.message(c,sid,'system',{'unresolved_intention':payload['planning_goal'],'question':p['text']})
            output={'status':'discussed' if mode=='discuss' else 'needs_clarification','session_id':sid,'narration':p['text'],
                    'world_changes':False,'summary':'No commitment or acceptance was inferred from this exchange.'}
        elif mode=='plan':
            if set(p)!={'mode','plan'}: raise ValueError('Plan mode requires a structured plan only.')
            view=plans.draft_plan(c,sid,payload['planning_goal'],p['plan'],payload.get('plan_id'))
            plans.message(c,sid,'system',{'planned_intention':payload['planning_goal'],'plan_id':view['id']})
            plans.message(c,sid,'assistant',{'proposed_scope':view['summary'],'unresolved':view['unresolved']})
            output={'status':'awaiting_plan_review','session_id':sid,'plan':view,
                    'narration':view['summary']+' Nothing has been committed. Review this proposed scope against your full instruction.'}
        else: raise ValueError('Choose inspect, discuss, clarify or plan. A model cannot authorize world changes.')
    except (ValueError,KeyError,TypeError) as exc:
        plans.message(c,sid,'system',{'planning_error':str(exc),'goal_preserved':payload['planning_goal']})
        output=follow([{'error':str(exc),'world_changes':False}])
    c.execute("UPDATE model_requests SET status='applied',applied_summary=?,applied_at=CURRENT_TIMESTAMP WHERE id=?",(output.get('summary',output['status']),row['id']))
    return output


def run_local(c, request_id, max_rounds=9, force=False, checkpoint=False):
    if not _LOCAL_RUN_LOCK.acquire(blocking=False):raise RuntimeError('Another model response is already in progress. Wait for it before retrying.')
    try:return _run_local(c,request_id,max_rounds,force,checkpoint)
    finally:_LOCAL_RUN_LOCK.release()


def _run_local(c, request_id, max_rounds=9, force=False, checkpoint=False):
    """Bounded real configured-model loop; stops at discussion/clarification/review."""
    from .model_gateway import run_request_local,apply_model_request
    def interrupted():
        from .agency import consume_interrupt
        if not checkpoint or not consume_interrupt(c):return None
        from .narrative_diagnostics import record_failure,paused
        error=RuntimeError('Paused at the requested safe boundary.');error.code='interrupted'
        record_failure(c,request_id,error);c.commit()
        return paused(c,request_id)
    for _ in range(max_rounds):
        if checkpoint:c.commit() # Save the pending continuation before slow inference.
        stopped=interrupted()
        if stopped:return stopped
        row=c.execute('SELECT status FROM model_requests WHERE id=?',(request_id,)).fetchone()
        if not row or row['status'] not in ('pending','responded'):raise ValueError('Only an unfinished request can be resumed; completed actions are not replayed.')
        started=time.perf_counter()
        try:
            result=run_request_local(c,request_id,force=force,apply=False) if row['status']=='pending' else {'status':'responded'}
        except (ConnectionError,TimeoutError,RuntimeError,ValueError) as error:
            from .narrative_diagnostics import record_failure
            record_failure(c,request_id,error,elapsed=time.perf_counter()-started)
            if checkpoint:c.commit()
            raise
        if result.get('status')=='external_recommended':
            from .mobile_runtime import referral_for_request
            return referral_for_request(c,request_id,result['assessment'],reason=result.get('message','A stronger model is recommended for this plan.'))
        stopped=interrupted()
        if stopped:return stopped
        c.execute('SAVEPOINT model_application')
        try:
            applied=apply_model_request(c,request_id)
            c.execute('RELEASE model_application')
        except Exception as error:
            c.execute('ROLLBACK TO model_application');c.execute('RELEASE model_application')
            c.execute("UPDATE model_requests SET status='pending' WHERE id=?",(request_id,))
            from .narrative_diagnostics import record_failure
            record_failure(c,request_id,error)
            if checkpoint:c.commit()
            raise ValueError('The model response could not be applied; the unfinished request is safe to retry.') from error
        if checkpoint:c.commit()
        if applied.get('status')!='awaiting_action_interpretation': return applied
        request_id=applied['next_request']['request_id']
    return {'status':'needs_clarification','summary':'The model planning loop reached its bound. No plan was authorized.'}


def play(c,text,session_id=None,plan_id=None,provider='local',force_local=False):
    req=start_request(c,text,provider,session_id,plan_id)
    if provider=='local':
        try:
            out=run_local(c,req['request_id'],force=force_local)
            out['session_id']=int(c.execute('SELECT target_id FROM model_requests WHERE id=?',(req['request_id'],)).fetchone()[0])
            return out
        except (ConnectionError,RuntimeError,ValueError) as exc:
            from .mobile_runtime import referral_for_request
            out=referral_for_request(c,req['request_id'],{'recommendation':'external_recommended'},reason=f'Configured local model unavailable: {exc}')
            out['session_id']=req.get('target_id') or int(c.execute('SELECT target_id FROM model_requests WHERE id=?',(req['request_id'],)).fetchone()[0])
            return out
    return {'status':'awaiting_action_interpretation',**req,'session_id':int(c.execute('SELECT target_id FROM model_requests WHERE id=?',(req['request_id'],)).fetchone()[0])}


def feedback_request(c,view,provider='chatgpt'):
    """Execution facts return to the planner; revised commitments still need review."""
    plans.message(c,view['session_id'],'system',{'authoritative_execution_feedback':view['steps'],'status':view['status']})
    return start_request(c,'Review the execution feedback. Retain the original intention and committed prefix. Propose an alternative, a revision or a clarification; do not claim success.',
                         provider,view['session_id'],view['id'],feedback=[view],record_input=False)


def record_execution_narration(c,view):
    """Reuse the normal narrator boundary with committed engine facts only."""
    from .player import build_scene_packet
    from .turns import build_narration_envelope, TemplateNarratorProvider
    from .model_gateway import create_narration_request, configured_provider
    scene=build_scene_packet(c,canon_limit=3)
    facts=[s['result']['summary'] for s in view['steps'].values() if s['result'].get('summary')]
    summary=' '.join(facts) or 'The proposed plan has not committed any world operations.'
    result={'action_type':'planned_operations','status':view['status'],'summary':summary,
            'detail':{'plan_id':view['id'],'revision':view['revision']}}
    envelope=build_narration_envelope(view['original_instruction'],scene,result,scene)
    narration=TemplateNarratorProvider().narrate(envelope)
    owner=plans.current_actor(c); today=plans.day(c)
    tid=int(c.execute('INSERT INTO turns(player_actor_id,day_started,day_ended,raw_input,pre_scene_packet_id,post_scene_packet_id,result_json,narration_text) VALUES (?,?,?,?,?,?,?,?)',
        (owner,today,today,view['original_instruction'],scene['scene_packet_id'],scene['scene_packet_id'],json.dumps({'action':result}),narration)).lastrowid)
    req=create_narration_request(c,tid,envelope,configured_provider(c,'narration'))
    return {'turn_id':tid,'narration':narration,'narration_request':req}
