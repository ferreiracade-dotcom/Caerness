from __future__ import annotations

import json, random, sqlite3
from typing import Any, Callable

from .ecology import start_travel, find_route_path

STAGE_SCORE={None:0,'First':25,'Temper':38,'Third':52,'Breach':66,'Fifth':80,'Sixth':92}


def _day(conn): return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
def _j(raw,default):
    try:return json.loads(raw or '')
    except Exception:return default

def _actor_capability(conn:sqlite3.Connection, actor_id:int)->float:
    r=conn.execute("SELECT current_stage,vessel_adaptation,realization_integration,injury_constraint FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if not r:return 20.0
    base=float(STAGE_SCORE.get(r['current_stage'],20))
    base += (float(r['vessel_adaptation'])-50.0)*0.08 + (float(r['realization_integration'])-50.0)*0.08
    base -= float(r['injury_constraint'])*0.12
    c=conn.execute("SELECT MAX(ac.score) FROM actor_competence ac JOIN competence_domains d ON d.id=ac.domain_id WHERE ac.actor_id=? AND d.domain_key='martial'",(actor_id,)).fetchone()
    if c and c[0] is not None: base += (float(c[0])-50.0)*0.05
    return max(5.0,min(98.0,base))


def activate_tournament_substrate(conn:sqlite3.Connection)->dict[str,int]:
    loc=conn.execute("SELECT id FROM locations WHERE name='Cairnholt' ORDER BY id LIMIT 1").fetchone()
    if not loc:return {'tournament_series':0}
    lid=int(loc[0])
    before=int(conn.execute("SELECT COUNT(*) FROM tournament_series").fetchone()[0])
    conn.execute("""INSERT OR IGNORE INTO tournament_series(series_key,name,location_id,recurrence_days,next_registration_day,registration_lead_days,event_duration_days,cycle_index,convergence_every,status,metadata_json)
                  VALUES ('cairnholt-main','Cairnholt Tournament Cycle',?,365,180,60,21,0,5,'active',?)""",
                 (lid,json.dumps({'authority':'CAMPAIGN_CALIBRATION','canon_structure':'annual Cairnholt; every fifth cycle superseded by Amber Court Convergence','calendar_phase':'relative campaign calibration, not settled absolute era dating','source':'World Bible Part Ten'},sort_keys=True)))
    after=int(conn.execute("SELECT COUNT(*) FROM tournament_series").fetchone()[0])
    return {'tournament_series':after-before}


def next_tournament_due_day(conn:sqlite3.Connection,after_day:int,until_day:int)->int|None:
    vals=[]
    for q,args in [
        ("SELECT MIN(next_registration_day) FROM tournament_series WHERE status='active' AND next_registration_day>? AND next_registration_day<=?",(after_day,until_day)),
        ("SELECT MIN(next_review_day) FROM tournament_events WHERE status IN ('registration','active') AND next_review_day>? AND next_review_day<=?",(after_day,until_day)),
        ("SELECT MIN(next_review_day) FROM martial_challenges WHERE status='active' AND next_review_day>? AND next_review_day<=?",(after_day,until_day)),
    ]:
        r=conn.execute(q,args).fetchone()[0]
        if r is not None:vals.append(int(r))
    return min(vals) if vals else None


def _desire(conn,actor_id:int,field_key:str,day:int)->float:
    d=conn.execute("SELECT ambition,risk_tolerance,patience FROM actor_drives WHERE actor_id=?",(actor_id,)).fetchone()
    amb=float(d['ambition'])*100 if d else 50.0; risk=float(d['risk_tolerance'])*100 if d else 50.0
    training=10.0 if conn.execute("SELECT 1 FROM education_enrollments WHERE actor_id=? AND status='active' LIMIT 1",(actor_id,)).fetchone() else 0.0
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]); jitter=random.Random(seed+actor_id*997+day*17+(1 if 'rising' in field_key else 7)).uniform(-10,10)
    return amb*0.40+risk*0.20+training+_actor_capability(conn,actor_id)*0.25+jitter


