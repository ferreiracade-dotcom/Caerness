"""Discoverable, narrow world capabilities. No player-phrase recognition or SQL tool.

The model chooses operations and arrangements. This module owns permissions and
domain adapters; persisted quotations, people, stock and property own prerequisites.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Callable

from .opportunity import institution_decision_actor


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def day(c):
    return int(c.execute('SELECT current_day FROM world_state WHERE id=1').fetchone()[0])


def authority(c, actor, institution):
    row = c.execute("SELECT actor_type,status FROM actors WHERE id=?", (institution,)).fetchone()
    person = c.execute("SELECT status FROM actors WHERE id=?", (actor,)).fetchone()
    if not row or row['actor_type'] != 'institution' or row['status'] != 'active' or not person or person[0] != 'active':
        raise ValueError('The organisation or acting person is unavailable.')
    if institution_decision_actor(c, institution) != actor:
        raise ValueError('You do not have authority over this organisation.')


def present(c, actor, target):
    from .presence import actor_is_present_candidate
    loc = c.execute('SELECT current_location_id FROM actors WHERE id=?', (actor,)).fetchone()
    if not loc or loc[0] is None or not actor_is_present_candidate(c, target, int(loc[0]), purpose=f'scene:{actor}'):
        raise ValueError('A direct proposal requires meeting this person; arrange contact or travel first.')


def skill(c, actor, domain):
    row = c.execute('SELECT ac.score FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id WHERE ac.actor_id=? AND d.domain_key=?', (actor, domain)).fetchone()
    return float(row[0]) if row else 0.0


def work_capacity(c,actor):
    row=c.execute('SELECT functional_capacity FROM actor_health_profiles WHERE actor_id=?',(actor,)).fetchone()
    return float(row[0]) if row else 0.0


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    fields: dict[str, str]
    execute: Callable
    outputs: tuple[str, ...]

    def schema(self):
        return {'name': self.name, 'description': self.description,
                'arguments': self.fields, 'required': list(self.fields),
                'additional_arguments': False, 'outputs': list(self.outputs)}


CAPABILITIES: dict[str, Capability] = {}


def capability(name, description, fields, outputs):
    def register(fn):
        CAPABILITIES[name] = Capability(name, description, fields, fn, outputs)
        return fn
    return register


def check_arguments(name, args, allow_refs=False):
    if name not in CAPABILITIES:
        raise ValueError(f'Capability unavailable: {name}. Keep the goal unresolved; do not substitute another action.')
    fields = CAPABILITIES[name].fields
    if not isinstance(args, dict) or set(args) != set(fields):
        raise ValueError(f'{name} requires exactly {list(fields)}.')
    types = {'id': int, 'text': str, 'resources': dict}
    for key, kind in fields.items():
        v = args[key]
        if allow_refs and isinstance(v, dict) and set(v) == {'ref'}:
            if not isinstance(v['ref'], str): raise ValueError('A reference must be a string.')
            continue
        if not isinstance(v, types[kind]) or isinstance(v, bool):
            raise ValueError(f'{name}.{key} must be {kind}.')
        if kind == 'id' and v < 1: raise ValueError('IDs must be positive.')
        if kind == 'text' and (not v.strip() or len(v) > 4000): raise ValueError('Text must be nonempty and bounded.')
        if kind == 'resources':
            if not v or len(v) > 16: raise ValueError('Specify actual resources and quantities.')
            for resource, amount in v.items():
                if not isinstance(resource, str) or not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount) or amount <= 0:
                    raise ValueError('Resource quantities must be finite positive numbers.')


def describe_scope(c,owner,step):
    """Engine-authored effects, independent of the model's persuasive summary."""
    op,args=step['operation'],step['arguments']
    def person(aid):
        if type(aid)is not int: return 'the person proposed earlier'
        row=c.execute('SELECT name FROM actors WHERE id=?',(aid,)).fetchone()
        return str(row[0]) if row else 'an unavailable person'
    def institution(iid):
        try: authority(c,owner,iid)
        except ValueError: return 'an organisation you do not currently command'
        return person(iid)
    if op=='define_role': return f"Establish '{args['title']}' as a staff responsibility in {institution(args['institution_id'])}. Remit: {args['remit']}. This grants no other rights."
    if op=='offer_service': return f"Ask {person(args['person_id'])} to accept a responsibility and conditional service for {institution(args['institution_id'])}. Scope: {args['scope']}. Consent is not guaranteed; no gift or pay promise is included."
    if op=='allocate_resources': return f"Reserve existing stock of {institution(args['institution_id'])}: {dump(args['resources'])}. No currency conversion or new resources."
    if op=='commission_work':
        q=next((x for x in known_offerings(c,owner) if x['offering_id']==args['offering_id']),None)
        if q and q['work_order']:
            terms=q['work_order']
            items=', '.join(f'{amount:g} {resource}' for resource,amount in terms['resources'].items())
            quote_text=f"{items}; a target of {terms['duration_days']} days and a suitable {', '.join(terms['site_kinds'])}"
        else: quote_text='an unavailable quotation; execution will be blocked'
        return f"Attempt '{args['title']}' using the selected owned site, accepted service and reserved resources. Quoted requirements: {quote_text}. Completion requires world time and sustained means."
    if op=='refund_resources': return 'Return only the unspent balance of this plan reserve to its original organisation.'
    if op=='advance_time': return f"Pass {args['days']} days for the entire world, including risks and unrelated developments."
    if op=='answer_proposal': return f"Explicitly {args['choice']} the selected pending proposal addressed to you. Its existing terms and commit guards still apply."
    return CAPABILITIES[op].description


