from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Callable

from .health import add_condition, refresh_health_profile


def _day(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _alive(conn: sqlite3.Connection, actor_id: int) -> bool:
    row=conn.execute("""SELECT a.status,lp.life_status FROM actors a
                        LEFT JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.id=?""",(actor_id,)).fetchone()
    return bool(row and str(row[0]).lower() not in {'deceased','dead','destroyed','dissolved'} and (row[1] is None or str(row[1])=='living'))


def configure_groundbinding(conn: sqlite3.Connection, actor_id: int, bound_location_id: int, *,
                            binding_depth: float = 100.0, binding_status: str = 'bound',
                            metadata: dict[str,Any] | None = None) -> None:
    if not conn.execute("SELECT 1 FROM actors WHERE id=?",(actor_id,)).fetchone():
        raise ValueError('Unknown actor')
    if not conn.execute("SELECT 1 FROM locations WHERE id=?",(bound_location_id,)).fetchone():
        raise ValueError('Unknown bound location')
    if binding_status not in {'settling','bound','failed','ended'}:
        raise ValueError('Invalid Groundbinding status')
    day=_day(conn)
    current=conn.execute("SELECT current_location_id FROM actors WHERE id=?",(actor_id,)).fetchone()[0]
    inside=(current is not None and int(current)==int(bound_location_id))
    conn.execute(
        """INSERT INTO groundbinding_profiles(actor_id,bound_location_id,binding_status,dependency_state,binding_depth,
               mismatch_burden,last_inside_day,last_review_day,next_review_day,metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(actor_id) DO UPDATE SET bound_location_id=excluded.bound_location_id,
             binding_status=excluded.binding_status,binding_depth=excluded.binding_depth,
             metadata_json=excluded.metadata_json""",
        (actor_id,bound_location_id,binding_status,'comfortable',max(0,min(100,float(binding_depth))),0.0,
         day if inside else None,day,day+14,json.dumps(metadata or {},sort_keys=True)),
    )


def seed_current_groundbinding(conn: sqlite3.Connection) -> dict[str,int]:
    """Seed only people explicitly identified as Groundbound in MASTER FINAL."""
    silent=conn.execute("SELECT id FROM locations WHERE name='Silent Peak'").fetchone()
    if not silent:
        return {'groundbound_profiles_configured':0}
    count=0
    for name in ('Clement Bray','Rowena Fitch'):
        row=conn.execute("SELECT id FROM actors WHERE actor_type='character' AND name=?",(name,)).fetchone()
        if not row:
            continue
        configure_groundbinding(conn,int(row[0]),int(silent[0]),binding_depth=100,binding_status='bound',metadata={
            'authority':'WORLD_BIBLE_EXPLICIT',
            'basis':'MASTER FINAL identifies this Silent Peak Watcher as Groundbound',
            'permanent_binding':True,
            'not_a_stage_bonus':True,
        })
        count+=1
    conn.execute("INSERT OR REPLACE INTO engine_meta(key,value) VALUES ('groundbinding_activation_version','1')")
    return {'groundbound_profiles_configured':count}


def _profile_vector(conn: sqlite3.Connection, location_id: int | None) -> tuple[float,float,float,float] | None:
    if location_id is None:
        return None
    row=conn.execute("""SELECT current_density,current_stability,current_replenishment,current_concentration
                        FROM location_environment_profiles WHERE location_id=?""",(int(location_id),)).fetchone()
    if not row:
        return None
    return tuple(float(x) for x in row)


def _near_margin(conn: sqlite3.Connection, current_location_id: int | None, bound_location_id: int) -> bool:
    if current_location_id is None:
        return False
    if int(current_location_id)==int(bound_location_id):
        return True
    a=conn.execute("SELECT name,parent_location_id FROM locations WHERE id=?",(int(current_location_id),)).fetchone()
    b=conn.execute("SELECT name,parent_location_id FROM locations WHERE id=?",(int(bound_location_id),)).fetchone()
    if not a or not b:
        return False
    an=str(a['name']).lower(); bn=str(b['name']).lower()
    if bn in an or an in bn:
        return True
    if a['parent_location_id'] is not None and int(a['parent_location_id'])==int(bound_location_id):
        return True
    if b['parent_location_id'] is not None and int(b['parent_location_id'])==int(current_location_id):
        return True
    return False


def _mismatch_factor(conn: sqlite3.Connection, current_location_id: int | None, bound_location_id: int) -> float:
    if current_location_id is not None and int(current_location_id)==int(bound_location_id):
        return 0.0
    if _near_margin(conn,current_location_id,bound_location_id):
        return 0.35
    bv=_profile_vector(conn,bound_location_id); cv=_profile_vector(conn,current_location_id)
    if not bv or not cv:
        return 1.0
    distance=sum(abs(a-b) for a,b in zip(bv,cv))/(4.0*100.0)
    # Pattern specialization is place-specific: even superficially similar ground is not equivalent.
    return max(0.65,min(1.45,0.72+distance*1.15))


def _state_for_burden(burden: float) -> str:
    if burden < 20: return 'comfortable'
    if burden < 55: return 'straining'
    if burden < 90: return 'failing'
    return 'catastrophic'


def _strain_condition(conn: sqlite3.Connection, actor_id: int) -> sqlite3.Row | None:
    return conn.execute("""SELECT * FROM health_conditions WHERE actor_id=? AND label='Groundbinding mismatch'
                           AND status IN ('active','recovering','chronic') ORDER BY id DESC LIMIT 1""",(actor_id,)).fetchone()


def _sync_health(conn: sqlite3.Connection, actor_id: int, burden: float, state: str, *, catastrophic: bool=False) -> int | None:
    cond=_strain_condition(conn,actor_id)
    day=_day(conn)
    if state=='comfortable' and burden < 8:
        if cond:
            conn.execute("UPDATE health_conditions SET status='resolved',resolved_day=?,severity=0,capacity_impact=0,pain_impact=0 WHERE id=?",(day,int(cond['id'])))
            refresh_health_profile(conn,actor_id,day)
        return None
    severity=max(8.0,min(95.0,burden*(0.72 if state=='straining' else 0.92 if state=='failing' else 1.0)))
    capacity=max(5.0,min(90.0,burden*(0.48 if state=='straining' else 0.72 if state=='failing' else 0.90)))
    fatality=0.0 if state!='catastrophic' else min(60.0,18.0+(burden-90.0)*3.0)
    if cond:
        conn.execute("""UPDATE health_conditions SET severity=?,capacity_impact=?,pain_impact=?,fatality_pressure=?,
                      recovery_rate_per_30=?,progression_rate_per_30=?,specialist_requirement=?,status='active',last_review_day=?,next_review_day=? WHERE id=?""",
                     (severity,capacity,severity*0.35,fatality,0.0,0.0,'vein_mender' if state in {'failing','catastrophic'} else 'none',day,day+14,int(cond['id'])))
        refresh_health_profile(conn,actor_id,day)
        return int(cond['id'])
    cid=add_condition(conn,actor_id,'vein_core','Groundbinding mismatch',severity=severity,body_system='Vessel/Core',
                         capacity_impact=capacity,pain_impact=severity*0.35,recovery_rate_per_30=0.0,
                         progression_rate_per_30=0.0,fatality_pressure=fatality,
                         specialist_requirement='vein_mender' if state in {'failing','catastrophic'} else 'none',
                         next_review_days=14,metadata={'cause':'groundbinding_off_ground_mismatch','catastrophic':catastrophic})
    refresh_health_profile(conn,actor_id,day)
    return cid


def _history(conn: sqlite3.Connection, actor_id: int, day: int, before: str, after: str, b0: float, b1: float,
             location_id: int | None, summary: str, metadata: dict[str,Any] | None=None) -> None:
    conn.execute("""INSERT INTO groundbinding_history(actor_id,day,state_before,state_after,burden_before,burden_after,location_id,summary,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (actor_id,day,before,after,b0,b1,location_id,summary,json.dumps(metadata or {},sort_keys=True)))


def _review_one(conn: sqlite3.Connection, row: sqlite3.Row, day: int, event_logger: Callable[...,int] | None) -> tuple[int,int]:
    actor_id=int(row['actor_id'])
    if not _alive(conn,actor_id):
        conn.execute("UPDATE groundbinding_profiles SET binding_status='ended',last_review_day=?,next_review_day=? WHERE actor_id=?",(day,day+365,actor_id))
        return 1,0
    locrow=conn.execute("SELECT current_location_id FROM actors WHERE id=?",(actor_id,)).fetchone()
    current=int(locrow[0]) if locrow and locrow[0] is not None else None
    bound=int(row['bound_location_id']); delta=max(1,day-int(row['last_review_day']))
    before_state=str(row['dependency_state']); b0=float(row['mismatch_burden'])
    inside=current is not None and int(current)==bound
    changed=0
    if inside:
        # Return before catastrophic collapse can reverse straining/failing mismatch over time.
        recovery_per30=16.0 + float(row['binding_depth'])/100.0*4.0
        b1=max(0.0,b0-recovery_per30*delta/30.0)
        last_inside=day
    else:
        cp=conn.execute("SELECT training_effort,current_stage FROM cultivation_profiles WHERE actor_id=?",(actor_id,)).fetchone()
        effort=float(cp['training_effort'])/100.0 if cp else 0.5
        stage=str(cp['current_stage']) if cp and cp['current_stage'] is not None else None
        stage_pressure={'First':0.85,'Temper':0.90,'Third':1.0,'Breach':1.08,'Fifth':1.18,'Sixth':1.28}.get(stage,0.9)
        mismatch=_mismatch_factor(conn,current,bound)
        # Normal absence builds slowly; hard cultivation and high-stage output accelerate it.
        per30=(4.0 + 4.5*effort)*stage_pressure*mismatch*(0.65+0.35*float(row['binding_depth'])/100.0)
        b1=min(100.0,b0+per30*delta/30.0)
        last_inside=row['last_inside_day']
    after_state=_state_for_burden(b1)
    cat_condition=row['catastrophic_condition_id']
    if after_state=='catastrophic' and before_state!='catastrophic':
        cat_condition=_sync_health(conn,actor_id,b1,after_state,catastrophic=True)
        # Catastrophic mismatch is anatomical failure, not loss of earned Stage. Pause cultivation
        # and mark the Core damaged rather than erasing history or silently demoting Stage.
        conn.execute("UPDATE cultivation_profiles SET core_state='Damaged-Core',active=0,status='incapacitated',injury_constraint=100 WHERE actor_id=?",(actor_id,))
        changed=1
        if event_logger:
            name=conn.execute("SELECT name FROM actors WHERE id=?",(actor_id,)).fetchone()[0]
            event_logger(day=day,event_type='groundbinding_collapse',title=f'{name} suffers Groundbinding collapse',
                         summary=f'{name} remained outside bound ground until Vessel/Core mismatch became catastrophic.',
                         severity=5,source_actor_id=actor_id,target_actor_ids=(actor_id,),location_id=current,
                         visibility='limited',rumorability=0.45,reliability=0.9)
    else:
        _sync_health(conn,actor_id,b1,after_state)
        changed=1 if after_state!=before_state or abs(b1-b0)>=4.0 else 0
    conn.execute("""UPDATE groundbinding_profiles SET dependency_state=?,mismatch_burden=?,last_inside_day=?,last_review_day=?,
                  next_review_day=?,catastrophic_condition_id=? WHERE actor_id=?""",
                 (after_state,b1,last_inside,day,day+14,cat_condition,actor_id))
    if changed:
        _history(conn,actor_id,day,before_state,after_state,b0,b1,current,
                 'Groundbinding dependency changed with location, time away, exertion and ecological mismatch.',
                 {'inside_bound_ground':inside,'bound_location_id':bound})
    return 1,changed


def next_groundbinding_due_day(conn: sqlite3.Connection, after_day: int, end_day: int) -> int | None:
    row=conn.execute("""SELECT MIN(next_review_day) FROM groundbinding_profiles
                        WHERE binding_status IN ('settling','bound','failed') AND next_review_day>? AND next_review_day<=?""",
                     (after_day,end_day)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def process_due_groundbinding(conn: sqlite3.Connection, day: int, *, event_logger: Callable[...,int] | None=None) -> dict[str,int]:
    rows=conn.execute("""SELECT * FROM groundbinding_profiles WHERE binding_status IN ('settling','bound','failed')
                         AND next_review_day<=? ORDER BY next_review_day,actor_id""",(day,)).fetchall()
    reviewed=changed=0
    for row in rows:
        a,b=_review_one(conn,row,day,event_logger); reviewed+=a; changed+=b
    return {'groundbinding_reviews':reviewed,'groundbinding_changes':changed}


def groundbinding_context(conn: sqlite3.Connection, actor_id: int) -> dict[str,Any] | None:
    row=conn.execute("SELECT * FROM groundbinding_profiles WHERE actor_id=? AND binding_status IN ('settling','bound','failed')",(actor_id,)).fetchone()
    if not row:
        return None
    cur=conn.execute("SELECT current_location_id FROM actors WHERE id=?",(actor_id,)).fetchone()
    current=int(cur[0]) if cur and cur[0] is not None else None
    inside=current is not None and current==int(row['bound_location_id'])
    state=str(row['dependency_state']); burden=float(row['mismatch_burden'])
    if inside:
        return {'inside':True,'state':state,'burden':burden,'vessel_factor':1.10,'realization_factor':1.02,'opportunity_factor':1.02}
    penalties={'comfortable':0.94,'straining':0.82,'failing':0.58,'catastrophic':0.25}
    p=penalties[state]
    return {'inside':False,'state':state,'burden':burden,'vessel_factor':p,'realization_factor':max(0.35,p+0.08),'opportunity_factor':max(0.30,p+0.05)}


def groundbinding_summary(conn: sqlite3.Connection) -> dict[str,int]:
    q=lambda sql:int(conn.execute(sql).fetchone()[0])
    return {
        'profiles':q("SELECT COUNT(*) FROM groundbinding_profiles"),
        'groundbound':q("SELECT COUNT(*) FROM groundbinding_profiles WHERE binding_status='bound'"),
        'straining_or_worse':q("SELECT COUNT(*) FROM groundbinding_profiles WHERE dependency_state IN ('straining','failing','catastrophic')"),
        'catastrophic':q("SELECT COUNT(*) FROM groundbinding_profiles WHERE dependency_state='catastrophic'"),
    }
