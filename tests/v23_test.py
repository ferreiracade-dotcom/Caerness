from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, connect, init_db, reset_db
from engine.politics import (
    configure_polity, create_dynasty, add_dynasty_member, set_territorial_control,
    add_territorial_claim, add_succession_claim, create_political_link, add_political_process,
    politics_summary,
)
from engine.simulation import advance_connection


def actor(c,name,kind='character'):
    c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,?, 'active')",(name,kind))
    return int(c.execute("SELECT id FROM actors WHERE name=?",(name,)).fetchone()[0])


def run():
    reset_db(); init_db(); assert ENGINE_VERSION in {'0.23.0','0.24.0','0.25.0','0.26.0','0.26.1','0.27.1','0.28.0','0.29.0', '0.30.0','0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0'}
    with connect() as c:
        assert c.execute("SELECT COUNT(*) FROM political_polities").fetchone()[0]==0
        for n,k in [('North March','region'),('River Ward','region'),('South Vale','region')]:
            c.execute("INSERT INTO locations(name,kind) VALUES (?,?)",(n,k))
        north=int(c.execute("SELECT id FROM locations WHERE name='North March'").fetchone()[0])
        river=int(c.execute("SELECT id FROM locations WHERE name='River Ward'").fetchone()[0])
        south=int(c.execute("SELECT id FROM locations WHERE name='South Vale'").fetchone()[0])
        ia=actor(c,'Kingdom A','institution'); ib=actor(c,'Kingdom B','institution'); ic=actor(c,'March C','institution')
        ra=actor(c,'Ruler A'); heir=actor(c,'Heir A'); rival=actor(c,'Rival A')
        pa=configure_polity(c,ia,polity_kind='kingdom',ruler_actor_id=ra,succession_method='hereditary',stability=70)
        pb=configure_polity(c,ib,polity_kind='kingdom',stability=65)
        pc=configure_polity(c,ic,polity_kind='march',stability=55)
        dyn=create_dynasty(c,'House Test',home_polity_id=pa)
        add_dynasty_member(c,dyn,ra,status='head'); add_dynasty_member(c,dyn,heir,seniority=70)
        c.execute("UPDATE political_polities SET ruling_dynasty_id=? WHERE id=?",(dyn,pa))
        set_territorial_control(c,pa,north,legitimacy=80,integration=85)
        set_territorial_control(c,pb,river,legitimacy=65,integration=70)
        set_territorial_control(c,pb,south,legitimacy=55,integration=50)
        create_political_link(c,pb,pc,'vassalage',autonomy=60)
        add_succession_claim(c,pa,heir,dynasty_id=dyn,legitimacy=85,support=75,priority=80)
        add_succession_claim(c,pa,rival,legitimacy=45,support=30,priority=40)
        # This claim is configured to change the map if its campaign pressure reaches threshold.
        claim=add_territorial_claim(c,pa,river,claim_kind='treaty_claim',legitimacy=72,support=75,pressure=70,
                                    rate_per_30_days=10,threshold=75,resolution_policy='transfer',review_cadence_days=15)
        # Structural politics also progresses off camera.
        add_political_process(c,pa,'integration',location_id=north,rate_per_30_days=4,threshold=50,cadence_days=15)
        # Ruler dies; established succession claims must resolve at shared-clock review.
        c.execute("UPDATE actors SET status='dead' WHERE id=?",(ra,))
        advance_connection(c,30)
        p=c.execute("SELECT * FROM political_polities WHERE id=?",(pa,)).fetchone()
        assert int(p['ruler_actor_id'])==heir
        tc=c.execute("SELECT * FROM territorial_control WHERE location_id=?",(river,)).fetchone()
        assert int(tc['controller_polity_id'])==pa
        assert c.execute("SELECT status FROM territorial_claims WHERE id=?",(claim,)).fetchone()[0]=='fulfilled'
        assert c.execute("SELECT political_owner FROM locations WHERE id=?",(river,)).fetchone()[0]=='Kingdom A'
        assert c.execute("SELECT COUNT(*) FROM political_history WHERE transition_type='ruler_set'").fetchone()[0]>=1
        assert c.execute("SELECT COUNT(*) FROM political_history WHERE transition_type='territorial_control'").fetchone()[0]>=4
        assert c.execute("SELECT COUNT(*) FROM events WHERE event_type LIKE 'politics:%'").fetchone()[0]>=2
        s=politics_summary(c)
        assert s['polities']==3 and s['territories']==3 and s['history_entries']>=1
        c.commit()
    print('v0.23 politics/macro-history regression PASS')

if __name__=='__main__': run()
