"""General tool/plan protocol over Caerness's existing local/manual model gateway."""
from __future__ import annotations

import json

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


def start_request(c, text, provider='chatgpt', session_id=None, plan_id=None, feedback=None, record_input=True, rounds=0):
    from .model_gateway import create_request
    s=plans.session(c,session_id); sid=s['id']
    if record_input: plans.message(c,sid,'player',text)
    existing=plans.plan_view(c,plan_id) if plan_id is not None else None
    if existing and existing['session_id']!=sid: raise ValueError('Resume the conversation that owns this plan.')
    payload={'protocol':PROTOCOL,'raw_player_input':text,'planning_goal':existing['original_instruction'] if existing else text,
        'session_id':sid,'plan_id':plan_id,'rounds':rounds,'conversation':json.loads(plans.session(c,sid)['messages_json'])[-24:],
        'context':context(c,s['owner_actor_id']), 'current_plan':existing,
        'read_tools':READ_TOOLS,'capabilities':[cap.schema() for cap in CAPABILITIES.values()],
        'feedback':feedback or [],
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
    return create_request(c,'action_interpretation',payload,provider=provider,target_kind='ai_session',target_id=sid)


def apply_response(c, row, response, payload):
    p=response['proposal']; mode=p.get('mode')
    sid=int(payload['session_id']); s=plans.session(c,sid)
    def follow(feedback):
        rounds=int(payload.get('rounds',0))+1
        if rounds>6:
            plans.message(c,sid,'system','The planning round limit was reached. The original goal remains unresolved; no world operation was executed.')
            return {'status':'needs_clarification','session_id':sid,'summary':'The planning round limit was reached; the goal remains unresolved.'}
        req=start_request(c,payload['raw_player_input'],row['provider'],sid,payload.get('plan_id'),feedback,False,rounds)
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
                    value=context(c,s['owner_actor_id'],inst)
                elif tool=='offerings' and not args: value=known_offerings(c,s['owner_actor_id'])
                elif tool=='plan_status' and set(args)=={'plan_id'} and type(args['plan_id'])is int:
                    value=plans.plan_view(c,args['plan_id'])
                else: raise ValueError('Read tool or arguments unavailable; unrestricted database access is forbidden.')
                results.append({'tool':tool,'arguments':args,'result':value})
            plans.message(c,sid,'tool',results)
            output=follow(results)
        elif mode in ('discuss','clarify'):
            if set(p)!={'mode','text'} or not isinstance(p['text'],str) or not p['text'].strip(): raise ValueError('Discussion/clarification requires text only, without operations.')
            plans.message(c,sid,'assistant',p['text'])
            output={'status':'discussed' if mode=='discuss' else 'needs_clarification','session_id':sid,'narration':p['text'],
                    'world_changes':False,'summary':'No commitment or acceptance was inferred from this exchange.'}
        elif mode=='plan':
            if set(p)!={'mode','plan'}: raise ValueError('Plan mode requires a structured plan only.')
            view=plans.draft_plan(c,sid,payload['planning_goal'],p['plan'],payload.get('plan_id'))
            plans.message(c,sid,'assistant',{'proposed_scope':view['summary'],'unresolved':view['unresolved']})
            output={'status':'awaiting_plan_review','session_id':sid,'plan':view,
                    'narration':view['summary']+' Nothing has been committed. Review this proposed scope against your full instruction.'}
        else: raise ValueError('Choose inspect, discuss, clarify or plan. A model cannot authorize world changes.')
    except (ValueError,KeyError,TypeError) as exc:
        plans.message(c,sid,'system',{'planning_error':str(exc),'goal_preserved':payload['planning_goal']})
        output=follow([{'error':str(exc),'world_changes':False}])
    c.execute("UPDATE model_requests SET status='applied',applied_summary=?,applied_at=CURRENT_TIMESTAMP WHERE id=?",(output.get('summary',output['status']),row['id']))
    return output


def run_local(c, request_id, max_rounds=7, force=False):
    """Bounded real configured-model loop; stops at discussion/clarification/review."""
    from .model_gateway import run_request_local
    for _ in range(max_rounds):
        result=run_request_local(c,request_id,force=force,apply=True)
        if result.get('status')=='external_recommended':
            from .mobile_runtime import referral_for_request
            return referral_for_request(c,request_id,result['assessment'],reason=result.get('message','A stronger model is recommended for this plan.'))
        applied=result.get('applied',result)
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
