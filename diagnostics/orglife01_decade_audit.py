from __future__ import annotations
import json, os, sqlite3, sys, time
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import reset_db,init_db,connect,SCHEMA_VERSION,ENGINE_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.simulation import advance_connection,current_day

OUT=Path(os.environ.get('CAERNESS_ORGLIFE_DECADE_OUT','/mnt/data/caerness_orglife')).resolve(); OUT.mkdir(parents=True,exist_ok=True)
DB=OUT/'SCHEMA81_ORGLIFE_DECADE.db'; REPORT=OUT/'SCHEMA81_ORGLIFE_DECADE_AUDIT.json'

def count(c,t,where='1=1'):
    try:return int(c.execute(f'SELECT COUNT(*) FROM {t} WHERE {where}').fetchone()[0])
    except sqlite3.DatabaseError:return 0

def grouped(c,sql): return {str(r[0]):int(r[1]) for r in c.execute(sql).fetchall()}

def snap(c,year):
    return {
      'year':year,'day':current_day(c),
      'actors':count(c,'actors'),
      'active_institutions':int(c.execute("SELECT COUNT(*) FROM institution_profiles ip JOIN actors a ON a.id=ip.actor_id WHERE a.status='active'").fetchone()[0]),
      'institution_kinds':grouped(c,"SELECT ip.institution_kind,COUNT(*) FROM institution_profiles ip JOIN actors a ON a.id=ip.actor_id WHERE a.status='active' GROUP BY ip.institution_kind ORDER BY COUNT(*) DESC,ip.institution_kind"),
      'lifecycle_status':grouped(c,"SELECT lifecycle_status,COUNT(*) FROM organization_lifecycle_profiles GROUP BY lifecycle_status ORDER BY lifecycle_status"),
      'lifecycle_events':grouped(c,"SELECT event_type,COUNT(*) FROM organization_lifecycle_events GROUP BY event_type ORDER BY event_type"),
      'lineage_links':grouped(c,"SELECT link_kind,COUNT(*) FROM organization_lineage_links GROUP BY link_kind ORDER BY link_kind"),
      'polities_active':count(c,'political_polities',"status!='dissolved'"),
      'polities_dissolved':count(c,'political_polities',"status='dissolved'"),
      'sovereignty':grouped(c,"SELECT sovereignty_status,COUNT(*) FROM polity_lifecycle_profiles GROUP BY sovereignty_status ORDER BY sovereignty_status"),
      'merchant_candidates':grouped(c,"SELECT candidate_kind||':'||status,COUNT(*) FROM emergent_institution_candidates GROUP BY candidate_kind,status ORDER BY candidate_kind,status"),
      'underworld_orgs_active':count(c,'underworld_organizations',"status='active'"),
      'conflict_incidents':count(c,'conflict_incidents'),
      'conflict_responses':count(c,'conflict_responses'),
      'campaign_operations':count(c,'war_campaign_operations'),
      'enterprises_active':count(c,'civilian_enterprises',"status='active'"),
      'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],
      'fk':len(c.execute('PRAGMA foreign_key_check').fetchall()),
    }

def main():
    os.environ['CAERNESS_DB_PATH']=str(DB); os.environ['CAERNESS_TEST_MODE']='1'
    if DB.exists(): DB.unlink()
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    report={'engine_version':ENGINE_VERSION,'schema_version':SCHEMA_VERSION,'snapshots':[snap(c,0)],'started':time.time()}
    for year in range(1,11):
        t=time.perf_counter(); advance_connection(c,365); c.commit(); elapsed=time.perf_counter()-t
        s=snap(c,year); s['advance_seconds']=round(elapsed,4); report['snapshots'].append(s)
        REPORT.write_text(json.dumps(report,indent=2,sort_keys=True))
        print(json.dumps({'year':year,'day':s['day'],'seconds':s['advance_seconds'],'institutions':s['active_institutions'],'polities':s['polities_active'],'dissolved':s['polities_dissolved'],'lifecycle_events':s['lifecycle_events'],'merchant_candidates':s['merchant_candidates'],'incidents':s['conflict_incidents'],'campaigns':s['campaign_operations'],'integrity':s['integrity'],'fk':s['fk']},sort_keys=True),flush=True)
        if s['integrity']!='ok' or s['fk']:
            raise SystemExit(2)
    report['finished']=time.time(); report['elapsed_seconds']=round(report['finished']-report['started'],3)
    REPORT.write_text(json.dumps(report,indent=2,sort_keys=True))
    c.close()
if __name__=='__main__':main()
