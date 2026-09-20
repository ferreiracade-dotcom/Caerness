from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from .opportunity import create_proposal, add_term, present_proposal
from .reputation import value as reputation_value, adjust as adjust_reputation
from .relationships import adjust_relationship_pair


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _j(v: Any) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def configure_preference(
    conn: sqlite3.Connection,
    patron_actor_id: int,
    domain_key: str,
    *,
    interest_level: float = 70,
    prestige_motive: float = 40,
    developmental_motive: float = 40,
    ideological_motive: float = 0,
    preferred_support_kind: str = "stipend",
    max_amount_per_cycle: float = 5,
    recurrence_days: int = 30,
    openness_to_emerging: float = 50,
    networking_motive: float = 0,
    circle_cadence_days: int = 60,
    taste: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    day = _day(conn)
    conn.execute(
        """INSERT INTO patronage_preferences(
               patron_actor_id,domain_key,interest_level,taste_json,prestige_motive,developmental_motive,ideological_motive,
               preferred_support_kind,max_amount_per_cycle,recurrence_days,openness_to_emerging,networking_motive,circle_cadence_days,status,created_day,updated_day,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)
           ON CONFLICT(patron_actor_id,domain_key) DO UPDATE SET
             interest_level=excluded.interest_level,taste_json=excluded.taste_json,prestige_motive=excluded.prestige_motive,
             developmental_motive=excluded.developmental_motive,ideological_motive=excluded.ideological_motive,
             preferred_support_kind=excluded.preferred_support_kind,max_amount_per_cycle=excluded.max_amount_per_cycle,
             recurrence_days=excluded.recurrence_days,openness_to_emerging=excluded.openness_to_emerging,
             networking_motive=excluded.networking_motive,circle_cadence_days=excluded.circle_cadence_days,status='active',
             updated_day=excluded.updated_day,metadata_json=excluded.metadata_json""",
        (
            patron_actor_id, domain_key, max(0, min(100, float(interest_level))), _j(taste or {}),
            max(0, min(100, float(prestige_motive))), max(0, min(100, float(developmental_motive))),
            max(0, min(100, float(ideological_motive))), preferred_support_kind,
            max(0, float(max_amount_per_cycle)), max(1, int(recurrence_days)),
            max(0, min(100, float(openness_to_emerging))), max(0, min(100, float(networking_motive))),
            max(14, int(circle_cadence_days)), day, day, _j(metadata or {}),
        ),
    )
    return int(conn.execute("SELECT id FROM patronage_preferences WHERE patron_actor_id=? AND domain_key=?", (patron_actor_id, domain_key)).fetchone()[0])


def _active_household(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT h.* FROM households h JOIN household_members hm ON hm.household_id=h.id
           WHERE hm.actor_id=? AND hm.status='active' AND h.status IN ('active','declining')
           ORDER BY CASE WHEN h.head_actor_id=? THEN 0 ELSE 1 END,hm.authority DESC,h.id LIMIT 1""",
        (actor_id, actor_id),
    ).fetchone()


def _best_funding_source(conn: sqlite3.Connection, actor_id: int, amount: float) -> tuple[str, int] | None:
    # Prefer a merchant's owned enterprise where it can comfortably fund the support; nobles usually resolve to household wealth.
    ent = conn.execute(
        """SELECT id,cash FROM civilian_enterprises WHERE owner_actor_id=? AND status='active' AND cash>=?
           ORDER BY cash DESC,id LIMIT 1""", (actor_id, max(0.0, amount * 2.0))
    ).fetchone()
    hh = _active_household(conn, actor_id)
    choices: list[tuple[float, str, int]] = []
    if ent:
        choices.append((float(ent['cash']), 'enterprise', int(ent['id'])))
    if hh and float(hh['liquidity']) >= max(0.0, amount * 2.0):
        choices.append((float(hh['liquidity']), 'household', int(hh['id'])))
    if not choices:
        return None
    choices.sort(reverse=True)
    return choices[0][1], choices[0][2]


def discover_candidates(conn: sqlite3.Connection, patron_actor_id: int, domain_key: str, *, limit: int = 8) -> list[dict[str, Any]]:
    pref = conn.execute(
        "SELECT * FROM patronage_preferences WHERE patron_actor_id=? AND domain_key=? AND status='active'",
        (patron_actor_id, domain_key),
    ).fetchone()
    if not pref:
        return []
    # Patronage is about known talent, not hidden omniscience. Public visibility and reputation both matter.
    rows = conn.execute(
        """SELECT oc.*,a.name FROM opportunity_capabilities oc JOIN actors a ON a.id=oc.subject_id
           WHERE oc.subject_kind='actor' AND oc.domain_key=? AND oc.status='active' AND a.status='active'
             AND oc.subject_id<>? ORDER BY oc.quality DESC,oc.public_visibility DESC,oc.id""",
        (domain_key, patron_actor_id),
    ).fetchall()
    out: list[dict[str, Any]] = []
    openness = float(pref['openness_to_emerging'])
    prestige = float(pref['prestige_motive'])
    development = float(pref['developmental_motive'])
    for r in rows:
        quality = float(r['quality']); visibility = float(r['public_visibility']); availability = float(r['availability'])
        rep = reputation_value(conn, 'actor', int(r['subject_id']), [domain_key, 'art_culture'], default=max(25.0, visibility * .6))
        established_fit = (quality * .38 + rep * .30 + visibility * .20 + availability * .12)
        emerging_fit = quality * .50 + max(0.0, 70.0 - rep) * .20 + visibility * .10 + availability * .20
        motive_mix = (prestige / 100.0) * established_fit + (development / 100.0) * emerging_fit
        if prestige + development < 1:
            motive_mix = established_fit
        score = established_fit * .55 + motive_mix * .45
        # Low visibility makes discovery less likely even when quality is excellent.
        discoverability = min(1.0, max(0.0, (visibility * .65 + rep * .35) / 100.0))
        score *= .45 + .55 * discoverability
        # Patrons explicitly open to emerging talent tolerate low existing reputation.
        if rep < 45:
            score += (openness - 50.0) * .12
        if score >= 45:
            out.append({
                'actor_id': int(r['subject_id']), 'name': str(r['name']), 'fit_score': round(score, 3),
                'quality': quality, 'reputation': round(rep, 2), 'visibility': visibility,
                'capability_key': str(r['capability_key']),
            })
    out.sort(key=lambda x: (-x['fit_score'], -x['quality'], x['actor_id']))
    return out[:max(1, int(limit))]


def propose_patronage(
    conn: sqlite3.Connection,
    patron_actor_id: int,
    beneficiary_actor_id: int,
    domain_key: str,
    *,
    title: str | None = None,
    amount_per_cycle: float | None = None,
    recurrence_days: int | None = None,
    duration_days: int | None = None,
    patronage_kind: str | None = None,
    funding_source_kind: str | None = None,
    funding_source_id: int | None = None,
    exclusivity: float = 0,
    support: dict[str, Any] | None = None,
    expectations: dict[str, Any] | None = None,
    additional_terms: list[dict[str, Any]] | None = None,
    source_attention_case_id: int | None = None,
) -> tuple[int, int]:
    pref = conn.execute("SELECT * FROM patronage_preferences WHERE patron_actor_id=? AND domain_key=? AND status='active'", (patron_actor_id, domain_key)).fetchone()
    amount = float(amount_per_cycle if amount_per_cycle is not None else (pref['max_amount_per_cycle'] if pref else 0))
    recurrence = int(recurrence_days if recurrence_days is not None else (pref['recurrence_days'] if pref else 30))
    pkind = str(patronage_kind or (pref['preferred_support_kind'] if pref else 'stipend'))
    if amount < 0 or recurrence < 1:
        raise ValueError('invalid patronage support cadence')
    if funding_source_kind is None or funding_source_id is None:
        src = _best_funding_source(conn, patron_actor_id, amount)
        if src is None and amount > 0:
            raise ValueError('patron has no funded household or enterprise capable of supporting this patronage')
        if src:
            funding_source_kind, funding_source_id = src
    pid = create_proposal(
        conn, patron_actor_id, 'patronage', domain_key, title or f"Patronage in {domain_key}",
        target_actor_id=beneficiary_actor_id, source_attention_case_id=source_attention_case_id, source_kind='patronage_preference',
        source_id=int(pref['id']) if pref else None,
        metadata={'patronage01': True, 'patronage_kind': pkind, 'independence_preserved': True},
    )
    add_term(
        conn, pid, 'recurring_stipend', subject_kind='actor', subject_id=beneficiary_actor_id, execution_order=20,
        value={
            'amount': amount, 'recurrence_days': recurrence, 'duration_days': duration_days,
            'funding_source_kind': funding_source_kind or 'none', 'funding_source_id': funding_source_id,
            'patronage_kind': pkind, 'support': support or {}, 'expectations': expectations or {},
            'exclusivity': max(0.0, min(1.0, float(exclusivity))), 'independence_preserved': True,
            'patron_actor_id': patron_actor_id, 'beneficiary_actor_id': beneficiary_actor_id,
        },
    )
    for term in additional_terms or []:
        add_term(conn, pid, str(term['term_kind']), subject_kind=term.get('subject_kind'), subject_id=term.get('subject_id'),
                 value=term.get('value') or {}, required=bool(term.get('required', True)), execution_order=int(term.get('execution_order', 100)))
    iid = present_proposal(conn, pid, rationale='Patronage offers support without making the beneficiary an employee or transferring unrelated work unless explicit terms say otherwise.')
    return pid, iid


def materialize_from_proposal(conn: sqlite3.Connection, proposal: sqlite3.Row, day: int) -> int | None:
    if str(proposal['proposal_kind']) != 'patronage':
        return None
    existing = conn.execute("SELECT id FROM patronage_relationships WHERE source_proposal_id=?", (int(proposal['id']),)).fetchone()
    if existing:
        return int(existing[0])
    stipend = conn.execute(
        "SELECT * FROM opportunity_proposal_terms WHERE proposal_id=? AND term_kind='recurring_stipend' AND status='executed' ORDER BY execution_order,id LIMIT 1",
        (int(proposal['id']),),
    ).fetchone()
    if not stipend:
        return None
    v = _loads(stipend['value_json'], {})
    explicit_patron = v.get('patron_actor_id')
    explicit_beneficiary = v.get('beneficiary_actor_id')
    patron_actor = int(explicit_patron) if explicit_patron is not None else int(proposal['proposer_actor_id'])
    target_actor = int(explicit_beneficiary) if explicit_beneficiary is not None else (int(proposal['target_actor_id']) if proposal['target_actor_id'] is not None else None)
    target_inst = int(proposal['target_institution_actor_id']) if explicit_beneficiary is None and proposal['target_institution_actor_id'] is not None else None
    src_kind = str(v.get('funding_source_kind') or 'none'); src_id = v.get('funding_source_id')
    new_exclusivity=max(0.0, min(1.0, float(v.get('exclusivity') or 0)))
    if target_actor is not None:
        conflicts=conn.execute(
            "SELECT * FROM patronage_relationships WHERE beneficiary_actor_id=? AND domain_key=? AND status IN ('active','strained') ORDER BY id",
            (target_actor,str(proposal['domain_key'])),
        ).fetchall()
        for rel in conflicts:
            if int(rel['patron_actor_id']) == patron_actor:
                continue
            if float(rel['exclusivity']) >= .75 or new_exclusivity >= .75:
                raise ValueError('patronage exclusivity conflicts with an existing active patronage relationship')
    cur = conn.execute(
        """INSERT INTO patronage_relationships(
               patron_actor_id,patron_household_id,patron_enterprise_id,patron_institution_actor_id,
               beneficiary_actor_id,beneficiary_institution_actor_id,domain_key,patronage_kind,amount_per_cycle,
               recurrence_days,next_due_day,started_day,end_day,exclusivity,independence_preserved,status,
               source_proposal_id,support_json,expectations_json,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,'active',?,?,?,?)""",
        (
            patron_actor, int(src_id) if src_kind=='household' and src_id is not None else None,
            int(src_id) if src_kind=='enterprise' and src_id is not None else None,
            int(proposal['proposer_institution_actor_id']) if explicit_patron is None and proposal['proposer_institution_actor_id'] is not None else None,
            target_actor, target_inst, str(proposal['domain_key']), str(v.get('patronage_kind') or 'stipend'),
            max(0.0, float(v.get('amount') or 0)), max(1, int(v.get('recurrence_days') or 30)), day + max(1, int(v.get('recurrence_days') or 30)),
            day, day + int(v['duration_days']) if v.get('duration_days') is not None else None,
            new_exclusivity, int(proposal['id']),
            _j(v.get('support') or {}), _j(v.get('expectations') or {}), _j({'patronage01': True}),
        ),
    )
    rid = int(cur.lastrowid)
    if target_actor is not None:
        adjust_reputation(conn, 'actor', target_actor, str(proposal['domain_key']), 0.75, day=day, metadata={'patronage_started': rid})
        _resolve_competition_after_acceptance(conn, target_actor, str(proposal['domain_key']), patron_actor, int(proposal['id']), day, exclusive=new_exclusivity >= .75)
    return rid


def _destination_household(conn: sqlite3.Connection, actor_id: int | None) -> int | None:
    if actor_id is None:
        return None
    row = _active_household(conn, int(actor_id))
    return int(row['id']) if row else None


def _pay_one(conn: sqlite3.Connection, row: sqlite3.Row, due: int, day: int, event_logger: Callable[..., int] | None = None) -> dict[str, Any]:
    amount = max(0.0, float(row['amount_per_cycle']))
    source_kind='none'; source_id=None; available=0.0
    if row['patron_enterprise_id'] is not None:
        source_kind='enterprise'; source_id=int(row['patron_enterprise_id'])
        src=conn.execute("SELECT cash,status FROM civilian_enterprises WHERE id=?", (source_id,)).fetchone()
        available=float(src['cash']) if src and str(src['status'])=='active' else 0.0
    elif row['patron_household_id'] is not None:
        source_kind='household'; source_id=int(row['patron_household_id'])
        src=conn.execute("SELECT liquidity,status FROM households WHERE id=?", (source_id,)).fetchone()
        available=float(src['liquidity']) if src and str(src['status']) in {'active','declining'} else 0.0
    paid=min(amount,max(0.0,available))
    if source_kind=='enterprise' and paid>0:
        conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?", (paid,day,source_id))
        conn.execute("INSERT INTO enterprise_accounts(enterprise_id,day,account_kind,amount,description,source_kind,source_id) VALUES (?,?, 'expense',?,'Patronage support','patronage',?)", (source_id,day,paid,int(row['id'])))
    elif source_kind=='household' and paid>0:
        conn.execute("UPDATE households SET liquidity=liquidity-?,updated_day=? WHERE id=?", (paid,day,source_id))
    dest=_destination_household(conn, int(row['beneficiary_actor_id']) if row['beneficiary_actor_id'] is not None else None)
    if paid>0 and dest is not None:
        conn.execute("UPDATE households SET liquidity=liquidity+?,wealth=wealth+?*0.15,updated_day=? WHERE id=?", (paid,paid,day,dest))
    elif paid>0 and row['beneficiary_actor_id'] is not None:
        aid=int(row['beneficiary_actor_id'])
        existing=conn.execute("SELECT id FROM resources WHERE actor_id=? AND resource_type='cash' ORDER BY id LIMIT 1",(aid,)).fetchone()
        if existing:
            conn.execute("UPDATE resources SET amount=amount+?,updated_day=? WHERE id=?",(paid,day,int(existing['id'])))
        else:
            conn.execute("INSERT INTO resources(actor_id,resource_type,amount,unit,updated_day) VALUES (?,'cash',?,'calibration units',?)",(aid,paid,day))
    status='paid' if paid+1e-9>=amount else ('partial' if paid>0 else 'missed')
    conn.execute("INSERT OR IGNORE INTO patronage_payments(patronage_id,due_day,resolved_day,amount_due,amount_paid,source_kind,source_id,destination_household_id,status,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (int(row['id']),due,day,amount,paid,source_kind,source_id,dest,status,_j({})))
    rel_status='active' if status=='paid' else 'strained'
    next_due=due+int(row['recurrence_days'])
    if row['end_day'] is not None and next_due>int(row['end_day']):
        rel_status='ended'
    conn.execute("UPDATE patronage_relationships SET status=?,next_due_day=?,metadata_json=metadata_json WHERE id=?", (rel_status,next_due,int(row['id'])))
    return {'patronage_id':int(row['id']),'amount_due':amount,'amount_paid':paid,'status':status}



def refresh_patronage_circles(conn: sqlite3.Connection, day: int | None = None) -> dict[str, int]:
    """Project only deliberately convened patron networks into circles.

    Multiple beneficiaries alone are insufficient. The patron must have an explicit networking motive,
    which keeps private sponsorship separate from salon/court/workshop social organization.
    """
    day = _day(conn) if day is None else int(day)
    created = 0; updated = 0; dormant = 0
    prefs = conn.execute(
        "SELECT * FROM patronage_preferences WHERE status='active' AND networking_motive>=45 ORDER BY patron_actor_id,domain_key"
    ).fetchall()
    eligible_keys: set[tuple[int,str]] = set()
    for pref in prefs:
        patron = int(pref['patron_actor_id']); domain = str(pref['domain_key'])
        rels = conn.execute(
            """SELECT * FROM patronage_relationships
               WHERE patron_actor_id=? AND domain_key=? AND beneficiary_actor_id IS NOT NULL
                 AND status IN ('active','strained') ORDER BY id""", (patron,domain)
        ).fetchall()
        # A patron and one beneficiary is a relationship, not a circle.
        unique = {int(r['beneficiary_actor_id']): r for r in rels}
        if len(unique) < 2:
            continue
        eligible_keys.add((patron,domain))
        cadence=max(14,int(pref['circle_cadence_days']))
        meta=_loads(pref['metadata_json'],{})
        visibility=max(0.0,min(100.0,float(meta.get('circle_visibility',50.0))))
        patron_rep=reputation_value(conn,'actor',patron,[domain,'art_culture','public'],default=45.0)
        member_reps=[reputation_value(conn,'actor',aid,[domain,'art_culture','public'],default=35.0) for aid in unique]
        prestige=max(0.0,min(100.0,patron_rep*.45+(sum(member_reps)/len(member_reps))*.40+float(pref['networking_motive'])*.15))
        circle=conn.execute("SELECT * FROM patronage_circles WHERE patron_actor_id=? AND domain_key=?",(patron,domain)).fetchone()
        if not circle:
            cid=int(conn.execute(
                """INSERT INTO patronage_circles(patron_actor_id,domain_key,started_day,next_gathering_day,cadence_days,cohesion,public_visibility,prestige,status,metadata_json)
                   VALUES (?,?,?,?,?,50,?,?,'active',?)""",
                (patron,domain,day,day+cadence,cadence,visibility,prestige,_j({'patroncircle01':True}))
            ).lastrowid); created+=1
        else:
            cid=int(circle['id'])
            next_day=int(circle['next_gathering_day']) if str(circle['status'])=='active' else day+cadence
            conn.execute("UPDATE patronage_circles SET cadence_days=?,public_visibility=?,prestige=?,status='active',ended_day=NULL,next_gathering_day=? WHERE id=?",
                         (cadence,visibility,prestige,next_day,cid)); updated+=1
        active_members=set()
        for aid,rel in unique.items():
            active_members.add(aid)
            conn.execute(
                """INSERT INTO patronage_circle_members(circle_id,actor_id,patronage_id,joined_day,role_kind,status,metadata_json)
                   VALUES (?,?,?,?,'beneficiary','active',?)
                   ON CONFLICT(circle_id,actor_id) DO UPDATE SET patronage_id=excluded.patronage_id,status='active',left_day=NULL""",
                (cid,aid,int(rel['id']),day,_j({})))
        prior=conn.execute("SELECT actor_id FROM patronage_circle_members WHERE circle_id=? AND status='active'",(cid,)).fetchall()
        for r in prior:
            aid=int(r['actor_id'])
            if aid not in active_members:
                conn.execute("UPDATE patronage_circle_members SET status='left',left_day=? WHERE circle_id=? AND actor_id=?",(day,cid,aid))
    # Existing circles whose patron no longer has enough convened active beneficiaries become dormant, not erased.
    circles=conn.execute("SELECT id,patron_actor_id,domain_key FROM patronage_circles WHERE status='active'").fetchall()
    for c in circles:
        key=(int(c['patron_actor_id']),str(c['domain_key']))
        if key not in eligible_keys:
            conn.execute("UPDATE patronage_circles SET status='dormant' WHERE id=?",(int(c['id']),)); dormant+=1
    return {'created':created,'updated':updated,'dormant':dormant}


def _circle_pair_key(a: int, b: int) -> tuple[int,int]:
    return (a,b) if a < b else (b,a)


def host_due_patronage_circles(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str,int]:
    rows=conn.execute("SELECT * FROM patronage_circles WHERE status='active' AND next_gathering_day<=? ORDER BY next_gathering_day,id",(day,)).fetchall()
    gatherings=0; introductions=0
    for circle in rows:
        cid=int(circle['id']); patron=int(circle['patron_actor_id'])
        members=[int(r['actor_id']) for r in conn.execute(
            "SELECT actor_id FROM patronage_circle_members WHERE circle_id=? AND status='active' ORDER BY actor_id",(cid,)).fetchall()]
        if len(members)<2:
            conn.execute("UPDATE patronage_circles SET status='dormant' WHERE id=?",(cid,)); continue
        gid=int(conn.execute(
            "INSERT OR IGNORE INTO patronage_circle_gatherings(circle_id,day,gathering_kind,attendance_count,introductions_made,metadata_json) VALUES (?,?,'salon',?,0,?)",
            (cid,day,len(members)+1,_j({'patron_present':True}))).lastrowid or 0)
        if gid==0:
            old=conn.execute("SELECT id FROM patronage_circle_gatherings WHERE circle_id=? AND day=?",(cid,day)).fetchone(); gid=int(old[0])
        made=0
        # Introduce at most three genuinely new pairs per gathering. Existing relationships can deepen elsewhere.
        for i,a in enumerate(members):
            for b in members[i+1:]:
                x,y=_circle_pair_key(a,b)
                if conn.execute("SELECT 1 FROM patronage_circle_introductions WHERE circle_id=? AND actor_a_id=? AND actor_b_id=?",(cid,x,y)).fetchone():
                    continue
                conn.execute(
                    "INSERT INTO patronage_circle_introductions(circle_id,gathering_id,actor_a_id,actor_b_id,introduced_day,introduction_kind,metadata_json) VALUES (?,?,?,?,?,'patron_circle',?)",
                    (cid,gid,x,y,day,_j({'patron_actor_id':patron})))
                adjust_relationship_pair(conn,a,b,day,symmetric={'familiarity_delta':12.0,'respect_delta':2.0,'professional_confidence_delta':3.0})
                made+=1; introductions+=1
                if made>=3: break
            if made>=3: break
        conn.execute("UPDATE patronage_circle_gatherings SET introductions_made=? WHERE id=?",(made,gid))
        # Cohesion grows modestly through actual gatherings, never through mere shared patronage.
        conn.execute("UPDATE patronage_circles SET cohesion=MIN(100,cohesion+?),next_gathering_day=? WHERE id=?",
                     (1.5+0.5*made,day+int(circle['cadence_days']),cid))
        gatherings+=1
        if event_logger is not None:
            try:
                event_logger(day=day,event_type='patronage_circle_gathering',title='Patronage circle gathers',
                             summary=f"A {circle['domain_key']} circle around a patron gathered with {len(members)} beneficiaries and {made} new introductions.",
                             severity=1,source_actor_id=patron,target_actor_ids=tuple(members))
            except Exception:
                pass
    return {'gatherings':gatherings,'introductions':introductions}


def _style_tags(raw: str | None) -> set[str]:
    meta=_loads(raw,{})
    tags=meta.get('style_tags') or meta.get('style_tag') or []
    if isinstance(tags,str): tags=[tags]
    return {str(t).strip().lower() for t in tags if str(t).strip()}


def evaluate_cultural_movements(conn: sqlite3.Connection, day: int | None = None) -> int:
    """Recognize a style/school only from a real convened circle plus shared output evidence."""
    day=_day(conn) if day is None else int(day); changed=0
    circles=conn.execute("SELECT * FROM patronage_circles WHERE status='active' AND domain_key IN ('art_culture','painting','sculpture','music','literature','craft') ORDER BY id").fetchall()
    for c in circles:
        cid=int(c['id'])
        members=[int(r['actor_id']) for r in conn.execute("SELECT actor_id FROM patronage_circle_members WHERE circle_id=? AND status='active'",(cid,)).fetchall()]
        if len(members)<3: continue
        marks=','.join('?' for _ in members)
        works=conn.execute(
            f"SELECT id,creator_actor_id,quality,metadata_json FROM cultural_objects WHERE creator_actor_id IN ({marks}) AND created_day>=? AND status!='destroyed' AND quality>=75 ORDER BY id",
            (*members,int(c['started_day']))).fetchall()
        evidence: dict[str,list[sqlite3.Row]]={}
        for w in works:
            for tag in _style_tags(w['metadata_json']): evidence.setdefault(tag,[]).append(w)
        for tag,tagworks in evidence.items():
            creators={int(w['creator_actor_id']) for w in tagworks if w['creator_actor_id'] is not None}
            if len(creators)<3 or len(tagworks)<3: continue
            mean_q=sum(float(w['quality']) for w in tagworks)/len(tagworks)
            influence=max(0.0,min(100.0,mean_q*.55+float(c['prestige'])*.25+float(c['cohesion'])*.20))
            status='recognized' if len(tagworks)>=5 and mean_q>=84 and influence>=70 else 'emerging'
            existing=conn.execute("SELECT * FROM cultural_movements WHERE circle_id=? AND domain_key=? AND style_tag=?",(cid,str(c['domain_key']),tag)).fetchone()
            ev={'creator_actor_ids':sorted(creators),'work_ids':[int(w['id']) for w in tagworks],'shared_style_tag':tag}
            if not existing:
                conn.execute(
                    """INSERT INTO cultural_movements(circle_id,domain_key,style_tag,display_name,emerged_day,recognized_day,member_count,work_count,mean_quality,influence,status,evidence_json,metadata_json)
                       VALUES (?,?,?,NULL,?,?,?,?,?,?,?, ?,?)""",
                    (cid,str(c['domain_key']),tag,day,day if status=='recognized' else None,len(creators),len(tagworks),mean_q,influence,status,_j(ev),_j({'patroncircle01':True,'structural_identity':True})))
                changed+=1
            else:
                new_status='recognized' if str(existing['status'])=='recognized' or status=='recognized' else 'emerging'
                rec_day=int(existing['recognized_day']) if existing['recognized_day'] is not None else (day if new_status=='recognized' else None)
                conn.execute("UPDATE cultural_movements SET recognized_day=?,member_count=?,work_count=?,mean_quality=?,influence=?,status=?,evidence_json=? WHERE id=?",
                             (rec_day,len(creators),len(tagworks),mean_q,influence,new_status,_j(ev),int(existing['id'])))
    return changed


def patronage_circle_network(conn: sqlite3.Connection, domain_key: str | None = None) -> dict[str,int]:
    where="WHERE status='active'"; args: tuple[Any,...]=()
    if domain_key is not None:
        where += " AND domain_key=?"; args=(domain_key,)
    circles=conn.execute(f"SELECT id FROM patronage_circles {where}",args).fetchall()
    ids=[int(r['id']) for r in circles]
    if not ids:
        return {'circles':0,'members':0,'gatherings':0,'introductions':0,'movements':0}
    marks=','.join('?' for _ in ids)
    return {
        'circles':len(ids),
        'members':int(conn.execute(f"SELECT COUNT(*) FROM patronage_circle_members WHERE circle_id IN ({marks}) AND status='active'",ids).fetchone()[0]),
        'gatherings':int(conn.execute(f"SELECT COUNT(*) FROM patronage_circle_gatherings WHERE circle_id IN ({marks})",ids).fetchone()[0]),
        'introductions':int(conn.execute(f"SELECT COUNT(*) FROM patronage_circle_introductions WHERE circle_id IN ({marks})",ids).fetchone()[0]),
        'movements':int(conn.execute(f"SELECT COUNT(*) FROM cultural_movements WHERE circle_id IN ({marks}) AND status IN ('emerging','recognized')",ids).fetchone()[0]),
    }

def next_patronage_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    row=conn.execute("SELECT MIN(next_due_day) FROM patronage_relationships WHERE status IN ('active','strained') AND next_due_day>? AND next_due_day<=?",(after_day,end_day)).fetchone()
    if row and row[0] is not None: vals.append(int(row[0]))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='patronage_circles'").fetchone():
        row=conn.execute("SELECT MIN(next_gathering_day) FROM patronage_circles WHERE status='active' AND next_gathering_day>? AND next_gathering_day<=?",(after_day,end_day)).fetchone()
        if row and row[0] is not None: vals.append(int(row[0]))
    return min(vals) if vals else None


def process_due_patronage(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str, int]:
    rows=conn.execute("SELECT * FROM patronage_relationships WHERE status IN ('active','strained') AND next_due_day<=? ORDER BY next_due_day,id",(day,)).fetchall()
    payments=0; strained=0
    for row in rows:
        due=int(row['next_due_day'])
        if row['end_day'] is not None and due>int(row['end_day']):
            conn.execute("UPDATE patronage_relationships SET status='ended' WHERE id=?",(int(row['id']),)); continue
        res=_pay_one(conn,row,due,day,event_logger)
        payments+=1
        if res['status']!='paid': strained+=1
    c=refresh_patronage_circles(conn,day)
    g=host_due_patronage_circles(conn,day,event_logger=event_logger)
    movements=evaluate_cultural_movements(conn,day)
    return {'payments':payments,'strained':strained,'circles_created':c['created'],'circle_gatherings':g['gatherings'],'circle_introductions':g['introductions'],'movements_changed':movements}


def configure_seeking_profile(
    conn: sqlite3.Connection,
    beneficiary_actor_id: int,
    domain_key: str,
    *,
    desire_level: float = 70,
    preferred_support_kind: str = 'stipend',
    min_amount_per_cycle: float = 0,
    preferred_duration_days: int | None = 360,
    max_exclusivity: float = 1,
    funding_priority: float = 70,
    prestige_priority: float = 45,
    independence_priority: float = 70,
    max_simultaneous_requests: int = 1,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Persist an actor-owned desire to find patronage.

    This is intent state, not an automatic trait of artists or poor characters. In particular,
    the engine never invents this profile merely because somebody could use money.
    """
    day=_day(conn)
    conn.execute(
        """INSERT INTO patronage_seek_profiles(
               beneficiary_actor_id,domain_key,desire_level,preferred_support_kind,min_amount_per_cycle,
               preferred_duration_days,max_exclusivity,funding_priority,prestige_priority,independence_priority,
               max_simultaneous_requests,status,created_day,updated_day,next_review_day,metadata_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?,?)
           ON CONFLICT(beneficiary_actor_id,domain_key) DO UPDATE SET
             desire_level=excluded.desire_level,preferred_support_kind=excluded.preferred_support_kind,
             min_amount_per_cycle=excluded.min_amount_per_cycle,preferred_duration_days=excluded.preferred_duration_days,
             max_exclusivity=excluded.max_exclusivity,funding_priority=excluded.funding_priority,
             prestige_priority=excluded.prestige_priority,independence_priority=excluded.independence_priority,
             max_simultaneous_requests=excluded.max_simultaneous_requests,status='active',updated_day=excluded.updated_day,
             next_review_day=excluded.next_review_day,metadata_json=excluded.metadata_json""",
        (beneficiary_actor_id,domain_key,max(0,min(100,float(desire_level))),preferred_support_kind,
         max(0,float(min_amount_per_cycle)),preferred_duration_days,max(0,min(1,float(max_exclusivity))),
         max(0,min(100,float(funding_priority))),max(0,min(100,float(prestige_priority))),
         max(0,min(100,float(independence_priority))),max(1,int(max_simultaneous_requests)),day,day,day,_j(metadata or {})),
    )
    return int(conn.execute("SELECT id FROM patronage_seek_profiles WHERE beneficiary_actor_id=? AND domain_key=?",(beneficiary_actor_id,domain_key)).fetchone()[0])


def discover_patrons(conn: sqlite3.Connection, beneficiary_actor_id: int, domain_key: str, *, limit: int = 8) -> list[dict[str, Any]]:
    profile=conn.execute("SELECT * FROM patronage_seek_profiles WHERE beneficiary_actor_id=? AND domain_key=? AND status='active'",(beneficiary_actor_id,domain_key)).fetchone()
    if not profile:
        return []
    player=conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    # Existing exclusive patronage means the actor cannot honestly solicit a rival unless the relationship ends first.
    exclusive=conn.execute("SELECT 1 FROM patronage_relationships WHERE beneficiary_actor_id=? AND domain_key=? AND status IN ('active','strained') AND exclusivity>=.75 LIMIT 1",(beneficiary_actor_id,domain_key)).fetchone()
    if exclusive:
        return []
    prefs=conn.execute("SELECT * FROM patronage_preferences WHERE domain_key=? AND status='active' AND patron_actor_id<>? ORDER BY interest_level DESC,id",(domain_key,beneficiary_actor_id)).fetchall()
    out=[]
    beneficiary_rep=reputation_value(conn,'actor',beneficiary_actor_id,[domain_key,'art_culture','public'],default=35)
    for pref in prefs:
        patron=int(pref['patron_actor_id'])
        # A player's own patronage choices must not be made by NPC automation. They can still receive the request.
        if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'",(patron,)).fetchone():
            continue
        patron_candidates=discover_candidates(conn,patron,domain_key,limit=50)
        candidate=next((x for x in patron_candidates if int(x['actor_id'])==int(beneficiary_actor_id)),None)
        if not candidate:
            continue
        amount=max(float(profile['min_amount_per_cycle']), min(float(pref['max_amount_per_cycle']), max(.5,float(pref['interest_level'])/22.0)))
        source=_best_funding_source(conn,patron,amount)
        if source is None and amount>0:
            continue
        active_count=int(conn.execute("SELECT COUNT(*) FROM patronage_relationships WHERE patron_actor_id=? AND status IN ('active','strained')",(patron,)).fetchone()[0])
        capacity=max(0.0,1.0-active_count/4.0)
        patron_rep=reputation_value(conn,'actor',patron,['art_culture','public','professional'],default=45)
        funding_fit=min(100.0,amount/max(.5,float(profile['min_amount_per_cycle']) or 1.0)*45.0)
        score=(float(candidate['fit_score'])*.32 + float(pref['interest_level'])*.18 +
               funding_fit*(float(profile['funding_priority'])/100.0)*.20 +
               patron_rep*(float(profile['prestige_priority'])/100.0)*.15 +
               capacity*100*.15)
        out.append({'patron_actor_id':patron,'fit_score':round(score,3),'amount_per_cycle':round(amount,2),
                    'funding_source_kind':source[0] if source else 'none','funding_source_id':source[1] if source else None,
                    'patron_reputation':round(patron_rep,2),'beneficiary_reputation':round(beneficiary_rep,2),
                    'patron_interest':float(pref['interest_level']),'patron_preference_id':int(pref['id']),
                    'is_player_patron':bool(player and player[0] is not None and int(player[0])==patron)})
    out.sort(key=lambda x:(-float(x['fit_score']),int(x['patron_actor_id'])))
    return out[:max(1,int(limit))]


def request_patronage(conn: sqlite3.Connection, beneficiary_actor_id: int, patron_actor_id: int, domain_key: str, *, amount_per_cycle: float | None = None) -> tuple[int,int]:
    profile=conn.execute("SELECT * FROM patronage_seek_profiles WHERE beneficiary_actor_id=? AND domain_key=? AND status='active'",(beneficiary_actor_id,domain_key)).fetchone()
    if not profile:
        raise ValueError('beneficiary has no active patronage-seeking intent')
    candidates=discover_patrons(conn,beneficiary_actor_id,domain_key,limit=50)
    cand=next((x for x in candidates if int(x['patron_actor_id'])==int(patron_actor_id)),None)
    if not cand:
        raise ValueError('patron is not a currently plausible match')
    amount=float(amount_per_cycle if amount_per_cycle is not None else cand['amount_per_cycle'])
    pid=create_proposal(conn,beneficiary_actor_id,'patronage',domain_key,f"Request for patronage in {domain_key}",target_actor_id=patron_actor_id,
                        source_kind='patronage_seek_profile',source_id=int(profile['id']),metadata={'patronnet01':True,'direction':'beneficiary_request'})
    pmeta=_loads(profile['metadata_json'],{})
    desired_exclusivity=min(float(profile['max_exclusivity']),max(0.0,float(pmeta.get('desired_exclusivity') or 0.0)))
    add_term(conn,pid,'recurring_stipend',subject_kind='actor',subject_id=beneficiary_actor_id,execution_order=20,value={
        'amount':amount,'recurrence_days':30,'duration_days':profile['preferred_duration_days'],
        'funding_source_kind':cand['funding_source_kind'],'funding_source_id':cand['funding_source_id'],
        'patronage_kind':str(profile['preferred_support_kind']),'support':{'independence_preserved':True},
        'expectations':{'beneficiary_requested_support':True},'exclusivity':desired_exclusivity,
        'independence_preserved':True,'patron_actor_id':patron_actor_id,'beneficiary_actor_id':beneficiary_actor_id,
    })
    iid=present_proposal(conn,pid,rationale='The beneficiary actively sought a real patron whose preferences, means, and knowledge made support plausible.')
    return pid,iid


def ensure_patronage_seeking(conn: sqlite3.Connection, day: int | None = None) -> int:
    """Allow explicit beneficiary-side patronage intent to produce bounded approaches."""
    day=_day(conn) if day is None else int(day)
    player=conn.execute("SELECT player_actor_id FROM player_state WHERE id=1").fetchone()
    player_id=int(player[0]) if player and player[0] is not None else None
    created=0
    rows=conn.execute("SELECT * FROM patronage_seek_profiles WHERE status='active' AND next_review_day<=? AND desire_level>=45 ORDER BY desire_level DESC,id",(day,)).fetchall()
    for row in rows:
        beneficiary=int(row['beneficiary_actor_id'])
        # Never invent outgoing player decisions. A player's profile may be queried manually by UI/action code.
        if player_id is not None and beneficiary==player_id:
            conn.execute("UPDATE patronage_seek_profiles SET next_review_day=?,updated_day=? WHERE id=?",(day+30,day,int(row['id'])))
            continue
        pending=int(conn.execute("SELECT COUNT(*) FROM opportunity_proposals WHERE proposal_kind='patronage' AND proposer_actor_id=? AND source_kind='patronage_seek_profile' AND source_id=? AND status IN ('draft','pending','countered')",(beneficiary,int(row['id']))).fetchone()[0])
        slots=max(0,int(row['max_simultaneous_requests'])-pending)
        if slots<=0:
            conn.execute("UPDATE patronage_seek_profiles SET next_review_day=?,updated_day=? WHERE id=?",(day+30,day,int(row['id'])))
            continue
        candidates=discover_patrons(conn,beneficiary,str(row['domain_key']),limit=max(4,slots*3))
        existing_targets={int(x[0]) for x in conn.execute("SELECT target_actor_id FROM opportunity_proposals WHERE proposer_actor_id=? AND source_kind='patronage_seek_profile' AND source_id=? AND status IN ('draft','pending','countered','accepted') AND target_actor_id IS NOT NULL",(beneficiary,int(row['id']))).fetchall()}
        for cand in candidates:
            if slots<=0: break
            patron=int(cand['patron_actor_id'])
            if patron in existing_targets: continue
            request_patronage(conn,beneficiary,patron,str(row['domain_key']))
            created+=1; slots-=1
        conn.execute("UPDATE patronage_seek_profiles SET next_review_day=?,updated_day=? WHERE id=?",(day+60,day,int(row['id'])))
    refresh_patronage_competitions(conn,day)
    return created


def _proposal_patron_beneficiary(conn: sqlite3.Connection, proposal_id: int) -> tuple[int|None,int|None,float,float]:
    p=conn.execute("SELECT * FROM opportunity_proposals WHERE id=?",(proposal_id,)).fetchone()
    if not p or str(p['proposal_kind'])!='patronage': return None,None,0.0,0.0
    t=conn.execute("SELECT value_json FROM opportunity_proposal_terms WHERE proposal_id=? AND term_kind='recurring_stipend' ORDER BY execution_order,id LIMIT 1",(proposal_id,)).fetchone()
    if not t: return None,None,0.0,0.0
    v=_loads(t[0],{})
    patron=int(v['patron_actor_id']) if v.get('patron_actor_id') is not None else int(p['proposer_actor_id'])
    beneficiary=int(v['beneficiary_actor_id']) if v.get('beneficiary_actor_id') is not None else (int(p['target_actor_id']) if p['target_actor_id'] is not None else None)
    return patron,beneficiary,float(v.get('amount') or 0),float(v.get('exclusivity') or 0)


def refresh_patronage_competitions(conn: sqlite3.Connection, day: int | None = None) -> int:
    day=_day(conn) if day is None else int(day); created=0
    proposals=conn.execute("SELECT id,domain_key FROM opportunity_proposals WHERE proposal_kind='patronage' AND status='pending' ORDER BY id").fetchall()
    groups: dict[tuple[int,str],list[tuple[int,int,float,float]]]={}
    for p in proposals:
        patron,beneficiary,amount,excl=_proposal_patron_beneficiary(conn,int(p['id']))
        if patron is None or beneficiary is None: continue
        groups.setdefault((beneficiary,str(p['domain_key'])),[]).append((int(p['id']),patron,amount,excl))
    for (beneficiary,domain),entries in groups.items():
        distinct={e[1] for e in entries}
        if len(distinct)<2: continue
        comp=conn.execute("SELECT * FROM patronage_competitions WHERE beneficiary_actor_id=? AND domain_key=? AND status='active' ORDER BY id DESC LIMIT 1",(beneficiary,domain)).fetchone()
        if not comp:
            cid=int(conn.execute("INSERT INTO patronage_competitions(beneficiary_actor_id,domain_key,started_day,status,metadata_json) VALUES (?,?,?,'active',?)",(beneficiary,domain,day,_j({'patronnet01':True}))).lastrowid); created+=1
        else: cid=int(comp['id'])
        for pid,patron,amount,excl in entries:
            conn.execute("INSERT OR IGNORE INTO patronage_competition_entries(competition_id,proposal_id,patron_actor_id,amount_per_cycle,exclusivity,entered_day,status) VALUES (?,?,?,?,?,?,'active')",(cid,pid,patron,amount,excl,day))
    return created


def _resolve_competition_after_acceptance(conn: sqlite3.Connection, beneficiary_actor_id: int, domain_key: str, winning_patron_actor_id: int, winning_proposal_id: int, day: int, *, exclusive: bool) -> None:
    refresh_patronage_competitions(conn,day)
    comps=conn.execute("SELECT * FROM patronage_competitions WHERE beneficiary_actor_id=? AND domain_key=? AND status='active'",(beneficiary_actor_id,domain_key)).fetchall()
    for comp in comps:
        cid=int(comp['id'])
        conn.execute("UPDATE patronage_competition_entries SET status=CASE WHEN proposal_id=? THEN 'won' ELSE 'lost' END WHERE competition_id=?",(winning_proposal_id,cid))
        conn.execute("UPDATE patronage_competitions SET status='resolved',resolved_day=?,winning_patron_actor_id=? WHERE id=?",(day,winning_patron_actor_id,cid))
        if exclusive:
            losers=conn.execute("SELECT proposal_id FROM patronage_competition_entries WHERE competition_id=? AND proposal_id<>?",(cid,winning_proposal_id)).fetchall()
            for row in losers:
                conn.execute("UPDATE opportunity_proposals SET status='withdrawn' WHERE id=? AND status IN ('draft','pending','countered')",(int(row[0]),))


def patronage_network(conn: sqlite3.Connection, domain_key: str | None = None) -> dict[str,Any]:
    where="WHERE status IN ('active','strained')"; args: tuple[Any,...]=()
    if domain_key is not None:
        where += " AND domain_key=?"; args=(domain_key,)
    rels=conn.execute(f"SELECT * FROM patronage_relationships {where} ORDER BY id",args).fetchall()
    patrons={int(r['patron_actor_id']) for r in rels}; beneficiaries={int(r['beneficiary_actor_id']) for r in rels if r['beneficiary_actor_id'] is not None}
    return {'relationships':len(rels),'patrons':len(patrons),'beneficiaries':len(beneficiaries),
            'multi_patron_beneficiaries':int(conn.execute(f"SELECT COUNT(*) FROM (SELECT beneficiary_actor_id FROM patronage_relationships {where} AND beneficiary_actor_id IS NOT NULL GROUP BY beneficiary_actor_id HAVING COUNT(*)>1)",args).fetchone()[0]) if rels else 0,
            'active_competitions':int(conn.execute("SELECT COUNT(*) FROM patronage_competitions WHERE status='active'" + (" AND domain_key=?" if domain_key is not None else ""),args).fetchone()[0])}


def ensure_patronage_attention(conn: sqlite3.Connection, day: int | None = None) -> int:
    """Create bounded ATTENTION cases for patrons who have explicit patronage preferences.

    Preferences are the patron's own durable taste/motive state. The matching layer never creates
    an artistic interest merely because a famous artist exists.
    """
    day = _day(conn) if day is None else int(day)
    from .attention import create_attention_case
    created = 0
    prefs = conn.execute(
        "SELECT * FROM patronage_preferences WHERE status='active' AND interest_level>=45 ORDER BY interest_level DESC,id"
    ).fetchall()
    for pref in prefs:
        patron = int(pref['patron_actor_id'])
        if not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (patron,)).fetchone():
            continue
        active_count = int(conn.execute("SELECT COUNT(*) FROM patronage_relationships WHERE patron_actor_id=? AND status IN ('active','strained')", (patron,)).fetchone()[0])
        max_active = 1 + (1 if float(pref['interest_level']) >= 80 else 0) + (1 if float(pref['interest_level']) >= 95 else 0)
        if active_count >= max_active:
            continue
        candidates = discover_candidates(conn, patron, str(pref['domain_key']), limit=6)
        selected = None
        for cand in candidates:
            target = int(cand['actor_id'])
            if conn.execute("SELECT 1 FROM patronage_relationships WHERE patron_actor_id=? AND beneficiary_actor_id=? AND domain_key=? AND status IN ('active','strained') LIMIT 1", (patron,target,str(pref['domain_key']))).fetchone():
                continue
            if conn.execute("SELECT 1 FROM strategic_attention_cases WHERE observer_actor_id=? AND target_actor_id=? AND domain_key=? AND interest_kind='patronize' AND status IN ('observing','planning','approaching','fulfilled') LIMIT 1", (patron,target,str(pref['domain_key']))).fetchone():
                continue
            selected = cand; break
        if not selected:
            continue
        amount = min(float(pref['max_amount_per_cycle']), max(0.5, float(pref['interest_level']) / 22.0))
        source = _best_funding_source(conn, patron, amount)
        if source is None and amount > 0:
            continue
        skind, sid = source if source else ('none', None)
        salience = max(0.0, min(100.0, float(selected['fit_score']) * .75 + float(pref['interest_level']) * .25))
        create_attention_case(
            conn, patron, int(selected['actor_id']), str(pref['domain_key']), 'patronize', salience=salience,
            source_kind='patronage_preference', source_id=int(pref['id']), expires_in_days=240,
            metadata={
                'provider':'patronage_preference','title':f"Patronage of {selected['name']}",
                'amount_per_cycle':round(amount,2),'recurrence_days':int(pref['recurrence_days']),
                'duration_days':360,'patronage_kind':str(pref['preferred_support_kind']),
                'funding_source_kind':skind,'funding_source_id':sid,'exclusivity':0.0,
                'support':{'independence_preserved':True},
                'expectations':{'association_expected':True,'ownership_of_unrelated_work':False},
                'candidate_evidence':selected,
            },
        )
        created += 1
    return created


def note_cultural_success(conn: sqlite3.Connection, creator_actor_id: int, quality: float, *, day: int | None = None, object_id: int | None = None) -> dict[str, Any]:
    """Feed acclaimed work back into artist and patron reputation without transferring ownership."""
    day = _day(conn) if day is None else int(day)
    q = max(0.0, min(100.0, float(quality)))
    artist_delta = max(0.0, (q - 55.0) / 24.0)
    if artist_delta > 0:
        adjust_reputation(conn, 'actor', creator_actor_id, 'art_culture', artist_delta, day=day, metadata={'cultural_object_id':object_id})
    patrons = conn.execute(
        "SELECT * FROM patronage_relationships WHERE beneficiary_actor_id=? AND status IN ('active','strained') AND domain_key IN ('art_culture','painting','sculpture','music','literature','craft')",
        (creator_actor_id,),
    ).fetchall()
    affected=[]
    for rel in patrons:
        delta=max(0.0,(q-65.0)/45.0)
        if delta>0:
            new=adjust_reputation(conn,'actor',int(rel['patron_actor_id']),'art_culture',delta,day=day,metadata={'patronage_id':int(rel['id']),'beneficiary_actor_id':creator_actor_id,'cultural_object_id':object_id})
            affected.append({'patron_actor_id':int(rel['patron_actor_id']),'delta':delta,'new_reputation':new})
    circle_effects=[]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='patronage_circles'").fetchone():
        circles=conn.execute(
            """SELECT pc.* FROM patronage_circles pc JOIN patronage_circle_members pcm ON pcm.circle_id=pc.id
               WHERE pcm.actor_id=? AND pcm.status='active' AND pc.status='active'""",(creator_actor_id,)).fetchall()
        for circle in circles:
            visibility=float(circle['public_visibility'])
            prestige_delta=max(0.0,(q-72.0)/90.0)*(visibility/100.0)
            if prestige_delta>0:
                conn.execute("UPDATE patronage_circles SET prestige=MIN(100,prestige+?) WHERE id=?",(prestige_delta,int(circle['id'])))
            spill=[]
            # Association can help a little when the circle is public, but cannot manufacture peer achievement.
            if q>=85 and visibility>=55:
                peer_delta=min(.20,max(0.0,(q-82.0)/100.0)*(visibility/100.0))
                if peer_delta>0:
                    peers=conn.execute("SELECT actor_id FROM patronage_circle_members WHERE circle_id=? AND status='active' AND actor_id<>?",(int(circle['id']),creator_actor_id)).fetchall()
                    for peer in peers:
                        aid=int(peer['actor_id'])
                        adjust_reputation(conn,'actor',aid,'art_culture',peer_delta,day=day,metadata={'circle_id':int(circle['id']),'associated_success_actor_id':creator_actor_id,'cultural_object_id':object_id})
                        spill.append({'actor_id':aid,'delta':peer_delta})
            circle_effects.append({'circle_id':int(circle['id']),'prestige_delta':prestige_delta,'peer_spillover':spill})
        evaluate_cultural_movements(conn,day)
    return {'artist_delta':artist_delta,'patrons':affected,'circles':circle_effects}
