from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.politics import *
from engine.simulation import advance_connection


def actor(c,n,t='character',status='active'):
    c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,?,?)",(n,t,status)); return int(c.execute("SELECT id FROM actors WHERE name=?",(n,)).fetchone()[0])

def must_fail(fn):
    try: fn()
    except (ValueError,sqlite3.IntegrityError, Exception) as e:
        if isinstance(e, AssertionError): raise
        return
    raise AssertionError('expected failure')

import sqlite3

def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'}
    with connect() as c:
        assert c.execute("SELECT COUNT(*) FROM political_polities").fetchone()[0]==0
        l1=c.execute("INSERT INTO locations(name,kind) VALUES ('Aland','region')").lastrowid
        l2=c.execute("INSERT INTO locations(name,kind) VALUES ('Bland','region')").lastrowid
        i1=actor(c,'State One','institution'); i2=actor(c,'State Two','institution'); i3=actor(c,'State Three','institution')
        p1=configure_polity(c,i1,polity_kind='kingdom',review_cadence_days=10)
        p2=configure_polity(c,i2,polity_kind='kingdom',review_cadence_days=10)
        p3=configure_polity(c,i3,polity_kind='duchy',review_cadence_days=10)
        noninst=actor(c,'Ordinary Person')
        dead=actor(c,'Dead Person',status='dead')
        must_fail(lambda: configure_polity(c,noninst,polity_kind='kingdom'))
        must_fail(lambda: set_ruler(c,p1,dead))
        set_territorial_control(c,p1,l1)
        # A location has one authoritative controller; second assignment transfers rather than duplicates.
        set_territorial_control(c,p2,l1,reason='test transfer')
        assert c.execute("SELECT COUNT(*) FROM territorial_control WHERE location_id=?",(l1,)).fetchone()[0]==1
        assert c.execute("SELECT controller_polity_id FROM territorial_control WHERE location_id=?",(l1,)).fetchone()[0]==p2
        # Hierarchical political cycles are invalid.
        create_political_link(c,p1,p2,'vassalage')
        create_political_link(c,p2,p3,'vassalage')
        must_fail(lambda: create_political_link(c,p3,p1,'vassalage'))
        # A territorial state cannot simply disappear and orphan its land.
        must_fail(lambda: dissolve_polity(c,p2))
        # Tie/near-tie succession is a crisis, not an arbitrary coronation.
        a=actor(c,'Claimant A'); b=actor(c,'Claimant B'); old=actor(c,'Old Ruler')
        set_ruler(c,p1,old)
        add_succession_claim(c,p1,a,legitimacy=60,support=50,priority=50)
        add_succession_claim(c,p1,b,legitimacy=60,support=50,priority=50)
        c.execute("UPDATE actors SET status='dead' WHERE id=?",(old,))
        advance_connection(c,10)
        r=c.execute("SELECT ruler_actor_id,status FROM political_polities WHERE id=?",(p1,)).fetchone()
        assert r['ruler_actor_id'] is None and r['status']=='succession_crisis'
        # Dead claimants are not chosen.
        c.execute("UPDATE actors SET status='dead' WHERE id=?",(a,)); c.execute("UPDATE political_succession_claims SET support=90 WHERE claimant_actor_id=?",(a,))
        chosen=resolve_succession(c,p1,require_clear_margin=False)
        assert chosen==b
        # Claim pressure below threshold does not prematurely alter control.
        set_territorial_control(c,p2,l2)
        cl=add_territorial_claim(c,p1,l2,pressure=10,rate_per_30_days=1,threshold=90,resolution_policy='transfer',review_cadence_days=10)
        advance_connection(c,10)
        assert c.execute("SELECT controller_polity_id FROM territorial_control WHERE location_id=?",(l2,)).fetchone()[0]==p2
        # Dissolution with a successor transfers all controlled territory and closes hierarchy links.
        dissolve_polity(c,p2,successor_polity_id=p3,reason='edge successor test')
        assert c.execute("SELECT status FROM political_polities WHERE id=?",(p2,)).fetchone()[0]=='dissolved'
        assert c.execute("SELECT COUNT(*) FROM territorial_control WHERE controller_polity_id=?",(p2,)).fetchone()[0]==0
        assert c.execute("SELECT controller_polity_id FROM territorial_control WHERE location_id=?",(l1,)).fetchone()[0]==p3
        must_fail(lambda: set_territorial_control(c,p2,l1))
        # Every map mutation has durable history.
        assert c.execute("SELECT COUNT(*) FROM political_history").fetchone()[0]>=8
        c.commit()
    print('v0.23 adversarial politics edge audit PASS')

if __name__=='__main__': run()
