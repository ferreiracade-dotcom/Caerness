from __future__ import annotations
import json, os, shutil, sqlite3, sys, time
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed, SOURCE_NAMESPACE
from engine.activation import activate_existing_loops
from engine.coverage import start_coverage_run, snapshot_coverage, coverage_gate, ten_year_gate, finish_coverage_run
from engine.simulation import advance_connection, current_day

OUT_DIR = Path(os.environ.get('CAERNESS_ONEYEAR_OUT', '/mnt/data/oneyear01_output')).resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = OUT_DIR / 'ONEYEAR01_diagnostic.db'
MIDYEAR_COPY = OUT_DIR / 'ONEYEAR01_day180_restart_source.db'
DIAG_JSON = OUT_DIR / 'ONEYEAR01_diagnostics.json'

MONTHLY_TARGETS = [30,60,90,120,150,180,210,240,270,300,330,360,365]


def table_exists(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def scalar(c, sql, params=(), default=0):
    try:
        r=c.execute(sql,params).fetchone()
        return default if not r or r[0] is None else r[0]
    except sqlite3.DatabaseError:
        return default

def count(c, table, where='1=1', params=()):
    if not table_exists(c, table): return 0
    return int(scalar(c, f'SELECT COUNT(*) FROM {table} WHERE {where}', params, 0))

def top_counts(c, table, col, where='1=1', limit=20):
    if not table_exists(c, table): return {}
    try:
        rows=c.execute(f'SELECT {col},COUNT(*) FROM {table} WHERE {where} GROUP BY {col} ORDER BY COUNT(*) DESC,{col} LIMIT ?', (limit,)).fetchall()
        return {str(r[0]):int(r[1]) for r in rows}
    except sqlite3.DatabaseError:
        return {}

def stock_by_good(c):
    if not table_exists(c,'commercial_stock'): return {}
    rows=c.execute('''SELECT COALESCE(g.name,CAST(s.good_id AS TEXT)),SUM(s.quantity)
                      FROM commercial_stock s LEFT JOIN market_goods g ON g.id=s.good_id
                      GROUP BY s.good_id ORDER BY s.good_id''').fetchall()
    return {str(r[0]):round(float(r[1] or 0),6) for r in rows}

def treasury_summary(c):
    if not table_exists(c,'regional_public_treasuries'): return {}
    r=c.execute("SELECT COUNT(*),COALESCE(SUM(cash),0),COALESCE(SUM(debt),0) FROM regional_public_treasuries").fetchone()
    return {'count':int(r[0]),'cash':round(float(r[1]),6),'debt':round(float(r[2]),6)}

def process_summary(c, run_id):
    if not table_exists(c,'process_execution_log'): return {}
    rows=c.execute('''SELECT process_key,COUNT(*),COALESCE(SUM(due_count),0),COALESCE(SUM(eligible_count),0),
                             COALESCE(SUM(executed_count),0),COALESCE(SUM(changed_count),0),COALESCE(SUM(blocked_count),0)
                      FROM process_execution_log WHERE coverage_run_id=? GROUP BY process_key ORDER BY process_key''',(run_id,)).fetchall()
    return {str(r[0]):{'runs':int(r[1]),'due':int(r[2] or 0),'eligible':int(r[3] or 0),'executed':int(r[4] or 0),'changed':int(r[5] or 0),'blocked':int(r[6] or 0)} for r in rows}

def required_process_failures(c, run_id):
    missing=[]
    rows=c.execute("SELECT domain_key,label,process_keys_json,autonomous_initiation_required,required_for_ten_year FROM coverage_registry ORDER BY domain_key").fetchall()
    psummary=process_summary(c,run_id)
    for r in rows:
        if not int(r[4] or 0) or not int(r[3] or 0):
            continue
        try: keys=json.loads(r[2] or '[]')
        except Exception: keys=[]
        if keys and not any(k in psummary for k in keys):
            missing.append({'domain_key':r[0],'label':r[1],'expected_process_keys':keys})
    return missing

def hard_invariants(c):
    failures=[]
    checks=[]
    def chk(label, sql, params=(), allow_zero=True):
        try: n=int(scalar(c,sql,params,0) or 0)
        except Exception as e:
            failures.append({'check':label,'error':str(e)}); return
        checks.append({'check':label,'violations':n})
        if n: failures.append({'check':label,'violations':n})
    chk('negative_commercial_stock', "SELECT COUNT(*) FROM commercial_stock WHERE quantity < -0.000001")
    if table_exists(c,'merchant_trade_contracts'):
        chk('trade_delivered_exceeds_quantity', "SELECT COUNT(*) FROM merchant_trade_contracts WHERE delivered_quantity > quantity + 0.000001 OR shipped_quantity > quantity + 0.000001 OR delivered_quantity < -0.000001 OR shipped_quantity < -0.000001")
    if table_exists(c,'commercial_shipments'):
        chk('nonpositive_shipment_quantity', "SELECT COUNT(*) FROM commercial_shipments WHERE quantity <= 0")
    if table_exists(c,'craft_production_orders'):
        chk('invalid_craft_output_quantity', "SELECT COUNT(*) FROM craft_production_orders WHERE requested_output_qty <= 0")
    if table_exists(c,'regional_public_treasuries'):
        chk('negative_public_debt', "SELECT COUNT(*) FROM regional_public_treasuries WHERE debt < -0.000001")
    if table_exists(c,'regional_public_projects'):
        chk('project_overconsumption', "SELECT COUNT(*) FROM regional_public_projects WHERE cash_spent > required_cash + 0.000001 OR labor_days_used > required_labor_days + 0.000001 OR material_quantity_used > required_material_quantity + 0.000001")
    if table_exists(c,'agriculture_harvests'):
        chk('negative_harvest', "SELECT COUNT(*) FROM agriculture_harvests WHERE actual_quantity < -0.000001")
    fk=c.execute('PRAGMA foreign_key_check').fetchall(); integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
    checks.append({'check':'foreign_keys','violations':len(fk)})
    checks.append({'check':'integrity','value':integrity})
    if fk: failures.append({'check':'foreign_keys','violations':len(fk),'sample':[tuple(x) for x in fk[:10]]})
    if integrity!='ok': failures.append({'check':'integrity','value':integrity})
    return {'pass':not failures,'checks':checks,'failures':failures}

def belief_firewall_audit(c):
    out={'decision_evaluations':count(c,'decision_evaluations'),'candidate_rows':count(c,'decision_candidate_audit'),'canon_basis_hits':0,'samples':[]}
    if table_exists(c,'decision_candidate_audit'):
        hits=c.execute("SELECT id,information_basis_json FROM decision_candidate_audit WHERE lower(information_basis_json) LIKE '%canon%' LIMIT 20").fetchall()
        out['canon_basis_hits']=len(hits)
        out['canon_basis_samples']=[{'id':int(r[0]),'basis':str(r[1])[:500]} for r in hits]
        rows=c.execute("SELECT id,provider_key,action_kind,information_basis_json FROM decision_candidate_audit WHERE selected=1 ORDER BY id DESC LIMIT 10").fetchall()
        out['samples']=[{'id':int(r[0]),'provider':r[1],'action':r[2],'basis':json.loads(r[3] or '{}')} for r in rows]
    return out

def snapshot(c, run_id, label):
    day=current_day(c)
    cov=snapshot_coverage(c,run_id,phase=label)
    states=Counter(x['state'] for x in cov)
    s={
      'label':label,'day':day,
      'coverage_states':dict(states),
      'coverage_failures':[x for x in cov if x['state'] in {'missing_mechanism','missing_population','missing_autonomy'} and x['domain_key']!='51_player_boundary'],
      'actors':{'all':count(c,'actors'),'active':count(c,'actors',"status='active'"),'deceased':count(c,'actors',"status IN ('deceased','dead')"),'characters':count(c,'actors',"actor_type='character'")},
      'households':count(c,'households',"status='active'"),'unions_active':count(c,'household_unions',"status='active'"),
      'enterprises':{'all':count(c,'civilian_enterprises'),'active':count(c,'civilian_enterprises',"status='active'")},
      'stock_total':round(float(scalar(c,'SELECT COALESCE(SUM(quantity),0) FROM commercial_stock',default=0)),6),
      'stock_by_good':stock_by_good(c),
      'shipments':top_counts(c,'commercial_shipments','status'),
      'trade_contracts':top_counts(c,'merchant_trade_contracts','status'),
      'craft_orders':top_counts(c,'craft_production_orders','status'),
      'harvests':count(c,'agriculture_harvests'),
      'health_conditions':top_counts(c,'health_conditions','status'),
      'care_requests':top_counts(c,'health_care_requests','status'),
      'medical_treatments':top_counts(c,'medical_treatments','status'),
      'law_cases':top_counts(c,'law_cases','status'),
      'war_operations':top_counts(c,'war_campaign_operations','status'),
      'underworld_orgs':top_counts(c,'underworld_organizations','organization_type',"status='active'"),
      'underworld_rackets':top_counts(c,'underworld_rackets','racket_kind',"status='active'") if table_exists(c,'underworld_rackets') else {},
      'protection_accounts':count(c,'underworld_protection_accounts',"status='active'"),
      'treasury':treasury_summary(c),
      'resolution_transitions':count(c,'resolution_transitions'),
      'resolution_to_levels':top_counts(c,'resolution_transitions','to_level'),
      'latent_entities':top_counts(c,'latent_entities','status'),
      'institution_candidates':top_counts(c,'emergent_institution_candidates','status'),
      'events':count(c,'events'),'event_types':top_counts(c,'events','event_type',limit=25),
      'decisions':count(c,'decision_evaluations'),
      'beliefs':count(c,'actor_beliefs'),
      'processes':process_summary(c,run_id),
      'invariants':hard_invariants(c),
    }
    return s

def main():
    os.environ['CAERNESS_DB_PATH']=str(DB_PATH)
    os.environ['CAERNESS_TEST_MODE']='1'
    if DB_PATH.exists(): DB_PATH.unlink()
    reset_db(force=True,backup=False); init_db()
    c=connect(); seed=import_current_seed(c); activation=activate_existing_loops(c); c.commit()
    opening_gate=coverage_gate(c)
    decade_before=ten_year_gate(c)
    if not opening_gate['pass']:
        raise AssertionError(('opening coverage failed',opening_gate))
    if decade_before['pass'] or decade_before.get('one_year_unattended_passed'):
        raise AssertionError(('ten-year gate should be closed before ONEYEAR-01',decade_before))
    run_id=start_coverage_run(c,'ONEYEAR-01 integrated ordinary unattended run',source_seed_namespace=SOURCE_NAMESPACE,
                              engine_version=ENGINE_VERSION,schema_version=SCHEMA_VERSION,
                              metadata={'unattended':True,'target_days':365,'player_selected':False})
    c.commit()
    diagnostics={'engine_version':ENGINE_VERSION,'schema_version':SCHEMA_VERSION,'coverage_run_id':run_id,
                 'seed_result':seed,'activation_result':activation,'opening_gate':opening_gate,'ten_year_gate_before':decade_before,
                 'started_wall_time':time.time(),'snapshots':[],'restart':{},'anomalies':[]}
    diagnostics['snapshots'].append(snapshot(c,run_id,'opening'))
    last=0
    for target in MONTHLY_TARGETS:
        step=target-last
        t0=time.perf_counter()
        advance_connection(c,step)
        c.commit()
        elapsed=time.perf_counter()-t0
        snap=snapshot(c,run_id,f'day_{target}')
        snap['advance_wall_seconds']=round(elapsed,6)
        diagnostics['snapshots'].append(snap)
        if not snap['invariants']['pass']:
            diagnostics['anomalies'].append({'day':target,'kind':'hard_invariant','details':snap['invariants']['failures']})
            DIAG_JSON.write_text(json.dumps(diagnostics,indent=2,sort_keys=True,default=str))
            raise AssertionError(('hard invariant failed',target,snap['invariants']['failures']))
        print(f"DAY {target}: {elapsed:.3f}s events={snap['events']} actors={snap['actors']['all']} stock={snap['stock_total']} resolutions={snap['resolution_transitions']}", flush=True)
        if target==180:
            # Explicit save/close/reopen boundary. Copy the persisted save before reopening as evidence.
            c.commit(); c.close()
            shutil.copy2(DB_PATH,MIDYEAR_COPY)
            c=connect()
            assert current_day(c)==180
            rr=c.execute("SELECT status FROM coverage_runs WHERE id=?",(run_id,)).fetchone()
            diagnostics['restart']={'day':180,'coverage_run_status_after_reopen':rr[0] if rr else None,'persisted':True}
            print('MIDYEAR RESTART: reopened persisted day-180 database', flush=True)
        last=target
    final_gate=coverage_gate(c,run_id)
    process_missing=required_process_failures(c,run_id)
    firewall=belief_firewall_audit(c)
    invariants=hard_invariants(c)
    finish_coverage_run(c,run_id,status='completed')
    c.commit()
    final_process=process_summary(c,run_id)
    diagnostics['final_gate']=final_gate
    diagnostics['required_process_failures']=process_missing
    diagnostics['belief_firewall']=firewall
    diagnostics['final_invariants']=invariants
    diagnostics['final_process_summary']=final_process
    diagnostics['end_day']=current_day(c)
    diagnostics['finished_wall_time']=time.time()
    diagnostics['pass_pre_acceptance']=bool(final_gate['pass'] and not process_missing and invariants['pass'] and firewall['canon_basis_hits']==0 and current_day(c)==365)
    c.close()
    DIAG_JSON.write_text(json.dumps(diagnostics,indent=2,sort_keys=True,default=str))
    print('FINAL',json.dumps({'end_day':diagnostics['end_day'],'pass_pre_acceptance':diagnostics['pass_pre_acceptance'],
                             'process_missing':process_missing,'canon_basis_hits':firewall['canon_basis_hits'],
                             'coverage_failures':final_gate['failure_count'],'invariants':invariants['pass']},sort_keys=True),flush=True)
    if not diagnostics['pass_pre_acceptance']:
        raise SystemExit(2)

if __name__=='__main__':
    main()