def context(c, actor, institution_id=None):
    """Only owned organisational records and the ordinary knowledge-safe scene."""
    from .player import build_scene_packet
    scene = build_scene_packet(c, canon_limit=3)
    if institution_id is None:
        organisations = [dict(r) for r in c.execute("SELECT id,name FROM actors WHERE actor_type='institution' AND status='active'") if institution_decision_actor(c, int(r['id'])) == actor]
        return {'scene': scene, 'organisations': organisations}
    authority(c, actor, institution_id)
    return {
        'institution_id': institution_id,
        'members': [dict(r) for r in c.execute("SELECT a.id,a.name,m.role_text FROM institution_memberships m JOIN actors a ON a.id=m.member_actor_id WHERE m.institution_actor_id=? AND m.status='active' AND a.status='active'", (institution_id,))],
        'resources': [dict(r) for r in c.execute('SELECT resource_type,amount,unit FROM resources WHERE actor_id=?', (institution_id,))],
        'roles': [dict(r) for r in c.execute("SELECT id,title,domain_key,capacity_slots FROM institutional_roles WHERE institution_actor_id=? AND status='active'", (institution_id,))],
        'sites': [dict(r) for r in c.execute("SELECT id,name,asset_kind,location_id FROM strategic_assets WHERE owner_institution_actor_id=? AND status='active'", (institution_id,))],
        'information_basis': 'Your organisation records. Private NPC motives, opinions and hidden resources are excluded.'
    }


def known_offerings(c, actor):
    from .presence import actors_plausibly_present
    loc = c.execute('SELECT current_location_id FROM actors WHERE id=?',(actor,)).fetchone()[0]
    known = set(actors_plausibly_present(c,int(loc),purpose=f'scene:{actor}')) if loc is not None else set()
    out = []
    for row in c.execute("SELECT * FROM seekable_offerings WHERE status='active' AND access_mode IN ('open','visit','appointment') AND location_id=? AND visibility>=50", (loc,)):
        if int(row['provider_actor_id']) in known:
            work = json.loads(row['metadata_json']).get('work_order')
            out.append({'offering_id': int(row['id']), 'provider_actor_id': int(row['provider_actor_id']),
                        'domain': row['domain_key'], 'subject': row['subject_key'], 'work_order': work,
                        'quotation_digest':digest({'provider':row['provider_actor_id'],'domain':row['domain_key'],'subject':row['subject_key'],'work_order':work})})
    return out