def _candidate_rows(conn,field_key:str,day:int)->list[sqlite3.Row]:
    rows=conn.execute("""SELECT a.id,a.name,a.current_location_id,lp.birth_day,lp.life_stage,cp.current_stage
        FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id JOIN cultivation_profiles cp ON cp.actor_id=a.id
        WHERE a.actor_type='character' AND a.status='active' AND lp.life_status='living' AND cp.core_state='Open-Core' AND cp.active=1 AND cp.status='active'
          AND lp.life_stage IN ('youth','adult','elder') AND cp.current_stage IS NOT NULL""").fetchall()
    out=[]
    for r in rows:
        age=(day-int(r['birth_day']))/365.0 if r['birth_day'] is not None else None
        st=str(r['current_stage'])
        if field_key in {'rising','rising_court'}:
            if st not in {'First','Temper','Third'} or (age is not None and age>30):continue
        else:
            if st=='Sixth' or (age is not None and age<18):continue
        out.append(r)
    return out


def _register_named_entries(conn,event_id:int,field_id:int,field_key:str,location_id:int,day:int,named_cap:int=4)->int:
    candidates=[]
    for r in _candidate_rows(conn,field_key,day):
        if conn.execute("SELECT 1 FROM tournament_entries WHERE event_id=? AND actor_id=?",(event_id,int(r['id']))).fetchone():continue
        desire=_desire(conn,int(r['id']),field_key,day)
        if desire<48:continue
        origin=r['current_location_id']
        if origin is None:continue
        if int(origin)!=location_id and not find_route_path(conn,int(origin),location_id,day=day):continue
        candidates.append((desire+_actor_capability(conn,int(r['id']))*0.2,int(r['id']),int(origin)))
    candidates.sort(reverse=True)
    count=0
    for score,aid,origin in candidates[:named_cap]:
        conn.execute("INSERT INTO tournament_entries(event_id,field_id,actor_id,origin_location_id,seed_score,status,registered_day,metadata_json) VALUES (?,?,?,?,?,'registered',?,?)",
                     (event_id,field_id,aid,origin,score,day,json.dumps({'authority':'ENGINE_DERIVED','named_registry_entry':True},sort_keys=True)))
        if origin!=location_id:
            try:start_travel(conn,'actor',aid,location_id,metadata={'purpose':'tournament','event_id':event_id,'return_origin_location_id':origin})
            except ValueError:
                conn.execute("UPDATE tournament_entries SET status='withdrawn',metadata_json=? WHERE event_id=? AND actor_id=?",(json.dumps({'withdrawal_reason':'travel_unavailable'},sort_keys=True),event_id,aid))
        count+=1
    return count


def _open_event(conn,series:sqlite3.Row,day:int)->tuple[int,int]:
    cycle=int(series['cycle_index'])+1
    conv=(cycle%int(series['convergence_every'])==0)
    kind='convergence' if conv else 'annual'
    start=day+int(series['registration_lead_days']); end=start+int(series['event_duration_days'])
    name='Amber Court Convergence' if conv else 'Cairnholt Tournament'
    cur=conn.execute("INSERT OR IGNORE INTO tournament_events(series_id,event_kind,name,location_id,registration_day,start_day,end_day,next_review_day,status,metadata_json) VALUES (?,?,?,?,?,?,?,?, 'registration',?)",
                     (series['id'],kind,name,series['location_id'],day,start,end,start,json.dumps({'authority':'CAMPAIGN_CALIBRATION','cycle_index':cycle,'full_field_contains_latent_unnamed_competitors':True},sort_keys=True)))
    eid=int(cur.lastrowid or conn.execute("SELECT id FROM tournament_events WHERE series_id=? AND start_day=?",(series['id'],start)).fetchone()[0])
    specs=[('grand_open',32,'individual'),('rising_court',32,'individual'),('company_contest',16,'structural'),('masters_invitation',0,'structural')] if conv else [('open',32,'individual'),('rising',32,'individual'),('companies',16,'structural')]
    registered=0
    for key,cap,mode in specs:
        fcur=conn.execute("INSERT OR IGNORE INTO tournament_fields(event_id,field_key,simulation_mode,capacity,status,metadata_json) VALUES (?,?,?,?,?,?)",
            (eid,key,mode,cap,'registration' if mode=='individual' else 'structural',json.dumps({'authority':'CAMPAIGN_CALIBRATION','named_entry_cap':4},sort_keys=True)))
        fid=int(fcur.lastrowid or conn.execute("SELECT id FROM tournament_fields WHERE event_id=? AND field_key=?",(eid,key)).fetchone()[0])
        if mode=='individual':registered+=_register_named_entries(conn,eid,fid,key,int(series['location_id']),day,4)
    conn.execute("UPDATE tournament_series SET cycle_index=?,next_registration_day=next_registration_day+recurrence_days WHERE id=?",(cycle,series['id']))
    return eid,registered


