from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

DEPENDENCY_KINDS = {
    'chemical_medication', 'intoxicant', 'stimulant', 'gambling', 'elixir_performance', 'other'
}
PSYCH_FAMILIES = {'trauma','grief','anxiety','depression','nightmares','obsession','severe_mental_illness','other'}


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _living(conn: sqlite3.Connection, actor_id: int) -> bool:
    row=conn.execute("SELECT a.status,lp.life_status FROM actors a LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?",(actor_id,)).fetchone()
    return bool(row and str(row['status'])!='deceased' and (row['life_status'] is None or str(row['life_status'])=='living'))


def _meta(raw: str | None) -> dict[str,Any]:
    try: return json.loads(raw) if raw else {}
    except Exception: return {}


def _upsert_pressure(conn: sqlite3.Connection, actor_id: int, kind: str, description: str, intensity: float, threshold: float=10.0) -> None:
    row=conn.execute("SELECT id FROM pressures WHERE actor_id=? AND kind=? ORDER BY id LIMIT 1",(actor_id,kind)).fetchone()
    intensity=max(0.0,float(intensity))
    if row:
        conn.execute("UPDATE pressures SET description=?,intensity=?,threshold=?,updated_day=? WHERE id=?",(description,intensity,threshold,_day(conn),int(row[0])))
    elif intensity>0:
        conn.execute("INSERT INTO pressures(actor_id,kind,description,intensity,threshold,updated_day) VALUES (?,?,?,?,?,?)",(actor_id,kind,description,intensity,threshold,_day(conn)))


def _sync_dependency_pressure(conn: sqlite3.Connection, actor_id: int, dependency_kind: str) -> None:
    row=conn.execute("SELECT * FROM dependency_profiles WHERE actor_id=? AND dependency_kind=?",(actor_id,dependency_kind)).fetchone()
    if not row: return
    status=str(row['status'])
    intensity=0.0 if status in {'resolved','risk'} else max(float(row['functional_impairment']),float(row['urge_load'])*0.45)
    _upsert_pressure(conn,actor_id,f'dependency:{dependency_kind}',f"Dependence on {dependency_kind.replace('_',' ')} is creating practical pressure.",intensity,20.0)


def _sync_psych_pressure(conn: sqlite3.Connection, actor_id: int, family: str) -> None:
    rows=conn.execute("SELECT severity,functional_impairment,status FROM psychological_conditions WHERE actor_id=? AND condition_family=? AND status IN ('active','recovering','chronic')",(actor_id,family)).fetchall()
    intensity=max([max(float(r['functional_impairment']),float(r['severity'])*0.25) for r in rows],default=0.0)
    _upsert_pressure(conn,actor_id,f'psychological:{family}',f"Persistent {family.replace('_',' ')} is affecting ordinary functioning.",intensity,20.0)