def quote(c, actor, offering_id):
    published = next((o for o in known_offerings(c, actor) if o['offering_id'] == offering_id), None)
    if not published or not published['work_order']:
        raise ValueError('No accessible, quantified work quotation exists. Negotiate a quotation rather than inventing its price or means.')
    q = published['work_order']
    required = {'project_kind','resources','duration_days','site_kinds','minimum_skill'}
    if set(q) != required or q['project_kind'] not in ('architecture','public_work','artwork','textile','manuscript','craft'):
        raise ValueError('The work quotation is incomplete or not supported by the existing project owner.')
    check_arguments('allocate_resources', {'institution_id': 1, 'resources': q['resources']})
    if not isinstance(q['duration_days'], int) or q['duration_days'] < 30 or not q['site_kinds']:
        raise ValueError('The work quotation lacks a credible timeline or site requirement.')
    offering = c.execute('SELECT capacity_per_30,availability FROM seekable_offerings WHERE id=?',(offering_id,)).fetchone()
    if not offering or float(offering['capacity_per_30']) < 1 or float(offering['availability']) <= 0:
        raise ValueError('This provider has no offered work capacity available.')
    return published


@capability('define_role', 'Establish a responsibility within an existing organisation you command. This grants no nobility, political sovereignty or magical competence.',
            {'institution_id':'id','title':'text','domain':'text','remit':'text'}, ('role_id',))
def define_role(c, owner, plan_id, step_key, args):
    from .adaptive_planning import create_role
    authority(c, owner, args['institution_id'])
    if not c.execute('SELECT 1 FROM competence_domains WHERE domain_key=?', (args['domain'],)).fetchone():
        raise ValueError('This competence domain is not modelled; retain the requirement as unresolved.')
    rid = create_role(c, args['institution_id'], f'ai_plan_{plan_id}_{step_key}', args['title'], args['domain'],
        role_kind='staff_role', source_kind='ai_plan', source_id=plan_id, remit={'scope':args['remit']})
    return {'role_id': rid, 'summary': f"Established the responsibility: {args['title']}.", 'state':'completed'}


def validate_service(c, owner, institution, person, role_id, offering_id, quotation_digest):
    from .adaptive_planning import role_open_slots
    authority(c, owner, institution)
    role = c.execute("SELECT * FROM institutional_roles WHERE id=? AND institution_actor_id=? AND status='active'", (role_id, institution)).fetchone()
    target = c.execute("SELECT actor_type,status FROM actors WHERE id=?", (person,)).fetchone()
    if not role or not target or target['actor_type'] != 'character' or target['status'] != 'active' or person == owner:
        raise ValueError('The responsibility or recipient is unavailable.')
    if role_open_slots(c, role_id) < 1: raise ValueError('The responsibility has no vacant place.')
    present(c, owner, person)
    q = quote(c, owner, offering_id)
    if q['quotation_digest'] != quotation_digest: raise ValueError('The published quotation changed after review. Revise and review the plan before accepting new terms.')
    if q['provider_actor_id'] != person or q['domain'] != role['domain_key']:
        raise ValueError('The selected person or responsibility does not match this quotation.')
    if skill(c, person, role['domain_key']) < float(q['work_order']['minimum_skill']):
        raise ValueError('The person has not demonstrated the required competence.')
    if work_capacity(c,person)<=0: raise ValueError('The person does not have established functional capacity for this work.')
    return role, q


def validate_guard(c, metadata, terms):
    guard = metadata['ai_plan_guard']
    validate_service(c, guard['owner'], guard['institution'], guard['person'], guard['role_id'], guard['offering_id'],guard['quotation_digest'])
    snap = [{'term_kind':str(t['term_kind']), 'subject_kind':t['subject_kind'], 'subject_id':t['subject_id'],
             'value':json.loads(t['value_json'])} for t in terms]
    if digest(snap) != guard['terms_digest']:
        raise ValueError('Changed terms require a new reviewed plan; the old authorization does not cover them.')


