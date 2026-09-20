from __future__ import annotations

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.resolution_controller import create_institution_candidate, update_institution_candidate, crystallize_institution_candidate
from engine.organization_agency import start_regime
from engine.organization_lifecycle import merge_polities, unify_polities
from engine.politics import add_political_process
from engine.simulation import advance_connection


def setup_world():
    reset_db(force=True, backup=False)
    init_db()
    c=connect()
    import_current_seed(c)
    activate_existing_loops(c)
    c.commit()
    return c


def polity(c,name):
    return c.execute("select p.* from political_polities p join actors a on a.id=p.institution_actor_id where a.name=?",(name,)).fetchone()


def main():
    c=setup_world()
    try:
        assert int(c.execute("select value from engine_meta where key='schema_version'").fetchone()[0])>=81
        active_profiles=int(c.execute("select count(*) from institution_profiles ip join actors a on a.id=ip.actor_id where a.status='active'").fetchone()[0])
        life_profiles=int(c.execute("select count(*) from organization_lifecycle_profiles").fetchone()[0])
        assert life_profiles==active_profiles
        assert c.execute("select count(*) from political_polities").fetchone()[0]==7
        assert c.execute("select count(*) from polity_lifecycle_profiles").fetchone()[0]==7
        assert c.execute("select count(*) from organization_lifecycle_events").fetchone()[0]==0, 'activation must not invent lifecycle history'

        # A causally eligible organization can exist without a socially known name.
        loc=int(c.execute("select id from locations where name='Aldergate'").fetchone()[0])
        cid=create_institution_candidate(c,'merchant concern',location_id=loc,significance_score=10,
                                         evidence=[{'kind':'trade_relationship','source':'ORGLIFE acceptance'}])
        update_institution_candidate(c,cid,significance_score=40)
        aid=crystallize_institution_candidate(c,cid)
        a=c.execute("select * from actors where id=?",(aid,)).fetchone()
        assert str(a['name']).startswith('[STRUCTURAL] merchant concern candidate #')
        assert 'name unresolved' in str(a['notes'])
        assert c.execute("select 1 from organization_lifecycle_profiles where institution_actor_id=?",(aid,)).fetchone()
        assert c.execute("select 1 from organization_agency_profiles where institution_actor_id=?",(aid,)).fetchone()
        assert c.execute("select count(*) from organization_lifecycle_events where institution_actor_id=? and event_type='formation'",(aid,)).fetchone()[0]==1

        # Government/regime replacement changes who governs, not which country exists.
        g=polity(c,'Greywood'); gi=int(g['institution_actor_id'])
        old_lineage=int(c.execute("select count(*) from organization_lineage_links where predecessor_institution_actor_id=? or successor_institution_actor_id=?",(gi,gi)).fetchone()[0])
        gov_actor=int(c.execute("select decision_actor_id from polity_government_actors where polity_id=?",(int(g['id']),)).fetchone()[0])
        start_regime(c,gi,leader_actor_id=gov_actor,regime_kind='acceptance_test_regime',worldview={'frontier':'harder'})
        assert c.execute("select status from political_polities where id=?",(int(g['id']),)).fetchone()[0]!='dissolved'
        assert c.execute("select count(*) from organization_lineage_links where predecessor_institution_actor_id=? or successor_institution_actor_id=?",(gi,gi)).fetchone()[0]==old_lineage

        # Country fission requires a real territorial separatist process. Low integration alone is not enough.
        west=int(c.execute("select id from locations where name='Westbrook'").fetchone()[0])
        old_channel=int(c.execute("select id from conflict_channels where channel_key='greywood_dunmoor_westbrook_stoneford'").fetchone()[0])
        c.execute("update territorial_control set integration=10 where location_id=? and controller_polity_id=?",(west,int(g['id'])))
        proc=add_political_process(c,int(g['id']),'separatism',location_id=west,rate_per_30_days=5,volatility=0,
                                   threshold=10,auto_action='fragment',cadence_days=30,notes='ORGLIFE acceptance separatism')
        advance_connection(c,90)
        newp=c.execute("select * from political_polities where id>7 and status<>'dissolved' order by id desc limit 1").fetchone()
        assert newp and int(c.execute("select controller_polity_id from territorial_control where location_id=?",(west,)).fetchone()[0])==int(newp['id'])
        new_iid=int(newp['institution_actor_id'])
        assert c.execute("select 1 from polity_government_actors where polity_id=?",(int(newp['id']),)).fetchone()
        assert c.execute("select sovereignty_status from polity_lifecycle_profiles where polity_id=?",(int(newp['id']),)).fetchone()[0]=='sovereign'
        assert c.execute("select count(*) from organization_lineage_links where predecessor_institution_actor_id=? and successor_institution_actor_id=? and link_kind='secession'",(gi,new_iid)).fetchone()[0]==1
        assert c.execute("select status from conflict_channels where id=?",(old_channel,)).fetchone()[0]=='resolved'
        assert c.execute("select count(*) from conflict_channels where status='active' and (polity_a_id=? or polity_b_id=?)",(int(newp['id']),int(newp['id']))).fetchone()[0]>=1
        assert c.execute("select active from political_processes where id=?",(proc,)).fetchone()[0]==0

        # Re-absorption is country death for the breakaway polity, not a regime change.
        merge_polities(c,int(g['id']),int(newp['id']),reason='ORGLIFE acceptance reabsorption')
        assert c.execute("select status from political_polities where id=?",(int(newp['id']),)).fetchone()[0]=='dissolved'
        assert c.execute("select status from actors where id=?",(new_iid,)).fetchone()[0]=='inactive'
        assert c.execute("select lifecycle_status from organization_lifecycle_profiles where institution_actor_id=?",(new_iid,)).fetchone()[0]=='absorbed'
        assert int(c.execute("select controller_polity_id from territorial_control where location_id=?",(west,)).fetchone()[0])==int(g['id'])
        assert c.execute("select count(*) from organization_lineage_links where predecessor_institution_actor_id=? and successor_institution_actor_id=? and link_kind='absorption'",(new_iid,gi)).fetchone()[0]==1

        # A union can also produce a genuinely new country rather than choosing one old state as survivor.
        w=polity(c,'Windmere'); s=polity(c,'Sunreach Confederacy')
        predecessor_territories=int(c.execute("select count(*) from territorial_control where controller_polity_id in (?,?)",(int(w['id']),int(s['id']))).fetchone()[0])
        union_pid=unify_polities(c,[int(w['id']),int(s['id'])],reason='ORGLIFE acceptance union')
        union=c.execute("select * from political_polities where id=?",(union_pid,)).fetchone(); union_iid=int(union['institution_actor_id'])
        assert c.execute("select count(*) from territorial_control where controller_polity_id=?",(union_pid,)).fetchone()[0]==predecessor_territories
        assert all(c.execute("select status from political_polities where id=?",(pid,)).fetchone()[0]=='dissolved' for pid in (int(w['id']),int(s['id'])))
        assert c.execute("select count(*) from organization_lineage_links where successor_institution_actor_id=? and link_kind='merger'",(union_iid,)).fetchone()[0]==2
        assert c.execute("select 1 from polity_government_actors where polity_id=?",(union_pid,)).fetchone()
        assert c.execute("select status from actors where id=?",(union_iid,)).fetchone()[0]=='active'

        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not c.execute('pragma foreign_key_check').fetchall()
        print('ORGLIFE-01 country/institution lifecycle adversarial acceptance PASS')
    finally:
        c.close()


if __name__=='__main__':
    main()