def record_dependency_exposure(conn: sqlite3.Connection, actor_id: int, dependency_kind: str, *, source_kind: str,
                               amount: float=1.0, reinforcing_value: float=50.0, adverse_consequence: float=0.0,
                               source_ref_kind: str | None=None, source_ref_id: int | None=None,
                               metadata: dict[str,Any] | None=None) -> int:
    if dependency_kind not in DEPENDENCY_KINDS: raise ValueError('Unknown dependency kind')
    if not _living(conn,actor_id): raise ValueError('Dependency exposure requires living actor')
    if amount<=0: raise ValueError('Exposure amount must be positive')
    day=_day(conn)
    if source_ref_kind and source_ref_id is not None:
        old=conn.execute("SELECT id FROM dependency_exposures WHERE actor_id=? AND source_ref_kind=? AND source_ref_id=? AND dependency_kind=?",(actor_id,source_ref_kind,source_ref_id,dependency_kind)).fetchone()
        if old: return int(old[0])
    cur=conn.execute("""INSERT INTO dependency_exposures(actor_id,dependency_kind,day,source_kind,amount,reinforcing_value,adverse_consequence,source_ref_kind,source_ref_id,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (actor_id,dependency_kind,day,source_kind,float(amount),max(0,min(100,float(reinforcing_value))),max(0,min(100,float(adverse_consequence))),source_ref_kind,source_ref_id,json.dumps(metadata or {},sort_keys=True)))
    pid=conn.execute("SELECT * FROM dependency_profiles WHERE actor_id=? AND dependency_kind=?",(actor_id,dependency_kind)).fetchone()
    load=float(amount)*(0.35+max(0,min(100,float(reinforcing_value)))/100.0)
    adverse=max(0,min(100,float(adverse_consequence)))
    if not pid:
        conn.execute("""INSERT INTO dependency_profiles(actor_id,dependency_kind,status,exposure_count,reinforcement_load,urge_load,tolerance_load,functional_impairment,consequence_load,last_exposure_day,last_review_day,next_review_day,metadata_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (actor_id,dependency_kind,'risk',1,load,min(100,load*3),min(100,load*1.5),min(100,adverse*0.2),adverse,day,day,day+30,json.dumps({},sort_keys=True)))
    else:
        count=int(pid['exposure_count'])+1
        reinforcement=float(pid['reinforcement_load'])+load
        urge=min(100,float(pid['urge_load'])+load*(2.0 if dependency_kind!='gambling' else 2.5))
        tolerance=min(100,float(pid['tolerance_load'])+load*(1.2 if dependency_kind in {'chemical_medication','intoxicant','stimulant'} else 0.45))
        consequences=min(100,float(pid['consequence_load'])+adverse)
        impairment=min(100,max(float(pid['functional_impairment']), consequences*0.35 + urge*0.18))
        status=str(pid['status'])
        # Exposure during recovery is a relapse signal, but one ordinary exposure is not automatically addiction.
        if status=='recovering': status='dependent' if urge>=28 or adverse>=35 else 'risk'
        elif status in {'risk','resolved'} and ((count>=3 and reinforcement>=8 and urge>=18) or adverse>=70): status='dependent'
        conn.execute("""UPDATE dependency_profiles SET status=?,exposure_count=?,reinforcement_load=?,urge_load=?,tolerance_load=?,functional_impairment=?,consequence_load=?,last_exposure_day=?,last_review_day=?,next_review_day=? WHERE id=?""",
                     (status,count,reinforcement,urge,tolerance,impairment,consequences,day,day,day+30,int(pid['id'])))
    _sync_dependency_pressure(conn,actor_id,dependency_kind)
    return int(cur.lastrowid)


def begin_dependency_recovery(conn: sqlite3.Connection, actor_id: int, dependency_kind: str, *, support_quality: float=50.0, metadata: dict[str,Any] | None=None) -> None:
    row=conn.execute("SELECT id,status,metadata_json FROM dependency_profiles WHERE actor_id=? AND dependency_kind=?",(actor_id,dependency_kind)).fetchone()
    if not row or str(row['status']) not in {'dependent','risk','recovering'}: raise ValueError('No active dependency state')
    m=_meta(row['metadata_json']); m['recovery_support_quality']=max(0,min(100,float(support_quality))); m['recovery_started_day']=_day(conn); m.update(metadata or {})
    conn.execute("UPDATE dependency_profiles SET status='recovering',metadata_json=?,next_review_day=? WHERE id=?",(json.dumps(m,sort_keys=True),_day(conn)+30,int(row['id'])))
    _sync_dependency_pressure(conn,actor_id,dependency_kind)


def record_psychological_stressor(conn: sqlite3.Connection, actor_id: int, stress_family: str, *, burden: float,
                                  source_kind: str, source_ref_kind: str | None=None, source_ref_id: int | None=None,
                                  metadata: dict[str,Any] | None=None) -> int:
    if stress_family not in PSYCH_FAMILIES: raise ValueError('Unknown psychological family')
    if not _living(conn,actor_id): raise ValueError('Psychological stressor requires living actor')
    if burden<=0: raise ValueError('Burden must be positive')
    if source_ref_kind and source_ref_id is not None:
        old=conn.execute("SELECT id FROM psychological_stressors WHERE actor_id=? AND stress_family=? AND source_ref_kind=? AND source_ref_id=?",(actor_id,stress_family,source_ref_kind,source_ref_id)).fetchone()
        if old: return int(old[0])
    cur=conn.execute("""INSERT INTO psychological_stressors(actor_id,stress_family,day,burden,source_kind,source_ref_kind,source_ref_id,metadata_json)
                       VALUES (?,?,?,?,?,?,?,?)""",(actor_id,stress_family,_day(conn),max(0,min(100,float(burden))),source_kind,source_ref_kind,source_ref_id,json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def record_psychological_support(conn: sqlite3.Connection, actor_id: int, *, condition_id: int | None=None,
                                 support_kind: str='family', helpfulness: float=50.0, metadata: dict[str,Any] | None=None) -> int:
    if not _living(conn,actor_id): raise ValueError('Support target must be living')
    if condition_id is not None:
        row=conn.execute("SELECT actor_id,status FROM psychological_conditions WHERE id=?",(condition_id,)).fetchone()
        if not row or int(row['actor_id'])!=actor_id or str(row['status']) not in {'active','recovering','chronic'}: raise ValueError('Invalid psychological condition')
    cur=conn.execute("INSERT INTO psychological_support(actor_id,condition_id,day,support_kind,helpfulness,metadata_json) VALUES (?,?,?,?,?,?)",(actor_id,condition_id,_day(conn),support_kind,max(-100,min(100,float(helpfulness))),json.dumps(metadata or {},sort_keys=True)))
    return int(cur.lastrowid)


def _ensure_condition_from_burden(conn: sqlite3.Connection, actor_id: int, family: str, day: int) -> bool:
    current=conn.execute("SELECT * FROM psychological_conditions WHERE actor_id=? AND condition_family=? AND status IN ('active','recovering','chronic') ORDER BY id DESC LIMIT 1",(actor_id,family)).fetchone()
    if current: return False
    row=conn.execute("SELECT COUNT(*),COALESCE(SUM(burden),0),MAX(burden) FROM psychological_stressors WHERE actor_id=? AND stress_family=? AND day>=?",(actor_id,family,day-365)).fetchone()
    count,total,maximum=int(row[0]),float(row[1]),float(row[2] or 0)
    # Ordinary distress is not automatically pathologized. Persistent state requires substantial or repeated burden.
    if not (maximum>=80 or (count>=2 and total>=95) or (count>=3 and total>=75)): return False
    severity=min(90,max(20,maximum*0.55+max(0,total-maximum)*0.20))
    impairment=min(80,max(8,severity*0.35))
    conn.execute("""INSERT INTO psychological_conditions(actor_id,condition_family,severity,functional_impairment,status,onset_day,last_review_day,next_review_day,metadata_json)
                    VALUES (?,?,?,?,'active',?,?,?,?)""",(actor_id,family,severity,impairment,day,day,day+30,json.dumps({'source':'accumulated_stressors'},sort_keys=True)))
    _sync_psych_pressure(conn,actor_id,family)
    return True


def _ingest_elixir_exposures(conn: sqlite3.Connection) -> int:
    rows=conn.execute("""SELECT e.* FROM elixir_exposures e
                         LEFT JOIN dependency_exposures d ON d.source_ref_kind='elixir_exposure' AND d.source_ref_id=e.id AND d.dependency_kind='elixir_performance'
                         WHERE d.id IS NULL ORDER BY e.id""").fetchall()
    n=0
    for e in rows:
        # Elixir is explicitly not chemically addictive. Repeated reliance may create performance dependence.
        record_dependency_exposure(conn,int(e['actor_id']),'elixir_performance',source_kind='cultivation_fuel',amount=max(0.25,float(e['units_consumed'])),reinforcing_value=min(90,35+float(e['reserve_gain'])*4),adverse_consequence=min(100,float(e['sediment_gain'])*12),source_ref_kind='elixir_exposure',source_ref_id=int(e['id']),metadata={'chemical_addiction':False})
        n+=1
    return n


def _ingest_severe_health_stressors(conn: sqlite3.Connection) -> int:
    rows=conn.execute("""SELECT h.* FROM health_conditions h
                         LEFT JOIN psychological_stressors p ON p.source_ref_kind='health_condition' AND p.source_ref_id=h.id AND p.stress_family='trauma'
                         WHERE p.id IS NULL AND h.severity>=75 AND h.status IN ('active','recovering','chronic','resolved') ORDER BY h.id""").fetchall()
    n=0
    for h in rows:
        if not _living(conn,int(h['actor_id'])): continue
        burden=min(100,max(10,(float(h['severity'])-60)*1.15 + float(h['pain_impact'])*0.25))
        record_psychological_stressor(conn,int(h['actor_id']),'trauma',burden=burden,source_kind='severe_injury_or_illness',source_ref_kind='health_condition',source_ref_id=int(h['id']),metadata={'label':str(h['label'])})
        n+=1
    return n


def _ingest_bereavement(conn: sqlite3.Connection) -> int:
    rows=conn.execute("""SELECT r.actor_a_id living_id,r.actor_b_id deceased_id,r.trust,r.affection,r.obligation,lp.last_review_day AS death_day
                         FROM relationships r
                         JOIN actor_life_profiles alp ON alp.actor_id=r.actor_a_id
                         JOIN actor_life_profiles lp ON lp.actor_id=r.actor_b_id
                         LEFT JOIN psychological_stressors p ON p.actor_id=r.actor_a_id AND p.source_ref_kind='bereavement_actor' AND p.source_ref_id=r.actor_b_id AND p.stress_family='grief'
                         WHERE alp.life_status='living' AND lp.life_status='deceased' AND lp.last_review_day IS NOT NULL AND p.id IS NULL
                           AND (r.trust>=55 OR r.affection>=55 OR r.obligation>=55)""").fetchall()
    n=0
    for r in rows:
        burden=min(75,max(20,(float(r['trust'])+float(r['affection'])+float(r['obligation']))*0.20))
        record_psychological_stressor(conn,int(r['living_id']),'grief',burden=burden,source_kind='bereavement',source_ref_kind='bereavement_actor',source_ref_id=int(r['deceased_id']),metadata={'death_day':int(r['death_day'])})
        n+=1
    return n

def next_psych_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    vals=[]
    for table in ('dependency_profiles','psychological_conditions'):
        row=conn.execute(f"SELECT MIN(next_review_day) FROM {table} WHERE status IN ('risk','dependent','recovering','chronic','active') AND next_review_day>? AND next_review_day<=?",(after_day,end_day)).fetchone()
        if row and row[0] is not None: vals.append(int(row[0]))
    # A monthly catch-up lets newly created concrete source events be ingested without creating conditions from nothing.
    month=((after_day//30)+1)*30
    if month<=end_day: vals.append(month)
    return min(vals) if vals else None


def process_due_psychology(conn: sqlite3.Connection, day: int, *, event_logger: Callable[...,int] | None=None) -> dict[str,int]:
    ingested=_ingest_elixir_exposures(conn)+_ingest_severe_health_stressors(conn)+_ingest_bereavement(conn)
    created=0; dep_reviewed=0; psych_reviewed=0; resolved=0
    # Convert only accumulated substantial stress into persistent psychological state.
    pairs=conn.execute("SELECT DISTINCT actor_id,stress_family FROM psychological_stressors WHERE day<=?",(day,)).fetchall()
    for p in pairs:
        if _ensure_condition_from_burden(conn,int(p['actor_id']),str(p['stress_family']),day): created+=1

    deps=conn.execute("SELECT * FROM dependency_profiles WHERE status IN ('risk','dependent','recovering') AND next_review_day<=? ORDER BY id",(day,)).fetchall()
    for d in deps:
        dep_reviewed+=1; status=str(d['status']); urge=float(d['urge_load']); tol=float(d['tolerance_load']); impairment=float(d['functional_impairment']); consequences=float(d['consequence_load'])
        days_since=max(0,day-int(d['last_exposure_day'] or day)); quiet=max(0.0,min(1.0,days_since/90.0))
        m=_meta(d['metadata_json']); support=float(m.get('recovery_support_quality',0.0))
        if status=='recovering':
            reduction=4.0+support*0.08+quiet*5
            urge=max(0,urge-reduction); impairment=max(0,impairment-reduction*0.65); consequences=max(0,consequences-reduction*0.25); tol=max(0,tol-reduction*0.35)
            if urge<8 and impairment<5 and days_since>=90: status='resolved'; resolved+=1
        elif status=='dependent' and days_since>=90:
            # Spontaneous improvement is possible but slow; support accelerates it. No cultivation cure.
            urge=max(0,urge-(1.5+quiet*2)); impairment=max(0,impairment-1.0)
        elif status=='risk' and days_since>=120:
            urge=max(0,urge-4); tol=max(0,tol-2)
            if urge<5: status='resolved'; resolved+=1
        conn.execute("UPDATE dependency_profiles SET status=?,urge_load=?,tolerance_load=?,functional_impairment=?,consequence_load=?,last_review_day=?,next_review_day=? WHERE id=?",(status,urge,tol,impairment,consequences,day,day+30,int(d['id'])))
        _sync_dependency_pressure(conn,int(d['actor_id']),str(d['dependency_kind']))

    conds=conn.execute("SELECT * FROM psychological_conditions WHERE status IN ('active','recovering','chronic') AND next_review_day<=? ORDER BY id",(day,)).fetchall()
    for p in conds:
        psych_reviewed+=1; severity=float(p['severity']); impairment=float(p['functional_impairment']); status=str(p['status'])
        sr=conn.execute("SELECT COALESCE(SUM(helpfulness),0),COUNT(*) FROM psychological_support WHERE actor_id=? AND (condition_id=? OR condition_id IS NULL) AND day>=? AND day<=?",(int(p['actor_id']),int(p['id']),int(p['last_review_day']),day)).fetchone()
        helpful=float(sr[0] or 0); reduction=max(-8,min(12,helpful/35.0))
        if reduction>0: status='recovering'
        severity=max(0,min(100,severity-reduction)); impairment=max(0,min(100,impairment-reduction*0.7))
        if severity<10 and impairment<6: status='resolved'; resolved+=1
        elif severity>=65 and day-int(p['onset_day'])>=365: status='chronic'
        conn.execute("UPDATE psychological_conditions SET severity=?,functional_impairment=?,status=?,last_review_day=?,next_review_day=?,resolved_day=CASE WHEN ?='resolved' THEN ? ELSE resolved_day END WHERE id=?",(severity,impairment,status,day,day+30,status,day,int(p['id'])))
        _sync_psych_pressure(conn,int(p['actor_id']),str(p['condition_family']))
    return {'ingested_sources':ingested,'conditions_created':created,'dependency_reviews':dep_reviewed,'psych_reviews':psych_reviewed,'resolved':resolved}


def psychology_summary(conn: sqlite3.Connection) -> dict[str,int]:
    return {
        'dependency_profiles':int(conn.execute("SELECT COUNT(*) FROM dependency_profiles").fetchone()[0]),
        'active_dependencies':int(conn.execute("SELECT COUNT(*) FROM dependency_profiles WHERE status IN ('dependent','recovering')").fetchone()[0]),
        'dependency_exposures':int(conn.execute("SELECT COUNT(*) FROM dependency_exposures").fetchone()[0]),
        'psychological_stressors':int(conn.execute("SELECT COUNT(*) FROM psychological_stressors").fetchone()[0]),
        'active_psychological_conditions':int(conn.execute("SELECT COUNT(*) FROM psychological_conditions WHERE status IN ('active','recovering','chronic')").fetchone()[0]),
    }
