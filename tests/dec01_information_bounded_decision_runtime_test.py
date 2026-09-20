"""DEC-01 acceptance: actor information -> concrete provider candidates -> weighted choice -> domain execution."""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.decisions import build_actor_context, decide_actor
from engine.decision_runtime import generate_candidates
from engine.belief import ensure_claim, add_claim_evidence, observe_claim
from engine.underworld_rebuild import seed_city_underworld, protect_business
from engine.underworld_decisions import execute_underworld_action


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_dec01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); return c,path


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=63
    c,path=bootstrap()
    assert c.execute("SELECT value FROM engine_meta WHERE key='decision_runtime_version'").fetchone()[0]=='1'
    assert c.execute("SELECT value FROM engine_meta WHERE key='decision_information_rule'").fetchone()[0]=='actor_accessible_only'

    city=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[DEC01] Aldergate Test','city')").lastrowid)
    seed_city_underworld(c,city_location_id=city,force=True,salt=6301)

    # Find an existing protected account and a real rival organization to attempt a poach.
    acct=c.execute("""SELECT p.*,o.current_leader_actor_id FROM underworld_protection_accounts p
                      JOIN underworld_organizations o ON o.id=p.protector_organization_id
                      WHERE p.status='active' ORDER BY p.id LIMIT 1""").fetchone()
    assert acct, 'seed must create at least one concrete protection account'
    home_org=int(acct['protector_organization_id']); leader=int(acct['current_leader_actor_id'])
    rival=c.execute("SELECT id,current_leader_actor_id FROM underworld_organizations WHERE id<>? AND status='active' AND current_leader_actor_id IS NOT NULL ORDER BY id LIMIT 1",(home_org,)).fetchone()
    assert rival
    rival_org=int(rival['id']); rival_leader=int(rival['current_leader_actor_id'])
    poach=protect_business(c,rival_org,int(acct['enterprise_id']),int(acct['zone_id']),payment_per_30=1.25,service_strength=45,fear_component=50,metadata={'dec01_test':True})
    assert poach['disputed'] is True
    incident=c.execute("SELECT * FROM underworld_incidents WHERE target_organization_id=? AND source_organization_id=? AND incident_kind='protection_poach' AND status='open' ORDER BY id DESC LIMIT 1",(home_org,rival_org)).fetchone()
    assert incident

    # Hidden objective evidence does not become a decision input just because it exists in the DB.
    hidden_claim=ensure_claim(c,'dec01:hidden','A hidden rival ledger exists.',created_day=0,subject_kind='organization',subject_id=rival_org)
    hidden_ev=add_claim_evidence(c,hidden_claim,evidence_kind='sealed_ledger',summary='Hidden ledger',polarity='supports',reliability=.95,salience=.9,domain_key='underworld',available_from_day=0)

    # A genuinely actor-accessible but conflicted claim can generate an investigation candidate.
    claim=ensure_claim(c,'dec01:uncertain','The rival intends another protection poach.',created_day=0,subject_kind='organization',subject_id=rival_org)
    sup=add_claim_evidence(c,claim,evidence_kind='informant',source_actor_id=rival_leader,summary='An informant says another poach is planned.',polarity='supports',reliability=.72,salience=.7,domain_key='underworld',available_from_day=0)
    con=add_claim_evidence(c,claim,evidence_kind='counter_report',source_actor_id=rival_leader,summary='A second report says the plan was cancelled.',polarity='contradicts',reliability=.72,salience=.7,domain_key='underworld',available_from_day=0)
    observe_claim(c,leader,claim,sup,received_day=0); state=observe_claim(c,leader,claim,con,received_day=0)
    assert state.stance=='uncertain' and state.confidence<=.45

    envelope=build_actor_context(c,leader,0)
    assert envelope['canon']==[]
    assert envelope['information_guardrails']['world_bible_as_personal_knowledge'] is False
    assert hidden_claim not in {int(b['claim_id']) for b in envelope['beliefs']}
    assert claim in {int(b['claim_id']) for b in envelope['beliefs']}

    candidates=generate_candidates(c,leader,'STRATEGIC',0,envelope)
    keys={x.action_kind for x in candidates}
    assert {'warn_protection_poacher','retaliate_protection_poach','negotiate_protection_poach'} & keys
    assert 'investigate_underworld_claim' in keys
    assert all(x.action_kind not in {'advance_goal','address_pressure','work_relationship','force_goal'} for x in candidates)
    poach_candidates=[x for x in candidates if x.action_kind in {'warn_protection_poacher','retaliate_protection_poach','negotiate_protection_poach'}]
    assert all(int(x.information_basis['underworld_incident_id'])==int(incident['id']) for x in poach_candidates)
    investigation=next(x for x in candidates if x.action_kind=='investigate_underworld_claim')
    assert claim in investigation.claim_ids and hidden_ev not in investigation.evidence_ids

    # Domain owner executes the concrete grievance response and closes the exact incident.
    warning=next(x for x in poach_candidates if x.action_kind=='warn_protection_poacher')
    result=execute_underworld_action(c,leader,warning.action_kind,warning.payload,0)
    assert not result.get('blocked'), result
    assert c.execute("SELECT status FROM underworld_incidents WHERE id=?",(int(incident['id']),)).fetchone()[0]=='answered'
    assert c.execute("SELECT 1 FROM underworld_operations WHERE organization_id=? AND operation_kind='warn_protection_poacher' AND target_organization_id=?",(home_org,rival_org)).fetchone()

    # New selector persists the complete candidate set and uses non-degenerate weighted probabilities.
    did=decide_actor(c,leader,'STRATEGIC',1)
    d=c.execute("SELECT * FROM decisions WHERE id=?",(did,)).fetchone(); assert d
    assert d['action_type'] not in {'advance_goal','address_pressure','work_relationship','force_goal'}
    ev=c.execute("SELECT * FROM decision_evaluations WHERE decision_id=?",(did,)).fetchone(); assert ev
    audit=c.execute("SELECT * FROM decision_candidate_audit WHERE evaluation_id=? ORDER BY id",(int(ev['id']),)).fetchall()
    assert len(audit)>=2 and sum(int(r['selected']) for r in audit)==1
    plausible=[r for r in audit if int(r['plausible'])]
    assert abs(sum(float(r['selection_probability']) for r in plausible)-1.0)<1e-6
    assert any(0.0<float(r['selection_probability'])<1.0 for r in plausible) if len(plausible)>1 else True
    summary=json.loads(ev['envelope_summary_json']); assert summary['canon_chunk_count']==0 and summary['information_rule']=='actor_accessible_only'

    # Bosses are strategic causal actors; monthly underworld maintenance no longer owns a second strategy selector.
    profile=c.execute("SELECT tier,cadence_days FROM simulation_profiles WHERE actor_id=?",(leader,)).fetchone()
    assert profile['tier']=='STRATEGIC' and int(profile['cadence_days'])<=30

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    c.commit(); c.close()

    # Simulate a schema-62 campaign and prove migration adds DEC-01 without inventing decision history.
    c=connect()
    c.execute('DROP TABLE decision_candidate_audit'); c.execute('DROP TABLE decision_evaluations')
    c.execute("DELETE FROM schema_migrations WHERE version=63"); c.execute("UPDATE engine_meta SET value='62' WHERE key='schema_version'")
    c.commit(); c.close(); init_db(); c=connect()
    assert c.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()[0]==str(SCHEMA_VERSION)
    assert c.execute("SELECT COUNT(*) FROM decision_evaluations").fetchone()[0]==0
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; c.close()
    print('DEC-01 information-bounded decision runtime tests: PASS')

if __name__=='__main__': run()
