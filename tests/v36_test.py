from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.spectacle import activate_spectacle_substrate,process_due_spectacle,_public_rating
from engine.coverage import snapshot_coverage


def _actor(c,name,loc,stage='First'):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id,status) VALUES (?,'character',?,?,'active')",(name,loc,loc)).lastrowid)
    c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day) VALUES (?,-9000,'adult',1,'living',0)",(aid,))
    c.execute("INSERT INTO cultivation_profiles(actor_id,core_state,current_stage,active,vessel_adaptation,realization_integration,training_effort,resource_access,teacher_support,injury_constraint,last_review_day,next_review_day,status) VALUES (?,'Open-Core',?,1,50,50,50,50,50,0,0,30,'active')",(aid,stage))
    return aid


def run():
    assert ENGINE_VERSION in {'0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=36
    reset_db();init_db()
    with connect() as c:
        locs={}
        for name in ['Cairnholt','Toll’s Reach','Waymeet','Aldergate']:
            locs[name]=int(c.execute("INSERT INTO locations(name,kind,is_canon) VALUES (?,'city',1)",(name,)).lastrowid)
        red=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES ('Red Board','institution','active')").lastrowid)
        c.execute("INSERT INTO institution_profiles(actor_id,institution_kind) VALUES (?,'gambling/fight syndicate')",(red,))
        before_actors=int(c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])
        r1=activate_spectacle_substrate(c); r2=activate_spectacle_substrate(c)
        assert r1['spectacle_books']==5 and r1['prizefight_markets']==3,r1
        assert r1['spectacle_books_created']==5 and r2['spectacle_books_created']==0,(r1,r2)
        assert r1['prizefight_markets_created']==3 and r2['prizefight_markets_created']==0,(r1,r2)
        assert int(c.execute("SELECT COUNT(*) FROM latent_entities WHERE latent_kind='prizefighter_pool'").fetchone()[0])==3
        assert int(c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])==before_actors
        assert int(c.execute("SELECT COUNT(*) FROM prizefight_markets WHERE coercion_profile<>'voluntary' OR legality='criminal'").fetchone()[0])==0

        # Published odds are public-belief state, not a leak of hidden/current cultivation capability.
        a=_actor(c,'Public Equal A',locs['Cairnholt'],'First'); b=_actor(c,'Public Equal B',locs['Cairnholt'],'Fifth')
        ra=_public_rating(c,a); rb=_public_rating(c,b)
        assert ra==rb==50.0,(ra,rb)
        c.execute("UPDATE cultivation_profiles SET current_stage='Sixth',vessel_adaptation=95,realization_integration=95 WHERE actor_id=?",(a,))
        c.execute("UPDATE cultivation_profiles SET current_stage='First',vessel_adaptation=10,realization_integration=10 WHERE actor_id=?",(b,))
        assert _public_rating(c,a)==ra and _public_rating(c,b)==rb

        # First structural card: schedule, keep fighters latent, then resolve and settle aggregate books.
        c.execute("UPDATE world_state SET current_day=14 WHERE id=1")
        before_resources=int(c.execute("SELECT COUNT(*) FROM resources").fetchone()[0])
        q=process_due_spectacle(c,14)
        assert q['cards_scheduled']>=1 and q['betting_markets_opened']>=1,q
        card=c.execute("SELECT * FROM prizefight_cards WHERE status='scheduled' ORDER BY id LIMIT 1").fetchone(); assert card
        assert int(c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])==before_actors+2
        book_cash={int(r['id']):float(r['cash']) for r in c.execute("SELECT id,cash FROM civilian_enterprises WHERE json_extract(metadata_json,'$.resolution')='AGGREGATE_BOOKMAKING_FOOTPRINT'")}
        c.execute("UPDATE world_state SET current_day=? WHERE id=1",(int(card['scheduled_day']),))
        rr=process_due_spectacle(c,int(card['scheduled_day']))
        assert rr['cards_resolved']>=1 and rr['prizefight_bouts_resolved']>=3 and rr['betting_markets_settled']>=1,rr
        assert int(c.execute("SELECT COUNT(*) FROM betting_markets WHERE status='settled'").fetchone()[0])>=1
        assert int(c.execute("SELECT COUNT(*) FROM resources").fetchone()[0])==before_resources, 'aggregate betting must not debit invented named bettors'
        assert any(float(c.execute("SELECT cash FROM civilian_enterprises WHERE id=?",(eid,)).fetchone()[0])!=cash for eid,cash in book_cash.items())
        assert int(c.execute("SELECT COUNT(*) FROM prizefight_bouts WHERE json_extract(metadata_json,'$.structural_fighters')=1").fetchone()[0])>=3

        # Durable success promotes only to a one-person latent identity, never a named actor.
        m=c.execute("SELECT * FROM prizefight_markets WHERE market_key='toll-prize-halls'").fetchone(); assert m
        c.execute("UPDATE prizefight_markets SET champion_streak=3,champion_profile_json=? ,next_card_day=40 WHERE id=?",(json.dumps({'streak':3,'public_form':72}),m['id']))
        c.execute("UPDATE world_state SET current_day=40 WHERE id=1"); process_due_spectacle(c,40)
        promote_card=c.execute("SELECT * FROM prizefight_cards WHERE market_id=? AND status='scheduled' ORDER BY id DESC LIMIT 1",(m['id'],)).fetchone(); assert promote_card
        meta=json.loads(promote_card['metadata_json']); meta.update({'incumbent_champion_present':True,'main_event_public_form_a':80,'main_event_public_form_b':45,'main_event_true_form_a':95,'main_event_true_form_b':10})
        c.execute("UPDATE prizefight_cards SET metadata_json=? WHERE id=?",(json.dumps(meta,sort_keys=True),promote_card['id']))
        c.execute("UPDATE world_state SET current_day=? WHERE id=1",(int(promote_card['scheduled_day']),)); pr=process_due_spectacle(c,int(promote_card['scheduled_day']))
        assert pr['latent_champions_promoted']>=1,pr
        latent=c.execute("SELECT * FROM latent_entities WHERE archetype='closed_core_prizefighter_champion' ORDER BY id DESC LIMIT 1").fetchone(); assert latent and int(latent['count_estimate'])==1 and latent['status']=='latent'
        assert int(c.execute("SELECT COUNT(*) FROM actors").fetchone()[0])==before_actors+2, 'promotion must stop at latent resolution'

        cov={x['domain_key']:x for x in snapshot_coverage(c,None,phase='v36-test')}
        assert cov['35_gambling']['mechanism_status']=='RUNNABLE' and cov['35_gambling']['populated_count']>=1
        assert cov['36_prizefighting']['mechanism_status']=='RUNNABLE' and cov['36_prizefighting']['populated_count']>=1
        c.commit()
    print('v0.36.0 spectacle-economy regression PASS')

if __name__=='__main__': run()
