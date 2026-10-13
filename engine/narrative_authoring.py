"""Graded campaign authorship: creative claims, additive history and native entities.

No SQL tool is exposed to a model. Objective additions require a frozen consistency
review as well as engine checks; actions, money, consent and player authority remain
owned by domain executors. This layer never edits setting canon or opening files.
"""
from __future__ import annotations

import hashlib
import json
import re

from .continuity import add_historical_anchor, create_latent_entity, set_resolution, upsert_continuity_core


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def ensure(c):
    ddl='''CREATE TABLE IF NOT EXISTS narrative_authorship(
        id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL,proposal_json TEXT NOT NULL,
        constraints_json TEXT NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL,
        review_json TEXT,result_json TEXT,created_day INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS narrative_details(
        id INTEGER PRIMARY KEY,subject_actor_id INTEGER NOT NULL REFERENCES actors(id),
        detail_key TEXT NOT NULL,category TEXT NOT NULL,epistemic TEXT NOT NULL,
        speaker_actor_id INTEGER REFERENCES actors(id),related_actor_id INTEGER REFERENCES actors(id),
        text TEXT NOT NULL,start_day INTEGER,observed_day INTEGER NOT NULL,
        observer_actor_id INTEGER NOT NULL REFERENCES actors(id),authorship_id INTEGER,
        anchor_id INTEGER NOT NULL REFERENCES historical_anchors(id),
        UNIQUE(subject_actor_id,detail_key,epistemic,speaker_actor_id));
        CREATE INDEX IF NOT EXISTS narrative_details_observer ON narrative_details(observer_actor_id,subject_actor_id,id);'''
    for statement in ddl.split(';'):
        if statement.strip():c.execute(statement)
    c.execute('CREATE TABLE IF NOT EXISTS narrative_detail_observers(detail_id INTEGER NOT NULL REFERENCES narrative_details(id),actor_id INTEGER NOT NULL REFERENCES actors(id),PRIMARY KEY(detail_id,actor_id))')


def schema():
    def obj(properties):
        return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
    ref={'anyOf':[{'type':'integer','minimum':1},{'type':'string','pattern':'^new:[a-z][a-z0-9_]{0,39}$'}]}
    nullable_ref={'anyOf':ref['anyOf']+[{'type':'null'}]}
    text={'type':'string','minLength':1,'maxLength':1200}
    detail=obj({'subject_ref':ref,'key':{'type':'string','pattern':'^[a-z][a-z0-9_]{0,63}$'},
        'category':{'enum':['biography','work','acquaintance','custom','local_history','circumstance']},
        'epistemic':{'enum':['objective','recollection','rumour']},'text':text,
        'start_day':{'type':['integer','null']},'related_ref':nullable_ref,'speaker_ref':nullable_ref})
    entity=obj({'id':{'type':'string','pattern':'^[a-z][a-z0-9_]{0,39}$'},
        'kind':{'enum':['person','institution']},'name':{'type':'string','minLength':1,'maxLength':100},
        'subtype':{'type':'string','minLength':1,'maxLength':80},'location_id':{'type':'integer','minimum':1},
        'origin_day':{'type':'integer'},'background':text,'independent_goal':text,'leader_ref':nullable_ref})
    return {'entities':{'type':'array','items':entity,'maxItems':4},
            'details':{'type':'array','items':detail,'maxItems':8}}


def _actor(c, aid):
    row=c.execute('SELECT id,name,actor_type,subtype,status,current_location_id FROM actors WHERE id=?',(aid,)).fetchone()
    if not row:raise ValueError('A referenced person or institution does not exist.')
    return dict(row)


def _scope(c, owner):
    from .player import _present_actors, get_player
    loc=get_player(c)['current_location_id']
    return loc,{owner,*[a['id'] for a in _present_actors(c,owner,loc)]}


