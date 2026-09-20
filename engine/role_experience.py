from __future__ import annotations

import json
import random
import sqlite3
from typing import Any, Callable

from .career_reach import career_state, note_role_event, review_career_reach
from .relationships import adjust_relationship


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _rng(conn: sqlite3.Connection, actor_id: int, day: int, salt: int = 0) -> random.Random:
    seed = int(conn.execute("SELECT rng_seed FROM world_state WHERE id=1").fetchone()[0])
    return random.Random(seed * 1000003 + actor_id * 9176 + day * 131 + salt)


def _living(conn: sqlite3.Connection, actor_id: int) -> bool:
    row = conn.execute("""SELECT a.status,COALESCE(lp.life_status,'living') life_status
                          FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id
                          WHERE a.id=?""", (actor_id,)).fetchone()
    return bool(row and str(row['status']) == 'active' and str(row['life_status']) == 'living')


def _subtype(conn: sqlite3.Connection, actor_id: int) -> str:
    r = conn.execute("SELECT COALESCE(subtype,'') FROM actors WHERE id=?", (actor_id,)).fetchone()
    return str(r[0] or '').lower() if r else ''


def _resource_add(conn: sqlite3.Connection, actor_id: int, key: str, delta: float, unit: str = 'calibration units') -> None:
    day = _day(conn)
    row = conn.execute("SELECT id,amount FROM resources WHERE actor_id=? AND resource_type=?", (actor_id, key)).fetchone()
    if row:
        conn.execute("UPDATE resources SET amount=MAX(0,amount+?),updated_day=? WHERE id=?", (float(delta), day, int(row['id'])))
    else:
        conn.execute("INSERT INTO resources(actor_id,resource_type,amount,unit,updated_day) VALUES (?,?,?,?,?)",
                     (actor_id, key, max(0.0, float(delta)), unit, day))


def _resource_amount(conn: sqlite3.Connection, actor_id: int, key: str) -> float:
    row=conn.execute("SELECT amount FROM resources WHERE actor_id=? AND resource_type=? ORDER BY id LIMIT 1",(actor_id,key)).fetchone()
    return float(row[0]) if row else 0.0


def _relationship_delta(conn: sqlite3.Connection, a: int, b: int, *, stance: float = 0, trust: float = 0, obligation: float = 0) -> None:
    if a == b:
        return
    adjust_relationship(conn, int(a), int(b), _day(conn), stance_delta=stance, trust_delta=trust, obligation_delta=obligation)


