"""BELIEF-01 acceptance: actor-relative claims/evidence plus competence-bounded interpretation."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.belief import (
    ensure_claim, add_claim_evidence, observe_claim, actor_belief_envelope,
    build_competence_lens,
)
from engine.expertise import set_actor_competence
from engine.information import _upsert_knowledge


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_belief01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); return c,path


def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=62
    c,path=bootstrap()
    assert c.execute("SELECT value FROM engine_meta WHERE key='belief_model_version'").fetchone()[0]=='1'
    assert c.execute("SELECT value FROM engine_meta WHERE key='competence_lens_version'").fetchone()[0]=='1'

    loc=int(c.execute("INSERT INTO locations(name,kind) VALUES ('[BELIEF] Market Ward','district')").lastrowid)
    a=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id) VALUES ('[BELIEF] Analyst A','character',?)",(loc,)).lastrowid)
    b=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id) VALUES ('[BELIEF] Analyst B','character',?)",(loc,)).lastrowid)

    # One objective proposition can produce different actor-relative beliefs because access differs.
    claim=ensure_claim(c,'belief:test:grain','The eastern granary is short of grain.',subject_kind='location',subject_id=loc,authoritative_event_id=None,created_day=0)
    support=add_claim_evidence(c,claim,evidence_kind='ledger',summary='A clerk ledger shows repeated short deliveries.',polarity='supports',reliability=0.9,salience=0.8,domain_key='commerce',location_id=loc,available_from_day=0)
    contra1=add_claim_evidence(c,claim,evidence_kind='inspection',summary='An inspector reports stocked bins.',polarity='contradicts',reliability=0.95,salience=0.9,domain_key='commerce',location_id=loc,available_from_day=0)
    contra2=add_claim_evidence(c,claim,evidence_kind='invoice',summary='Fresh purchase receipts indicate replenishment.',polarity='contradicts',reliability=0.95,salience=0.8,domain_key='commerce',location_id=loc,available_from_day=0)

    first=observe_claim(c,a,claim,support,received_day=0)
    assert first.stance=='accepts' and first.confidence>0.5
    assert not c.execute("SELECT 1 FROM actor_beliefs WHERE actor_id=? AND claim_id=?",(b,claim)).fetchone()
    bstate=observe_claim(c,b,claim,contra1,received_day=0)
    assert bstate.stance=='rejects'

    # Correction history is explicit rather than silently overwriting the actor's past belief.
    observe_claim(c,a,claim,contra1,received_day=1)
    corrected=observe_claim(c,a,claim,contra2,received_day=1)
    assert corrected.stance=='rejects' and corrected.correction_count>=1, corrected
    revisions=int(c.execute("SELECT COUNT(*) FROM belief_revisions WHERE actor_id=? AND claim_id=?",(a,claim)).fetchone()[0])
    assert revisions>=2

    # Actor-safe envelopes expose only acquired evidence, not authoritative truth links.
    envelope=actor_belief_envelope(c,a)
    item=next(x for x in envelope if int(x['claim_id'])==claim)
    assert 'authoritative_event_id' not in item
    assert {int(e['id']) for e in item['evidence']}=={support,contra1,contra2}

    # Add a larger evidence field. One item remains objectively stored but inaccessible to A.
    hidden=add_claim_evidence(c,claim,evidence_kind='sealed_audit',summary='A sealed audit known only elsewhere.',polarity='supports',reliability=1.0,salience=1.0,domain_key='commerce',location_id=loc,available_from_day=0)
    extras=[]
    for i in range(36):
        eid=add_claim_evidence(c,claim,evidence_kind='market_cue',summary=f'Market cue {i}',polarity='supports' if i%2==0 else 'context',reliability=0.55+(i%4)*0.08,salience=0.2+(i%5)*0.12,domain_key='commerce',location_id=loc,available_from_day=0)
        observe_claim(c,a,claim,eid,received_day=2,access_kind='observed')
        extras.append(eid)

    # Competence changes attention/interpretation over the SAME accessible evidence; it cannot create access.
    set_actor_competence(c,a,'commerce',0)
    low=build_competence_lens(c,a,'commerce',claim_ids=[claim],situation='Assess the granary shortage.')
    set_actor_competence(c,a,'commerce',100)
    high=build_competence_lens(c,a,'commerce',claim_ids=[claim],situation='Assess the granary shortage.')
    assert low['accessible_evidence_count']==high['accessible_evidence_count']==3+len(extras)
    assert high['noticed_evidence_count']>low['noticed_evidence_count'], (low['noticed_evidence_count'],high['noticed_evidence_count'])
    assert hidden not in {int(e['evidence_id']) for e in high['noticed_evidence']}
    assert high['professional_reading']['competence']['score']==100.0
    assert high['guardrails']['uses_only_actor_accessible_evidence'] is True
    assert high['guardrails']['authoritative_truth_links_exposed'] is False

    # Existing information writers transparently mirror into the new claim/evidence model.
    _upsert_knowledge(c,a,'legacy:test','A courier says the bridge is closed.',0.72,3,source_kind='admin',location_id=loc)
    mirrored=c.execute("""SELECT ab.stance,ab.confidence FROM actor_beliefs ab
                          JOIN information_claims ic ON ic.id=ab.claim_id
                          WHERE ab.actor_id=? AND ic.claim_key='legacy:test'""",(a,)).fetchone()
    assert mirrored and mirrored['stance']=='accepts' and float(mirrored['confidence'])>0

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    c.commit(); c.close()
    print('BELIEF-01 claims/evidence + Competence Lens tests: PASS')

if __name__=='__main__': run()