def _create_round(conn,event:sqlite3.Row,field:sqlite3.Row,day:int)->int:
    entrants=conn.execute("SELECT actor_id,seed_score FROM tournament_entries WHERE field_id=? AND status='active' ORDER BY seed_score DESC,actor_id",(field['id'],)).fetchall()
    if len(entrants)<=1:return 0
    rnd=int(field['round_index'])+1
    ids=[int(r['actor_id']) for r in entrants]
    # High/low seeding avoids arbitrary neighboring insertion order and leaves upset potential to combat.
    pairs=[]
    while len(ids)>=2:pairs.append((ids.pop(0),ids.pop(-1)))
    if ids:
        # bye remains active
        pass
    for a,b in pairs:
        conn.execute("INSERT INTO tournament_bouts(event_id,field_id,round_index,actor_a_id,actor_b_id,status,scheduled_day,metadata_json) VALUES (?,?,?,?,?,'scheduled',?,?)",
                     (event['id'],field['id'],rnd,a,b,day,json.dumps({'rules':'controlled nonlethal tournament bout','authority':'ENGINE_DERIVED'},sort_keys=True)))
    conn.execute("UPDATE tournament_fields SET round_index=? WHERE id=?",(rnd,field['id']))
    return len(pairs)


def _start_event(conn,event:sqlite3.Row,day:int)->dict[str,int]:
    loc=int(event['location_id']); counts={'arrived':0,'withdrawn':0,'bouts':0}
    for ent in conn.execute("SELECT e.*,a.current_location_id FROM tournament_entries e JOIN actors a ON a.id=e.actor_id WHERE e.event_id=? AND e.status='registered'",(event['id'],)).fetchall():
        if ent['current_location_id'] is not None and int(ent['current_location_id'])==loc:
            conn.execute("UPDATE tournament_entries SET status='active' WHERE id=?",(ent['id'],));counts['arrived']+=1
        else:
            conn.execute("UPDATE tournament_entries SET status='withdrawn',eliminated_day=?,metadata_json=? WHERE id=?",(day,json.dumps({'withdrawal_reason':'not_at_venue_by_start'},sort_keys=True),ent['id']));counts['withdrawn']+=1
    for field in conn.execute("SELECT * FROM tournament_fields WHERE event_id=?",(event['id'],)).fetchall():
        if field['simulation_mode']=='structural':continue
        n=int(conn.execute("SELECT COUNT(*) FROM tournament_entries WHERE field_id=? AND status='active'",(field['id'],)).fetchone()[0])
        if n>=2:
            conn.execute("UPDATE tournament_fields SET status='active' WHERE id=?",(field['id'],)); counts['bouts']+=_create_round(conn,event,field,day)
        elif n==1:
            conn.execute("UPDATE tournament_fields SET status='active' WHERE id=?",(field['id'],)); _resolve_named_track(conn,event,conn.execute("SELECT * FROM tournament_fields WHERE id=?",(field['id'],)).fetchone(),day)
        else:conn.execute("UPDATE tournament_fields SET status='resolved',metadata_json=? WHERE id=?",(json.dumps({'champion_resolution':'latent_field','reason':'no_named_entries'},sort_keys=True),field['id']))
    conn.execute("UPDATE tournament_events SET status='active',next_review_day=? WHERE id=?",(day+2,event['id']))
    return counts


def _structural_final(conn,event:sqlite3.Row,field:sqlite3.Row,named_winner:int,day:int)->bool:
    cap=_actor_capability(conn,named_winner); difficulty=57.0 if field['field_key'] in {'open','grand_open'} else 34.0
    seed=int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0]); rng=random.Random(seed+int(event['id'])*1777+int(field['id'])*31+named_winner)
    return cap+rng.uniform(-14,14)>=difficulty


def _return_home(conn,entry:sqlite3.Row,event_location:int)->None:
    origin=entry['origin_location_id']; aid=int(entry['actor_id'])
    if origin is None or int(origin)==event_location:return
    a=conn.execute("SELECT current_location_id,status FROM actors WHERE id=?",(aid,)).fetchone()
    if not a or a['status']!='active' or a['current_location_id'] is None or int(a['current_location_id'])!=event_location:return
    if conn.execute("SELECT 1 FROM travel_plans WHERE subject_kind='actor' AND subject_id=? AND status IN ('active','stalled')",(aid,)).fetchone():return
    try:start_travel(conn,'actor',aid,int(origin),metadata={'purpose':'return_from_tournament','event_id':int(entry['event_id'])})
    except ValueError:pass


