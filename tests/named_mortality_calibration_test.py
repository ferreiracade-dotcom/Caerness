"""Named natural mortality: no immortality windows, world-demography rates, canon longevity anchors.

World Bible: "Cultivation extends the prime before it extends old age"; bodies age and fail "even at
the summit"; the biological rules of the Vein are common to humanity.  Longevity anchors are the
engine's tonal curves (LONGEVITY_MIDPOINT / DECLINE_START), not guaranteed death dates.
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect
from engine.health import natural_annual_hazard, LONGEVITY_MIDPOINT, configure_health_profile
from engine.household_life import set_life_profile
from engine.simulation import advance_connection

CLASSES=list(LONGEVITY_MIDPOINT)


def median_death_age(lc):
    s,a=1.0,18
    while s>.5 and a<400: s*=1-natural_annual_hazard(a,lc); a+=1
    return a


def run():
    # 1. No adult is ever immortal, and risk never falls with age.
    for lc in CLASSES:
        prev=0.0
        for age in range(18,200):
            h=natural_annual_hazard(age,lc)
            assert 0<h<=0.6,(lc,age,h)
            assert h>=prev-1e-12,(lc,age,h,prev)
            prev=h

    # 2. Ordinary people die at the world's own demographic rates (background tracked-person bands:
    #    15-49 0.18%, 50-64 0.9%, 65-74 3%, 75+ 8.5%), so promotion to the named layer changes nothing.
    assert .001<=natural_annual_hazard(30,'ordinary')<=.005
    assert .02<=natural_annual_hazard(70,'ordinary')<=.05
    assert .05<=natural_annual_hazard(80,'ordinary')<=.12

    # 3. Higher stages never carry more natural risk at the same age ("cultivation preserves health").
    for age in range(18,160):
        hs=[natural_annual_hazard(age,lc) for lc in CLASSES]
        assert all(a>=b-1e-12 for a,b in zip(hs,hs[1:])),(age,hs)

    # 4. Median lifespans sit on the tonal anchors (within 3%); the prime is extended more than old age.
    for lc in CLASSES:
        med=median_death_age(lc)
        assert abs(med-LONGEVITY_MIDPOINT[lc])<=.03*LONGEVITY_MIDPOINT[lc],(lc,med)

    # 4b. The World Bible's Sixth census (all ~40 living Sixths: median age 88, oldest 118, "very old")
    #     must be a plausible steady state: Sixths entering around 58 +/- 12 and dying by this curve.
    import math
    w=[0.0]*221
    for entry in range(25,95):
        pe=math.exp(-.5*((entry-58)/12)**2); s=1.0
        for age in range(entry,221):
            w[age]+=pe*s; s*=1-natural_annual_hazard(age,'sixth')
    total=sum(w); cum=0.0; median=oldest=None
    for age,x in enumerate(w):
        cum+=x/total
        if median is None and cum>=.5: median=age
        if oldest is None and cum>=1-1/40: oldest=age
    assert 80<=median<=95 and 110<=oldest<=128,(median,oldest)

    # 5. Integration: ordinary 75-year-olds actually die through the production health scheduler.
    path=Path(tempfile.gettempdir())/f'caerness_named_mortality_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db()
    c=connect()
    c.execute("INSERT INTO locations(name,kind) VALUES ('Mortality Calibration Hamlet','village')")
    loc=int(c.execute("SELECT id FROM locations WHERE name='Mortality Calibration Hamlet'").fetchone()[0])
    ids=[]
    for i in range(40):
        aid=int(c.execute("INSERT INTO actors(name,actor_type,status,current_location_id,home_location_id) VALUES (?,'character','active',?,?)",(f'[NMC] Elder {i}',loc,loc)).lastrowid)
        set_life_profile(c,aid,birth_day=-(75*365),family_formation_eligible=False)
        configure_health_profile(c,aid,longevity_class='ordinary',baseline_health=75)
        ids.append(aid)
    c.commit()
    advance_connection(c,3*365); c.commit()
    dead=c.execute(f"SELECT COUNT(*) FROM actors WHERE status='deceased' AND id IN ({','.join('?'*len(ids))})",ids).fetchone()[0]
    # Expected ~6 of 40 over three years at 75-78; bounds are wide but exclude "nobody dies".
    assert 1<=dead<=20,dead
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('Named mortality calibration: PASS',{lc:median_death_age(lc) for lc in CLASSES},'elder deaths',dead)

if __name__=='__main__': run()