def check(c, owner, spec):
    if not isinstance(spec,dict) or set(spec)!={'entities','details'}:raise ValueError('Authorship requires entities and details only.')
    if not isinstance(spec['entities'],list) or not isinstance(spec['details'],list) or len(spec['entities'])>4 or len(spec['details'])>8 or not (spec['entities'] or spec['details']):
        raise ValueError('Supply a bounded nonempty authorship batch.')
    today=c.execute('SELECT current_day FROM world_state').fetchone()[0]
    loc,accessible=_scope(c,owner);new={};names=set()
    def resolve(ref, nullable=False):
        if ref is None and nullable:return None
        if type(ref)is int and ref in accessible:return _actor(c,ref)
        if isinstance(ref,str) and ref.startswith('new:') and ref[4:] in new:return new[ref[4:]]
        raise ValueError('References must be accessible existing entities or earlier declared new entities.')
    for e in spec['entities']:
        if not isinstance(e,dict) or set(e)!=set(schema()['entities']['items']['properties']):raise ValueError('Invalid entity fields; resources, powers and ownership cannot be authored here.')
        if not isinstance(e['id'],str) or not re.fullmatch('[a-z][a-z0-9_]{0,39}',e['id']) or e['id'] in new:raise ValueError('New identity keys must be unique.')
        if e['kind'] not in ('person','institution'):raise ValueError('This route currently materializes people and institutions.')
        for key,limit in (('name',100),('subtype',80),('background',1200),('independent_goal',1200)):
            if not isinstance(e[key],str) or not e[key].strip() or len(e[key])>limit:raise ValueError('Identity and independent circumstances must be bounded nonempty text.')
        if e['name'].casefold() in names or c.execute('SELECT 1 FROM actors WHERE lower(name)=lower(?)',(e['name'],)).fetchone():raise ValueError('An existing identity cannot be recreated or renamed.')
        names.add(e['name'].casefold())
        if type(e['location_id'])is not int or e['location_id']!=loc:raise ValueError('Initial entity introduction requires the current established location.')
        if type(e['origin_day'])is not int or e['origin_day']>today:raise ValueError('Origins cannot lie in the future.')
        if e['kind']=='person':
            if e['leader_ref'] is not None or not today-110*366<=e['origin_day']<=today:raise ValueError('New people need plausible ordinary lifetimes; extraordinary profiles require their domain mechanism.')
        else:
            leader=resolve(e['leader_ref'])
            if e['leader_ref']==owner or leader.get('actor_type', 'character' if leader.get('kind')=='person' else '')!='character':raise ValueError('An independent institution needs an NPC leader, not invented player authority.')
        new[e['id']]=e
    keys=set()
    for d in spec['details']:
        if not isinstance(d,dict) or set(d)!=set(schema()['details']['items']['properties']):raise ValueError('Invalid detail fields.')
        resolve(d['subject_ref']);related=resolve(d['related_ref'],True);speaker=resolve(d['speaker_ref'],True)
        if d['category'] not in ('biography','work','acquaintance','custom','local_history','circumstance') or d['epistemic'] not in ('objective','recollection','rumour'):raise ValueError('Unsupported detail category or epistemic status.')
        if not isinstance(d['key'],str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}',d['key']):raise ValueError('Stable detail keys are required.')
        identity=(d['subject_ref'],d['key'],d['epistemic'],d['speaker_ref'])
        if identity in keys:raise ValueError('Duplicate detail identity in a batch.')
        keys.add(identity)
        if d['key'] in {'narrative_identity','birth_day','death_day','spouse','parents','stage','treasury','resources','authority','consent','ownership','victory','obligation'}:raise ValueError('Structural identity, family, capabilities and action outcomes require domain validation.')
        if not isinstance(d['text'],str) or not d['text'].strip() or len(d['text'])>1200:raise ValueError('Detail text must be bounded.')
        if d['start_day'] is not None and (type(d['start_day'])is not int or d['start_day']>today):raise ValueError('Historical details cannot be future outcomes.')
        if d['epistemic']!='objective' and (speaker is None or speaker.get('actor_type','character' if speaker.get('kind')=='person' else '')!='character'):raise ValueError('Claims need an identified speaker.')
        if d['epistemic']=='objective' and d['speaker_ref'] is not None:raise ValueError('Objective facts do not use a claim speaker.')
        if d['epistemic']=='objective' and isinstance(d['subject_ref'],str) and new[d['subject_ref'][4:]]['kind']=='person' and d['start_day'] is not None and d['start_day']<new[d['subject_ref'][4:]]['origin_day']:
            raise ValueError('A biographical fact cannot predate the subject birth.')
        if d['category']=='work' and d['epistemic']=='objective' and related is not None and related.get('actor_type','institution' if related.get('kind')=='institution' else '')!='institution':raise ValueError('Work affiliation requires an institution.')
        if type(d['subject_ref'])is int:
            if d['epistemic']=='objective' and d['start_day'] is not None:
                birth=c.execute('SELECT birth_day FROM actor_life_profiles WHERE actor_id=?',(d['subject_ref'],)).fetchone()
                if birth and birth[0] is not None and d['start_day']<birth[0]:raise ValueError('A biographical fact cannot predate the subject birth.')
            previous=c.execute('SELECT text FROM narrative_details WHERE subject_actor_id=? AND detail_key=? AND epistemic=? AND speaker_actor_id IS ?',
                (d['subject_ref'],d['key'],d['epistemic'],d['speaker_ref'])).fetchone()
            if previous and previous[0]!=d['text']:raise ValueError('A stable detail cannot overwrite established continuity; use a new dated development or a distinct uncertain claim.')
    return today


