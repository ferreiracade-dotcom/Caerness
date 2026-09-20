from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def create_jurisdiction(conn: sqlite3.Connection, jurisdiction_key: str, name: str, authority_kind: str, *,
                        polity_id: int | None = None, location_id: int | None = None, priority: int = 50,
                        metadata: dict[str,Any] | None = None) -> int:
    cur=conn.execute("""INSERT INTO law_jurisdictions(jurisdiction_key,name,authority_kind,polity_id,location_id,priority,metadata_json)
                        VALUES (?,?,?,?,?,?,?)""",
                     (jurisdiction_key,name,authority_kind,polity_id,location_id,int(priority),json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def add_rule(conn: sqlite3.Connection, jurisdiction_id: int, rule_key: str, name: str, matter_kind: str, *,
             evidence_threshold: float = 55, default_remedy: str = 'order', metadata: dict[str,Any] | None = None) -> int:
    cur=conn.execute("""INSERT INTO law_rules(jurisdiction_id,rule_key,name,matter_kind,evidence_threshold,default_remedy,metadata_json)
                        VALUES (?,?,?,?,?,?,?)""",
                     (jurisdiction_id,rule_key,name,matter_kind,max(0,min(100,float(evidence_threshold))),default_remedy,
                      json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def create_office(conn: sqlite3.Connection, office_key: str, name: str, jurisdiction_id: int, *,
                  location_id: int | None = None, institution_actor_id: int | None = None,
                  presiding_actor_id: int | None = None, capacity: float = 50, integrity: float = 70,
                  corruption_pressure: float = 10, metadata: dict[str,Any] | None = None) -> int:
    cur=conn.execute("""INSERT INTO law_offices(office_key,name,jurisdiction_id,location_id,institution_actor_id,presiding_actor_id,
                        capacity,integrity,corruption_pressure,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (office_key,name,jurisdiction_id,location_id,institution_actor_id,presiding_actor_id,
                      max(0,min(100,float(capacity))),max(0,min(100,float(integrity))),max(0,min(100,float(corruption_pressure))),
                      json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def _location_polity(conn: sqlite3.Connection, location_id: int) -> int | None:
    r=conn.execute("""SELECT controller_polity_id FROM territorial_control WHERE location_id=?
                      ORDER BY since_day DESC LIMIT 1""",(location_id,)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def resolve_jurisdiction(conn: sqlite3.Connection, location_id: int, matter_kind: str, *, polity_id: int | None = None) -> tuple[int,int] | None:
    pid=_location_polity(conn,location_id) if polity_id is None else polity_id
    rows=conn.execute("""SELECT j.*,r.id AS rule_id FROM law_jurisdictions j JOIN law_rules r ON r.jurisdiction_id=j.id
                         WHERE j.status='active' AND r.status='active' AND r.matter_kind=?
                         AND (j.location_id=? OR j.polity_id=? OR (j.location_id IS NULL AND j.polity_id IS NULL))
                         ORDER BY CASE WHEN j.location_id=? THEN 3 WHEN j.polity_id=? THEN 2 ELSE 1 END DESC,
                                  j.priority DESC,j.id""",
                      (matter_kind,location_id,pid,location_id,pid)).fetchall()
    if not rows: return None
    return int(rows[0]['id']),int(rows[0]['rule_id'])


def _office_delay(office: sqlite3.Row) -> int:
    capacity=float(office['capacity']); corruption=float(office['corruption_pressure'])
    return max(2,int(round(12.0-capacity*.08+corruption*.025)))


def file_case(conn: sqlite3.Connection, *, location_id: int, matter_kind: str, claim_text: str,
              claimant_actor_id: int | None = None, respondent_actor_id: int | None = None,
              claimant_enterprise_id: int | None = None, respondent_enterprise_id: int | None = None,
              subject_kind: str = 'other', subject_id: int | None = None, amount_claimed: float = 0,
              polity_id: int | None = None, metadata: dict[str,Any] | None = None) -> int:
    resolved=resolve_jurisdiction(conn,location_id,matter_kind,polity_id=polity_id)
    if not resolved: raise ValueError('no applicable jurisdiction/rule')
    jid,rid=resolved
    office=conn.execute("""SELECT * FROM law_offices WHERE jurisdiction_id=? AND status IN ('active','strained')
                           AND (location_id=? OR location_id IS NULL) ORDER BY CASE WHEN location_id=? THEN 1 ELSE 0 END DESC,capacity DESC,id LIMIT 1""",
                        (jid,location_id,location_id)).fetchone()
    day=_day(conn); oid=int(office['id']) if office else None; delay=_office_delay(office) if office else 30
    cur=conn.execute("""INSERT INTO law_cases(jurisdiction_id,rule_id,office_id,matter_kind,location_id,claimant_actor_id,
                        respondent_actor_id,claimant_enterprise_id,respondent_enterprise_id,subject_kind,subject_id,claim_text,
                        amount_claimed,status,filed_day,last_review_day,next_review_day,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'complaint',?,?,?,?)""",
                     (jid,rid,oid,matter_kind,location_id,claimant_actor_id,respondent_actor_id,claimant_enterprise_id,
                      respondent_enterprise_id,subject_kind,subject_id,claim_text,max(0,float(amount_claimed)),day,day,day+delay,
                      json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def add_case_evidence(conn: sqlite3.Connection, case_id: int, evidence_kind: str, summary: str, *, strength: float,
                      source_kind: str | None = None, source_id: int | None = None,
                      metadata: dict[str,Any] | None = None) -> int:
    day=_day(conn)
    cur=conn.execute("""INSERT INTO law_case_evidence(case_id,evidence_kind,source_kind,source_id,summary,strength,submitted_day,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?)""",
                     (case_id,evidence_kind,source_kind,source_id,summary,max(0,min(100,float(strength))),day,
                      json.dumps(metadata or {},sort_keys=True)))
    score=conn.execute("SELECT MIN(100,COALESCE(SUM(strength*.55),0)) FROM law_case_evidence WHERE case_id=?",(case_id,)).fetchone()[0]
    conn.execute("UPDATE law_cases SET evidence_score=? WHERE id=?",(float(score or 0),case_id))
    return int(cur.lastrowid)


def _case_party_actor(conn: sqlite3.Connection, row: sqlite3.Row, side: str) -> int | None:
    direct=row[f'{side}_actor_id']
    if direct is not None: return int(direct)
    ent=row[f'{side}_enterprise_id']
    if ent is None: return None
    r=conn.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?",(int(ent),)).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _publish_judgment(conn: sqlite3.Connection, case: sqlite3.Row, judgment_id: int, finding: str, amount: float, day: int) -> None:
    try:
        from .belief import ensure_claim, add_claim_evidence, observe_claim
        claim=ensure_claim(conn,f'law:case:{int(case["id"])}:judgment',
                           f'Case #{int(case["id"])} was decided for {finding}; award {amount:.2f}.',
                           subject_kind='law_case',subject_id=int(case['id']),created_day=day,source_kind='law')
        ev=add_claim_evidence(conn,claim,evidence_kind='judgment',source_id=judgment_id,
                              summary=f'Entered judgment in case #{int(case["id"])}.',reliability=.96,salience=.8,
                              domain_key='law',location_id=int(case['location_id']),available_from_day=day,
                              metadata={'case_id':int(case['id']),'judgment_id':judgment_id})
        for side in ('claimant','respondent'):
            aid=_case_party_actor(conn,case,side)
            if aid is not None:
                observe_claim(conn,aid,claim,ev,received_day=day,access_kind='legal_notice',reason='judgment_received')
    except (ImportError,sqlite3.OperationalError):
        pass


def _enforce(conn: sqlite3.Connection, case: sqlite3.Row, judgment: sqlite3.Row, day: int) -> tuple[float,str]:
    amount=float(judgment['amount_awarded'])
    if str(judgment['finding'])!='claimant' or amount<=0:
        return 0.0,'enforced'
    payer=case['respondent_enterprise_id']; payee=case['claimant_enterprise_id']
    if payer is None or payee is None:
        return 0.0,'unenforceable'
    prow=conn.execute("SELECT cash,debt FROM civilian_enterprises WHERE id=?",(int(payer),)).fetchone()
    if not prow: return 0.0,'unenforceable'
    paid=min(amount,max(0.0,float(prow['cash'])))
    if paid>0:
        conn.execute("UPDATE civilian_enterprises SET cash=cash-?,updated_day=? WHERE id=?",(paid,day,int(payer)))
        conn.execute("UPDATE civilian_enterprises SET cash=cash+?,updated_day=? WHERE id=?",(paid,day,int(payee)))
        conn.execute("""INSERT INTO commercial_cash_transfers(day,from_enterprise_id,to_enterprise_id,amount,transfer_kind,metadata_json)
                        VALUES (?,?,?,?, 'legal_judgment',?)""",
                     (day,int(payer),int(payee),paid,json.dumps({'case_id':int(case['id']),'judgment_id':int(judgment['id'])},sort_keys=True)))
    short=max(0.0,amount-paid)
    if short>0:
        conn.execute("UPDATE civilian_enterprises SET debt=debt+?,updated_day=? WHERE id=?",(short,day,int(payer)))
    return paid,('enforced' if short<=1e-9 else 'partially_enforced')


def _process_case(conn: sqlite3.Connection, row: sqlite3.Row, day: int) -> str:
    office=conn.execute("SELECT * FROM law_offices WHERE id=?",(row['office_id'],)).fetchone() if row['office_id'] is not None else None
    if not office or str(office['status'])=='inactive' or float(office['capacity'])<10:
        conn.execute("UPDATE law_cases SET status='stalled',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,int(row['id'])))
        return 'stalled'
    delay=_office_delay(office); status=str(row['status'])
    if status=='stalled':
        status='complaint'
    if status=='complaint':
        conn.execute("UPDATE law_cases SET status='evidence',last_review_day=?,next_review_day=? WHERE id=?",(day,day+delay,int(row['id'])))
        return 'evidence'
    if status=='evidence':
        score=float(conn.execute("SELECT MIN(100,COALESCE(SUM(strength*.55),0)) FROM law_case_evidence WHERE case_id=?",(int(row['id']),)).fetchone()[0] or 0)
        conn.execute("UPDATE law_cases SET evidence_score=? WHERE id=?",(score,int(row['id'])))
        if score < 10:
            conn.execute("UPDATE law_cases SET status='stalled',last_review_day=?,next_review_day=? WHERE id=?",(day,day+30,int(row['id'])))
            return 'stalled'
        conn.execute("UPDATE law_cases SET status='hearing',last_review_day=?,next_review_day=? WHERE id=?",(day,day+delay,int(row['id'])))
        return 'hearing'
    if status=='hearing':
        rule=conn.execute("SELECT * FROM law_rules WHERE id=?",(int(row['rule_id']),)).fetchone()
        effective=float(row['evidence_score'])+(float(office['integrity'])-50)*.10-float(office['corruption_pressure'])*.10
        favored=json.loads(office['metadata_json'] or '{}').get('favored_side')
        if favored=='respondent': effective-=15
        elif favored=='claimant': effective+=15
        liable=effective>=float(rule['evidence_threshold'])
        finding='claimant' if liable else 'respondent'
        amount=float(row['amount_claimed']) if liable and str(rule['default_remedy']) in ('damages','restitution','fine') else 0.0
        cur=conn.execute("""INSERT INTO law_judgments(case_id,day,finding,remedy_kind,amount_awarded,status,metadata_json)
                            VALUES (?,?,?,?,?,'entered',?)""",
                         (int(row['id']),day,finding,str(rule['default_remedy']) if liable else 'dismissal',amount,
                          json.dumps({'effective_evidence':effective,'office_integrity':float(office['integrity']),
                                      'corruption_pressure':float(office['corruption_pressure'])},sort_keys=True)))
        text=f"{finding} finding under {rule['name']}"
        conn.execute("UPDATE law_cases SET status='decided',decision_text=?,last_review_day=?,next_review_day=? WHERE id=?",
                     (text,day,day+max(1,delay//2),int(row['id'])))
        _publish_judgment(conn,row,int(cur.lastrowid),finding,amount,day)
        return 'decided'
    if status=='decided':
        conn.execute("UPDATE law_cases SET status='enforcement',last_review_day=?,next_review_day=? WHERE id=?",(day,day+1,int(row['id'])))
        return 'enforcement'
    if status=='enforcement':
        judgment=conn.execute("SELECT * FROM law_judgments WHERE case_id=?",(int(row['id']),)).fetchone()
        paid,jstatus=_enforce(conn,row,judgment,day) if judgment else (0.0,'unenforceable')
        if judgment:
            conn.execute("UPDATE law_judgments SET amount_enforced=?,status=? WHERE id=?",(paid,jstatus,int(judgment['id'])))
        conn.execute("""INSERT INTO law_enforcement_steps(case_id,judgment_id,day,step_kind,success,summary,metadata_json)
                        VALUES (?,?,?,?,?,?,?)""",
                     (int(row['id']),int(judgment['id']) if judgment else None,day,'financial_enforcement',1 if jstatus in ('enforced','partially_enforced') else 0,
                      f'Enforced {paid:.2f} of the judgment.',json.dumps({'judgment_status':jstatus},sort_keys=True)))
        conn.execute("UPDATE law_cases SET status='closed',last_review_day=?,next_review_day=? WHERE id=?",(day,day,int(row['id'])))
        return 'closed'
    return status


def _autofile_breached_contracts(conn: sqlite3.Connection, day: int) -> int:
    made=0
    rows=conn.execute("""SELECT c.*,b.location_id AS buyer_location,s.location_id AS seller_location
                         FROM merchant_trade_contracts c
                         JOIN civilian_enterprises b ON b.id=c.buyer_enterprise_id
                         JOIN civilian_enterprises s ON s.id=c.seller_enterprise_id
                         WHERE c.status='breached' ORDER BY c.id""").fetchall()
    for r in rows:
        if conn.execute("SELECT 1 FROM law_cases WHERE subject_kind='merchant_trade_contract' AND subject_id=?",(int(r['id']),)).fetchone():
            continue
        loc=int(r['destination_location_id'])
        if not resolve_jurisdiction(conn,loc,'contract'): continue
        claimant=int(r['buyer_enterprise_id']) if float(r['delivered_quantity'])<float(r['quantity']) else int(r['seller_enterprise_id'])
        respondent=int(r['seller_enterprise_id']) if claimant==int(r['buyer_enterprise_id']) else int(r['buyer_enterprise_id'])
        cid=file_case(conn,location_id=loc,matter_kind='contract',claim_text=f'Breach of trade contract #{int(r["id"])}.',
                      claimant_enterprise_id=claimant,respondent_enterprise_id=respondent,subject_kind='merchant_trade_contract',
                      subject_id=int(r['id']),amount_claimed=max(0.0,float(r['quantity'])*float(r['unit_price'])-float(r['amount_paid'])),
                      metadata={'autofiled_from_contract':int(r['id'])})
        add_case_evidence(conn,cid,'contract_record',f'Trade contract #{int(r["id"])} is recorded as breached.',strength=85,
                          source_kind='merchant_trade_contract',source_id=int(r['id']))
        made+=1
    return made


def next_law_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    r=conn.execute("SELECT MIN(next_review_day) FROM law_cases WHERE status NOT IN ('closed','dismissed') AND next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()
    if r and r[0] is not None: vals.append(int(r[0]))
    # A breached contract with an applicable rule is eligible for prompt filing.
    if conn.execute("""SELECT 1 FROM merchant_trade_contracts c WHERE c.status='breached'
                         AND NOT EXISTS(SELECT 1 FROM law_cases lc WHERE lc.subject_kind='merchant_trade_contract' AND lc.subject_id=c.id)
                         AND EXISTS(SELECT 1 FROM law_rules r JOIN law_jurisdictions j ON j.id=r.jurisdiction_id
                                    WHERE r.matter_kind='contract' AND r.status='active' AND j.status='active') LIMIT 1""").fetchone():
        d=min(end_day,after_day+1)
        if d>after_day: vals.append(d)
    return min(vals) if vals else None


def process_due_law(conn: sqlite3.Connection, day: int, *, event_logger: Callable[..., int] | None = None) -> dict[str,int]:
    filed=_autofile_breached_contracts(conn,day)
    rows=conn.execute("SELECT * FROM law_cases WHERE status NOT IN ('closed','dismissed') AND next_review_day<=? ORDER BY next_review_day,id",(day,)).fetchall()
    counts={'filed':filed,'reviewed':0,'stalled':0,'decided':0,'closed':0}
    for row in rows:
        state=_process_case(conn,row,day); counts['reviewed']+=1
        if state in counts: counts[state]+=1
    return counts


def law_summary(conn: sqlite3.Connection) -> dict[str,int]:
    return {'jurisdictions':int(conn.execute("SELECT COUNT(*) FROM law_jurisdictions WHERE status='active'").fetchone()[0]),
            'rules':int(conn.execute("SELECT COUNT(*) FROM law_rules WHERE status='active'").fetchone()[0]),
            'open_cases':int(conn.execute("SELECT COUNT(*) FROM law_cases WHERE status NOT IN ('closed','dismissed')").fetchone()[0]),
            'judgments':int(conn.execute("SELECT COUNT(*) FROM law_judgments").fetchone()[0])}
