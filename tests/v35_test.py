from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.tournaments import activate_tournament_substrate,process_due_tournaments
from engine.domain_actions import domain_action_options,execute_domain_action,apply_accepted_interaction_domain_action


def add_fighter(c,name,loc,stage='Temper',age=24):
    cur=c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES (?,'character',?,?,'active')",(name,loc,loc)); aid=int(cur.lastrowid)
    c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day) VALUES (?,?,'adult',1,'living',0)",(aid,-age*365))
    c.execute("INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,training_effort,resource_access,teacher_support,injury_constraint,last_review_day,next_review_day,status) VALUES (?,'Open-Core',?,1,58,55,60,55,40,0,0,30,'active')",(aid,stage))
    return aid


def run():
    assert ENGINE_VERSION in {'0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=35
    reset_db();init_db()
    with connect() as c:
        c.execute("INSERT INTO locations(name,kind,is_canon) VALUES ('Cairnholt','city',1)"); loc=int(c.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0])
        fighters=[add_fighter(c,f'Fighter {i}',loc,'Temper' if i<3 else 'Third',22+i) for i in range(6)]
        assert activate_tournament_substrate(c)['tournament_series']==1
        # Registration occurs causally at the scheduled review, without claiming the named registry is the whole field.
        c.execute('UPDATE world_state SET current_day=180 WHERE id=1'); r=process_due_tournaments(c,180)
        assert r['events_created']==1 and r['entries_registered']>0,r
        event=c.execute("SELECT * FROM tournament_events").fetchone(); assert event and event['status']=='registration'
        assert c.execute("SELECT COUNT(*) FROM tournament_fields WHERE event_id=? AND simulation_mode='structural'",(event['id'],)).fetchone()[0]>=1
        assert all(__import__('json').loads(x[0]).get('full_field_contains_latent_unnamed_competitors') for x in c.execute("SELECT metadata_json FROM tournament_events"))
        # Start and resolve named tracked bracket; duel resolver owns each actual named-v-named bout.
        for day in range(int(event['start_day']),int(event['end_day'])+40):
            c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,)); process_due_tournaments(c,day)
            if c.execute("SELECT status FROM tournament_events WHERE id=?",(event['id'],)).fetchone()[0]=='resolved':break
        assert c.execute("SELECT status FROM tournament_events WHERE id=?",(event['id'],)).fetchone()[0]=='resolved'
        assert c.execute("SELECT COUNT(*) FROM tournament_bouts WHERE event_id=? AND status='resolved'",(event['id'],)).fetchone()[0]>=1
        assert c.execute("SELECT COUNT(*) FROM combat_engagements WHERE engagement_kind='duel' AND json_extract(metadata_json,'$.tournament_event_id')=?",(event['id'],)).fetchone()[0]>=1
        # A field may correctly end with no named champion because latent competitors are part of the real field.
        for f in c.execute("SELECT metadata_json FROM tournament_fields WHERE event_id=? AND simulation_mode='individual'",(event['id'],)):
            meta=__import__('json').loads(f[0]); assert meta.get('champion_resolution') in {'named','latent_field'}

        # Social challenge initiation requires pre-existing local tension and acceptance; no universal compelled-duel rule.
        a,b=fighters[0],fighters[1]
        c.execute("INSERT INTO relationships(actor_a_id,actor_b_id,stance,trust,obligation,updated_day) VALUES (?,?,?,?,?,?)",(a,b,-50,-20,0,0))
        c.execute('UPDATE world_state SET current_day=400 WHERE id=1')
        opts=domain_action_options(c,a,'ACTIVE',400)
        ch=[o for o in opts if o.kind=='propose_martial_challenge']; assert ch
        ex=execute_domain_action(c,a,ch[0],400); iid=int(ex['interaction_id'])
        inter=c.execute("SELECT * FROM interactions WHERE id=?",(iid,)).fetchone()
        applied=apply_accepted_interaction_domain_action(c,inter,400); assert applied and applied['challenge_id']
        challenge=c.execute("SELECT * FROM martial_challenges WHERE id=?",(applied['challenge_id'],)).fetchone(); assert challenge['lethal']==0 and challenge['status']=='active'
        for day in range(401,430):
            c.execute('UPDATE world_state SET current_day=? WHERE id=1',(day,));process_due_tournaments(c,day)
            if c.execute("SELECT status FROM martial_challenges WHERE id=?",(challenge['id'],)).fetchone()[0]=='resolved':break
        assert c.execute("SELECT status FROM martial_challenges WHERE id=?",(challenge['id'],)).fetchone()[0]=='resolved'
        # Coverage is honest: combat runnable; tournament partial because company/prize layers remain separate.
        from engine.coverage import snapshot_coverage
        cov={x['domain_key']:x for x in snapshot_coverage(c,None,phase='v35-test')}
        assert cov['16_combat']['mechanism_status']=='RUNNABLE'
        assert cov['17_tournament']['mechanism_status']=='PARTIAL'
        c.commit()
    print('v0.35.0 autonomous combat/tournament regression PASS')

if __name__=='__main__':run()