def constraints(c,owner,spec):
    """Private engine verification envelope, never player-facing scene knowledge."""
    ids={owner}
    for e in spec['entities']:
        if type(e['leader_ref'])is int:ids.add(e['leader_ref'])
    for d in spec['details']:
        ids.update(x for x in (d['subject_ref'],d['speaker_ref'],d['related_ref']) if type(x)is int)
    snapshots=[]
    for aid in sorted(ids):
        values={'identity':_actor(c,aid)}
        for table,column in [('actor_life_profiles','actor_id'),('actor_careers','actor_id'),('historical_anchors','entity_id'),('continuity_cores','entity_id'),('resources','actor_id'),('institution_memberships','member_actor_id')]:
            query=f'SELECT * FROM {table} WHERE {column}=?'
            if table in ('historical_anchors','continuity_cores'):query+=" AND entity_kind IN ('actor','institution')"
            values[table]=[dict(r) for r in c.execute(query,(aid,))]
        values['kinship']=[dict(r) for r in c.execute('SELECT * FROM kinship_links WHERE actor_a_id=? OR actor_b_id=?',(aid,aid))]
        values['details']=[dict(r) for r in c.execute('SELECT * FROM narrative_details WHERE subject_actor_id=? ORDER BY id',(aid,))]
        snapshots.append(values)
    return {'day':c.execute('SELECT current_day FROM world_state').fetchone()[0],'actors':snapshots,
            'locations':[dict(r) for r in c.execute('SELECT id,name,kind FROM locations WHERE id=?',(_scope(c,owner)[0],))]}


def prepare(c,sid,spec):
    from .ai_planning import session
    ensure(c);owner=session(c,sid)['owner_actor_id'];today=check(c,owner,spec)
    frozen=constraints(c,owner,spec)
    digest=hashlib.sha256(dump({'proposal':spec,'constraints':frozen}).encode()).hexdigest()
    cur=c.execute("INSERT INTO narrative_authorship(session_id,proposal_json,constraints_json,digest,status,created_day) VALUES (?,?,?,?,'prepared',?)",(sid,dump(spec),dump(frozen),digest,today))
    return {'id':cur.lastrowid,'digest':digest,'proposal':spec,'constraints':frozen}


def visible(c,owner,subject=None,limit=12,offset=0,search=''):
    ensure(c)
    if type(limit)is not int or type(offset)is not int or not 1<=limit<=24 or offset<0 or not isinstance(search,str) or len(search)>200:raise ValueError('Invalid bounded continuity query.')
    query='SELECT subject_actor_id,detail_key,category,epistemic,speaker_actor_id,related_actor_id,text,start_day,observed_day FROM narrative_details WHERE (observer_actor_id=? OR id IN (SELECT detail_id FROM narrative_detail_observers WHERE actor_id=?))'
    args=[owner,owner]
    if subject is not None:query+=' AND subject_actor_id=?';args.append(subject)
    if search:
        query+=' AND (detail_key LIKE ? OR text LIKE ?)';args.extend(['%'+search+'%','%'+search+'%'])
    return [dict(r) for r in c.execute(query+' ORDER BY id DESC LIMIT ? OFFSET ?',(*args,min(limit,24),offset))]


