from __future__ import annotations
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION,SCHEMA_VERSION,reset_db,init_db,connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.groundbinding import process_due_groundbinding,groundbinding_context
from engine.cultivation import _cultivation_context


def run():
    assert ENGINE_VERSION in {'0.47.0','0.54.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION>=47
    old=os.environ.get('CAERNESS_DB_PATH'); os.environ['CAERNESS_DB_PATH']='/tmp/caerness_v47.db'
    try:
        reset_db(force=True);init_db(); c=connect();import_current_seed(c);activate_existing_loops(c)
        rows=c.execute("SELECT a.name,g.* FROM groundbinding_profiles g JOIN actors a ON a.id=g.actor_id ORDER BY a.name").fetchall()
        assert [r['name'] for r in rows]==['Clement Bray','Rowena Fitch'],[r['name'] for r in rows]
        assert c.execute("SELECT COUNT(*) FROM groundbinding_profiles g JOIN actors a ON a.id=g.actor_id WHERE a.name='Vincent Greaves'").fetchone()[0]==0
        silent=int(c.execute("SELECT id FROM locations WHERE name='Silent Peak'").fetchone()[0])
        cairn=int(c.execute("SELECT id FROM locations WHERE name='Cairnholt'").fetchone()[0])
        crownhold=int(c.execute("SELECT id FROM locations WHERE name='Crownhold'").fetchone()[0])
        rowena=int(c.execute("SELECT id FROM actors WHERE name='Rowena Fitch'").fetchone()[0])
        clement=int(c.execute("SELECT id FROM actors WHERE name='Clement Bray'").fetchone()[0])
        assert groundbinding_context(c,rowena)['inside'] is True
        ctx=_cultivation_context(c,rowena,'Breach')
        assert ctx['groundbinding']['inside'] is True and ctx['groundbinding']['vessel_factor']>1

        # Ordinary absence is gradual, not a boundary death trigger.
        c.execute("UPDATE actors SET current_location_id=? WHERE id=?",(cairn,rowena))
        for day in range(14,99,14):
            c.execute("UPDATE world_state SET current_day=? WHERE id=1",(day,));process_due_groundbinding(c,day)
        g=c.execute("SELECT * FROM groundbinding_profiles WHERE actor_id=?",(rowena,)).fetchone()
        assert g['dependency_state'] in ('straining','failing'),dict(g)
        assert float(g['mismatch_burden'])<90
        stage_before=c.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(rowena,)).fetchone()[0]

        # Returning in time reverses early/failing mismatch.
        c.execute("UPDATE actors SET current_location_id=? WHERE id=?",(silent,rowena))
        for day in range(112,211,14):
            c.execute("UPDATE world_state SET current_day=? WHERE id=1",(day,));process_due_groundbinding(c,day)
        g=c.execute("SELECT * FROM groundbinding_profiles WHERE actor_id=?",(rowena,)).fetchone()
        assert g['dependency_state']=='comfortable' and float(g['mismatch_burden'])<8,dict(g)
        assert c.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(rowena,)).fetchone()[0]==stage_before

        # Prolonged absence under active cultivation can become catastrophic; earned Stage is not erased.
        c.execute("UPDATE actors SET current_location_id=? WHERE id=?",(crownhold,clement))
        fifth=c.execute("SELECT current_stage FROM cultivation_profiles WHERE actor_id=?",(clement,)).fetchone()[0]
        for day in range(224,729,14):
            c.execute("UPDATE world_state SET current_day=? WHERE id=1",(day,));process_due_groundbinding(c,day)
            if c.execute("SELECT dependency_state FROM groundbinding_profiles WHERE actor_id=?",(clement,)).fetchone()[0]=='catastrophic': break
        g=c.execute("SELECT * FROM groundbinding_profiles WHERE actor_id=?",(clement,)).fetchone()
        assert g['dependency_state']=='catastrophic',dict(g)
        cp=c.execute("SELECT current_stage,core_state,active,status FROM cultivation_profiles WHERE actor_id=?",(clement,)).fetchone()
        assert cp['current_stage']==fifth and cp['core_state']=='Damaged-Core' and int(cp['active'])==0 and cp['status']=='incapacitated',dict(cp)
        assert c.execute("SELECT COUNT(*) FROM health_conditions WHERE actor_id=? AND label='Groundbinding mismatch'",(clement,)).fetchone()[0]>=1
        c.close()
    finally:
        if old is None: os.environ.pop('CAERNESS_DB_PATH',None)
        else: os.environ['CAERNESS_DB_PATH']=old
    print('v0.47.0 Groundbinding dependency regression PASS')

if __name__=='__main__': run()