@capability('offer_service', 'Offer a role and a conditional work engagement to one existing suitable person. They may refuse or counter; no invented personnel. Uses an accessible published quotation.',
            {'institution_id':'id','person_id':'id','role_id':'id','offering_id':'id','quotation_digest':'text','scope':'text'}, ('proposal_id','interaction_id','appointment_id','engagement_id'))
def offer_service(c, owner, plan_id, step_key, args):
    from .opportunity import create_proposal, add_term, present_proposal, _actor_obligation_load
    from .interactions import resolve_interaction
    role, q = validate_service(c, owner, args['institution_id'], args['person_id'], args['role_id'], args['offering_id'],args['quotation_digest'])
    pid = create_proposal(c, owner, 'appointment', q['domain'], args['scope'],
        proposer_institution_actor_id=args['institution_id'], target_actor_id=args['person_id'],
        source_kind='ai_plan', source_id=plan_id)
    add_term(c, pid, 'appointment', subject_kind='actor', subject_id=args['person_id'], execution_order=20,
        value={'institution_actor_id':args['institution_id'],'holder_actor_id':args['person_id'],
               'role_id':args['role_id'],'title':role['title'],'appointment_kind':role['role_kind'],
               'obligations':{'work_description':args['scope'],'only_work_quotation':args['offering_id'],'conditional_on':'funded work order and site','additional_rights_or_promises':False}})
    add_term(c, pid, 'service_commitment', subject_kind='actor', subject_id=args['person_id'], execution_order=30,
        value={'service_kind':q['subject'],'scope':{'description':args['scope'],'only_work_quotation':args['offering_id'],'conditional_on':'funded work order and site','additional_rights_or_promises':False},'exclusivity':0.5})
    rows = c.execute('SELECT * FROM opportunity_proposal_terms WHERE proposal_id=? ORDER BY execution_order,id', (pid,)).fetchall()
    guard = {'owner':owner,'institution':args['institution_id'],'person':args['person_id'],
             'role_id':args['role_id'],'offering_id':args['offering_id'],
             'quotation_digest':args['quotation_digest'],
             'terms_digest':digest([{'term_kind':r['term_kind'],'subject_kind':r['subject_kind'],'subject_id':r['subject_id'],'value':json.loads(r['value_json'])} for r in rows])}
    c.execute('UPDATE opportunity_proposals SET metadata_json=? WHERE id=?', (dump({'ai_plan_guard':guard}),pid))
    iid = present_proposal(c, pid)
    row = c.execute('SELECT terms_json,status FROM interactions WHERE id=?', (iid,)).fetchone()
    if row['status'] == 'pending':
        terms = json.loads(row['terms_json']); load, _ = _actor_obligation_load(c,args['person_id'])
        terms['burden'] = 1.0 + load*3
        c.execute('UPDATE interactions SET terms_json=? WHERE id=?',(dump(terms),iid))
    ir = resolve_interaction(c,iid,day(c))
    return service_result(c, pid, iid)


def service_result(c, pid, iid):
    p = c.execute('SELECT status FROM opportunity_proposals WHERE id=?',(pid,)).fetchone()
    ap = c.execute('SELECT id FROM institutional_appointments WHERE source_interaction_id=?',(iid,)).fetchone()
    se = c.execute('SELECT id FROM service_engagements WHERE source_proposal_id=?',(pid,)).fetchone()
    state = 'completed' if ap and se else ('awaiting_response' if p and p[0] in ('pending','countered') else 'refused')
    interaction = c.execute('SELECT status FROM interactions WHERE id=?',(iid,)).fetchone()
    if state!='completed' and interaction and interaction[0]=='accepted': state='blocked'
    return {'proposal_id':pid,'interaction_id':iid,'appointment_id':int(ap[0]) if ap else None,
            'engagement_id':int(se[0]) if se else None,'state':state,
            'summary': 'The responsibility and conditional service were accepted.' if state=='completed' else 'The offer is unresolved or refused. No work or funding was assumed.'}