def _resolve_named_track(conn,event:sqlite3.Row,field:sqlite3.Row,day:int)->None:
    active=conn.execute("SELECT * FROM tournament_entries WHERE field_id=? AND status='active' ORDER BY seed_score DESC,id",(field['id'],)).fetchall()
    if len(active)!=1:return
    winner=active[0]; aid=int(winner['actor_id']); full_win=_structural_final(conn,event,field,aid,day)
    meta=_j(field['metadata_json'],{});meta['named_track_winner_actor_id']=aid
    if full_win:
        meta['champion_resolution']='named'; conn.execute("UPDATE tournament_entries SET status='champion' WHERE id=?",(winner['id'],)); champ=aid
    else:
        meta['champion_resolution']='latent_field'; meta['named_track_winner_lost_to_structural_field']=True
        conn.execute("UPDATE tournament_entries SET status='eliminated',eliminated_day=? WHERE id=?",(day,winner['id'])); champ=None
    conn.execute("UPDATE tournament_fields SET status='resolved',champion_actor_id=?,metadata_json=? WHERE id=?",(champ,json.dumps(meta,sort_keys=True),field['id']))
    _return_home(conn,winner,int(event['location_id']))



def _referee_decision(conn: sqlite3.Connection, duel_id: int, day: int, *, max_rounds: int) -> dict[str, Any] | None:
    eng=conn.execute("SELECT * FROM combat_engagements WHERE id=?",(duel_id,)).fetchone()
    if not eng or eng['status']!='active' or int(eng['round_index'])<max_rounds:return None
    cs=conn.execute("SELECT * FROM duel_combatants WHERE engagement_id=? ORDER BY id",(duel_id,)).fetchall()
    if len(cs)!=2:return None
    def score(c):return float(c['readiness'])*0.4+float(c['stamina'])*0.25+float(c['composure'])*0.2+float(c['momentum'])*0.15
    ranked=sorted(cs,key=lambda c:(score(c),-int(c['actor_id'])),reverse=True); winner,loser=ranked[0],ranked[1]
    conn.execute("UPDATE duel_combatants SET status='victorious' WHERE id=?",(winner['id'],));conn.execute("UPDATE duel_combatants SET status='defeated' WHERE id=?",(loser['id'],))
    outcome={'winner_actor_id':int(winner['actor_id']),'resolution':'referee_decision','max_controlled_exchanges':max_rounds}
    conn.execute("UPDATE combat_engagements SET status='resolved',phase='aftermath',day_ended=?,outcome_json=? WHERE id=?",(day,json.dumps(outcome,sort_keys=True),duel_id))
    from .harm import project_duel_harm
    harm = project_duel_harm(conn, duel_id)
    return {'status':'resolved','engagement_id':duel_id,'outcome':outcome,'referee_decision':True,'harm_incidents':[int(h['id']) for h in harm]}

def _record_martial_anchor(conn: sqlite3.Connection, actor_id: int, *, kind: str, source_id: int, weight: float, description: str, day: int) -> int | None:
    if not conn.execute("SELECT 1 FROM cultivation_profiles WHERE actor_id=? AND core_state='Open-Core' AND active=1 AND status='active'",(actor_id,)).fetchone():
        return None
    from .cultivation import record_realization_anchor
    return record_realization_anchor(conn,actor_id,kind,source_kind=kind,source_id=source_id,weight=weight,description=description,
                                     metadata={'concrete_martial_experience':True,'single_use':True},day=day)


