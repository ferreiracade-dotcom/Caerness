from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.adaptive_planning import create_role
from engine.organization_needs import (
    set_role_staffing_requirement,
    create_capability_requirement,
    refresh_organization_needs,
)
from engine.opportunity import (
    opportunity_decision_candidates,
    execute_opportunity_action,
    register_capability,
)
from engine.reputation import adjust as adjust_reputation
from engine.interactions import apply_player_response


def setup_world():
    reset_db(force=True, backup=False)
    init_db()
    c = connect()
    import_current_seed(c)
    activate_existing_loops(c)
    c.commit()
    return c


def add_actor(c, name, subtype, loc):
    day = int(c.execute("select current_day from world_state where id=1").fetchone()[0])
    aid = int(c.execute(
        "insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','ORGNEED-01 test',0)",
        (name, subtype, loc, loc),
    ).lastrowid)
    c.execute(
        "insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'ACTIVE',7,.3,.75,?,?,2)",
        (aid, day, day + 7),
    )
    return aid


def set_competence(c, actor, domain, score):
    day = int(c.execute("select current_day from world_state where id=1").fetchone()[0])
    did = int(c.execute("select id from competence_domains where domain_key=?", (domain,)).fetchone()[0])
    c.execute(
        "insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,?,'campaign',?) "
        "on conflict(actor_id,domain_id,specialty_key) do update set score=excluded.score,updated_day=excluded.updated_day",
        (actor, did, score, day),
    )


def candidate(cands, action_kind):
    return next(x for x in cands if x.action_kind == action_kind)