@capability('allocate_resources', 'Reserve existing organisational stock into this plan. Quantities are conserved and unspent reserves can be refunded.',
            {'institution_id':'id','resources':'resources'}, ('allocation_id',))
def allocate_resources(c, owner, plan_id, step_key, args):
    authority(c,owner,args['institution_id'])
    for resource,amount in args['resources'].items():
        changed = c.execute('UPDATE resources SET amount=amount-?,updated_day=? WHERE actor_id=? AND resource_type=? AND amount>=?',
            (amount,day(c),args['institution_id'],resource,amount)).rowcount
        if changed != 1: raise ValueError(f'Insufficient {resource}; no replacement stock or wealth was created.')
    aid = int(c.execute('INSERT INTO ai_resource_allocations(plan_id,institution_actor_id,resources_json) VALUES (?,?,?)',
        (plan_id,args['institution_id'],dump(args['resources']))).lastrowid)
    return {'allocation_id':aid,'state':'completed','summary':'Existing resources were reserved for the plan.'}


@capability('commission_work', 'Start an existing civilian project under consenting personnel, a real site and a quantified quotation. Resources are consumed exactly once and the native simulation advances the work.',
            {'institution_id':'id','allocation_id':'id','engagement_id':'id','offering_id':'id','quotation_digest':'text','site_id':'id','title':'text'}, ('project_id',))
def commission_work(c,owner,plan_id,step_key,args):
    from .civilian import create_project
    authority(c,owner,args['institution_id'])
    q = quote(c,owner,args['offering_id']); spec = q['work_order']
    if q['quotation_digest']!=args['quotation_digest']: raise ValueError('The quoted work or price changed after review; do not spend under stale terms.')
    allocation = c.execute("SELECT * FROM ai_resource_allocations WHERE id=? AND plan_id=? AND institution_actor_id=? AND status='reserved'",(args['allocation_id'],plan_id,args['institution_id'])).fetchone()
    engagement = c.execute("SELECT * FROM service_engagements WHERE id=? AND client_institution_actor_id=? AND provider_kind='actor' AND status='active'",(args['engagement_id'],args['institution_id'])).fetchone()
    if not allocation or not engagement or engagement['provider_id'] != q['provider_actor_id']:
        raise ValueError('Actual reserved resources and an accepted service commitment are required.')
    site = c.execute("SELECT * FROM strategic_assets WHERE id=? AND status='active' AND owner_institution_actor_id=?",(args['site_id'],args['institution_id'])).fetchone()
    offering = c.execute('SELECT location_id FROM seekable_offerings WHERE id=?',(args['offering_id'],)).fetchone()
    if not site or site['asset_kind'] not in spec['site_kinds'] or site['location_id'] != offering[0]:
        raise ValueError('Secure a suitable owned site in the provider location first. No land rights were invented.')
    slots = json.loads(site['metadata_json']).get('work_slots',0)
    occupied = c.execute("SELECT COUNT(*) FROM ai_work_links w JOIN civilian_projects p ON p.id=w.project_id WHERE w.site_id=? AND p.status IN ('active','paused')",(site['id'],)).fetchone()[0]
    if occupied >= slots: raise ValueError('The site has no established work capacity available.')
    present(c,owner,q['provider_actor_id'])
    score = skill(c,q['provider_actor_id'],q['domain'])
    if score < spec['minimum_skill']: raise ValueError('The responsible person cannot perform the quoted work.')
    capacity=work_capacity(c,q['provider_actor_id'])
    if capacity<=0: raise ValueError('The responsible person cannot currently perform the work.')
    if c.execute("SELECT 1 FROM civilian_projects WHERE creator_actor_id=? AND status IN ('active','paused')",(q['provider_actor_id'],)).fetchone():
        raise ValueError('The responsible person is already occupied by active work; do not count them twice.')
    reserved = json.loads(allocation['resources_json']); spent = json.loads(allocation['spent_json'])
    for resource,amount in spec['resources'].items():
        if reserved.get(resource,0)-spent.get(resource,0) < amount: raise ValueError(f'The accepted quotation requires more {resource}.')
        spent[resource] = spent.get(resource,0)+amount
    c.execute('UPDATE ai_resource_allocations SET spent_json=? WHERE id=?',(dump(spent),allocation['id']))
    pid = create_project(c,args['title'],spec['project_kind'],patron_actor_id=owner,creator_actor_id=q['provider_actor_id'],
        location_id=site['location_id'],target_day=day(c)+spec['duration_days'],quality_potential=score,
        funding=100,material_access=100,skilled_labor=score*capacity/100,
        metadata={'ai_plan_id':plan_id,'site_id':int(site['id']),'institution_actor_id':args['institution_id'],
                  'consumed_resources':spec['resources'],'building_kind':'other'})
    c.execute('INSERT INTO ai_work_links(project_id,plan_id,site_id,offering_id,service_engagement_id) VALUES (?,?,?,?,?)',
              (pid,plan_id,site['id'],args['offering_id'],args['engagement_id']))
    return {'project_id':pid,'state':'active','summary':f"Work began on {args['title']}. Completion is still pending; the quoted resources were consumed."}


