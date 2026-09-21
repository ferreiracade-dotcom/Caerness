from __future__ import annotations

import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.hollow import (
    extract_current, press_heir_claim, register_heir, seal_mantle, pass_mantle,
    process_inheritor_death, ascend_inheritor, set_power_broker_stance,
)
from engine.household_life import mark_actor_deceased
from engine.coverage import snapshot_coverage


def _id(c,name):
    r=c.execute("SELECT id FROM actors WHERE name=?",(name,)).fetchone(); assert r,name; return int(r[0])


def _bootstrap():
    reset_db(); init_db()
    c=connect(); import_current_seed(c); activate_existing_loops(c); return c


def run():
    assert ENGINE_VERSION in {'0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=38

    # Opening authority model: Deep Court elders are power-brokers, not heirs.
    c=_bootstrap()
    grand=_id(c,'Grand Coven'); malric=_id(c,'Malric Vell'); dravik=_id(c,'Dravik'); bastian=_id(c,'Bastian Crow'); ronan=_id(c,'Ronan Birch')
    state=c.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?",(grand,)).fetchone()
    assert int(state['inheritor_actor_id'])==malric and int(state['foremost_heir_actor_id'])==dravik
    assert state['succession_status']=='open' and int(state['mantle_sealed'])==0
    heirs=c.execute("SELECT h.*,a.name FROM grand_coven_heirs h JOIN actors a ON a.id=h.actor_id WHERE h.institution_actor_id=?",(grand,)).fetchall()
    assert [r['name'] for r in heirs]==['Dravik'],[dict(r) for r in heirs]
    pb={r['name']:dict(r) for r in c.execute("SELECT p.*,a.name FROM grand_coven_power_brokers p JOIN actors a ON a.id=p.actor_id WHERE p.institution_actor_id=?",(grand,)).fetchall()}
    assert pb['Bastian Crow']['role_kind']=='deep_court_elder'
    assert pb['Ronan Birch']['role_kind']=='senior_power'
    try:
        press_heir_claim(c,grand,bastian)
        raise AssertionError('Deep Court elder must not become an heir merely by Court office')
    except ValueError as e:
        assert 'actual heir' in str(e).lower() or 'deep court' in str(e).lower()

    # A Court elder can support an actual heir without becoming that heir.
    gareth=_id(c,'Gareth Vell')
    register_heir(c,grand,gareth,claim_kind='rival_heir',formal_status='recognized',political_support=55,metadata={'test':'v38'})
    set_power_broker_stance(c,grand,bastian,stance='supports',supported_heir_actor_id=gareth)
    assert c.execute("SELECT supported_heir_actor_id FROM grand_coven_power_brokers WHERE institution_actor_id=? AND actor_id=?",(grand,bastian)).fetchone()[0]==gareth
    assert int(c.execute("SELECT COUNT(*) FROM grand_coven_heirs WHERE actor_id=?",(bastian,)).fetchone()[0])==0

    # Hollow extraction transfers current only; affiliation does not mean every Coven junior has extracted.
    formal_unknown=int(c.execute("SELECT COUNT(*) FROM hollow_practice_profiles WHERE hollow_status='formal_coven' AND practiced_extraction IS NULL").fetchone()[0])
    assert formal_unknown>0
    corbin=_id(c,'Corbin Yarrow'); roderick=_id(c,'Roderick Ash')
    before_p=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(corbin,)).fetchone())
    before_s=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(roderick,)).fetchone())
    event=extract_current(c,corbin,roderick,1.5,context_kind='practice',metadata={'test':'v38'})
    after_p=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(corbin,)).fetchone())
    after_s=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(roderick,)).fetchone())
    ev=c.execute("SELECT * FROM hollow_extraction_events WHERE id=?",(event,)).fetchone(); assert ev and float(ev['transferred_current'])>0
    assert abs((before_p['current_reserve']+before_s['current_reserve'])-(after_p['current_reserve']+after_s['current_reserve']))<1e-8
    for k in ['current_stage','core_capacity','vessel_adaptation','realization_integration']:
        assert after_p[k]==before_p[k],(k,before_p[k],after_p[k])
    assert c.execute("SELECT practiced_extraction FROM hollow_practice_profiles WHERE actor_id=?",(corbin,)).fetchone()[0]==1
    c.close()

    # Sealing closes the lawful field; Passing transfers current only; death completes accession without a new Carrion.
    c=_bootstrap(); grand=_id(c,'Grand Coven'); malric=_id(c,'Malric Vell'); dravik=_id(c,'Dravik')
    pre_d=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(dravik,)).fetchone())
    pre_m=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(malric,)).fetchone())
    seal_mantle(c,grand,dravik)
    state=c.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?",(grand,)).fetchone(); assert state['succession_status']=='sealed' and int(state['mantle_sealed'])==1
    moved=pass_mantle(c,grand,requested_current=2.0); assert moved>0
    post_d=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(dravik,)).fetchone())
    post_m=dict(c.execute("SELECT * FROM cultivation_profiles WHERE actor_id=?",(malric,)).fetchone())
    assert abs((pre_d['current_reserve']+pre_m['current_reserve'])-(post_d['current_reserve']+post_m['current_reserve']))<1e-8
    for k in ['current_stage','core_capacity','vessel_adaptation','realization_integration']:
        assert post_d[k]==pre_d[k],k
    try:
        pass_mantle(c,grand,requested_current=1.0)
        raise AssertionError('Passing cannot be replayed')
    except ValueError:
        pass
    mark_actor_deceased(c,malric,reason='v38 sudden death test')
    assert process_inheritor_death(c,grand)
    state=c.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?",(grand,)).fetchone()
    assert int(state['inheritor_actor_id'])==dravik
    events=[json.loads(r['metadata_json'] or '{}') for r in c.execute("SELECT metadata_json FROM grand_coven_mantle_events WHERE institution_actor_id=?",(grand,)).fetchall()]
    assert all(not m.get('carrion_triggered',False) for m in events),events
    c.close()

    # Unsealed succession with a genuinely pressed rival can remain contested/vacant; Carrion still does not reset.
    c=_bootstrap(); grand=_id(c,'Grand Coven'); malric=_id(c,'Malric Vell'); gareth=_id(c,'Gareth Vell')
    register_heir(c,grand,gareth,claim_kind='rival_heir',formal_status='recognized',political_support=70,metadata={'test':'v38-contested'})
    press_heir_claim(c,grand,gareth,reason='test rival presses before Sealing')
    mark_actor_deceased(c,malric,reason='v38 contested sudden death test')
    assert process_inheritor_death(c,grand)
    state=c.execute("SELECT * FROM grand_coven_succession_state WHERE institution_actor_id=?",(grand,)).fetchone()
    assert state['succession_status']=='vacant' and state['inheritor_actor_id']==malric,dict(state)
    last=c.execute("SELECT metadata_json FROM grand_coven_mantle_events WHERE event_kind='sudden_death_transition' ORDER BY id DESC LIMIT 1").fetchone()
    meta=json.loads(last[0]); assert meta['carrion_triggered'] is False and meta['contested'] is True
    c.close()

    # Ascension is terminal: sealed heir receives current, predecessor dies, successor accedes; no retired former Inheritor exists.
    c=_bootstrap(); grand=_id(c,'Grand Coven'); malric=_id(c,'Malric Vell'); dravik=_id(c,'Dravik')
    seal_mantle(c,grand,dravik)
    moved=ascend_inheritor(c,grand,requested_current=1.0); assert moved>0
    assert c.execute("SELECT status FROM actors WHERE id=?",(malric,)).fetchone()[0]=='deceased'
    assert int(c.execute("SELECT inheritor_actor_id FROM grand_coven_succession_state WHERE institution_actor_id=?",(grand,)).fetchone()[0])==dravik
    assert int(c.execute("SELECT COUNT(*) FROM grand_coven_mantle_events WHERE event_kind='ascension'",).fetchone()[0])==1

    cov={x['domain_key']:x for x in snapshot_coverage(c,None,phase='v38-test')}
    assert cov['14_hollow_succession']['mechanism_status']=='RUNNABLE' and cov['14_hollow_succession']['populated_count']>0,cov['14_hollow_succession']
    c.commit(); c.close()
    print('v0.38.0 Hollow practice / Grand Coven succession regression PASS')

if __name__=='__main__': run()
