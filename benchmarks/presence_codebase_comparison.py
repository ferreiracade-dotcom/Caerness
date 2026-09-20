"""PRESBACK-01 benchmark: Caerness scan presence vs Neighborly-style reverse location index.

Neighborly's low-resolution model keeps both a character's frequented locations and a
location's FrequentedBy reverse component.  This prototype asks whether adopting that
*access pattern* helps Caerness without replacing SQLite authority or PRES-01 semantics.
"""
from __future__ import annotations
import os, sys, tempfile, time, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.simulation import advance_connection
from engine.presence import actors_plausibly_present, _stable_fraction, _clamp, _location_is_large


def bootstrap():
    p=Path(tempfile.gettempdir())/'caerness_presback01.db'
    os.environ['CAERNESS_DB_PATH']=str(p); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    advance_connection(c,180); c.commit(); return c


def indexed_present(conn, location_id:int, *, day:int, purpose:str='ordinary_contact') -> list[int]:
    location_id=int(location_id);day=int(day)
    # Neighborly-style reverse lookup: start from actors with a reason to frequent THIS
    # location, not every active character in the world. Exact travel is another reason.
    rows=conn.execute('''
        SELECT DISTINCT a.id,a.status,a.home_location_id,a.current_location_id
        FROM actors a
        LEFT JOIN actor_presence_profiles p ON p.actor_id=a.id
        LEFT JOIN actor_presence_habits h ON h.actor_id=a.id AND h.location_id=?
             AND h.effective_from_day<=? AND (h.effective_to_day IS NULL OR h.effective_to_day>=?)
        LEFT JOIN travel_plans tp ON tp.subject_kind='actor' AND tp.subject_id=a.id
             AND tp.status IN ('active','stalled')
        WHERE a.actor_type='character' AND a.status='active'
          AND (h.id IS NOT NULL OR p.base_location_id=? OR a.current_location_id=? OR tp.current_location_id=?)
        ORDER BY a.id
    ''',(location_id,day,day,location_id,location_id,location_id)).fetchall()
    if not rows:return []
    ids=[int(r['id']) for r in rows]; marks=','.join('?' for _ in ids)
    # Latest active travel row per candidate, matching production semantics.
    travel={}
    for r in conn.execute(f'''SELECT * FROM travel_plans WHERE subject_kind='actor' AND status IN ('active','stalled')
                              AND subject_id IN ({marks}) ORDER BY subject_id,id DESC''',ids).fetchall():
        aid=int(r['subject_id'])
        if aid not in travel: travel[aid]=r
    profiles={int(r['actor_id']):r for r in conn.execute(f'SELECT * FROM actor_presence_profiles WHERE actor_id IN ({marks})',ids).fetchall()}
    habits={}
    for r in conn.execute('''SELECT * FROM actor_presence_habits WHERE location_id=? AND effective_from_day<=?
                             AND (effective_to_day IS NULL OR effective_to_day>=?) ORDER BY actor_id,weight DESC,id''',(location_id,day,day)).fetchall():
        habits.setdefault(int(r['actor_id']),[]).append(r)
    large=_location_is_large(conn,location_id);out=[]
    for a in rows:
        aid=int(a['id']);tr=travel.get(aid)
        if tr is not None:
            if tr['current_route_id'] is not None and tr['segment_due_day'] is not None and day<int(tr['segment_due_day']):
                continue
            if int(tr['current_location_id'])==location_id:out.append(aid)
            continue
        hs=habits.get(aid,());miss=1.0;has=False
        for h in hs:
            w=_clamp(float(h['weight'])*(0.55+0.45*float(h['confidence'])))
            if str(h['habit_kind'])=='legacy_anchor' and large:w=min(w,0.12)
            miss*=1.0-w;has=True
        prob=1.0-miss
        prof=profiles.get(aid)
        if not has and prof is not None and prof['base_location_id'] is not None and int(prof['base_location_id'])==location_id:
            prob=0.22 if large else 0.52;has=True
        if not has and a['current_location_id'] is not None and int(a['current_location_id'])==location_id:
            prob=0.10 if large else 0.28
        prob=round(_clamp(prob),4)
        if prob>0 and (prob>=1 or _stable_fraction('presence',aid,location_id,day,purpose)<=prob):out.append(aid)
    return out


def run():
    c=bootstrap()
    pairs=[tuple(r) for r in c.execute('''SELECT DISTINCT to_location_id,due_day FROM rumour_transmissions
                                          WHERE due_day<=180 ORDER BY due_day,to_location_id''').fetchall()]
    # Include all locations on several quiet days so parity is not only a rumour-path test.
    locs=[int(r[0]) for r in c.execute("SELECT id FROM locations WHERE kind NOT IN ('continent') ORDER BY id").fetchall()]
    for d in (1,30,90,180): pairs.extend((lid,d) for lid in locs)
    # de-dupe while preserving deterministic order
    pairs=list(dict.fromkeys((int(a),int(b)) for a,b in pairs))

    mismatches=[]
    t=time.perf_counter();base=[]
    for loc,day in pairs: base.append(actors_plausibly_present(c,loc,day=day,purpose='rumour'))
    base_s=time.perf_counter()-t
    t=time.perf_counter();cand=[]
    for loc,day in pairs: cand.append(indexed_present(c,loc,day=day,purpose='rumour'))
    indexed_s=time.perf_counter()-t
    for i,(a,b) in enumerate(zip(base,cand)):
        if a!=b:mismatches.append({'location_id':pairs[i][0],'day':pairs[i][1],'scan':a,'indexed':b})
    result={'calls':len(pairs),'scan_seconds':base_s,'indexed_seconds':indexed_s,'speedup':base_s/indexed_s if indexed_s else None,
            'mismatches':len(mismatches),'first_mismatches':mismatches[:5],
            'active_characters':int(c.execute("SELECT COUNT(*) FROM actors WHERE actor_type='character' AND status='active'").fetchone()[0]),
            'presence_profiles':int(c.execute('SELECT COUNT(*) FROM actor_presence_profiles').fetchone()[0]),
            'presence_habits':int(c.execute('SELECT COUNT(*) FROM actor_presence_habits').fetchone()[0])}
    print(json.dumps(result,indent=2));c.close();return result

if __name__=='__main__':run()
