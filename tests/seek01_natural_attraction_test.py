from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.seeking import publish_personal_instruction, ensure_martial_instruction_intents, process_seek_intent
from engine.simulation import advance_connection


def setup_world():
    reset_db(force=True, backup=False)
    init_db()
    c = connect()
    import_current_seed(c)
    activate_existing_loops(c)
    c.commit()
    return c


def add_actor(c, name: str, subtype: str, loc: int, tier: str = 'ACTIVE') -> int:
    day = int(c.execute('select current_day from world_state where id=1').fetchone()[0])
    aid = int(c.execute(
        "insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character',?,?,?,'active','SEEK natural attraction test',0)",
        (name, subtype, loc, loc),
    ).lastrowid)
    c.execute(
        "insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,?,7,.3,.75,?,?,2)",
        (aid, tier, day, day + 7),
    )
    return aid


def main():
    c = setup_world()
    try:
        peak = int(c.execute("select id from locations where name='Silent Peak outer approach'").fetchone()[0])
        master = add_actor(c, 'SEEK Natural Hermit', 'secluded martial master', peak)
        did = int(c.execute("select id from competence_domains where domain_key='martial_instruction'").fetchone()[0])
        c.execute("insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,96,'campaign',0)", (master, did))
        c.execute("insert or replace into player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) values (1,?,?,?,0)", (master, peak, 'SEEK natural hermit'))
        offering = publish_personal_instruction(
            c, master, 'martial_instruction', subject_key='martial_instruction', reputation=94, visibility=88,
            access_mode='visit', capacity=3, duration_days=240, completion_gain=10,
        )

        created = ensure_martial_instruction_intents(c, 0)
        assert created > 0, 'no practitioner independently formed a need for instruction'
        intents = c.execute(
            "select id from actor_seek_intents where domain_key='martial_instruction' and status='searching' order by id"
        ).fetchall()
        assert intents

        started = 0
        blocked_unknown = 0
        for r in intents:
            res = process_seek_intent(c, int(r[0]), 0)
            if res['action'] == 'started_travel':
                started += 1
            elif res['action'] == 'blocked_unknown_location':
                blocked_unknown += 1
        assert 1 <= started <= 3, (created, started, blocked_unknown)
        active_load = float(c.execute(
            "select coalesce(sum(quantity),0) from actor_seek_intents where selected_offering_id=? and status in ('traveling','approaching')",
            (offering,),
        ).fetchone()[0])
        assert active_load <= 3.0 + 1e-9, active_load

        advance_connection(c, 20)
        incoming = int(c.execute(
            "select count(*) from interactions where recipient_actor_id=? and status='pending' and terms_json like '%seek_intent_id%'",
            (master,),
        ).fetchone()[0])
        assert 1 <= incoming <= 3, incoming
        # The engine can create the demand, discovery and journey, but it cannot answer for the player.
        assert int(c.execute(
            "select count(*) from interactions where recipient_actor_id=? and status='accepted' and terms_json like '%seek_intent_id%'",
            (master,),
        ).fetchone()[0]) == 0

        assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('SEEK-01 natural attraction/capacity acceptance PASS', {'created_needs': created, 'started_travel': started, 'pending_player_requests': incoming})
    finally:
        c.close()


if __name__ == '__main__':
    main()
