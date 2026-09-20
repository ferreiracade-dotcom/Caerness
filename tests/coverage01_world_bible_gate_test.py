"""COVERAGE-01 acceptance: opening-world population/autonomy gate and two-way resolution."""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.coverage import coverage_gate, snapshot_coverage
from engine.civilian import create_enterprise
from engine.health import ensure_health_profile, add_condition, request_care, process_due_health
from engine.relationships import ensure_relationship
from engine.resolution_controller import (process_due_resolution, create_institution_candidate,
    update_institution_candidate, review_entity)


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_coverage01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db()
    c=connect(); import_current_seed(c); activation=activate_existing_loops(c); c.commit()
    return c,path,activation


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=69
    c,path,activation=bootstrap()

    # Opening-world substrate exists as structural/aggregate capacity rather than invented named people.
    assert activation['opening_health_sites_created']>=1
    assert activation['opening_agriculture_fields_created']>=1
    assert activation['opening_law_jurisdictions_created']>=1
    assert c.execute("SELECT COUNT(*) FROM health_care_sites WHERE json_extract(metadata_json,'$.not_named_canon_provider')=1").fetchone()[0]>=1
    assert c.execute("SELECT COUNT(*) FROM agriculture_fields WHERE json_extract(metadata_json,'$.not_named_canon_farm')=1").fetchone()[0]>=1
    assert c.execute("SELECT COUNT(*) FROM law_jurisdictions WHERE json_extract(metadata_json,'$.not_named_canon_court')=1").fetchone()[0]>=1

    gate=coverage_gate(c)
    assert gate['pass'] and gate['failure_count']==0,gate
    snap={x['domain_key']:x for x in snapshot_coverage(c)}
    assert snap['31_merchant_transport']['state']!='missing_population'  # shipment is a transient event, merchant substrate is opening population
    assert snap['37_crime_orgs']['populated_count']>=1                 # v0.60 concrete organization owner, not retired legacy profile
    assert snap['41_assassination']['populated_count']>=2             # Reckoning/Cormorants exist without forcing an opening murder
    assert snap['12_undertow_compacts']['state']=='conditional_dormant'
    assert snap['51_player_boundary']['state']=='missing_population'  # unattended opening has no player, but it is non-required

    # Structural health capacity can actually treat ordinary care without inventing a named physician.
    alder=int(c.execute("SELECT id FROM locations WHERE name='Aldergate'").fetchone()[0])
    care=int(c.execute("SELECT id FROM health_care_sites WHERE location_id=? AND status='active' ORDER BY id LIMIT 1",(alder,)).fetchone()[0])
    patient=int(c.execute("INSERT INTO actors(name,actor_type,subtype,home_location_id,current_location_id,status,is_demo) VALUES ('[COV01] Patient','character','ordinary resident',?,?,'active',0)",(alder,alder)).lastrowid)
    c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_stage,family_formation_eligible,life_status,last_review_day,metadata_json) VALUES (?,-10000,'adult',1,'living',0,'{}')",(patient,))
    ensure_health_profile(c,patient)
    cond=add_condition(c,patient,'injury','[COV01] ordinary fracture',severity=60,body_system='limb',next_review_days=7)
    req=request_care(c,patient,cond,site_id=care,treatment_kind='ordinary_medicine',urgency=70)
    c.execute("UPDATE world_state SET current_day=1 WHERE id=1"); process_due_health(c,1)
    rr=c.execute("SELECT * FROM health_care_requests WHERE id=?",(req,)).fetchone()
    assert rr['status']=='treated' and rr['assigned_provider_actor_id'] is None
    tr=c.execute("SELECT metadata_json FROM medical_treatments WHERE condition_id=? ORDER BY id DESC LIMIT 1",(cond,)).fetchone()
    assert json.loads(tr[0]).get('structural_provider_pool') is True

    # Keep existing opening entities out of this proof's due queue so only our causal latent identity is evaluated.
    c.execute("UPDATE entity_resolution SET next_review_day=9999")
    c.execute("UPDATE latent_entities SET created_day=1000,updated_day=1000 WHERE status IN ('latent','partially_crystallized')")
    c.execute("DELETE FROM latent_resolution_profiles")
    c.execute("UPDATE world_state SET current_day=200 WHERE id=1")

    enterprise=create_enterprise(c,'[COV01] Rising Ledger','merchant_house',location_id=alder,capital=180,cash=90,
                                 reputation=72,admin_quality=60,labor_capacity=50,risk_tolerance=55,metadata={'coverage01':True})
    latent=int(c.execute("""INSERT INTO latent_entities(latent_kind,archetype,location_id,count_estimate,constraints_json,
                         historical_context_json,status,created_day,updated_day,notes)
                         VALUES ('person','merchant_operator',?,1,?,?,'latent',0,0,'COVERAGE-01 latent merchant proof')""",
                         (alder,json.dumps({'enterprise_id':enterprise,'age_range':[30,42]}),
                          json.dumps({'enterprise_id':enterprise,'consequence_score':30,'regional_significance':30}))).lastrowid)
    r1=process_due_resolution(c,200)
    latent_row=c.execute("SELECT * FROM latent_entities WHERE id=?",(latent,)).fetchone()
    assert r1['latent_materialized']==1 and latent_row['status']=='crystallized' and latent_row['crystallized_entity_kind']=='actor',r1
    merchant=int(latent_row['crystallized_entity_id'])
    assert c.execute("SELECT actor_type FROM actors WHERE id=?",(merchant,)).fetchone()[0]=='character'
    assert c.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?",(enterprise,)).fetchone()[0]==merchant
    assert c.execute("SELECT 1 FROM enterprise_staff WHERE enterprise_id=? AND actor_id=? AND status='active'",(enterprise,merchant)).fetchone()
    assert c.execute("SELECT 1 FROM continuity_cores WHERE entity_kind='actor' AND entity_id=?",(merchant,)).fetchone()
    assert c.execute("SELECT resolution_level FROM entity_resolution WHERE entity_kind='actor' AND entity_id=?",(merchant,)).fetchone()[0]=='TRACKED'

    # A causally evidenced new criminal organization can cross the same boundary into the concrete v0.60 underworld owner.
    candidate=create_institution_candidate(c,'criminal organization',location_id=alder,founder_actor_id=merchant,
        proposed_name='Ash Knives',significance_score=20,
        resources={'organization_type':'gang','member_count_estimate':8,'territorial_presence':20,'violence_capacity':25},
        participants=[merchant],evidence=[{'kind':'repeated_joint_extortion','day':190}],day=200)
    update_institution_candidate(c,candidate,significance_score=45,evidence_append={'kind':'durable_shared_treasury','day':200},day=200)
    r2=process_due_resolution(c,200)
    cr=c.execute("SELECT * FROM emergent_institution_candidates WHERE id=?",(candidate,)).fetchone()
    assert r2['institution_crystallized']==1 and cr['status']=='crystallized',r2
    inst=int(cr['crystallized_institution_actor_id'])
    uw=c.execute("SELECT * FROM underworld_organizations WHERE institution_actor_id=?",(inst,)).fetchone()
    assert uw and uw['organization_type']=='gang' and uw['name']=='Ash Knives'

    # Safe down-resolution reduces processing cost but preserves identity, continuity, relationships and obligations/property links.
    other=int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND id NOT IN (?,?) ORDER BY id LIMIT 1",(merchant,patient)).fetchone()[0])
    rel=ensure_relationship(c,merchant,other,220,trust=25,familiarity=40,obligation=10)
    core_before=c.execute("SELECT core_json FROM continuity_cores WHERE entity_kind='actor' AND entity_id=?",(merchant,)).fetchone()[0]
    c.execute("UPDATE civilian_enterprises SET status='closed' WHERE id=?",(enterprise,))
    d1=review_entity(c,'actor',merchant,day=300); d2=review_entity(c,'actor',merchant,day=400)
    assert d1['action']=='defer' and d2['action']=='demote' and d2['applied_level']=='STRUCTURAL',(d1,d2)
    assert c.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?",(merchant,)).fetchone()[0]=='DORMANT'
    assert c.execute("SELECT 1 FROM actors WHERE id=?",(merchant,)).fetchone()
    assert c.execute("SELECT 1 FROM relationships WHERE id=?",(rel,)).fetchone()
    assert c.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE id=?",(enterprise,)).fetchone()[0]==merchant
    assert c.execute("SELECT core_json FROM continuity_cores WHERE entity_kind='actor' AND entity_id=?",(merchant,)).fetchone()[0]==core_before

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError: pass
    print('COVERAGE-01 World-Bible gate + resolution acceptance: PASS')

if __name__=='__main__': run()
