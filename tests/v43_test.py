from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.household_life import process_due_household_life,create_union
from engine.education import process_due_education,education_summary
from engine.domain_actions import domain_action_options


def run():
    assert ENGINE_VERSION in {'0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=43
    reset_db();init_db()
    with connect() as c:
        import_current_seed(c);activate_existing_loops(c)
        opening_structural=int(c.execute("SELECT COUNT(*) FROM structural_training_cohorts WHERE status='active'").fetchone()[0])
        assert opening_structural==90
        # Let ordinary life and institutional cohorts advance for a decade without NPC decision execution.
        for day in range(30,3651,30):
            c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,))
            process_due_household_life(c,day);process_due_education(c,day)
        assert c.execute("SELECT COUNT(*) FROM actor_life_profiles WHERE family_formation_eligible=1 AND life_status='living'").fetchone()[0]>100
        assert c.execute("SELECT COUNT(*) FROM social_contact_links").fetchone()[0]>50
        # Shared context creates familiarity, never an automatic union.
        assert c.execute("SELECT COUNT(*) FROM household_unions WHERE started_day>0").fetchone()[0]==0
        eligible_proposals=0
        for r in c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active'").fetchall():
            if any(x.kind=='propose_union' for x in domain_action_options(c,int(r[0]),'TRACKED',3650)):
                eligible_proposals+=1
        assert eligible_proposals>10,eligible_proposals
        es=education_summary(c)
        assert es['active_enrollments']==0  # named opening cohort can graduate
        assert es['active_structural_cohorts']==opening_structural and es['structural_active_trainees']>100,es
        assert c.execute("SELECT COUNT(*) FROM structural_training_cohorts WHERE status='completed'").fetchone()[0]>0
        # Birth continuity: FAMILY-02 needs a resolved female/male pair; the newborn's sex is a seeded roll.
        loc=int(c.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()[0])
        def fixture(name,age,sex):
            aid=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",(name,loc)).lastrowid)
            c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,demographic_sex,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,?,?,'adult',1,'living',3650,'{}')",(aid,3650-age*365,sex))
            return aid
        a,b=fixture('Generational Fixture A',30,'female'),fixture('Generational Fixture B',31,'male')
        uid=create_union(c,a,b,create_new_household_name='Generational Fixture Household')
        plan={'auto_children':True,'desired_children':1,'earliest_next_child_day':3650,'spacing_days':730,'birth_parent_unresolved':True,'authority':'TEST'}
        c.execute('UPDATE household_unions SET family_plan_json=? WHERE id=?',(json.dumps(plan),uid))
        c.execute('UPDATE world_state SET current_day=3650 WHERE id=1')
        out=process_due_household_life(c,3650)
        assert out['births']==1,out
        child=c.execute("SELECT a.id,lp.demographic_sex FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.name LIKE '[Latent child] Generational Fixture Household%' ESCAPE '\\'").fetchone()
        if not child:
            child=c.execute("SELECT a.id,lp.demographic_sex FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.subtype='child' ORDER BY a.id DESC LIMIT 1").fetchone()
        assert child and str(child[1]) in {'female','male'}
        assert c.execute("SELECT COUNT(*) FROM kinship_links WHERE actor_b_id=? AND kin_kind='parent'",(int(child[0]),)).fetchone()[0]==2
        c.commit()
    print('v0.43.0 generational continuity / structural training regression PASS')
if __name__=='__main__':run()
