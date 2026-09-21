from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.simulation import seed_demo, advance_connection
from engine.civilian import create_household, add_household_member, civilian_summary
from engine.household_life import (
    set_life_profile, create_union, update_family_plan, register_birth, create_guardianship,
    split_household, add_service_term, schedule_household_migration, set_demographic_cohort,
    household_life_summary, mark_actor_deceased,
)


def _fresh():
    reset_db(); init_db(); seed_demo(); init_db()


def _actor(conn, name, loc, subtype='civilian'):
    cur = conn.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,is_demo) VALUES (?,'character',?,?,?,?,0)",
                       (name, subtype, loc, loc, 'active'))
    return int(cur.lastrowid)


def run():
    _fresh()
    with connect() as conn:
        assert ENGINE_VERSION in {'0.19.1','0.20.0','0.20.1','0.21.0','0.22.0','0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
        cairn = int(conn.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0])
        toll = int(conn.execute("SELECT id FROM locations WHERE name=\"Toll's Reach\"").fetchone()[0])

        a = _actor(conn, '[DEMO19] Mara Vale', cairn)
        b = _actor(conn, '[DEMO19] Oren Vale', cairn)
        servant = _actor(conn, '[DEMO19] Jessa Reed', cairn)
        ward = _actor(conn, '[DEMO19] Toma Reed', cairn)
        youth = _actor(conn, '[DEMO19] Eren Young', cairn)
        unrelated = _actor(conn, '[DEMO19] Unrelated', cairn)

        hh = create_household(conn, '[DEMO19] Vale Household', head_actor_id=a, location_id=cairn, wealth=1000, liquidity=200, cohesion=75)
        add_household_member(conn, hh, b, role='partner', authority=80, dependency=0)
        set_life_profile(conn, a, birth_day=-30*365, demographic_sex='female', current_household_id=hh, family_formation_eligible=True)
        set_life_profile(conn, b, birth_day=-31*365, demographic_sex='male', current_household_id=hh, family_formation_eligible=True)
        set_life_profile(conn, servant, birth_day=-25*365, current_household_id=hh)
        set_life_profile(conn, ward, birth_day=-8*365, current_household_id=hh)
        set_life_profile(conn, youth, birth_day=-(18*365)+15, current_household_id=hh)
        add_household_member(conn, hh, youth, role='child', authority=5, dependency=40)
        set_life_profile(conn, unrelated, birth_day=-24*365)

        # Major commitments are explicit: the engine does not manufacture a union merely because profiles coexist.
        assert conn.execute('SELECT COUNT(*) FROM household_unions').fetchone()[0] == 0
        uid = create_union(conn, a, b, household_id=hh, union_kind='marriage')
        update_family_plan(conn, uid, desired_children=1, auto_children=True, birth_parent_actor_id=a,
                           earliest_next_child_day=30, spacing_days=730)
        create_guardianship(conn, a, ward, household_id=hh)
        add_service_term(conn, hh, servant, 'servant', review_in_days=60, loyalty=10, satisfaction=10, renewal_bias=10)
        schedule_household_migration(conn, hh, toll, 60, reason='new commercial appointment')
        set_demographic_cohort(conn, cairn, 'urban_common', '0_4', 1000, annual_birth_pressure=10, annual_migration_rate=.01)
        conn.commit()

        advance_connection(conn, 30)
        conn.commit()
        # Established family plan produces the next generation through authoritative story time.
        children = conn.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent'", (a,)).fetchall()
        generated = [int(r[0]) for r in children if int(r[0]) != ward]
        assert len(generated) == 1
        child = generated[0]
        prof = conn.execute('SELECT * FROM actor_life_profiles WHERE actor_id=?', (child,)).fetchone()
        assert prof and prof['life_stage'] == 'infant' and int(prof['current_household_id']) == hh
        # Youth crossed adulthood without a manually scripted event.
        assert conn.execute('SELECT life_stage FROM actor_life_profiles WHERE actor_id=?', (youth,)).fetchone()[0] == 'adult'
        assert conn.execute("SELECT COUNT(*) FROM life_events WHERE event_kind='coming_of_age' AND actor_id=?", (youth,)).fetchone()[0] == 1

        advance_connection(conn, 30)
        conn.commit()
        # Household migration moves the active household and its actual members.
        assert int(conn.execute('SELECT location_id FROM households WHERE id=?', (hh,)).fetchone()[0]) == toll
        assert int(conn.execute('SELECT current_location_id FROM actors WHERE id=?', (child,)).fetchone()[0]) == toll
        # Weak service relationship can end at its persisted review rather than remaining forever.
        assert conn.execute('SELECT status FROM household_service_terms WHERE actor_id=?', (servant,)).fetchone()[0] == 'former'

        # Household splitting carries people and bounded wealth rather than cloning the original household.
        new_hh = split_household(conn, hh, '[DEMO19] Young Vale Household', [youth], new_head_actor_id=youth,
                                 wealth_share=.1, liquidity_share=.1)
        assert int(conn.execute('SELECT current_household_id FROM actor_life_profiles WHERE actor_id=?', (youth,)).fetchone()[0]) == new_hh
        assert conn.execute('SELECT status FROM household_members WHERE household_id=? AND actor_id=?', (hh, youth)).fetchone()[0] == 'former'

        # Death is an explicit lifecycle transition available to health/combat/politics; v0.19 does not invent ordinary mortality.
        mark_actor_deceased(conn, b, reason='test lifecycle transition')
        assert conn.execute('SELECT life_status FROM actor_life_profiles WHERE actor_id=?', (b,)).fetchone()[0] == 'deceased'
        assert conn.execute('SELECT status FROM household_unions WHERE id=?', (uid,)).fetchone()[0] == 'widowed'

        advance_connection(conn, 305)  # total day 365
        conn.commit()
        cohort = conn.execute("SELECT SUM(population) FROM demographic_cohorts WHERE location_id=? AND cohort_key='urban_common'", (cairn,)).fetchone()
        assert cohort and float(cohort[0]) > 1000

        hs = household_life_summary(conn)
        assert hs['life_events'] >= 6 and hs['aggregate_population'] > 1000
        cs = civilian_summary(conn)
        assert cs['household_life']['active_guardianships'] == 1

    print('v19_test: PASS')


if __name__ == '__main__':
    run()