def _active_underworld_enterprise(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute("""SELECT ce.* FROM civilian_enterprises ce
                           WHERE ce.owner_actor_id=? AND ce.status='active' AND
                             (EXISTS(SELECT 1 FROM underworld_evidence ue WHERE ue.subject_kind='enterprise' AND ue.subject_id=ce.id)
                              OR lower(COALESCE(ce.metadata_json,'')) LIKE '%front_for_minor_crew%')
                           ORDER BY ce.id LIMIT 1""", (actor_id,)).fetchone()


def _merchant_enterprise(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute("""SELECT * FROM civilian_enterprises WHERE owner_actor_id=? AND status='active'
                           AND enterprise_kind IN ('merchant_house','trade','transport','service') ORDER BY id LIMIT 1""", (actor_id,)).fetchone()


def _is_witness(conn: sqlite3.Connection, actor_id: int) -> bool:
    return bool(conn.execute("""SELECT 1 FROM religious_affiliations ra JOIN religious_traditions rt ON rt.id=ra.tradition_id
                                WHERE ra.actor_id=? AND ra.status='active' AND lower(rt.name) LIKE '%witness%' LIMIT 1""", (actor_id,)).fetchone())


def _martial_institution(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    # Generic martial-career resolution is for practitioners inside martial institutions, not every
    # Open-Core king, convenor or institutional head who happens to have a membership row.
    return conn.execute("""SELECT im.*,a.name institution_name,COALESCE(ip.institution_kind,a.subtype,'') institution_kind
                           FROM institution_memberships im
                           JOIN actors a ON a.id=im.institution_actor_id
                           LEFT JOIN institution_profiles ip ON ip.actor_id=a.id
                           WHERE im.member_actor_id=? AND im.status='active'
                             AND lower(COALESCE(ip.institution_kind,a.subtype,'')) IN ('sect','clan/house','order','military school','school','coven')
                             AND (lower(COALESCE(im.role_text,'')) LIKE '%disciple%'
                                  OR lower(COALESCE(im.role_text,'')) LIKE '%fighter%'
                                  OR lower(COALESCE(im.role_text,'')) LIKE '%practitioner%'
                                  OR lower(COALESCE(im.role_text,'')) LIKE '%instructor%'
                                  OR lower(COALESCE(im.role_text,'')) LIKE '%teacher%'
                                  OR lower(COALESCE(im.membership_kind,''))='disciple')
                             AND lower(COALESCE(im.role_text,'')) NOT LIKE '%sect head%'
                             AND lower(COALESCE(im.role_text,'')) NOT LIKE '%clan head%'
                             AND lower(COALESCE(im.role_text,'')) NOT LIKE '%senior master%'
                             AND lower(COALESCE(im.role_text,'')) NOT LIKE '%senior elder%'
                           ORDER BY im.id LIMIT 1""", (actor_id,)).fetchone()


def _open_core(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM cultivation_profiles WHERE actor_id=? AND core_state='Open-Core' AND active=1 AND status='active'", (actor_id,)).fetchone()


def _role_kind(conn: sqlite3.Connection, actor_id: int) -> tuple[str | None, Any]:
    st = _subtype(conn, actor_id)
    uw = _active_underworld_enterprise(conn, actor_id)
    if uw is not None or any(x in st for x in ('gang ', 'gang collector', 'racket', 'enforcer', 'underworld')):
        return 'underworld', uw
    if any(x in st for x in ('long road', 'escort hand', 'road escort', 'caravan guard')):
        return 'longroad', None
    if _is_witness(conn, actor_id) or any(x in st for x in ('parish clerk','charitable organizer','witness clerk')):
        return 'witness', None
    mer = _merchant_enterprise(conn, actor_id)
    if mer is not None or any(x in st for x in ('merchant','factor','trader','freight')):
        return 'merchant', mer
    if any(x in st for x in ('retainer','horse-country fighter','estate guard','soldier')):
        return 'retainer', None
    inst = _martial_institution(conn, actor_id)
    if inst is not None and _open_core(conn, actor_id) is not None:
        return 'martial_institution', inst
    # Open-Core is a capability, not a profession. Kings, sect heads, great masters and political
    # figures must not be assigned a generic 'martial professional' career merely because they cultivate.
    if _open_core(conn, actor_id) is not None:
        exclusions=('king','queen','emperor','sect head','clan head','ruler','convenor','senior master','senior elder','greatest acknowledged','summit figure','grand coven','principal inheritor','political figure')
        working=('working fighter','working practitioner','duelist','mercenary','bounty','contract fighter','guard','professional fighter','working martial','escort captain')
        if not any(x in st for x in exclusions) and any(x in st for x in working):
            return 'martial', None
    return None, None


def _event(conn: sqlite3.Connection, event_logger: Callable[..., int], actor_id: int, event_type: str,
           title: str, summary: str, severity: int = 1, *, location_id: int | None = None) -> int:
    if location_id is None:
        row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
        location_id = int(row[0]) if row and row[0] is not None else None
    return int(event_logger(day=_day(conn), event_type=event_type, title=title, summary=summary, severity=severity,
                            source_actor_id=actor_id, target_actor_ids=(actor_id,), location_id=location_id,
                            visibility='limited', rumorability=0.08 if severity < 3 else 0.35, reliability=0.9))


def _reachable_destination(conn: sqlite3.Connection, actor_id: int, rng: random.Random, max_hops: int = 1) -> tuple[int,str,int] | None:
    row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not row or row[0] is None:
        return None
    origin = int(row[0]); max_hops=max(1,int(max_hops))
    frontier=[origin]; seen={origin}; depth={origin:0}; candidates=[]
    while frontier:
        here=frontier.pop(0); d=depth[here]
        if d>=max_hops: continue
        rows=conn.execute("""SELECT tr.to_location_id destination_id FROM travel_routes tr
                             WHERE tr.from_location_id=? AND tr.status IN ('open','restricted')
                             UNION
                             SELECT tr.from_location_id destination_id FROM travel_routes tr
                             WHERE tr.to_location_id=? AND tr.bidirectional=1 AND tr.status IN ('open','restricted')""",(here,here)).fetchall()
        for r in rows:
            dest=int(r['destination_id'])
            if dest in seen: continue
            seen.add(dest); depth[dest]=d+1; frontier.append(dest)
            name=conn.execute("SELECT name FROM locations WHERE id=?",(dest,)).fetchone()
            if name: candidates.append((dest,str(name[0]),d+1))
    if not candidates: return None
    # Wider reach makes distant work possible, not mandatory. Weight mildly toward the edge of reach.
    weights=[1.0 + .35*c[2] for c in candidates]; total=sum(weights); pick=rng.random()*total
    for c,w in zip(candidates,weights):
        pick-=w
        if pick<=0: return c
    return candidates[-1]


def _try_travel_assignment(conn: sqlite3.Connection, actor_id: int, purpose: str, rng: random.Random, *, max_hops: int = 1, metadata: dict[str,Any] | None = None) -> tuple[str | None, int | None]:
    if conn.execute("SELECT 1 FROM travel_plans WHERE subject_kind='actor' AND subject_id=? AND status IN ('active','stalled')", (actor_id,)).fetchone():
        return None, None
    dest = _reachable_destination(conn, actor_id, rng, max_hops=max_hops)
    if not dest:
        return None, None
    from .ecology import start_travel
    meta={'purpose':purpose,'role_experience':True,'reach_hops':dest[2]}; meta.update(metadata or {})
    try:
        pid = start_travel(conn, 'actor', actor_id, dest[0], metadata=meta)
    except ValueError:
        return None, None
    return dest[1], int(pid)


def _peer(conn: sqlite3.Connection, actor_id: int, rng: random.Random) -> int | None:
    row = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()
    if not row or row[0] is None:
        return None
    loc = int(row[0])
    candidates = conn.execute("""SELECT a.id FROM actors a JOIN cultivation_profiles cp ON cp.actor_id=a.id
        LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id
        WHERE a.actor_type='character' AND a.status='active' AND a.current_location_id=? AND a.id<>?
          AND cp.core_state='Open-Core' AND cp.active=1 AND cp.status='active' AND COALESCE(lp.life_status,'living')='living'
          AND NOT EXISTS(SELECT 1 FROM combat_engagements ce JOIN duel_combatants dc ON dc.engagement_id=ce.id WHERE ce.status='active' AND dc.actor_id=a.id)
        ORDER BY a.id""", (loc, actor_id)).fetchall()
    if not candidates:
        return None
    return int(candidates[rng.randrange(len(candidates))][0])


def _try_challenge(conn: sqlite3.Connection, actor_id: int, rng: random.Random, *, lethal_allowed: bool = False) -> dict[str, Any] | None:
    if conn.execute("SELECT 1 FROM combat_engagements ce JOIN duel_combatants dc ON dc.engagement_id=ce.id WHERE ce.status='active' AND dc.actor_id=? LIMIT 1", (actor_id,)).fetchone():
        return None
    other = _peer(conn, actor_id, rng)
    if other is None:
        return None
    d = conn.execute("SELECT aggression,risk_tolerance FROM actor_drives WHERE actor_id=?", (actor_id,)).fetchone()
    agg = float(d['aggression']) if d else 0.45
    risk = float(d['risk_tolerance']) if d else 0.45
    lethal = bool(lethal_allowed and agg > 0.72 and risk > 0.68 and rng.random() < 0.08)
    terms = 'lethal' if lethal else ('first_blood' if rng.random() < 0.30 else 'controlled')
    from .tournaments import create_accepted_challenge
    loc = int(conn.execute("SELECT current_location_id FROM actors WHERE id=?", (actor_id,)).fetchone()[0])
    ids = create_accepted_challenge(conn, actor_id, other, loc, _day(conn), terms_kind=terms)
    return {'opponent_actor_id':other,'terms_kind':terms,**ids}


def _resolve_pending_hit(conn: sqlite3.Connection, actor_id: int, enterprise_id: int, location_id: int | None, rng: random.Random, event_logger, organization_id: int | None = None) -> int:
    """Resolve the oldest previously ordered hit before generating another underworld beat."""
    from .underworld import update_underworld_organization, maybe_deepen_gang_structure
    day=_day(conn)
    rows=conn.execute("""SELECT * FROM underworld_evidence WHERE subject_kind='enterprise' AND subject_id=?
                         AND evidence_kind='targeted_violence' AND status='active' ORDER BY created_day,id""",(enterprise_id,)).fetchall()
    for row in rows:
        meta=json.loads(row['metadata_json'] or '{}')
        if not meta.get('outcome_not_assumed') or day-int(row['created_day']) < 60:
            continue
        roll=rng.random(); source_id=int(row['source_id']) if row['source_id'] is not None else None
        if roll < .48:
            outcome='target_killed'
            _event(conn,event_logger,actor_id,'role_underworld_hit_success','Ordered killing succeeded',
                   'The ordered killing reached the rival crew leader. The rival leader was killed; the rival crew survives as a group and may reorganize or retaliate.',5,location_id=location_id)
            conn.execute("UPDATE civilian_enterprises SET reputation=MIN(100,reputation+2.5),updated_day=? WHERE id=?",(day,enterprise_id))
            if organization_id is not None:
                update_underworld_organization(conn,organization_id,dimension_deltas={'reputation_deterrence':3.0,'violence_capacity':1.5,'cohesion':0.5})
        elif roll < .82:
            outcome='target_survived'
            _event(conn,event_logger,actor_id,'role_underworld_hit_failed','Ordered killing failed',
                   'The attempt on the rival crew leader failed. The target survived and now has concrete reason to expect further violence.',4,location_id=location_id)
            conn.execute("UPDATE civilian_enterprises SET reputation=MAX(0,reputation-1.0),updated_day=? WHERE id=?",(day,enterprise_id))
            if organization_id is not None:
                update_underworld_organization(conn,organization_id,dimension_deltas={'reputation_deterrence':-1.0,'cohesion':-0.5})
        else:
            outcome='attack_exposed'
            _event(conn,event_logger,actor_id,'role_underworld_hit_exposed','Ordered killing exposed the gang',
                   'The attempted killing failed messily enough to increase local exposure. The rival leader survived and the gang paid a reputational and cash cost.',5,location_id=location_id)
            conn.execute("UPDATE civilian_enterprises SET cash=MAX(0,cash-4),reputation=MAX(0,reputation-2.5),updated_day=? WHERE id=?",(day,enterprise_id))
            if organization_id is not None:
                update_underworld_organization(conn,organization_id,dimension_deltas={'reputation_deterrence':-2.0,'cohesion':-1.5,'membership_stability':-0.5})
        if organization_id is not None:
            maybe_deepen_gang_structure(conn,organization_id)
        meta.update({'outcome_not_assumed':False,'resolved_day':day,'outcome':outcome,'source_order_event_id':source_id})
        conn.execute("UPDATE underworld_evidence SET metadata_json=?,updated_day=? WHERE id=?",(json.dumps(meta,sort_keys=True),day,int(row['id'])))
        return 1
    return 0


def _underworld(conn: sqlite3.Connection, actor_id: int, enterprise: sqlite3.Row | None, rng: random.Random, event_logger) -> int:
    from .underworld import (
        record_underworld_evidence, ensure_actor_underworld_organization,
        organization_operational_factors, update_underworld_organization, maybe_deepen_gang_structure,
        simulate_underworld_membership_turnover, record_underworld_membership_flow, underworld_membership_profile,
    )
    day = _day(conn)
    if enterprise is None:
        return 0
    eid = int(enterprise['id']); loc = int(enterprise['location_id']) if enterprise['location_id'] is not None else None
    org=ensure_actor_underworld_organization(conn,actor_id,eid)
    org_id=int(org['id']) if org is not None else None
    org_type=str(org['organization_type']) if org is not None else 'criminal_enterprise'
    factors=organization_operational_factors(org)
    command_depth=int(org['command_depth']) if org is not None else 1
    member_count=float(org['member_count_estimate']) if org is not None else 1.0
    # Membership is a flow system, not a net-growth counter. Resolve ordinary recruitment,
    # desistance/loss and deepening before the headline criminal beat for this review.
    if org_id is not None:
        simulate_underworld_membership_turnover(
            conn,org_id,rng,cash=float(enterprise['cash']),violence_pressure=min(1.0,float(org['violence_capacity'])/100.0),
            event_logger=event_logger,actor_id=actor_id,location_id=loc,
        )
        org=conn.execute('SELECT * FROM underworld_organizations WHERE id=?',(org_id,)).fetchone()
        factors=organization_operational_factors(org); command_depth=int(org['command_depth']); member_count=float(org['member_count_estimate'])
    if _resolve_pending_hit(conn,actor_id,eid,loc,rng,event_logger,org_id):
        return 1
    drives = conn.execute("SELECT aggression,risk_tolerance,ambition,pragmatism FROM actor_drives WHERE actor_id=?", (actor_id,)).fetchone()
    agg=float(drives['aggression']) if drives else .5; risk=float(drives['risk_tolerance']) if drives else .5; amb=float(drives['ambition']) if drives else .5
    # Growth creates opportunities to change the gang's shape without changing its organizational form.
    # Recruitment, diversification and delegation are discrete events, not hidden levels.
    current_cash=float(conn.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(eid,)).fetchone()[0])
    if org is not None and amb > .60 and current_cash > 28:
        grow_roll=rng.random()
        # Deliberate expansion has no target headcount or small-gang ceiling. Whether another
        # recruitment push is plausible depends on organizational slack: money per current full
        # member, command/administrative depth, breadth of work, and how overloaded the periphery
        # already is. A gang may grow far past eighteen, remain small for decades, or contract.
        prof=underworld_membership_profile(conn,org_id)
        current_full=max(1.0,float(prof['core_members'])+float(prof['active_members']))
        peripheral=float(prof['peripheral_associates'])
        cash_per_full=current_cash/current_full
        peripheral_load=peripheral/current_full
        recruit_cut=(
            .030 + .028*amb
            + .018*min(2.0,cash_per_full/8.0)
            + .014*max(0.0,factors['rackets']-1.0)
            + .012*max(0.0,factors['fronts']-1.0)
            + .012*max(0.0,factors['command']-1.0)
        )
        recruit_cut*=max(.28,1.0-.30*max(0.0,peripheral_load-.50))
        recruit_cut=max(.015,min(.22,recruit_cut))
        if grow_roll < recruit_cut:
            # Recruitment-push size can scale modestly with organizational slack, but is still
            # discrete people rather than a percentage growth rule or a desired final size.
            recruits=1
            if rng.random() < min(.80,.30+.06*cash_per_full): recruits+=1
            if rng.random() < min(.55,.12+.08*max(0,command_depth-1)+.03*cash_per_full): recruits+=1
            if rng.random() < min(.30,.04+.05*max(0,command_depth-1)+.015*cash_per_full): recruits+=1
            ev=_event(conn,event_logger,actor_id,'role_underworld_recruitment','Gang made a recruitment push',
                   f'The gang deliberately brought {recruits} new probationary or peripheral hands into its orbit because its current work and front could support another recruitment push. They are not assumed to become durable full members immediately.',2,location_id=loc)
            record_underworld_membership_flow(conn,org_id,'recruitment',recruits,to_tier='peripheral',source_event_id=ev,metadata={'deliberate_expansion':True,'no_target_headcount':True})
            update_underworld_organization(conn,org_id,dimension_deltas={'cohesion':-.20*recruits,'membership_stability':-.10*recruits})
            org=maybe_deepen_gang_structure(conn,org_id)
            prof=underworld_membership_profile(conn,org_id)
            # crew_loyalty tracks current full members, not everybody who has ever been around the gang.
            current_full=float(prof['core_members'])+float(prof['active_members'])
            row=conn.execute("SELECT id FROM resources WHERE actor_id=? AND resource_type='crew_loyalty' ORDER BY id LIMIT 1",(actor_id,)).fetchone()
            if row: conn.execute("UPDATE resources SET amount=?,updated_day=? WHERE id=?",(current_full,day,int(row['id'])))
            return 1
        racket_room=max(.10,(100.0-float(org['racket_breadth']))/100.0)
        if grow_roll < .19*racket_room:
            # A racket-expansion beat must represent genuinely new criminal business.  Repeating
            # "illegal lending" or relabelling an opening stolen-goods racket as "cargo fencing"
            # cannot inflate racket breadth or organizational depth.
            options=[
                ('illegal lending','high-risk debt collection'),
                ('unlicensed betting','unlicensed gambling/bookmaking'),
                ('cargo fencing','stolen_goods_handling'),
                ('cargo diversion and commercial fraud','cargo_diversion_fraud'),
                ('warehouse-record manipulation','warehouse_record_fraud'),
                ('contraband cartage','smuggling_activity'),
            ]
            existing={str(r[0]) for r in conn.execute(
                "SELECT DISTINCT evidence_kind FROM underworld_evidence WHERE subject_kind='enterprise' AND subject_id=? AND status='active'",
                (eid,)).fetchall()}
            # Accept historical spelling variants from earlier diagnostics as equivalent.
            if 'stolen-goods handling' in existing: existing.add('stolen_goods_handling')
            remaining=[x for x in options if x[1] not in existing]
            if remaining:
                label,evidence_kind=remaining[rng.randrange(len(remaining))]
                breadth_gain=4.0+rng.random()*4.0
                ev=_event(conn,event_logger,actor_id,'role_underworld_racket_expansion','Gang added another racket',
                          f'The gang began taking a durable share of {label} alongside its existing collections and front business. This diversified the gang; it did not transform it into a different kind of criminal organization.',3,location_id=loc)
                record_underworld_evidence(conn,location_id=loc,subject_kind='enterprise',subject_id=eid,evidence_kind=evidence_kind,visibility='hidden',strength=30+rng.random()*15,source_kind='event',source_id=ev,metadata={'organization_id':org_id,'organization_type':org_type,'racket_expansion':label,'genuinely_new_racket':True},day=day)
                update_underworld_organization(conn,org_id,dimension_deltas={'racket_breadth':breadth_gain,'reputation_deterrence':.6})
                maybe_deepen_gang_structure(conn,org_id)
                return 1
    prior_conflicts = int(conn.execute("SELECT COUNT(*) FROM events WHERE source_actor_id=? AND event_type='role_underworld_conflict'", (actor_id,)).fetchone()[0])
    roll=rng.random()
    # Organization form is not an advancement level. Gang bosses may order targeted violence at any size;
    # deterrence, conflict history and capacity affect probability, not a hidden gang->Mafia ladder.
    hit_threshold=min(.15,.075 + .018*(factors['violence']-1.0) + .015*(factors['command']-1.0))
    if prior_conflicts >= 2 and agg > .52 and risk > .55 and amb > .60 and roll < hit_threshold:
        ev=_event(conn,event_logger,actor_id,'role_underworld_hit_ordered','Targeted retaliation ordered',
                  'The gang boss authorized a killing against a rival crew leader after repeated local conflict. The order is now a pending causal fact and must later resolve.',4,location_id=loc)
        record_underworld_evidence(conn,location_id=loc,subject_kind='enterprise',subject_id=eid,evidence_kind='targeted_violence',visibility='hidden',strength=58,source_kind='event',source_id=ev,metadata={'ordered_by_actor_id':actor_id,'target_resolution':'latent_rival_leader','outcome_not_assumed':True,'organization_id':org_id,'organization_type':org_type},day=day)
        _resource_add(conn,actor_id,'working_cash',-3.0)
        if org_id is not None:
            update_underworld_organization(conn,org_id,dimension_deltas={'violence_capacity':0.7})
        return 1
    conflict_cut=min(.40,.30 + .025*(factors['territory']-1.0) + .018*(factors['violence']-1.0))
    if roll < conflict_cut:
        capacity=max(.8,min(2.2,(factors['people']+factors['violence']+factors['deterrence'])/3.0))
        cash_delta=(-2+rng.random()*5)*capacity; rep_delta=(-2+rng.random()*5)*(0.85+.15*capacity)
        if cash_delta > 1.0 and rep_delta >= 0:
            result='The gang held the collection point and came away with the stronger local position.'
            org_deltas={'territorial_presence':1.5,'reputation_deterrence':1.2,'cohesion':0.4,'violence_capacity':0.3}
            member_delta=0.0
        elif cash_delta < 0 and rep_delta < 0:
            result='The rival crew forced the gang off the collection point; money and face were both lost.'
            org_deltas={'territorial_presence':-1.0,'reputation_deterrence':-0.8,'cohesion':-0.7}
            member_delta=-1.0 if member_count>4 and rng.random()<.12 else 0.0
        else:
            result='The fight broke without a clean territorial winner, but both groups paid for it.'
            org_deltas={'violence_capacity':0.2,'cohesion':-0.2}
            member_delta=0.0
        delegation=' A lieutenant or trusted hand coordinated part of the response without the boss personally directing every movement.' if command_depth>=2 else ''
        ev=_event(conn,event_logger,actor_id,'role_underworld_conflict',f'{org_type.replace("_"," ").title()} conflict',
                  f'A collection/territory dispute became a real street fight around the gang network. {result}{delegation}',3,location_id=loc)
        record_underworld_evidence(conn,location_id=loc,subject_kind='enterprise',subject_id=eid,evidence_kind='street_violence',visibility='local' if rng.random()<.35 else 'hidden',strength=42+rng.random()*18,source_kind='event',source_id=ev,metadata={'rival_group':'latent_local_crew','cash_delta':cash_delta,'reputation_delta':rep_delta,'organization_id':org_id,'organization_type':org_type},day=day)
        conn.execute("UPDATE civilian_enterprises SET cash=MAX(0,cash+?),reputation=MAX(0,MIN(100,reputation+?)),updated_day=? WHERE id=?",(cash_delta,rep_delta,day,eid))
        if org_id is not None:
            if member_delta < 0:
                prof=underworld_membership_profile(conn,org_id)
                tier='active' if float(prof['active_members'])>=1 else ('peripheral' if float(prof['peripheral_associates'])>=1 else 'core')
                record_underworld_membership_flow(conn,org_id,'death_or_incapacitation',abs(member_delta),from_tier=tier,source_event_id=ev,metadata={'source':'gang_fight','deaths':0,'incapacitation_or_death_unresolved':True})
            update_underworld_organization(conn,org_id,dimension_deltas=org_deltas)
            maybe_deepen_gang_structure(conn,org_id)
        if rng.random()<.22:
            from .health import add_condition
            add_condition(conn,actor_id,'injury','Injury from gang fight',severity=12+rng.random()*18,capacity_impact=4+rng.random()*8,pain_impact=8+rng.random()*10,recovery_rate_per_30=8,next_review_days=14,metadata={'source_event_id':ev,'role_experience':True})
        return 1
    if roll < .72:
        take=(1.0+rng.random()*4.0)*max(.85,min(2.4,(factors['rackets']+factors['people'])/2.0))
        if command_depth>=2:
            summary='Subordinate collectors handled several protection payments while the gang boss reconciled shares, disputes and enforcement decisions.'
        else:
            summary='The gang collected from businesses in its working ward through the same network that supports the front enterprise.'
        ev=_event(conn,event_logger,actor_id,'role_underworld_collection','Gang protection collection',summary,2,location_id=loc)
        record_underworld_evidence(conn,location_id=loc,subject_kind='enterprise',subject_id=eid,evidence_kind='protection_collection',visibility='hidden',strength=28+rng.random()*18,source_kind='event',source_id=ev,metadata={'role_experience':True,'organization_id':org_id,'organization_type':org_type},day=day)
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,reputation=MIN(100,reputation+0.4),updated_day=? WHERE id=?",(take,day,eid)); _resource_add(conn,actor_id,'working_cash',take)
        if org_id is not None:
            update_underworld_organization(conn,org_id,member_delta=0.0,dimension_deltas={'racket_breadth':0.65,'reputation_deterrence':0.35,'membership_stability':0.15})
            maybe_deepen_gang_structure(conn,org_id)
        return 1
    delegation=' Routine collections and yard business were increasingly handled by trusted hands beneath the boss.' if command_depth>=2 else ''
    _event(conn,event_logger,actor_id,'role_underworld_front','Legitimate front handled gang business',
              f"{enterprise['name']} handled ordinary customers while also serving as a meeting, storage and payment point for the gang.{delegation}",2,location_id=loc)
    conn.execute("UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?",(0.5+rng.random()*2.5,day,eid))
    if org_id is not None:
        update_underworld_organization(conn,org_id,dimension_deltas={'front_depth':0.7,'membership_stability':0.1})
        maybe_deepen_gang_structure(conn,org_id)
    return 1

def _longroad(conn, actor_id, rng, event_logger) -> int:
    name=conn.execute("SELECT name FROM actors WHERE id=?",(actor_id,)).fetchone()[0]
    cs=career_state(conn,actor_id,'longroad'); key=str(cs.get('stage_key') or 'escort_hand')
    responsibilities={str(x.get('key')) for x in cs.get('responsibilities',[]) if isinstance(x,dict)}
    formal_reach={'escort_hand':1,'proven_escort':2,'renowned_escort':3}.get(key,1)
    rep=_resource_amount(conn,actor_id,'road_reputation'); cp=_open_core(conn,actor_id); cstage=str(cp['current_stage']) if cp is not None and cp['current_stage'] else None
    so={'First':1,'Temper':2,'Third':3,'Breach':4,'Fifth':5,'Sixth':6}.get(cstage,0)
    eligible_reach=1
    if rep>=18 and so>=2: eligible_reach=2
    if rep>=22 and so>=3: eligible_reach=3
    if rep>=25 and so>=4: eligible_reach=4
    if 'contract_lead' in responsibilities or 'high_value_guard' in responsibilities: formal_reach=max(formal_reach,3)
    if 'master_grade_guard' in responsibilities: formal_reach=4
    reach=formal_reach
    stretch=False
    if eligible_reach>formal_reach and rng.random()<.36:
        reach=eligible_reach; stretch=True
    pay_by_reach={1:(1.5,3.5),2:(2.5,5.5),3:(4.0,8.0),4:(7.0,13.0)}
    pay=pay_by_reach[reach]
    title={1:'Long Road escort contract',2:'Higher-value Road escort',3:'Lead-scale escort commission',4:'Master-grade protection commission'}[reach]
    if rng.random() < .58:
        dest,pid=_try_travel_assignment(conn,actor_id,f'{key} paid Long Road contract',rng,max_hops=reach,metadata={'career_stage':key,'responsibilities':sorted(responsibilities)})
        if dest:
            _resource_add(conn,actor_id,'cash',pay[0]+rng.random()*pay[1])
            _resource_add(conn,actor_id,'road_reputation',0.8+rng.random()*(1.4+.4*reach),'index')
            lead = ' They were responsible for the escort detail rather than serving only as another hand.' if reach>=3 else ''
            if 'high_value_guard' in responsibilities and reach>=3: lead += ' The client specifically sought higher-grade protection.'
            stretch_note=' This commission was above their current durable Road standing, opened by reputation and martial capability.' if stretch else ''
            _event(conn,event_logger,actor_id,'role_longroad_contract',title,
                   f'{name} accepted work bound for {dest} at reach band {reach}; the journey and payment are persisted.{lead}{stretch_note}',2 if reach<3 else 3)
            return 1
    if rng.random() < (.12 + .025*reach):
        ch=_try_challenge(conn,actor_id,rng,lethal_allowed=True)
        if ch:
            other=conn.execute("SELECT name FROM actors WHERE id=?",(ch['opponent_actor_id'],)).fetchone()[0]
            _event(conn,event_logger,actor_id,'role_martial_challenge','Road challenge accepted',
                   f'{name} entered a {ch["terms_kind"]} challenge with {other}; the duel is resolved by the combat system.',3)
            return 1
    local_options=[f'{name} completed local guard, guide or convoy work.']
    if key in {'proven_escort','renowned_escort'}:
        local_options.append(f'{name} took responsibility for route choice and the safety of a small convoy.')
    if 'contract_lead' in responsibilities:
        local_options.append(f'{name} organized a local escort detail, assigned positions and answered for delivery.')
    if 'road_mentor' in responsibilities:
        local_options.append(f'{name} worked a Road job while teaching a less experienced hand how to read routes, clients and danger.')
    if 'master_grade_guard' in responsibilities:
        local_options.append(f'{name} reviewed a dangerous client movement and set a master-grade protection plan.')
    local=local_options[rng.randrange(len(local_options))]
    _resource_add(conn,actor_id,'cash',0.6+rng.random()*(1.8+.8*reach))
    _event(conn,event_logger,actor_id,'role_longroad_work',f'{cs.get("stage_name")}: Road work',local,1 if reach<3 else 2)
    return 1

def _martial_service(conn, actor_id, rng, event_logger, label: str, *, career_kind: str = 'martial_institution') -> int:
    name=conn.execute("SELECT name FROM actors WHERE id=?",(actor_id,)).fetchone()[0]
    cs=career_state(conn,actor_id,career_kind); key=str(cs.get('stage_key') or ('junior' if career_kind=='martial_institution' else 'practitioner'))
    responsibilities={str(x.get('key')) for x in cs.get('responsibilities',[]) if isinstance(x,dict)}
    if rng.random()<.035:
        ch=_try_challenge(conn,actor_id,rng,lethal_allowed=False)
        if ch:
            other=conn.execute("SELECT name FROM actors WHERE id=?",(ch['opponent_actor_id'],)).fetchone()[0]
            _event(conn,event_logger,actor_id,'role_martial_challenge',f'{label} challenge',
                   f'{name} accepted a {ch["terms_kind"]} bout with {other} as part of ordinary martial life; the combat is persisted and resolved mechanically.',2)
            return 1
    if career_kind=='martial_institution':
        pools={
          'junior':[
            ('training rotation',f'{name} drilled forms, exchanged with peers and helped reset the next training group.'),
            ('gate and grounds watch',f'{name} stood an armed gate/grounds rotation for {label}, checking arrivals and remaining available for a security response.'),
            ('patrol rotation',f'{name} completed a local security patrol for {label}.'),
            ('instruction support',f'{name} assisted an instructor during group practice, demonstrating basic work under supervision.'),
          ],
          'established':[
            ('experienced training rotation',f'{name} drilled with experienced peers and corrected junior repetitions under an instructor’s oversight.'),
            ('gate section duty',f'{name} handled an experienced gate/grounds duty with responsibility for routine judgment.'),
            ('institutional patrol',f'{name} completed a local institutional security patrol.'),
            ('junior support',f'{name} helped newer disciples through routine practice without holding formal teaching authority.'),
          ],
          'senior':[
            ('senior practice duty',f'{name} handled a difficult senior practice/service block for {label}.'),
            ('senior security duty',f'{name} served on a higher-trust institutional security duty.'),
            ('junior assessment support',f'{name} observed junior work and supplied an experienced opinion to the people responsible for assessment.'),
            ('external service duty',f'{name} represented {label} on a bounded external martial/service duty appropriate to senior standing.'),
          ],
        }
        duties=list(pools.get(key,pools['junior']))
        if 'patrol_lead' in responsibilities:
            duties.append(('patrol lead',f'{name} led a local security patrol and answered for route, discipline and report.'))
        if 'assistant_instructor' in responsibilities:
            duties.append(('assistant instruction',f'{name} ran part of a junior practice block while another instructor retained overall responsibility.'))
        if 'disciple_examiner' in responsibilities:
            duties.append(('disciple assessment',f'{name} assessed junior disciples in routine spear work and submitted recommendations.'))
        if 'external_representative' in responsibilities:
            duties.append(('external representation',f'{name} represented {label} on an external martial/service duty because the institution trusted their judgment.'))
        if 'full_instructor' in responsibilities:
            duties.extend([
                ('cohort instruction',f'{name} taught a full junior cohort and was responsible for progression, safety and correction.'),
                ('training-plan responsibility',f'{name} set and supervised a training block for a group of disciples.'),
            ])
    else:
        duties=[('professional practice',f'{name} completed ordinary martial practice and paid/professional work.')]
        if key=='veteran':
            duties.append(('veteran martial work',f'{name} handled a harder professional martial task and helped a less experienced practitioner through it.'))
        if 'contract_lead' in responsibilities:
            duties.append(('contract leadership',f'{name} led a small professional martial contract and answered for the other hands involved.'))
        if 'mentor' in responsibilities:
            duties.append(('working mentorship',f'{name} worked alongside a less experienced practitioner and deliberately coached them through the task.'))
        if 'independent_teacher' in responsibilities:
            duties.append(('independent teaching',f'{name} taught a small group or individual student while maintaining independent martial work.'))
    title,summary=duties[rng.randrange(len(duties))]
    importance = 2 if responsibilities or key not in ('junior','practitioner') else 1
    _event(conn,event_logger,actor_id,'role_martial_service',f'{label}: {title}',summary,importance)
    return 1

def _retainer(conn, actor_id, rng, event_logger) -> int:
    name=conn.execute("SELECT name FROM actors WHERE id=?",(actor_id,)).fetchone()[0]
    cs=career_state(conn,actor_id,'retainer'); key=str(cs.get('stage_key') or 'retainer')
    responsibilities={str(x.get('key')) for x in cs.get('responsibilities',[]) if isinstance(x,dict)}
    reach=2 if key=='senior_retainer' else 1
    if 'mounted_detail_lead' in responsibilities: reach=max(reach,2)
    if 'retainer_captain' in responsibilities: reach=3
    if rng.random()<.38:
        dest,pid=_try_travel_assignment(conn,actor_id,f'{key} estate patrol and mounted duty',rng,max_hops=reach,metadata={'career_stage':key,'responsibilities':sorted(responsibilities)})
        if dest:
            if 'retainer_captain' in responsibilities: wording='commanded a retainer detachment'
            elif 'mounted_detail_lead' in responsibilities or key=='senior_retainer': wording='led a mounted estate detail'
            else: wording='rode an estate/road patrol'
            _event(conn,event_logger,actor_id,'role_retainer_patrol',f'{cs.get("stage_name")}: patrol assignment',f'{name} {wording} toward {dest}; the movement is persisted as travel.',2 if reach<3 else 3)
            return 1
    if rng.random()<.08:
        ch=_try_challenge(conn,actor_id,rng,lethal_allowed=False)
        if ch:
            other=conn.execute("SELECT name FROM actors WHERE id=?",(ch['opponent_actor_id'],)).fetchone()[0]
            _event(conn,event_logger,actor_id,'role_martial_challenge','Retainer practice challenge',f'{name} fought a {ch["terms_kind"]} practice challenge with {other}.',2)
            return 1
    duties=[
        ('Mounted boundary circuit',f'{name} rode a local boundary circuit and reported back to the estate.'),
        ('Remount and tack inspection',f'{name} inspected remounts, tack and readiness, then worked horses needing correction.'),
        ('Estate guard rotation',f'{name} took an armed estate guard rotation.'),
        ('Local escort duty',f'{name} escorted estate people and goods on a local run.'),
    ]
    if key=='senior_retainer':
        duties.append(('Senior duty oversight',f'{name} supervised a routine estate security duty and signed off the report.'))
    if 'mounted_detail_lead' in responsibilities:
        duties.append(('Boundary detail lead',f'{name} led several retainers on a boundary circuit and signed off the report.'))
    if 'horsemaster' in responsibilities:
        duties.append(('Remount readiness supervision',f'{name} supervised remount readiness and decided which animals were fit for duty.'))
    if 'household_instructor' in responsibilities:
        duties.append(('Junior retainer drill',f'{name} drilled younger retainers in mounted readiness and practical fighting.'))
    if 'security_planner' in responsibilities:
        duties.append(('Security planning',f'{name} reviewed threats, routes and available people and set an estate protection plan.'))
    if 'retainer_captain' in responsibilities:
        duties.extend([
            ('Retainer roster command',f'{name} assigned the estate guard roster and answered for gaps in coverage.'),
            ('Mounted detachment command',f'{name} commanded a mounted retainer detachment on estate business.'),
        ])
    title,summary=duties[rng.randrange(len(duties))]
    _event(conn,event_logger,actor_id,'role_retainer_duty',f'{cs.get("stage_name")}: {title}',summary,1 if not responsibilities and key=='retainer' else 2)
    return 1

def _witness(conn, actor_id, rng, event_logger) -> int:
    name=conn.execute("SELECT name FROM actors WHERE id=?",(actor_id,)).fetchone()[0]
    cs=career_state(conn,actor_id,'witness'); key=str(cs.get('stage_key') or 'parish_worker')
    responsibilities={str(x.get('key')) for x in cs.get('responsibilities',[]) if isinstance(x,dict)}
    _resource_add(conn,actor_id,'local_trust',0.45+rng.random()*1.25,'index')
    duties=[
        ('Poor-relief case organized',f'{name} coordinated a concrete parish relief case, reconciling records, funds and a household in need.','role_witness_relief'),
        ('Parish records and service',f'{name} handled parish records, correspondence and ordinary service obligations.','role_witness_records'),
    ]
    if key in {'trusted_worker','established_worker'}:
        duties.append(('Trusted case review',f'{name} reviewed a difficult local service case and was trusted to resolve routine questions without escalating every detail.','role_witness_relief'))
    if 'relief_supervisor' in responsibilities:
        duties.append(('Relief supervision',f'{name} supervised a difficult relief case, checked another worker’s records and authorized the parish response within available means.','role_witness_relief'))
    if 'records_supervisor' in responsibilities:
        duties.append(('Records supervision',f'{name} supervised routine records and correspondence, correcting work before it reached parish leadership.','role_witness_records'))
    if 'volunteer_coordinator' in responsibilities:
        duties.append(('Volunteer coordination',f'{name} assigned volunteers across several ordinary parish needs and followed up incomplete work.','role_witness_relief'))
    if 'parish_service_coordinator' in responsibilities:
        duties.append(('Parish service coordination',f'{name} coordinated records, volunteers and relief obligations across several concurrent needs without seeking ordained office.','role_witness_records'))
    title,summary,etype=duties[rng.randrange(len(duties))]
    if etype=='role_witness_relief': _resource_add(conn,actor_id,'household_cash',-(0.1+rng.random()*.5))
    _event(conn,event_logger,actor_id,etype,title,summary,1 if not responsibilities and key=='parish_worker' else 2)
    return 1

def _merchant(conn, actor_id, enterprise, rng, event_logger) -> int:
    if enterprise is None:
        return 0
    name=conn.execute("SELECT name FROM actors WHERE id=?",(actor_id,)).fetchone()[0]; day=_day(conn)
    cs=career_state(conn,actor_id,'merchant'); key=str(cs.get('stage_key') or 'small_operator')
    responsibilities={str(x.get('key')) for x in cs.get('responsibilities',[]) if isinstance(x,dict)}
    formal_scale={'small_operator':1,'regional_operator':2,'major_operator':3}.get(key,1)
    net=max(0.0,float(enterprise['capital'])+float(enterprise['cash'])-float(enterprise['debt'])); rep=float(enterprise['reputation'])
    eligible_scale=1
    if net>=75 and rep>=50: eligible_scale=2
    if net>=190 and rep>=58: eligible_scale=3
    if 'regional_contractor' in responsibilities or 'factor_coordinator' in responsibilities: formal_scale=max(formal_scale,2)
    if 'multi_market_principal' in responsibilities: formal_scale=3
    scale=formal_scale
    if eligible_scale>formal_scale and rng.random()<.34:
        scale=eligible_scale
    reach={1:1,2:3,3:5}[scale]
    contract_prob={1:.45,2:.56,3:.64}[scale]
    if 'regional_contractor' in responsibilities: contract_prob=min(.78,contract_prob+.10)
    if rng.random()<contract_prob:
        contract_kind={1:'freight and provisions contract',2:'multi-route regional supply contract',3:'major multi-market supply commission'}[scale]
        dest,pid=_try_travel_assignment(conn,actor_id,contract_kind,rng,max_hops=reach,metadata={'career_stage':key,'contract_scale':scale,'responsibilities':sorted(responsibilities)})
        if dest:
            margin=(1.2+rng.random()*4.8) * (1.0 + .9*(scale-1))
            rep_gain=(.3+rng.random()*.8) * (1+.35*(scale-1))
            conn.execute("UPDATE civilian_enterprises SET cash=cash+?,capital=capital+?,reputation=MIN(100,reputation+?),labor_capacity=MIN(100,labor_capacity+?),updated_day=? WHERE id=?",
                         (margin, margin*.18, rep_gain, .15*scale, day, int(enterprise['id'])))
            title={1:'Regional freight contract',2:'Regional supply contract',3:'Major trading commission'}[scale]
            delegation=' They coordinated carriers/factors beneath them rather than personally handling every operational detail.' if scale>=2 or 'factor_coordinator' in responsibilities else ''
            warehouse=' Existing warehouse/stock responsibility let them stage goods rather than treating every load as a one-off movement.' if 'warehouse_operator' in responsibilities else ''
            stretch=' This commission exceeded their current durable commercial standing and was opened by actual business scale/reputation.' if scale>formal_scale else ''
            _event(conn,event_logger,actor_id,'role_merchant_contract',title,f'{name} accepted a scale-{scale} contract toward {dest}; proceeds, increased capital and business capacity are persisted.{delegation}{warehouse}{stretch}',2 if scale==1 else 3)
            return 1
    loss_prob={1:.25,2:.22,3:.20}[scale]
    if rng.random()<loss_prob:
        loss=(.5+rng.random()*3.0) * (1+.65*(scale-1))
        conn.execute("UPDATE civilian_enterprises SET cash=MAX(0,cash-?),updated_day=? WHERE id=?",(loss,day,int(enterprise['id'])))
        _event(conn,event_logger,actor_id,'role_merchant_loss','Commercial setback',f'{name} absorbed a scale-{scale} delayed payment, spoilage or freight loss worth {loss:.1f} calibration cash.',2 if scale<3 else 3)
        return 1
    gain=(.5+rng.random()*2.5) * (1+.75*(scale-1))
    conn.execute("UPDATE civilian_enterprises SET cash=cash+?,capital=capital+?,updated_day=? WHERE id=?",(gain,gain*.12,day,int(enterprise['id'])))
    if scale==1:
        summary=f'{name} completed a profitable local provisions/freight cycle worth {gain:.1f} calibration cash.'
    elif scale==2:
        summary=f'{name} managed a regional trading cycle through hired carriers and repeat counterparties, adding {gain:.1f} cash.'
    else:
        summary=f'{name} allocated capital across several simultaneous trading commitments and delegated routine movement, adding {gain:.1f} cash.'
    if 'warehouse_operator' in responsibilities: summary += ' Stock was staged through a persistent warehouse/holding function.'
    _event(conn,event_logger,actor_id,'role_merchant_trade',f'{cs.get("stage_name")}: trade cycle',summary,1 if scale==1 else 2)
    return 1

def process_role_experience_review(conn: sqlite3.Connection, actor_id: int, cadence_days: int, *, event_logger: Callable[..., int]) -> int:
    """Give ordinary NPCs causal access to profession, responsibility and martial experiences.

    v0.59 adds career/reach progression: success widens eligible opportunities and responsibility,
    but qualifications never force a promotion and camera identity is never consulted.
    """
    if not _living(conn, actor_id):
        return 0
    sim=conn.execute("SELECT tier,cadence_days FROM simulation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
    if sim and str(sim['tier'] or '').upper()=='DORMANT':
        return 0
    kind, context = _role_kind(conn, actor_id)
    if kind is None:
        return 0
    # Independent underworld organizations do not use a universal career ladder. Their structure
    # changes through organization state; other professions use flexible standing/responsibility reviews.
    if kind != 'underworld':
        review_career_reach(conn,actor_id,kind,context,max(1,int(cadence_days)),event_logger=event_logger)
    annual = {'underworld':1.7,'longroad':2.1,'witness':1.5,'merchant':1.8,'retainer':1.7,'martial_institution':1.8,'martial':0.65}[kind]
    chance=min(.42, annual * max(1,int(cadence_days)) / 365.0)
    day=_day(conn); rng=_rng(conn,actor_id,day,5800)
    if rng.random() >= chance:
        return 0
    result=0
    if kind=='underworld': result=_underworld(conn,actor_id,context,rng,event_logger)
    elif kind=='longroad': result=_longroad(conn,actor_id,rng,event_logger)
    elif kind=='witness': result=_witness(conn,actor_id,rng,event_logger)
    elif kind=='merchant': result=_merchant(conn,actor_id,context,rng,event_logger)
    elif kind=='retainer': result=_retainer(conn,actor_id,rng,event_logger)
    elif kind=='martial_institution': result=_martial_service(conn,actor_id,rng,event_logger,str(context['institution_name']) if context is not None else 'Institutional',career_kind='martial_institution')
    else: result=_martial_service(conn,actor_id,rng,event_logger,'Martial',career_kind='martial')
    if result and kind != 'underworld':
        note_role_event(conn,actor_id,kind,context)
    return result

