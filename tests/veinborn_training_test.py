"""Veinborn, staging and training uptake follow World Bible anchors, for canon and revealed people alike.

Canon: ~4.79M Open-Core ("Veinborn": 35% of the Hearth, ~8% outside) and ~2.05M staged cultivators;
"many Open-Core people never become staged cultivators"; serious martial society is "roughly 70-75% male"
from unequal training investment, "not a hard female Stage ceiling"; Open Core is "primarily hereditary".
"""
from __future__ import annotations
import collections, json, math, os, statistics, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.cultivation import (_realization_aptitude, _vessel_aptitude, staged_probability, inherited_open_core_probability,
                                resolve_cultivation_uptake, VEINBORN_SHARE)
from engine.person_ecology import _profile_stage
from engine.household_life import set_life_profile, create_union, register_birth


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_veinborn_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect()
    import_current_seed(c); activate_existing_loops(c); c.commit()
    return c,path


def run():
    # 1. Background identities reproduce canon's Veinborn and staged shares, about two-thirds male among the staged.
    for hearth,veinborn,staged in ((True,.35,.60),(False,.08,.37)):
        n=40000; opens=stg=male_stg=0
        for uid in range(n):
            sex='male' if uid%2 else 'female'
            o,st=_profile_stage(7,uid,hearth,sex)
            opens+=o; stg+=1 if st else 0; male_stg+=1 if st and sex=='male' else 0
        assert abs(opens/n-veinborn)<.02,(hearth,opens/n)
        assert abs(stg/opens-staged)<.04,(hearth,stg/opens)
        assert .60<=male_stg/stg<=.72,(hearth,male_stg/stg)
    # Staged share across the continent lands near canon's 2.05M of 4.79M (~43%).
    hearth_pop,outer_pop=3.5,48.5
    staged_total=hearth_pop*VEINBORN_SHARE[True]*.60+outer_pop*VEINBORN_SHARE[False]*.37
    assert 1.9<=staged_total<=2.2,staged_total
    # Heredity: martial families reliably produce Veinborn; spontaneous Open Cores are uncommon.
    assert inherited_open_core_probability(2,True)>inherited_open_core_probability(1,True)>inherited_open_core_probability(0,True)>inherited_open_core_probability(0,False)

    c,path=bootstrap()
    # 2. Aptitude is bell-shaped human variation (it was uniform): most near 1.0, rare tails both ways.
    ra=[_realization_aptitude(c,i) for i in range(1,6001)]
    va=[_vessel_aptitude(c,i) for i in range(1,6001)]
    assert .97<=statistics.median(ra)<=1.03 and .15<=statistics.pstdev(ra)<=.28
    assert sum(.85<=x<=1.15 for x in ra)/len(ra)>.45          # the middle is crowded, not flat
    assert sum(x>=1.6 for x in ra)>0 and sum(x<=.65 for x in ra)>0
    assert sum(x<.95 for x in va)/len(va)>.45 and min(va)<.55 and max(va)>2.0   # below-average Vessels are common too

    # 3. Revealed spouses are Veinborn far more often than they are practising martial artists, and female
    #    spouses of cultivators are staged less often than male ones.
    rows=c.execute("""SELECT lp.demographic_sex,cp.core_state,cp.current_stage,cp.active FROM latent_entities l
        JOIN actor_life_profiles lp ON lp.actor_id=l.crystallized_entity_id JOIN cultivation_profiles cp ON cp.actor_id=l.crystallized_entity_id
        WHERE l.archetype='spouse'""").fetchall()
    veinborn=[r for r in rows if r[1]=='Open-Core']
    staged=[r for r in veinborn if r[2]]
    assert len(staged)<len(veinborn) and sum(1 for r in veinborn if r[3])<len(veinborn)
    by_sex={s:[r for r in veinborn if r[0]==s] for s in ('female','male')}
    if by_sex['female'] and by_sex['male']:
        f=sum(1 for r in by_sex['female'] if r[2])/len(by_sex['female']); m=sum(1 for r in by_sex['male'] if r[2])/len(by_sex['male'])
        assert f<m,(f,m)

    # 4. Anyone Veinborn and not training may take it up: the young and the connected far more often.
    loc=int(c.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0])
    inst=int(c.execute("SELECT actor_id FROM institution_profiles WHERE institution_kind='sect' ORDER BY actor_id LIMIT 1").fetchone()[0])
    def veinborn_person(name,age,member):
        aid=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES (?,'character',?,?,'active')",(name,loc,loc)).lastrowid)
        set_life_profile(c,aid,birth_day=-age*365,demographic_sex='male' if aid%2 else 'female',family_formation_eligible=True)
        c.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,training_effort,
                     resource_access,teacher_support,injury_constraint,realization_aptitude,vessel_aptitude,next_realization_check_day,status,metadata_json)
                     VALUES (?,'Open-Core',NULL,0,20,10,0,40,0,0,1.0,1.0,365,'paused','{}')""",(aid,))
        if member:
            c.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,status,joined_day) VALUES (?,?,'member','active',0)",(inst,aid))
        return aid
    young=[veinborn_person(f'[VB] Young {i}',16,True) for i in range(60)]
    older=[veinborn_person(f'[VB] Older {i}',45,False) for i in range(60)]
    assert resolve_cultivation_uptake(c,45)==0          # only on the 30-day grid
    for d in range(30,5*365+1,30):
        c.execute("UPDATE world_state SET current_day=? WHERE id=1",(d,)); resolve_cultivation_uptake(c,d)
    active=lambda ids: c.execute(f"SELECT COUNT(*) FROM cultivation_profiles WHERE active=1 AND actor_id IN ({','.join('?'*len(ids))})",ids).fetchone()[0]
    ay,ao=active(young),active(older)
    assert ay>=25 and ao<=8 and ay>3*max(1,ao),(ay,ao)

    # 5. A newborn's Core is hereditary, and a Veinborn baby is unstaged.
    def adult(name,sex):
        aid=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",(name,loc)).lastrowid)
        set_life_profile(c,aid,birth_day=-28*365,demographic_sex=sex,family_formation_eligible=True)
        c.execute("""INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,status,metadata_json) VALUES (?,'Open-Core','Third',1,'active','{}')""",(aid,))
        return aid
    kids=collections.Counter()
    for i in range(30):
        u=create_union(c,adult(f'[VB] Mother {i}','female'),adult(f'[VB] Father {i}','male'),create_new_household_name=f'[VB] Household {i}')
        kid=register_birth(c,u)
        row=c.execute("SELECT core_state,current_stage FROM cultivation_profiles WHERE actor_id=?",(kid,)).fetchone()
        assert row and row[1] is None
        kids[row[0]]+=1
    assert kids['Open-Core']>=18,kids   # two Open-Core parents: ~80%

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('Veinborn / staging / training uptake: PASS',{'young_started':ay,'older_started':ao,'newborn_cores':dict(kids)})

if __name__=='__main__': run()
