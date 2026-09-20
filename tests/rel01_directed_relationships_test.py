"""REL-01 acceptance: directional social/evaluative relationships."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import reset_db, init_db, connect, ENGINE_VERSION, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.relationships import relationship_view, ensure_reciprocal_relationship, adjust_relationship
from engine.decisions import build_actor_context

def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_rel01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit(); return c,path

def run():
    assert ENGINE_VERSION=='0.60.0' and SCHEMA_VERSION>=60
    c,path=bootstrap()
    assert c.execute("SELECT value FROM engine_meta WHERE key='directed_relationship_model_version'").fetchone()[0]=='1'
    # Fresh callers can deliberately create reciprocal initial state without making it permanently shared.
    ids0=[int(r[0]) for r in c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id LIMIT 4").fetchall()]
    a,b=ids0[0],ids0[1]
    c.execute("DELETE FROM relationships WHERE (actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)",(a,b,b,a))
    ensure_reciprocal_relationship(c,a,b,9,stance=12,trust=20,obligation=5,familiarity=30)
    av=relationship_view(c,a,b); bv=relationship_view(c,b,a)
    assert av==bv, (av,bv)
    # One direction can change without mutating the reverse direction.
    adjust_relationship(c,a,b,10,trust_delta=17,respect_delta=9,resentment_delta=4,familiarity_delta=5)
    av2=relationship_view(c,a,b); bv2=relationship_view(c,b,a)
    assert av2['trust']==av['trust']+17 and bv2['trust']==bv['trust']
    assert av2['respect']==9 and bv2['respect']==0
    assert av2['resentment']==4 and bv2['resentment']==0
    # Decision context sees the actor's own view, not a symmetric average or the target's view.
    ctxa=build_actor_context(c,a,10,canon_limit=0); ctxb=build_actor_context(c,b,10,canon_limit=0)
    ra=next(r for r in ctxa['relationships'] if int(r['actor_b_id'])==b)
    rb=next(r for r in ctxb['relationships'] if int(r['actor_b_id'])==a)
    assert float(ra['trust'])==av2['trust'] and float(rb['trust'])==bv2['trust']
    # Structural ties remain separate from evaluative relationships.
    assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kinship_links'").fetchone()
    assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='household_unions'").fetchone()
    assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='teaching_relationships'").fetchone()
    # A one-sided view is legal: knowing/evaluating someone need not force the target to reciprocate.
    ids=[int(r[0]) for r in c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id LIMIT 3").fetchall()]
    x,y=ids[-2],ids[-1]
    c.execute("DELETE FROM relationships WHERE (actor_a_id=? AND actor_b_id=?) OR (actor_a_id=? AND actor_b_id=?)",(x,y,y,x))
    adjust_relationship(c,x,y,11,trust_delta=3,familiarity_delta=15)
    assert relationship_view(c,x,y)['trust']==3
    assert relationship_view(c,y,x)['trust']==0
    assert c.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?",(y,x)).fetchone() is None
    # No protagonist privilege: API contains no player branch and can diverge arbitrary NPC pair.
    adjust_relationship(c,y,x,12,fear_delta=7)
    assert relationship_view(c,x,y)['fear']==0 and relationship_view(c,y,x)['fear']==7
    # Schema dimensions exist.
    cols={r[1] for r in c.execute('PRAGMA table_info(relationships)').fetchall()}
    required={'familiarity','trust','affection','respect','fear','loyalty','resentment','obligation','professional_confidence'}
    assert required<=cols
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
    c.commit(); c.close(); print('REL-01 directed relationship tests: PASS')

if __name__=='__main__': run()