def _process_active_event(conn,event:sqlite3.Row,day:int)->dict[str,int]:
    from .combat import create_duel, resolve_duel_exchange
    out={'bouts_started':0,'exchanges':0,'bouts_resolved':0,'fields_resolved':0,'events_resolved':0}
    for bout in conn.execute("SELECT * FROM tournament_bouts WHERE event_id=? AND status IN ('scheduled','active') AND scheduled_day<=? ORDER BY id",(event['id'],day)).fetchall():
        eid=bout['duel_engagement_id']
        if eid is None:
            eid=create_duel(conn,f"{event['name']} bout",int(bout['actor_a_id']),int(bout['actor_b_id']),location_id=int(event['location_id']),objective='Tournament bout under submitted event rules',stakes=2,capability_a=_actor_capability(conn,int(bout['actor_a_id'])),capability_b=_actor_capability(conn,int(bout['actor_b_id'])),metadata={'tournament_event_id':int(event['id']),'tournament_bout_id':int(bout['id']),'nonlethal':True})
            conn.execute("UPDATE tournament_bouts SET duel_engagement_id=?,status='active' WHERE id=?",(eid,bout['id']));out['bouts_started']+=1
        result=resolve_duel_exchange(conn,int(eid));out['exchanges']+=1
        if result.get('status')!='resolved':
            decided=_referee_decision(conn,int(eid),day,max_rounds=8)
            if decided: result=decided
        if result.get('status')=='resolved':
            winner=(result.get('outcome') or {}).get('winner_actor_id')
            if winner is None:
                # tournament requires advancement; use higher remaining readiness if duel mutually disengages.
                cs=conn.execute("SELECT actor_id,readiness FROM duel_combatants WHERE engagement_id=? ORDER BY readiness DESC,actor_id LIMIT 1",(eid,)).fetchone(); winner=int(cs['actor_id'])
            loser=int(bout['actor_b_id']) if int(winner)==int(bout['actor_a_id']) else int(bout['actor_a_id'])
            conn.execute("UPDATE tournament_bouts SET status='resolved',winner_actor_id=?,resolved_day=? WHERE id=?",(winner,day,bout['id']))
            _record_martial_anchor(conn,int(bout['actor_a_id']),kind='tournament_bout',source_id=int(bout['id']),weight=0.85,
                                   description='A resolved tournament bout presented a concrete martial problem under live opposition.',day=day)
            _record_martial_anchor(conn,int(bout['actor_b_id']),kind='tournament_bout',source_id=int(bout['id']),weight=0.85,
                                   description='A resolved tournament bout presented a concrete martial problem under live opposition.',day=day)
            conn.execute("UPDATE tournament_entries SET status='eliminated',eliminated_day=? WHERE event_id=? AND actor_id=?",(day,event['id'],loser))
            ent=conn.execute("SELECT * FROM tournament_entries WHERE event_id=? AND actor_id=?",(event['id'],loser)).fetchone();
            if ent:_return_home(conn,ent,int(event['location_id']))
            out['bouts_resolved']+=1
    for f in conn.execute("SELECT * FROM tournament_fields WHERE event_id=? AND status='active' AND simulation_mode='individual'",(event['id'],)).fetchall():
        pending=int(conn.execute("SELECT COUNT(*) FROM tournament_bouts WHERE field_id=? AND round_index=? AND status IN ('scheduled','active')",(f['id'],f['round_index'])).fetchone()[0])
        if pending:continue
        active_n=int(conn.execute("SELECT COUNT(*) FROM tournament_entries WHERE field_id=? AND status='active'",(f['id'],)).fetchone()[0])
        if active_n<=1:
            _resolve_named_track(conn,event,f,day);out['fields_resolved']+=1
        else:out['bouts_started']+=_create_round(conn,event,f,day+2)
    unresolved=int(conn.execute("SELECT COUNT(*) FROM tournament_fields WHERE event_id=? AND simulation_mode='individual' AND status!='resolved'",(event['id'],)).fetchone()[0])
    if unresolved==0:
        conn.execute("UPDATE tournament_events SET status='resolved',next_review_day=?,metadata_json=metadata_json WHERE id=?",(day,event['id']));out['events_resolved']=1
    else:conn.execute("UPDATE tournament_events SET next_review_day=? WHERE id=?",(day+2,event['id']))
    return out


def create_accepted_challenge(conn:sqlite3.Connection,proposer:int,recipient:int,location_id:int,day:int,*,interaction_id:int|None=None,terms_kind:str='controlled')->dict[str,int]:
    from .combat import create_duel
    if terms_kind=='lethal': lethal=1
    else: lethal=0
    if conn.execute("SELECT 1 FROM combat_engagements ce JOIN duel_combatants dc ON dc.engagement_id=ce.id WHERE dc.actor_id IN (?,?) AND ce.status='active' LIMIT 1",(proposer,recipient)).fetchone():raise ValueError('a participant is already in active combat')
    cur=conn.execute("INSERT INTO martial_challenges(proposer_actor_id,recipient_actor_id,location_id,interaction_id,terms_kind,lethal,status,created_day,next_review_day,metadata_json) VALUES (?,?,?,?,?,?,'active',?,?,?)",
        (proposer,recipient,location_id,interaction_id,terms_kind,lethal,day,day+1,json.dumps({'authority':'ENGINE_DERIVED','accepted_terms':True},sort_keys=True)))
    cid=int(cur.lastrowid)
    duel=create_duel(conn,f"Accepted challenge: {proposer} vs {recipient}",proposer,recipient,location_id=location_id,objective=f"Accepted {terms_kind} challenge",stakes=4 if lethal else 2,capability_a=_actor_capability(conn,proposer),capability_b=_actor_capability(conn,recipient),metadata={'martial_challenge_id':cid,'nonlethal':not bool(lethal)})
    conn.execute("UPDATE martial_challenges SET duel_engagement_id=? WHERE id=?",(duel,cid))
    return {'challenge_id':cid,'duel_engagement_id':duel}