def _persist(c,owner,spec,authorship=None):
    today=check(c,owner,spec);refs={};created=[]
    def aid(ref):return refs[ref[4:]] if isinstance(ref,str) else ref
    for e in spec['entities']:
        if e['kind']=='person':
            from .resolution_controller import _materialize_latent_person, _sync_sim_tier
            from .embodiment import ensure_embodiment_profile
            from .presence import ensure_presence_profile
            lid=create_latent_entity(c,'person',e['subtype'],location_id=e['location_id'],constraints={'name':e['name'],'birth_day':e['origin_day']},historical_context={'biography':e['background'],'independent_goal':e['independent_goal'],'authorship_id':authorship})
            latent=c.execute('SELECT * FROM latent_entities WHERE id=?',(lid,)).fetchone()
            entity=_materialize_latent_person(c,latent,today,40,{'validated_campaign_authorship':40})
            ensure_embodiment_profile(c,entity)
            c.execute('UPDATE actors SET notes=? WHERE id=?',('Validated campaign authorship; previously undescribed history recorded.',entity))
            ensure_presence_profile(c,entity,base_location_id=e['location_id'],confidence=1,source_kind='narrative_introduction',effective_from_day=today)
            set_resolution(c,'actor',entity,'TRACKED',day=today,reason='Validated independent narrative introduction',source_kind='crystallization')
            _sync_sim_tier(c,entity,'TRACKED',today)
        else:
            from .resolution_controller import create_institution_candidate, update_institution_candidate, crystallize_institution_candidate
            leader=aid(e['leader_ref'])
            candidate=create_institution_candidate(c,e['subtype'],location_id=e['location_id'],proposed_name=e['name'],participants=[leader],
                resources={'preexisting_organization':True},evidence=[{'kind':'validated_campaign_authorship','authorship_id':authorship,'history':e['background'],'independent_goal':e['independent_goal']}])
            status=update_institution_candidate(c,candidate,significance_score=40)
            if status['status']!='eligible':raise ValueError('This institutional category needs additional native formation evidence; no successful institution was invented.')
            entity=crystallize_institution_candidate(c,candidate)
            c.execute('UPDATE institution_profiles SET founded_day=? WHERE actor_id=?',(e['origin_day'],entity))
            c.execute("UPDATE institution_memberships SET role_text='head',joined_day=? WHERE institution_actor_id=? AND member_actor_id=?",(today,entity,leader))
        refs[e['id']]=entity
        c.execute("INSERT INTO goals(actor_id,description,priority,status,created_day) VALUES (?,?,50,'active',?)",(entity,e['independent_goal'],today))
        upsert_continuity_core(c,'actor' if e['kind']=='person' else 'institution',entity,
            {'background':e['background'],'independent_goal':e['independent_goal'],'authorship_id':authorship},core_type='narrative_identity',historical_depth='shallow',source_kind='campaign')
        add_historical_anchor(c,'actor' if e['kind']=='person' else 'institution',entity,'narrative_origin',e['background'],start_day=e['origin_day'],detail={'authorship_id':authorship},canon_scope='campaign')
        created.append({'ref':'new:'+e['id'],'actor_id':entity,'name':e['name'],'kind':e['kind']})
    saved=[]
    records=spec['details']+[{'subject_ref':'new:'+e['id'],'key':'narrative_identity','category':'biography' if e['kind']=='person' else 'local_history',
        'epistemic':'objective','speaker_ref':None,'related_ref':None,'text':e['background'],'start_day':e['origin_day']} for e in spec['entities']]
    for d in records:
        subject,speaker,related=aid(d['subject_ref']),aid(d['speaker_ref']),aid(d['related_ref'])
        previous=c.execute('SELECT id FROM narrative_details WHERE subject_actor_id=? AND detail_key=? AND epistemic=? AND speaker_actor_id IS ?',(subject,d['key'],d['epistemic'],speaker)).fetchone()
        if previous:
            c.execute('INSERT OR IGNORE INTO narrative_detail_observers VALUES (?,?)',(previous[0],owner))
            saved.append(previous[0]);continue
        actor=_actor(c,subject);kind='institution' if actor['actor_type']=='institution' else 'actor'
        anchor=add_historical_anchor(c,kind,subject,'narrative_'+d['category'],d['text'],start_day=d['start_day'],
            detail={'key':d['key'],'epistemic':d['epistemic'],'speaker_actor_id':speaker,'related_actor_id':related,'observer_actor_id':owner,'authorship_id':authorship},
            source_kind='crystallization' if d['epistemic']=='objective' else 'memory',certainty=1 if d['epistemic']=='objective' else .5,canon_scope='campaign' if d['epistemic']=='objective' else 'provisional')
        cur=c.execute('INSERT INTO narrative_details(subject_actor_id,detail_key,category,epistemic,speaker_actor_id,related_actor_id,text,start_day,observed_day,observer_actor_id,authorship_id,anchor_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (subject,d['key'],d['category'],d['epistemic'],speaker,related,d['text'],d['start_day'],today,owner,authorship,anchor))
        saved.append(cur.lastrowid)
        for observer in {owner,speaker if speaker is not None else subject}:
            c.execute('INSERT OR IGNORE INTO narrative_detail_observers VALUES (?,?)',(cur.lastrowid,observer))
        if d['epistemic']=='objective' and related is not None:
            if d['category']=='work':
                c.execute("INSERT OR IGNORE INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status,joined_day,provenance_json) VALUES (?,?,'member','ordinary member','active',?,?)",(related,subject,d['start_day'] if d['start_day'] is not None else today,dump({'narrative_detail':cur.lastrowid})))
                if related in refs.values():
                    count=c.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'",(related,)).fetchone()[0]
                    c.execute("UPDATE institution_profiles SET capacity_json=json_set(capacity_json,'$.participant_count',?) WHERE actor_id=?",(count,related))
            elif d['category']=='acquaintance':
                from .relationships import ensure_relationship
                ensure_relationship(c,subject,related,today,started_day=d['start_day'],familiarity=10)
                ensure_relationship(c,related,subject,today,started_day=d['start_day'],familiarity=10)
    return {'created':created,'detail_ids':saved,'world_actions':False,'player_resources_or_authority_changed':False}


def record_claims(c,owner,details):
    ensure(c);spec={'entities':[],'details':details}
    if any(d.get('epistemic')=='objective' for d in details):raise ValueError('Objective additions need consistency review.')
    c.execute('SAVEPOINT narrative_claims')
    try:
        result=_persist(c,owner,spec);c.execute('RELEASE narrative_claims');return result
    except Exception:
        c.execute('ROLLBACK TO narrative_claims');c.execute('RELEASE narrative_claims');raise


def commit(c,run_id,digest,review):
    from .ai_planning import session
    ensure(c);row=c.execute('SELECT * FROM narrative_authorship WHERE id=?',(run_id,)).fetchone()
    if not row or row['status']!='prepared' or row['digest']!=digest:raise ValueError('Authorship proposal is missing, changed or already resolved.')
    if set(review)!={'compatible','independent','issues','reason'} or type(review['compatible'])is not bool or type(review['independent'])is not bool or not isinstance(review['issues'],list) or any(not isinstance(x,str) for x in review['issues']) or not isinstance(review['reason'],str):raise ValueError('Invalid authorship consistency review.')
    owner=session(c,row['session_id'])['owner_actor_id'];spec=json.loads(row['proposal_json'])
    check(c,owner,spec)
    if dump(constraints(c,owner,spec))!=row['constraints_json']:raise ValueError('World constraints changed; re-propose rather than use a stale review.')
    if not review['compatible'] or not review['independent'] or review['issues']:
        c.execute("UPDATE narrative_authorship SET status='rejected',review_json=? WHERE id=?",(dump(review),run_id))
        return {'status':'rejected','reason':'The proposed addition needs revision for consistency or independent causal plausibility. No hidden constraint details are disclosed.'}
    c.execute('SAVEPOINT narrative_authorship_commit')
    try:
        result=_persist(c,owner,spec,run_id)
        c.execute("UPDATE narrative_authorship SET status='applied',review_json=?,result_json=? WHERE id=?",(dump(review),dump(result),run_id))
        c.execute('RELEASE narrative_authorship_commit')
    except Exception:
        c.execute('ROLLBACK TO narrative_authorship_commit');c.execute('RELEASE narrative_authorship_commit');raise
    return {'status':'applied',**result}
