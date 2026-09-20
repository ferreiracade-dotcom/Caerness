from __future__ import annotations

import json
from pathlib import Path

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.decisions import build_actor_context
from engine.decision_runtime import generate_candidates
from engine.organization_agency import start_regime
from engine.conflict import execute_political_action


def setup_world():
    reset_db(force=True, backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c


def polity(c,name):
    return c.execute("select p.* from political_polities p join actors a on a.id=p.institution_actor_id where a.name=?",(name,)).fetchone()


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=81
        assert c.execute("select count(*) from political_polities").fetchone()[0]==7
        assert c.execute("select count(*) from polity_government_actors").fetchone()[0]==7
        assert c.execute("select count(*) from political_relations").fetchone()[0]>=6
        assert c.execute("select count(*) from conflict_channels").fetchone()[0]==5
        active_uw=c.execute("select count(*) from underworld_organizations where status not in ('destroyed','merged')").fetchone()[0]
        linked_uw=c.execute("select count(*) from underworld_organizations where institution_actor_id is not null and status not in ('destroyed','merged')").fetchone()[0]
        assert active_uw==linked_uw and active_uw>0

        # Regime change changes current regime without rewriting inherited institutional state.
        uw=c.execute("select * from underworld_organizations where institution_actor_id is not null order by id limit 1").fetchone(); iid=int(uw['institution_actor_id'])
        inherited=c.execute("select institutional_inheritance_json from organization_agency_profiles where institution_actor_id=?",(iid,)).fetchone()[0]
        old=c.execute("select id from organization_regimes where institution_actor_id=? and status='active'",(iid,)).fetchone()[0]
        start_regime(c,iid,leader_actor_id=uw['current_leader_actor_id'],regime_kind='test_hardline',worldview={'violence':'more_permissive'})
        new=c.execute("select id from organization_regimes where institution_actor_id=? and status='active'",(iid,)).fetchone()[0]
        assert new!=old
        assert c.execute("select institutional_inheritance_json from organization_agency_profiles where institution_actor_id=?",(iid,)).fetchone()[0]==inherited

        # Severe frontier incident: bounded diplomatic/retaliatory responses exist, campaign is physically gated.
        g=polity(c,'Greywood'); d=polity(c,'Dunmoor'); ch=c.execute("select * from conflict_channels where channel_key='greywood_dunmoor_westbrook_stoneford'").fetchone()
        actor=int(c.execute('select decision_actor_id from polity_government_actors where polity_id=?',(int(d['id']),)).fetchone()[0])
        cur=c.execute("insert into conflict_incidents(channel_id,day,initiator_polity_id,target_polity_id,incident_kind,severity,location_id,status,response_state,metadata_json) values (?,?,?,?,?,?,?,'open','none','{}')",
                      (int(ch['id']),0,int(g['id']),int(d['id']),'border_raid',86,ch['location_a_id']))
        inc=int(cur.lastrowid)
        cs=generate_candidates(c,actor,'STRATEGIC',0,build_actor_context(c,actor,0))
        kinds={x.action_kind for x in cs if x.provider_key=='polity_conflict'}
        assert {'settle_incident','demand_incident_redress','limited_retaliation'} <= kinds
        assert 'launch_limited_campaign' not in kinds

        # Duplicate response bug: one formal demand removes every response candidate for that incident; stale execution is blocked.
        res=execute_political_action(c,actor,'demand_incident_redress',{'incident_id':inc},0); assert not res.get('blocked')
        cs=generate_candidates(c,actor,'STRATEGIC',0,build_actor_context(c,actor,0))
        assert not [x for x in cs if x.provider_key=='polity_conflict' and x.payload.get('incident_id')==inc]
        stale=execute_political_action(c,actor,'demand_incident_redress',{'incident_id':inc},0); assert stale.get('blocked')
        assert c.execute('select count(*) from conflict_responses where incident_id=?',(inc,)).fetchone()[0]==1

        # Independent fresh incident + explicit route proves campaign option is a consequence of physical feasibility.
        cur=c.execute("insert into conflict_incidents(channel_id,day,initiator_polity_id,target_polity_id,incident_kind,severity,location_id,status,response_state,metadata_json) values (?,?,?,?,?,?,?,'open','none','{}')",
                      (int(ch['id']),0,int(g['id']),int(d['id']),'border_raid',88,ch['location_a_id']))
        inc2=int(cur.lastrowid)
        c.execute("insert into travel_routes(from_location_id,to_location_id,route_kind,base_days,capacity,reliability,seasonal_sensitivity,bidirectional,status,metadata_json) values (?,?,?,?,?,?,?,?,?,?)",
                  (int(ch['location_b_id']),int(ch['location_a_id']),'road',4,70,80,1,1,'open',json.dumps({'test_only':True})))
        cs=generate_candidates(c,actor,'STRATEGIC',0,build_actor_context(c,actor,0)); camps=[x for x in cs if x.action_kind=='launch_limited_campaign' and x.payload.get('incident_id')==inc2]
        assert len(camps)==1
        before_other={(int(r['polity_a_id']),int(r['polity_b_id'])):(r['relation_kind'],float(r['stance']),float(r['trust']),float(r['tension']))
                      for r in c.execute("select * from political_relations where not (polity_a_id=? and polity_b_id=?)",tuple(sorted((int(g['id']),int(d['id']))))).fetchall()}
        cres=execute_political_action(c,actor,'launch_limited_campaign',camps[0].payload,0); assert not cres.get('blocked') and cres.get('operation_id')
        assert c.execute('select count(*) from war_campaign_operations').fetchone()[0]>=1
        after_other={(int(r['polity_a_id']),int(r['polity_b_id'])):(r['relation_kind'],float(r['stance']),float(r['trust']),float(r['tension']))
                     for r in c.execute("select * from political_relations where not (polity_a_id=? and polity_b_id=?)",tuple(sorted((int(g['id']),int(d['id']))))).fetchall()}
        assert before_other==after_other

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('ORGAGENCY/POLITYAGENCY/CONFLICT-01 adversarial acceptance PASS')
    finally:
        c.close()

if __name__=='__main__': main()
