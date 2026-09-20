from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.reputation import adjust as adjust_reputation
from engine.seeking import publish_personal_instruction, process_due_seeking
from engine.education import enroll
from engine.simulation import advance_connection


def add_actor(c,name,loc):
    aid=int(c.execute("insert into actors(name,actor_type,subtype,home_location_id,current_location_id,status,notes,is_demo) values (?,'character','SEEK reputation test',?,?, 'active','',0)",(name,loc,loc)).lastrowid)
    c.execute("insert into simulation_profiles(actor_id,tier,cadence_days,volatility,agency,last_review_day,next_review_day,wake_threshold) values (?,'STRATEGIC',30,.2,.5,0,30,2)",(aid,))
    return aid


def main():
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    try:
        loc=int(c.execute("select id from locations where name='Cairnholt'").fetchone()[0])
        master=add_actor(c,'SEEK Reputable Master',loc); student=add_actor(c,'SEEK Successful Student',loc)
        did=int(c.execute("select id from competence_domains where domain_key='martial_instruction'").fetchone()[0])
        c.execute("insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,94,'campaign',0)",(master,did))
        c.execute("insert into actor_competence(actor_id,domain_id,score,source_kind,updated_day) values (?,?,10,'campaign',0)",(student,did))
        adjust_reputation(c,'actor',master,'martial_instruction',30,day=0,metadata={'seed_test':True}) # baseline 50 -> 80
        offering=publish_personal_instruction(c,master,'martial_instruction',duration_days=1,capacity=2,completion_gain=10)
        row=c.execute("select public_reputation,visibility,metadata_json from seekable_offerings where id=?",(offering,)).fetchone()
        assert 79.9 <= float(row['public_reputation']) <= 80.1, row['public_reputation']
        program=int(c.execute("select json_extract(metadata_json,'$.program_id') from seekable_offerings where id=?",(offering,)).fetchone()[0])
        enroll(c,student,program,primary_teacher_actor_id=master,practice_quality=1.0)
        before=float(c.execute("select value from social_reputation where subject_kind='actor' and subject_id=? and domain='martial_instruction'",(master,)).fetchone()[0])
        advance_connection(c,31)
        after=float(c.execute("select value from social_reputation where subject_kind='actor' and subject_id=? and domain='martial_instruction'",(master,)).fetchone()[0])
        assert after>before,(before,after)
        process_due_seeking(c,31)
        projected=float(c.execute("select public_reputation from seekable_offerings where id=?",(offering,)).fetchone()[0])
        assert abs(projected-after)<1e-6,(projected,after)
        assert c.execute("select status from education_enrollments where actor_id=? and program_id=?",(student,program)).fetchone()[0]=='completed'
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        print('SEEK-01 reputation feedback acceptance PASS',{'before':before,'after':after,'offering_rep':projected})
    finally: c.close()

if __name__=='__main__': main()
