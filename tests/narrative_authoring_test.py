"""Narrative-authoring engine/protocol tests. Model replies are explicit stubs, not literary evidence."""
import copy
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch

from engine.db import connect, init_db, DEFAULT_DB_PATH
from engine.player import set_player
from engine import ai_planning as plans
from engine import narrative_authoring as authors
from engine.narrative_runtime import play, person
from engine.local_model import LocalModelResult, set_runtime_config


APPROVE={'compatible':True,'independent':True,'issues':[],'reason':'Compatible ordinary history and independently motivated introductions.'}


def detail(subject,key,text,epistemic='objective',speaker=None,category='biography',related=None):
    return {'subject_ref':subject,'key':key,'category':category,'epistemic':epistemic,'text':text,
            'start_day':-30,'speaker_ref':speaker,'related_ref':related}


def main():
    path=Path(os.environ['CAERNESS_DB_PATH']);shutil.copy2(DEFAULT_DB_PATH,path);init_db()
    with connect() as c:
        owner=c.execute("SELECT id FROM actors WHERE name='Robert Baird'").fetchone()[0]
        petra=c.execute("SELECT id FROM actors WHERE name='Petra Fenn'").fetchone()[0]
        set_player(c,owner);sid=plans.session(c)['id'];authors.ensure(c)
        location=c.execute('SELECT current_location_id FROM player_state').fetchone()[0]
        money=[tuple(r) for r in c.execute('SELECT * FROM resources')]
        family=[tuple(r) for r in c.execute('SELECT * FROM kinship_links')]
        today=c.execute('SELECT current_day FROM world_state').fetchone()[0]
        set_runtime_config(c,device_profile='explicit_test_stub',local_endpoint='https://example.org/v1/chat/completions',local_model='explicit-authorship-stub')
        queue=[];packets=[]
        def stub(conn,messages,**kwargs):
            packet=messages[-1]['content'];payload=json.loads(packet.split('```json\n')[1].split('```')[0]);contract=json.loads(packet.split('```json\n')[2].split('```')[0])
            packets.append(payload)
            return LocalModelResult(json.dumps({'task_type':'action_interpretation','request_id':contract['request_id'],'proposal':queue.pop(0)}),'stub','not-real-inference')
        recollection=detail(petra,'early_winter','Petra remembers sharing a cold winter morning with Robert.', 'recollection',petra)
        with patch('engine.model_gateway.chat_local',side_effect=stub):
            queue[:]=[{'mode':'discuss','text':'Petra smiles. "I remember the cold, and your patience."','details':[recollection]}]
            result=play(c,'To Petra Fenn: What small memory do you treasure?',sid)
            assert result['status']=='discussed' and len(packets)==1 and not queue
            assert result['continuity_recorded']['detail_ids']
            assert authors.visible(c,owner,petra)[0]['epistemic']=='recollection'
            assert c.execute('SELECT COUNT(*) FROM narrative_authorship').fetchone()[0]==0
            count=c.execute('SELECT COUNT(*) FROM historical_anchors').fetchone()[0]
            queue[:]=[{'mode':'discuss','text':'She shifts her chair and laughs quietly.'}]
            play(c,'We can simply sit for a moment.',sid)
            assert c.execute('SELECT COUNT(*) FROM historical_anchors').fetchone()[0]==count
        assert c.execute('SELECT current_day FROM world_state').fetchone()[0]==today
        assert family==[tuple(r) for r in c.execute('SELECT * FROM kinship_links')]
        assert money==[tuple(r) for r in c.execute('SELECT * FROM resources')]
        assert authors.visible(c,petra,petra) and not authors.visible(c,owner+1,petra)
        c.commit()
        with connect() as other:
            assert any(d['detail_key']=='early_winter' for d in authors.visible(other,owner,petra))
            assert person(other,owner,petra)['authored_continuity']
        # Significant new people/institutions have no pre-existing named or latent entry.
        spec={'entities':[
            {'id':'instructor','kind':'person','name':'Celia Fairweather','subtype':'instructor','location_id':location,'origin_day':-35*365,
             'background':'A local instructor who spent years teaching practical letters and road accounts.','independent_goal':'Maintain patient teaching despite unreliable attendance.','leader_ref':None},
            {'id':'school','kind':'institution','name':'Willow Account School','subtype':'school','location_id':location,'origin_day':-5*365,
             'background':'A modest independent teaching association with a history of practical instruction.','independent_goal':'Preserve useful local instruction and its own standards.','leader_ref':'new:instructor'}],
            'details':[detail(petra,'school_work','Petra helps with ordinary lessons at Willow Account School.',category='work',related='new:school')]}
        assert not c.execute("SELECT 1 FROM actors WHERE name='Willow Account School'").fetchone()
        with patch('engine.model_gateway.chat_local',side_effect=stub):
            queue[:]=[{'mode':'author','authorship':spec},APPROVE,{'mode':'discuss','text':'Petra tells you about the school and its independent instructor.'}]
            result=play(c,'To Petra Fenn: Tell me about your work and the people involved.',sid)
            assert result['status']=='discussed' and not queue
            assert result['world_changes'] is True and result['campaign_authorship'][0]['created']
        assert any(p['protocol']=='narrative_authoring_review_v1' for p in packets)
        run=dict(c.execute("SELECT * FROM narrative_authorship WHERE status='applied'").fetchone())
        created=json.loads(run['result_json'])['created'];teacher,school=[r['actor_id'] for r in created]
        assert c.execute('SELECT actor_type FROM actors WHERE id=?',(school,)).fetchone()[0]=='institution'
        assert c.execute('SELECT 1 FROM actor_life_profiles WHERE actor_id=?',(teacher,)).fetchone()
        assert c.execute('SELECT 1 FROM simulation_profiles WHERE actor_id=?',(teacher,)).fetchone()
        assert c.execute("SELECT 1 FROM goals WHERE actor_id=? AND status='active'",(teacher,)).fetchone()
        assert c.execute('SELECT 1 FROM institution_profiles WHERE actor_id=?',(school,)).fetchone()
        assert c.execute("SELECT 1 FROM goals WHERE actor_id=? AND status='active'",(school,)).fetchone()
        from engine.opportunity import institution_decision_actor
        assert institution_decision_actor(c,school)==teacher and institution_decision_actor(c,school)!=owner
        assert any(d['detail_key']=='school_work' for d in authors.visible(c,owner,petra))
        assert any(d['detail_key']=='narrative_identity' for d in person(c,owner,teacher)['authored_continuity'])
        assert not c.execute('SELECT 1 FROM resources WHERE actor_id IN (?,?)',(teacher,school)).fetchone()
        # Ordinary work titles cannot become a back door to command authority.
        work={'entities':[],'details':[detail(owner,'volunteer_work','Head master of everything',category='work',related=school)]}
        prepared=authors.prepare(c,sid,work);authors.commit(c,prepared['id'],prepared['digest'],APPROVE)
        assert institution_decision_actor(c,school)==teacher
        # Deterministic negative checks, even if a model would approve.
        invalid=[]
        invalid.append({'entities':[],'details':[detail(petra,'spouse','Petra has a different spouse.')]})
        invalid.append({'entities':[],'details':[detail(petra,'school_work','Petra has never taught anywhere.',category='work',related=school)]})
        invalid.append({'entities':[],'details':[dict(detail(petra,'prebirth','A childhood event.'),start_day=-500*365)]})
        bad=copy.deepcopy(spec);bad['entities'][0]['name']='Robert Baird';invalid.append(bad)
        bad=copy.deepcopy(spec);bad['entities'][0]['name']='New Unfunded Person';bad['entities'][0]['resources']={'silver':1000000};invalid.append(bad)
        bad=copy.deepcopy(spec);bad['entities'][0]['name']='New Claimed Servant';bad['entities'][1]['name']='Player Gift Guild';bad['entities'][1]['leader_ref']=owner;invalid.append(bad)
        for proposal in invalid:
            try:authors.prepare(c,sid,proposal)
            except ValueError:pass
            else:raise AssertionError('Unsafe authored state accepted')
        # Semantic contradiction under a different key is independently reviewed,
        # with frozen saved kinship/anchors supplied rather than absence treated as proof.
        prepared=authors.prepare(c,sid,{'entities':[],'details':[detail(petra,'contradictory_history','Petra never knew Robert before today.')]})
        assert any(a['kinship'] for a in prepared['constraints']['actors'])
        rejected=authors.commit(c,prepared['id'],prepared['digest'],{'compatible':False,'independent':True,'issues':['Contradicts established relationship history.'],'reason':'Inconsistent.'})
        assert rejected['status']=='rejected' and not any(d['detail_key']=='contradictory_history' for d in authors.visible(c,owner,petra))
        # Stale and replayed reviews never overwrite changed campaign constraints.
        prepared=authors.prepare(c,sid,{'entities':[],'details':[detail(petra,'routine_visit','A routine visit to the market.')]})
        c.execute('UPDATE actors SET subtype=? WHERE id=?',('changed during review',petra))
        try:authors.commit(c,prepared['id'],prepared['digest'],APPROVE)
        except ValueError:pass
        else:raise AssertionError('Stale review accepted')
        c.execute("UPDATE actors SET subtype='spouse' WHERE id=?",(petra,))
        # Atomic rollback: an ineligible native merchant institution cannot leave its
        # newly materialized leader behind when the rest of the batch fails.
        bad=copy.deepcopy(spec);bad['entities'][0]['name']='Rolled Back Person';bad['entities'][1]['name']='Rolled Back Firm';bad['entities'][1]['subtype']='merchant_house'
        prepared=authors.prepare(c,sid,bad)
        try:authors.commit(c,prepared['id'],prepared['digest'],APPROVE)
        except ValueError:pass
        else:raise AssertionError('Native formation gate bypassed')
        assert not c.execute("SELECT 1 FROM actors WHERE name='Rolled Back Person'").fetchone()
        c.commit()
        from engine.simulation import advance_connection
        advance_connection(c,7);c.commit()
    with connect() as c:
        assert c.execute('SELECT current_day FROM world_state').fetchone()[0]==today+7
        assert c.execute('SELECT name FROM actors WHERE id=?',(school,)).fetchone()[0]=='Willow Account School'
        assert authors.visible(c,owner,petra) and authors.visible(c,owner,teacher)
        assert c.execute('SELECT COUNT(*) FROM narrative_authorship WHERE status="applied"').fetchone()[0]==2
    print('Permitted recollection, lightweight expression, significant new people/institution/work, knowledge scope, native independence, contradiction/stale/authority/resource safeguards, atomic rollback, reload and time passage PASS (stubbed model protocol)')

if __name__=='__main__':main()
