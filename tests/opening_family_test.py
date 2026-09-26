"""OPENING-01: canon unknowns (marriage, children, relationships) are resolved once at the opening,
never over canon, and single named adults can later marry into the unnamed population at the same rates.
"""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.opening_family import (draw_family_history, first_marriage_curve, first_marriage_hazard,
                                   resolve_opening_history, resolve_unnamed_marriages)
from engine.domain_actions import _union_option
from engine.relationships import ensure_reciprocal_relationship, adjust_relationship_pair
from engine.health import natural_annual_hazard, childhood_circumstance, FIRST_YEAR_MORTALITY
from engine.background_population import _mortality_probability
from engine.household_life import mark_actor_deceased
from engine.civilian_life import _resolve_succession_triggers
from engine.succession import _lineage_kin_bonus
import numpy as np


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_opening_family_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect()
    import_current_seed(c); activate_existing_loops(c); c.commit()
    return c,path


def meta(c,name):
    r=c.execute("SELECT a.id,lp.metadata_json FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.name=?",(name,)).fetchone()
    return int(r[0]),json.loads(r[1] or '{}')


def run():
    # 1. The pure draw is deterministic, and groups differ as canon suggests.
    h=draw_family_history('k',age=50,sex='female',longevity_class='third')
    assert h==draw_family_history('k',age=50,sex='female',longevity_class='third')
    def ever(curve,n=3000):
        return sum(draw_family_history(f'e{i}',age=60,sex='male',longevity_class='ordinary',curve=curve)['status']!='never_married' for i in range(n))/n
    base=first_marriage_curve('male','ordinary'); senior=first_marriage_curve('male','fifth')
    assert ever(base)>ever(senior)>ever((senior[0]+4,senior[1],senior[2]*.8))  # ordinary > senior > senior on the Road
    assert .85<=ever(base)<=.97
    # Nobody marries before 16, and hazards stay probabilities.
    assert first_marriage_hazard(14,base)==0 and all(0<=first_marriage_hazard(a,senior)<=1 for a in range(16,90))

    # Childhood follows the world's premodern demography in every model; ~30% die before fifteen on average.
    assert natural_annual_hazard(0.5,'ordinary')==FIRST_YEAR_MORTALITY
    assert abs(float(_mortality_probability(np.array([180.0]))[0])*12-FIRST_YEAR_MORTALITY)<1e-12
    surv=1.0
    for y in range(15): surv*=1-natural_annual_hazard(y,'ordinary')
    assert .62<=surv<=.76,surv

    c,path=bootstrap()
    # Circumstances shift a family's childhood risk around the average: lineage houses lower, remote country higher.
    def member_of(kind):
        return int(c.execute("""SELECT im.member_actor_id FROM institution_memberships im JOIN institution_profiles ip ON ip.actor_id=im.institution_actor_id
                                WHERE ip.institution_kind=? AND im.status='active' ORDER BY im.member_actor_id LIMIT 1""",(kind,)).fetchone()[0])
    remote=int(c.execute("SELECT id FROM locations WHERE kind IN ('area','region','mountain range') ORDER BY id LIMIT 1").fetchone()[0])
    lineage,_=childhood_circumstance(c,parent_ids=[member_of('clan/house')],location_id=None)
    plain,_=childhood_circumstance(c,parent_ids=[],location_id=None)
    far,tags=childhood_circumstance(c,parent_ids=[],location_id=remote)
    assert lineage<plain==1.0<far and 'remote_care_distance' in tags
    # Means, not labels: a house family far from care is still better placed than an ordinary one, and
    # remoteness costs a wealthy family less than a poor one.
    house=member_of('clan/house')
    rich_far,_=childhood_circumstance(c,parent_ids=[house],location_id=remote)
    rich_near,_=childhood_circumstance(c,parent_ids=[house],location_id=None)
    assert rich_far<far and (rich_far/rich_near)<(far/plain)
    # 2. Every named adult is resolved; canon's own family facts are kept, not redrawn.
    unresolved=c.execute("""SELECT COUNT(*) FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
        WHERE a.actor_type='character' AND a.status='active' AND lp.birth_day<=-18*365
          AND json_extract(lp.metadata_json,'$.marital_status') IS NULL""").fetchone()[0]
    assert unresolved==0,unresolved
    assert meta(c,'Emperor Osric Varen')[1]['marital_status_basis']=='canon_record'
    assert meta(c,'Niall Redcairn')[1]['marital_status_basis']=='canon_partial'   # canon child, no spouse named
    assert meta(c,'Lewis Grant')[1]['marital_status_basis']=='canon_partial'      # canon grandchild
    counts={r[0]:r[1] for r in c.execute("""SELECT json_extract(metadata_json,'$.marital_status'),COUNT(*) FROM actor_life_profiles
        WHERE json_extract(metadata_json,'$.marital_status_basis')='opening_draw' GROUP BY 1""")}
    assert counts.get('married',0)>counts.get('never_married',0)>0 and counts.get('widowed',0)>0,counts

    # 3. A married person's spouse is a persistent, low-attention person sharing an old union and household.
    married=c.execute("""SELECT lp.actor_id,json_extract(lp.metadata_json,'$.spouse_actor_id') FROM actor_life_profiles lp
        JOIN source_identity_map m ON m.entity_kind='actor' AND m.entity_id=lp.actor_id
        WHERE json_extract(lp.metadata_json,'$.marital_status')='married' AND json_extract(lp.metadata_json,'$.marital_status_basis')='opening_draw'
        ORDER BY lp.actor_id LIMIT 1""").fetchone()
    aid,spouse=int(married[0]),int(married[1])
    u=c.execute("SELECT started_day,household_id FROM household_unions WHERE status='active' AND ((actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?))",
                (aid,spouse,spouse,aid)).fetchone()
    assert u and int(u[0])<0 and u[1] is not None
    assert c.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?",(spouse,)).fetchone()[0]=='DORMANT'
    assert c.execute("SELECT started_day FROM relationships WHERE actor_a_id=? AND actor_b_id=?",(aid,spouse)).fetchone()[0]<0

    # 4. Canon ties become backdated relationships: a disciple has long known and respected their teacher.
    t=c.execute("""SELECT r.respect,r.started_day FROM relationships r JOIN actors s ON s.id=r.actor_a_id JOIN actors m ON m.id=r.actor_b_id
                   WHERE s.name='Alistair Hardy' AND m.name='Matthias Kerr'""").fetchone()
    assert t and t[0]>=50 and t[1]<0
    assert c.execute("SELECT COUNT(*) FROM relationships WHERE started_day<0").fetchone()[0]>1000

    # 4b. Heirs.  A widowed head with no named family: the household passes to a revealed adult child.
    row=c.execute("""SELECT lp.actor_id,g.id FROM actor_life_profiles lp JOIN households h ON h.head_actor_id=lp.actor_id
        JOIN latent_entities g ON g.latent_kind='kin_group' AND json_extract(g.constraints_json,'$.parent_actor_id')=lp.actor_id
        WHERE json_extract(lp.metadata_json,'$.marital_status')='widowed' AND h.status='active'
          AND EXISTS(SELECT 1 FROM json_each(json_extract(g.constraints_json,'$.birth_days')) b WHERE b.value<=-25*365)
        ORDER BY lp.actor_id LIMIT 1""").fetchone()
    if row is None:  # no widowed head in this seed: use a married one whose spouse dies first
        row=c.execute("""SELECT lp.actor_id,g.id FROM actor_life_profiles lp JOIN households h ON h.head_actor_id=lp.actor_id
            JOIN latent_entities g ON g.latent_kind='kin_group' AND json_extract(g.constraints_json,'$.parent_actor_id')=lp.actor_id
            WHERE h.status='active' AND EXISTS(SELECT 1 FROM json_each(json_extract(g.constraints_json,'$.birth_days')) b WHERE b.value<=-25*365)
            ORDER BY lp.actor_id LIMIT 1""").fetchone()
        sp=json.loads(c.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?",(row[0],)).fetchone()[0]).get('spouse_actor_id')
        if sp: mark_actor_deceased(c,int(sp),reason='test: spouse died first')
    head=int(row[0]); hid=int(c.execute("SELECT id FROM households WHERE head_actor_id=?",(head,)).fetchone()[0])
    mark_actor_deceased(c,head,reason='test: head died')
    _resolve_succession_triggers(c,0)
    new=c.execute("SELECT head_actor_id,status FROM households WHERE id=?",(hid,)).fetchone()
    assert new[0] is not None and new[1]=='active',tuple(new)
    assert c.execute("SELECT 1 FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind='parent'",(head,int(new[0]))).fetchone()
    assert c.execute("SELECT resolution_kind FROM succession_events WHERE household_id=? ORDER BY id DESC",(hid,)).fetchone()[0]=='claim_strength'

    # 4c. A lineage house's former head: their eldest adult child is revealed as a blood member and gains kin standing.
    lin=c.execute("""SELECT im.institution_actor_id,im.member_actor_id FROM institution_memberships im
        JOIN institution_profiles ip ON ip.actor_id=im.institution_actor_id
        JOIN latent_entities g ON g.latent_kind='kin_group' AND g.status='latent' AND json_extract(g.constraints_json,'$.parent_actor_id')=im.member_actor_id
        WHERE ip.institution_kind='clan/house' AND im.status='active'
          AND EXISTS(SELECT 1 FROM json_each(json_extract(g.constraints_json,'$.birth_days')) b WHERE b.value<=-25*365)
        ORDER BY im.member_actor_id LIMIT 1""").fetchone()
    if lin:
        bonus=_lineage_kin_bonus(c,int(lin[0]),int(lin[1]))
        kid=[k for k,v in bonus.items() if v==20.0]
        assert kid and c.execute("SELECT 1 FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=? AND status='active'",(int(lin[0]),kid[0])).fetchone()
        assert _lineage_kin_bonus(c,int(lin[0]),int(lin[1]))==bonus  # revealed once, not again

    # 4d. Every revealed person (background, underworld, latent, spouse) holding a Stage is calibrated inside
    #     it like canon people, not given a generic entry-level profile.
    generic=c.execute("""SELECT COUNT(*) FROM cultivation_profiles WHERE core_state='Open-Core' AND current_stage IS NOT NULL
        AND json_extract(metadata_json,'$.opening_factor_basis') IS NULL AND json_extract(metadata_json,'$.authority') IS NULL""").fetchone()[0]
    assert generic==0,generic
    assert c.execute("""SELECT COUNT(DISTINCT realization_aptitude) FROM cultivation_profiles
        WHERE json_extract(metadata_json,'$.source')='PERSONECO01' AND core_state='Open-Core'""").fetchone()[0]>1

    # 5. Resolution runs exactly once.
    assert resolve_opening_history(c)=={}

    # 6. The acquaintance clock is the relationship's start, not its last change (was reset by every update).
    loc=int(c.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()[0])
    from engine.household_life import set_life_profile
    def adult(name,sex):
        x=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",(name,loc)).lastrowid)
        set_life_profile(c,x,birth_day=-28*365,demographic_sex=sex,family_formation_eligible=True); return x
    a,b=adult('[OF] Ada','female'),adult('[OF] Bram','male')
    ensure_reciprocal_relationship(c,a,b,-2000,started_day=-2000,trust=40,stance=30)
    adjust_relationship_pair(c,a,b,0,symmetric={'trust_delta':1})  # a recent change must not reset the clock
    assert _union_option(c,a,0) is not None

    # 7. Run-time marriage into the unnamed population happens at the world's rates.
    singles=[adult(f'[OF] Single {i}','female' if i%2 else 'male') for i in range(40)]
    for x in singles:
        c.execute("UPDATE actor_life_profiles SET birth_day=-24*365,metadata_json=json_patch(metadata_json,?) WHERE actor_id=?",
                  (json.dumps({'marital_status':'never_married','marital_status_basis':'opening_draw'}),x))
    for d in range(30,3*365+1,30):
        c.execute("UPDATE world_state SET current_day=? WHERE id=1",(d,)); resolve_unnamed_marriages(c,d)
    wed=c.execute(f"""SELECT COUNT(*) FROM household_unions WHERE status='active' AND (actor_a_id IN ({','.join('?'*len(singles))})
                      OR actor_b_id IN ({','.join('?'*len(singles))}))""",singles+singles).fetchone()[0]
    assert 8<=wed<=36,wed   # ~half of 24-27 year-old never-married ordinary people marry within three years
    # Draws happen only on the 30-day grid, so an extra household-life pass on another day changes nothing.
    assert resolve_unnamed_marriages(c,3*365+7)==0
    # A revealed couple's next child is spaced from their own history, not all due at once.
    due=[json.loads(r[0])['earliest_next_child_day'] for r in c.execute(
        "SELECT family_plan_json FROM household_unions WHERE json_extract(family_plan_json,'$.mode')='OPENING_RESOLUTION_FAMILY_CONTINUITY' AND json_extract(family_plan_json,'$.auto_children')=1")]
    assert due and sum(d<=365 for d in due)/len(due)<.5,(len(due),sum(d<=365 for d in due))
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('OPENING-01 family/relationships: PASS',counts,'run-time marriages',wed)

if __name__=='__main__': run()