def _process_challenges(conn,day:int,event_logger:Callable[...,int]|None=None)->dict[str,int]:
    from .combat import resolve_duel_exchange
    out={'challenge_exchanges':0,'challenges_resolved':0}
    for ch in conn.execute("SELECT * FROM martial_challenges WHERE status='active' AND next_review_day<=? ORDER BY id",(day,)).fetchall():
        result=resolve_duel_exchange(conn,int(ch['duel_engagement_id']));out['challenge_exchanges']+=1
        if result.get('status')!='resolved' and not int(ch['lethal']):
            decided=_referee_decision(conn,int(ch['duel_engagement_id']),day,max_rounds=10)
            if decided: result=decided
        if result.get('status')=='resolved':
            conn.execute("UPDATE martial_challenges SET status='resolved',resolved_day=?,next_review_day=? WHERE id=?",(day,day,ch['id']))
            weight=1.55 if int(ch['lethal']) else 1.05
            for aid in (int(ch['proposer_actor_id']),int(ch['recipient_actor_id'])):
                _record_martial_anchor(conn,aid,kind='martial_challenge',source_id=int(ch['id']),weight=weight,
                                       description='A resolved accepted martial challenge forced adaptation against a resisting opponent.',day=day)
            # Lethal terms mean lethal intent, not guaranteed death. HARM-01 owns whether the
            # resolved exchange produced transient injury, persistent injury/disability, or death.
            out['challenges_resolved']+=1
        else:conn.execute("UPDATE martial_challenges SET next_review_day=? WHERE id=?",(day+1,ch['id']))
    return out


def process_due_tournaments(conn:sqlite3.Connection,day:int,event_logger:Callable[...,int]|None=None)->dict[str,int]:
    out={'series_due':0,'events_created':0,'entries_registered':0,'events_started':0,'arrived':0,'withdrawn':0,'bouts_started':0,'exchanges':0,'bouts_resolved':0,'fields_resolved':0,'events_resolved':0,'challenge_exchanges':0,'challenges_resolved':0}
    for series in conn.execute("SELECT * FROM tournament_series WHERE status='active' AND next_registration_day<=? ORDER BY id",(day,)).fetchall():
        out['series_due']+=1; eid,n=_open_event(conn,series,int(series['next_registration_day']));out['events_created']+=1;out['entries_registered']+=n
        if event_logger:event_logger(day=day,event_type='tournament_registration',title='Tournament registration opened',summary=f"Registration opened for tournament event #{eid}; {n} named entrants entered the tracked layer.",severity=2,location_id=int(series['location_id']))
    for event in conn.execute("SELECT * FROM tournament_events WHERE status='registration' AND next_review_day<=? ORDER BY id",(day,)).fetchall():
        r=_start_event(conn,event,day);out['events_started']+=1
        for k in ('arrived','withdrawn','bouts'): out['bouts_started' if k=='bouts' else k]+=r[k]
        if event_logger:event_logger(day=day,event_type='tournament_start',title=str(event['name']),summary=f"{event['name']} entered active competition under submitted event rules.",severity=3,location_id=int(event['location_id']))
    for event in conn.execute("SELECT * FROM tournament_events WHERE status='active' AND next_review_day<=? ORDER BY id",(day,)).fetchall():
        r=_process_active_event(conn,event,day)
        for k,v in r.items():out[k]+=v
        if r['events_resolved'] and event_logger:event_logger(day=day,event_type='tournament_result',title=str(event['name']),summary=f"{event['name']} completed its tracked individual fields; latent competitors remained part of the full field.",severity=3,location_id=int(event['location_id']))
    cr=_process_challenges(conn,day,event_logger=event_logger);out.update({k:out.get(k,0)+v for k,v in cr.items()})
    return out
