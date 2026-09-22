"""REL-02: interaction outcomes create directional social memory and repeated refusals close unchanged approaches."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, SCHEMA_VERSION
from engine.interactions import create_interaction, resolve_interaction
from engine.relationships import relationship_view


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_rel02_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(c,name):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",(name,)).lastrowid)
    c.execute("INSERT INTO actor_drives(actor_id,aggression,risk_tolerance,patience,loyalty,ambition,pragmatism) VALUES (?,?,?,?,?,?,?)",(aid,.5,.5,.5,.5,.5,.5))
    return aid


def run():
    assert SCHEMA_VERSION>=106
    c,path=bootstrap(); a=actor(c,'[REL02] A'); b=actor(c,'[REL02] B')
    terms={'purpose':'same repeated request','burden':10.0,'incentive':0.0}
    ids=[]
    for day in (0,20,40):
        iid=create_interaction(c,a,b,'request',day,stakes=2,terms=terms)
        result=resolve_interaction(c,iid,day+20)
        assert result.status=='rejected',result
        ids.append(iid)
    av=relationship_view(c,a,b); bv=relationship_view(c,b,a)
    assert av['resentment']>=3 and av['trust']<=-6,av
    assert bv['professional_confidence']<0,bv
    hist=c.execute("SELECT * FROM relationship_history WHERE source_kind='interaction' ORDER BY id").fetchall()
    assert len(hist)>=6 and {int(r['source_id']) for r in hist}>={ids[0],ids[1],ids[2]}

    # A fourth unchanged approach inside the cooldown is suppressed by returning the last real refusal.
    fourth=create_interaction(c,a,b,'request',60,stakes=2,terms=terms)
    assert fourth==ids[-1],(fourth,ids)
    assert c.execute("SELECT COUNT(*) FROM interactions WHERE proposer_actor_id=? AND recipient_actor_id=? AND interaction_type='request'",(a,b)).fetchone()[0]==3

    # A materially different subject remains possible: memory constrains repetition, not agency generally.
    different=create_interaction(c,a,b,'request',60,stakes=2,terms={'purpose':'different request','burden':0})
    assert different!=ids[-1]

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('REL-02 interaction memory: PASS')

if __name__=='__main__':run()
