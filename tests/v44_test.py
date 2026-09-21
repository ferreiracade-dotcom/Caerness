from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.resolution_controller import process_due_resolution,next_resolution_due_day
from engine.civilian import create_enterprise


def run():
    assert ENGINE_VERSION in {'0.44.0','0.45.0','0.46.0','0.47.0','0.54.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=44
    reset_db();init_db()
    with connect() as c:
        import_current_seed(c);activate_existing_loops(c)
        # Find an ordinary tracked named person with no leadership and low martial standing.
        row=c.execute("""SELECT er.entity_id FROM entity_resolution er JOIN actors a ON a.id=er.entity_id
            LEFT JOIN cultivation_profiles cp ON cp.actor_id=a.id
            WHERE er.entity_kind='actor' AND er.resolution_level='TRACKED' AND a.actor_type='character' AND a.status='active'
              AND COALESCE(cp.current_stage,'') IN ('','First','Temper')
              AND NOT EXISTS (SELECT 1 FROM institution_memberships im WHERE im.member_actor_id=a.id AND im.status='active' AND lower(COALESCE(im.role_text,'')) GLOB '*head*')
            ORDER BY er.entity_id LIMIT 1""").fetchone()
        assert row
        ordinary=int(row[0])
        # Two autonomous low-significance reviews are required before demotion.
        c.execute('UPDATE world_state SET current_day=90 WHERE id=1');process_due_resolution(c,90)
        assert c.execute("SELECT resolution_level FROM entity_resolution WHERE entity_kind='actor' AND entity_id=?",(ordinary,)).fetchone()[0]=='TRACKED'
        c.execute('UPDATE world_state SET current_day=180 WHERE id=1');out=process_due_resolution(c,180)
        assert c.execute("SELECT resolution_level FROM entity_resolution WHERE entity_kind='actor' AND entity_id=?",(ordinary,)).fetchone()[0]=='STRUCTURAL'
        assert out['demotions']>0
        # Objective economic consequence can promote the same persistent life again.
        loc=c.execute('SELECT current_location_id FROM actors WHERE id=?',(ordinary,)).fetchone()[0]
        if loc is None: loc=int(c.execute('SELECT id FROM locations ORDER BY id LIMIT 1').fetchone()[0]);c.execute('UPDATE actors SET current_location_id=? WHERE id=?',(loc,ordinary))
        create_enterprise(c,'Resolution Fixture Regional Concern','merchant_house',owner_actor_id=ordinary,location_id=int(loc),capital=100000,cash=50000)
        c.execute("UPDATE entity_resolution SET next_review_day=181 WHERE entity_kind='actor' AND entity_id=?",(ordinary,))
        c.execute('UPDATE world_state SET current_day=181 WHERE id=1');process_due_resolution(c,181)
        assert c.execute("SELECT resolution_level FROM entity_resolution WHERE entity_kind='actor' AND entity_id=?",(ordinary,)).fetchone()[0] in {'TRACKED','ACTIVE'}
        # A consequential anonymous individual is promoted in resolution without inventing a personal name.
        lid=int(loc)
        le=int(c.execute("""INSERT INTO latent_entities(latent_kind,archetype,location_id,count_estimate,constraints_json,historical_context_json,status,created_day,updated_day,notes)
             VALUES ('person','closed_core_prizefighter_champion',?,1,?,?,'latent',0,0,'fixture')""",
             (lid,json.dumps({'identity_status':'unnamed latent individual'}),json.dumps({'champion_streak':5,'regional_significance':12}))).lastrowid)
        assert next_resolution_due_day(c,181,400) is not None
        c.execute('UPDATE world_state SET current_day=365 WHERE id=1');out2=process_due_resolution(c,365)
        lp=c.execute('SELECT resolution_level,significance_score FROM latent_resolution_profiles WHERE latent_entity_id=?',(le,)).fetchone()
        assert lp and lp[0]=='TRACKED' and float(lp[1])>=40,lp
        assert c.execute("SELECT COUNT(*) FROM actors WHERE notes LIKE '%fixture%' AND actor_type='character'").fetchone()[0]==0
        assert out2['latent_reviewed']>0
        assert c.execute("SELECT COUNT(*) FROM resolution_reviews WHERE day>0").fetchone()[0]>0
        c.commit()
    print('v0.44.0 autonomous two-way resolution regression PASS')
if __name__=='__main__':run()