def main():
    c = setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0]) >= 89
        day = int(c.execute("select current_day from world_state where id=1").fetchone()[0])
        crownhold = int(c.execute("select id from locations where name='Crownhold'").fetchone()[0])
        crown_inst = int(c.execute("select institution_actor_id from political_polities where id=1").fetchone()[0])
        crown_actor = int(c.execute("select decision_actor_id from polity_government_actors where polity_id=1").fetchone()[0])

        # A role can exist without being a required vacancy. Spare/optional capacity creates no search motive.
        optional_role = create_role(
            c, crown_inst, 'optional_antiquarian', 'Optional Antiquarian', 'scholarship',
            role_kind='advisory_role', capacity_slots=1, source_kind='opening_structure', day=day,
        )
        state = refresh_organization_needs(c, crown_inst, day=day)
        assert state['active_autonomous_needs'] == 0
        assert not c.execute(
            "select 1 from organization_pressures where source_kind='institutional_role_staffing' and source_id=? and status='active'",
            (optional_role,),
        ).fetchone()

        # The same ontology becomes actionable only when the institution/domain explicitly says a slot is required.
        role_id = create_role(
            c, crown_inst, 'royal_foundry_master', 'Royal Foundry Master', 'craft',
            role_kind='technical_role', capacity_slots=1, source_kind='opening_structure', day=day,
        )
        set_role_staffing_requirement(
            c, role_id, minimum_filled_slots=1, autonomous_refill=True,
            minimum_candidate_quality=82, staffing_priority=88,
        )
        specialist = add_actor(c, 'ORGNEED Master Founder', 'master founder', crownhold)
        set_competence(c, specialist, 'craft', 94)
        adjust_reputation(c, 'actor', specialist, 'craft', 30, day=day)

        state = refresh_organization_needs(c, crown_inst, day=day)
        assert state['needs_created'] == 1 and state['active_autonomous_needs'] == 1
        pressure = c.execute(
            "select * from organization_pressures where source_kind='institutional_role_staffing' and source_id=? and status='active'",
            (role_id,),
        ).fetchone()
        assert pressure and 'opportunity_need' in pressure['metadata_json']

        # Ordinary DEC/OPPORTUNITY machinery now sees the need without a hand-seeded pressure.
        cands = opportunity_decision_candidates(c, crown_actor, 'STRATEGIC', day, {})
        start = candidate(cands, 'start_opportunity_search')
        opened = execute_opportunity_action(c, crown_actor, start.action_kind, start.payload, day)
        search_id = int(opened['search_id'])
        assert c.execute(
            "select 1 from opportunity_search_results where search_id=? and candidate_kind='actor' and candidate_id=?",
            (search_id, specialist),
        ).fetchone()

        cands = opportunity_decision_candidates(c, crown_actor, 'STRATEGIC', day, {})
        approach = candidate(cands, 'approach_opportunity_candidate')
        assert int(approach.payload['candidate_id']) == specialist
        proposed = execute_opportunity_action(c, crown_actor, approach.action_kind, approach.payload, day)
        assert proposed['adaptation_kind'] == 'reuse_role'
        assert int(proposed['role_id']) == role_id
        assert c.execute(
            "select count(*) from institutional_roles where institution_actor_id=? and role_key='royal_foundry_master'",
            (crown_inst,),
        ).fetchone()[0] == 1

        # Acceptance fills the real role; a subsequent need review resolves the causal pressure/search.
        c.execute(
            "insert or replace into player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) values (1,?,?,?,?)",
            (specialist, crownhold, 'ORGNEED acceptance', day),
        )
        apply_player_response(c, int(proposed['interaction_id']), specialist, 'accept', day + 1)
        assert c.execute(
            "select 1 from institutional_appointments where role_id=? and holder_actor_id=? and status='active'",
            (role_id, specialist),
        ).fetchone()
        resolved = refresh_organization_needs(c, crown_inst, day=day + 1)
        assert resolved['needs_resolved'] >= 1
        assert not c.execute(
            "select 1 from organization_pressures where source_kind='institutional_role_staffing' and source_id=? and status='active'",
            (role_id,),
        ).fetchone()
        assert c.execute("select status from opportunity_searches where id=?", (search_id,)).fetchone()[0] == 'fulfilled'

        # A separate explicit capability requirement may call for a provider. It is not inferred from lifecycle health.
        other_inst = int(c.execute(
            "select actor_id from institution_profiles where actor_id<>? order by actor_id limit 1", (crown_inst,)
        ).fetchone()[0])
        register_capability(
            c, 'institution', other_inst, 'medicine', 'field_medicine',
            quality=90, capacity=75, public_visibility=80, availability=85,
            source_kind='test_provider',
        )
        req_id = create_capability_requirement(
            c, crown_inst, 'field_medicine_reserve', 'field_medicine', 'medicine',
            minimum_capacity=60, minimum_readiness=55, search_kind='service_provider',
            role_key='field_medicine', min_quality=80, intensity=70, urgency=65,
            source_kind='standing_program', source_id=1,
            proposal={'title':'Field medicine reserve contract','service_kind':'field_medicine','duration_days':180},
            day=day + 1,
        )
        state = refresh_organization_needs(c, crown_inst, day=day + 1)
        cap_pressure = c.execute(
            "select * from organization_pressures where source_kind='organization_capability_requirement' and source_id=? and status='active'",
            (req_id,),
        ).fetchone()
        assert cap_pressure
        cands = opportunity_decision_candidates(c, crown_actor, 'STRATEGIC', day + 1, {})
        cap_start = next(x for x in cands if x.action_kind == 'start_opportunity_search' and int(x.payload['pressure_id']) == int(cap_pressure['id']))
        cap_search = execute_opportunity_action(c, crown_actor, cap_start.action_kind, cap_start.payload, day + 1)
        assert c.execute(
            "select 1 from opportunity_search_results where search_id=? and candidate_kind='institution' and candidate_id=?",
            (int(cap_search['search_id']), other_inst),
        ).fetchone()

        # Hiring/contracting does not magically increase capability. The pressure resolves only when the domain's
        # authoritative capability state actually meets the requirement.
        c.execute(
            "insert into organization_capabilities(institution_actor_id,capability_key,domain,capacity,readiness,basis_json,updated_day) "
            "values (?,?,?,?,?,'{}',?) on conflict(institution_actor_id,capability_key) do update set capacity=excluded.capacity,readiness=excluded.readiness,updated_day=excluded.updated_day",
            (crown_inst, 'field_medicine', 'medicine', 68, 62, day + 2),
        )
        resolved = refresh_organization_needs(c, crown_inst, day=day + 2)
        assert resolved['needs_resolved'] >= 1
        assert not c.execute(
            "select 1 from organization_pressures where source_kind='organization_capability_requirement' and source_id=? and status='active'",
            (req_id,),
        ).fetchone()

        # A bad lifecycle label alone is not enough to invent a profession-specific need.
        untouched_inst = int(c.execute(
            "select actor_id from institution_profiles where actor_id not in (?,?) order by actor_id limit 1",
            (crown_inst, other_inst),
        ).fetchone()[0])
        c.execute(
            "update organization_lifecycle_profiles set lifecycle_status='declining',vitality=30,cohesion=30 where institution_actor_id=?",
            (untouched_inst,),
        )
        untouched = refresh_organization_needs(c, untouched_inst, day=day + 2)
        assert untouched['active_autonomous_needs'] == 0
        assert not c.execute(
            "select 1 from organization_pressures where institution_actor_id=? and source_kind in ('institutional_role_staffing','organization_capability_requirement') and status='active'",
            (untouched_inst,),
        ).fetchone()

        assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('ORGNEED-01 autonomous evidence-bound need generation acceptance PASS')
    finally:
        c.close()


if __name__ == '__main__':
    main()
