from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.simulation import seed_demo, advance_connection
from engine.civilian import create_household, add_household_member
from engine.household_life import (
    set_life_profile, create_union, end_union, update_family_plan, register_birth,
    create_guardianship, end_guardianship, split_household, add_service_term,
    schedule_household_migration, set_demographic_cohort, mark_actor_deceased,
    add_kinship,
)


def fresh():
    reset_db(); init_db(); seed_demo(); init_db()


def actor(conn, name, loc, age=30, eligible=True):
    cur = conn.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,is_demo) VALUES (?,'character','civilian',?,?, 'active',0)", (name,loc,loc))
    aid=int(cur.lastrowid)
    set_life_profile(conn, aid, birth_day=-(age*365), current_household_id=None, family_formation_eligible=eligible)
    return aid


def expect_value_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError(f"expected ValueError from {fn.__name__}")


def run():
    fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {'0.19.1','0.20.0','0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
        cairn=int(conn.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0])
        toll=int(conn.execute("SELECT id FROM locations WHERE name=\"Toll's Reach\"").fetchone()[0])
        way=int(conn.execute("SELECT id FROM locations WHERE name='Windmere'").fetchone()[0])

        # Birth edge cases: exact due day, explicit birth-parent requirement, no retroactive manual birth.
        a=actor(conn,'[EDGE19] A',cairn,30,True); b=actor(conn,'[EDGE19] B',cairn,31,True)
        hh=create_household(conn,'[EDGE19] Birth HH',head_actor_id=a,location_id=cairn)
        add_household_member(conn,hh,b,role='partner',authority=80,dependency=0)
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id IN (?,?)",(hh,a,b))
        u=create_union(conn,a,b,household_id=hh)
        update_family_plan(conn,u,desired_children=1,auto_children=True,birth_parent_actor_id=a,earliest_next_child_day=17,spacing_days=500)
        conn.commit()
        advance_connection(conn,16); conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM life_events WHERE event_kind='birth'").fetchone()[0] == 0
        advance_connection(conn,1); conn.commit()
        born=conn.execute("SELECT actor_id,day FROM life_events WHERE event_kind='birth' ORDER BY id DESC LIMIT 1").fetchone()
        assert born and int(born['day']) == 17
        expect_value_error(register_birth,conn,u,child_name='[EDGE19] Retro',day=16)

        # Half-sibling links are real kinship, not only full-sibling links.
        end_union(conn,u)
        c=actor(conn,'[EDGE19] C',cairn,29,True)
        u2=create_union(conn,a,c,household_id=hh)
        child2=register_birth(conn,u2,child_name='[EDGE19] Half Child')
        child1=int(born['actor_id'])
        sib=conn.execute("SELECT 1 FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind='sibling' AND legal_status='recognized'",(child2,child1)).fetchone()
        assert sib
        # Re-adding the same recognized kinship is idempotent.
        k1,_=add_kinship(conn,a,child1,'parent',reciprocal_kind='child')
        k2,_=add_kinship(conn,a,child1,'parent',reciprocal_kind='child')
        assert k1==k2

        # Guardianship: moving a ward closes stale residence/dependency; duplicate create is idempotent; explicit ending closes links.
        g=actor(conn,'[EDGE19] Guardian',cairn,40,False); w=actor(conn,'[EDGE19] Ward',cairn,10,False)
        old=create_household(conn,'[EDGE19] Old Ward HH',head_actor_id=w,location_id=cairn)
        add_household_member(conn,old,w,role='ward',authority=0,dependency=90)
        conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?",(old,w))
        conn.execute("INSERT INTO household_dependencies(household_id,dependent_actor_id,sponsor_actor_id,dependency_kind,support_level,status,started_day) VALUES (?,?,?,?,?,'active',?)",(old,w,w,'ward',80,17))
        gh=create_household(conn,'[EDGE19] Guardian HH',head_actor_id=g,location_id=cairn)
        gid=create_guardianship(conn,g,w,household_id=gh)
        gid2=create_guardianship(conn,g,w,household_id=gh)
        assert gid==gid2
        assert conn.execute("SELECT status FROM household_members WHERE household_id=? AND actor_id=?",(old,w)).fetchone()[0]=='former'
        assert conn.execute("SELECT status FROM household_dependencies WHERE household_id=? AND dependent_actor_id=? ORDER BY id LIMIT 1",(old,w)).fetchone()[0]=='ended'
        end_guardianship(conn,gid,reason='edge test')
        assert conn.execute("SELECT status FROM guardianships WHERE id=?",(gid,)).fetchone()[0]=='ended'
        assert conn.execute("SELECT COUNT(*) FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind='guardian' AND legal_status='recognized'",(g,w)).fetchone()[0]==0

        # Household split validates membership, moves attached ward/service/dependency records, and repairs the old head.
        hhead=actor(conn,'[EDGE19] Split Head',cairn,45,False)
        stay=actor(conn,'[EDGE19] Stay',cairn,35,False)
        mover=actor(conn,'[EDGE19] Mover',cairn,22,False)
        serv=actor(conn,'[EDGE19] Service Mover',cairn,25,False)
        outsider=actor(conn,'[EDGE19] Outsider',cairn,25,False)
        sh=create_household(conn,'[EDGE19] Split Source',head_actor_id=hhead,location_id=cairn,wealth=1000,liquidity=500)
        for x,role,auth in [(stay,'partner',70),(mover,'child',20),(serv,'servant',10)]:
            add_household_member(conn,sh,x,role=role,authority=auth,dependency=10)
            conn.execute("UPDATE actor_life_profiles SET current_household_id=? WHERE actor_id=?",(sh,x))
        sid=add_service_term(conn,sh,serv,'servant',review_in_days=999)
        conn.execute("INSERT INTO household_dependencies(household_id,dependent_actor_id,sponsor_actor_id,dependency_kind,support_level,status,started_day) VALUES (?,?,?,?,?,'active',?)",(sh,mover,hhead,'client',50,17))
        expect_value_error(split_household,conn,sh,'[EDGE19] Bad Split',[outsider],new_head_actor_id=outsider)
        nh=split_household(conn,sh,'[EDGE19] New Split',[hhead,mover,serv],new_head_actor_id=hhead,wealth_share=.25,liquidity_share=.2)
        assert int(conn.execute("SELECT household_id FROM household_service_terms WHERE id=?",(sid,)).fetchone()[0])==nh
        assert int(conn.execute("SELECT household_id FROM household_dependencies WHERE dependent_actor_id=? AND status='active'",(mover,)).fetchone()[0])==nh
        assert int(conn.execute("SELECT head_actor_id FROM households WHERE id=?",(sh,)).fetchone()[0])==stay
        expect_value_error(split_household,conn,sh,'[EDGE19] Share Error',[stay],new_head_actor_id=stay,wealth_share=1.2)

        # Service term does not overwrite an existing family role, and duplicate active term is idempotent.
        family=actor(conn,'[EDGE19] Family Steward',cairn,33,False)
        add_household_member(conn,sh,family,role='cousin',authority=25,dependency=0)
        st1=add_service_term(conn,sh,family,'steward',review_in_days=30)
        st2=add_service_term(conn,sh,family,'steward',review_in_days=30)
        assert st1==st2
        assert conn.execute("SELECT role FROM household_members WHERE household_id=? AND actor_id=?",(sh,family)).fetchone()[0]=='cousin'

        # Migration scheduling supersedes stale plans and rejects past/same-place moves.
        p1=schedule_household_migration(conn,sh,toll,40,reason='first')
        p2=schedule_household_migration(conn,sh,way,50,reason='replacement')
        assert conn.execute("SELECT status FROM household_migration_plans WHERE id=?",(p1,)).fetchone()[0]=='cancelled'
        assert conn.execute("SELECT status FROM household_migration_plans WHERE id=?",(p2,)).fetchone()[0]=='planned'
        expect_value_error(schedule_household_migration,conn,sh,toll,10)
        expect_value_error(schedule_household_migration,conn,sh,cairn,60)

        # Death cleans up active service/guardianship/dependency state rather than leaving zombie records.
        dg=actor(conn,'[EDGE19] Dying Guardian',cairn,50,False); dw=actor(conn,'[EDGE19] Dying Ward',cairn,12,False)
        dh=create_household(conn,'[EDGE19] Death HH',head_actor_id=dg,location_id=cairn)
        dgid=create_guardianship(conn,dg,dw,household_id=dh)
        ds=add_service_term(conn,dh,dg,'steward',review_in_days=100)
        mark_actor_deceased(conn,dg,reason='edge cleanup')
        assert conn.execute("SELECT status FROM guardianships WHERE id=?",(dgid,)).fetchone()[0]=='ended'
        assert conn.execute("SELECT status FROM household_service_terms WHERE id=?",(ds,)).fetchone()[0]=='former'
        dep=conn.execute("SELECT sponsor_actor_id,status FROM household_dependencies WHERE dependent_actor_id=? ORDER BY id DESC LIMIT 1",(dw,)).fetchone()
        assert dep and dep['sponsor_actor_id'] is None and dep['status']=='active'

        # Aggregate cohorts age forward without double-aging; total population is conserved apart from explicit birth/migration pressure.
        set_demographic_cohort(conn,cairn,'edge_demo','0_4',1000,annual_birth_pressure=100,annual_migration_rate=0)
        conn.commit()
        current=int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        target=current+365
        advance_connection(conn,365); conn.commit()
        rows=conn.execute("SELECT age_band,population FROM demographic_cohorts WHERE location_id=? AND cohort_key='edge_demo'",(cairn,)).fetchall()
        vals={str(r['age_band']):float(r['population']) for r in rows}
        assert '5_12' in vals and vals['5_12'] > 0
        total=sum(vals.values())
        if ENGINE_VERSION in {'0.20.0','0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}:
            assert 1000.0 < total < 1100.0, vals  # v0.20 adds explicit age-band mortality
        else:
            assert abs(total - 1100.0) < 0.01, vals
        assert 0 < vals['5_12'] < 1100  # no same-tick cascade into later bands

    print('v19_edge_test: PASS')

if __name__=='__main__':
    run()