@capability('refund_resources', 'Return this plan\'s remaining unspent reserve to its original owner. Spent resources cannot be recovered.',
            {'allocation_id':'id'}, ())
def refund_resources(c,owner,plan_id,step_key,args):
    row = c.execute("SELECT * FROM ai_resource_allocations WHERE id=? AND plan_id=? AND status='reserved'",(args['allocation_id'],plan_id)).fetchone()
    if not row: raise ValueError('No unspent reserve is available to refund.')
    authority(c,owner,int(row['institution_actor_id']))
    spent = json.loads(row['spent_json'])
    for resource,amount in json.loads(row['resources_json']).items():
        c.execute('UPDATE resources SET amount=amount+?,updated_day=? WHERE actor_id=? AND resource_type=?',
                  (amount-spent.get(resource,0),day(c),row['institution_actor_id'],resource))
    c.execute("UPDATE ai_resource_allocations SET status='refunded' WHERE id=?",(row['id'],))
    return {'state':'completed','summary':'Remaining unspent resources were returned; prior spending remains historical.'}


@capability('advance_time', 'Advance the shared world clock after explicit review. NPCs and native delegated projects continue independently. This does not generate success or reveal offscreen events.',
            {'days':'id'}, ())
def advance_time(c,owner,plan_id,step_key,args):
    from .simulation import advance_connection
    if args['days']>3650: raise ValueError('Use a bounded time-skip tranche of at most ten years.')
    advance_connection(c,args['days'])
    return {'state':'completed','summary':f"{args['days']} days passed for the whole world."}


@capability('answer_proposal', 'Explicitly answer an existing pending proposal addressed to the acting person. Never answer on an NPC\'s behalf. Changed terms still pass their domain commit guard.',
            {'interaction_id':'id','choice':'text'}, ())
def answer_proposal(c,owner,plan_id,step_key,args):
    from .interactions import apply_player_response
    row=c.execute("SELECT recipient_actor_id FROM interactions WHERE id=? AND status='pending'",(args['interaction_id'],)).fetchone()
    if not row or int(row[0])!=owner or args['choice'] not in ('accept','reject','counter'):
        raise ValueError('Only the actual recipient may answer this pending proposal with accept, reject or counter.')
    result=apply_player_response(c,args['interaction_id'],owner,args['choice'],day(c))
    return {'state':'completed','summary':result.summary}
