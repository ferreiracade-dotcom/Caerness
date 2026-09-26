"""ROUTES-01: the canon travel graph connects the world the World Bible describes, at canon travel times."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.ecology import find_route_path
from engine.route_network import ensure_canon_route_network, unreachable_places


def run():
    path=Path(tempfile.gettempdir())/f'caerness_routes01_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect()
    import_current_seed(c); activate_existing_loops(c); c.commit()
    loc=lambda n: int(c.execute("SELECT id FROM locations WHERE name=?",(n,)).fetchone()[0])
    def days(a,b):
        p=find_route_path(c,loc(a),loc(b),day=0)
        assert p,(a,b)
        return sum(float(c.execute("SELECT base_days FROM travel_routes WHERE id=?",(r,)).fetchone()[0]) for r in p)

    # "The geography is intentionally connective rather than zoned": every travel destination is reachable.
    assert unreachable_places(c)==[],unreachable_places(c)
    assert ensure_canon_route_network(c)['routes01_added']==0      # idempotent

    # Canon travel-time table (Part 20), ordinary caravan days, is honoured by the shortest path.
    for a,b,lo,hi in [('Aldergate','Cairnholt',4,6),('Cairnholt','Waymeet',2,3),('Cairnholt','Lysmere',5,7),
                      ('Cairnholt','Toll’s Reach',12,16),('Cairnholt','Grand Coven complex',10,14),('Cairnholt','Aldenmoor',5,7)]:
        assert lo<=days(a,b)<=hi,(a,b,days(a,b))
    # The capital is not closer to Cairnholt through Highford than through the Aldergate corridor.
    assert 7<=days('Crownhold','Cairnholt')<=9,days('Crownhold','Cairnholt')

    # Stonegate crosses the northern Spine into Greywood (a trade crossing, not a war frontier).
    sg=loc('Stonegate Pass')
    assert any(c.execute("SELECT political_owner FROM locations WHERE id=?",(int(r[0] if int(r[1])==sg else r[1]),)).fetchone()[0]=='Greywood'
               for r in c.execute("SELECT from_location_id,to_location_id FROM travel_routes WHERE ? IN (from_location_id,to_location_id)",(sg,)).fetchall())
    # Every capital reaches every other; outer kingdoms are farther than the Hearth's own scale.
    capitals=['Crownhold','Ravenfield','Eldenfell','Saltmere','Sunreach','Brackenfell','Stormhollow']
    for i,a in enumerate(capitals):
        for b in capitals[i+1:]:
            assert days(a,b)>=5,(a,b)

    # Every frontier pressure channel has both endpoints and a traversable route between them, so an
    # incident that escalates far enough can become a real campaign.
    for key,la,lb in c.execute("SELECT channel_key,location_a_id,location_b_id FROM conflict_channels").fetchall():
        assert la is not None and lb is not None,key
        assert find_route_path(c,int(la),int(lb),day=0),key
    assert c.execute("SELECT 1 FROM conflict_channels WHERE channel_key='thornward_stormhollow_southern_ridges'").fetchone()
    east_west=c.execute("SELECT la.name,lb.name FROM conflict_channels ch JOIN locations la ON la.id=ch.location_a_id JOIN locations lb ON lb.id=ch.location_b_id WHERE channel_key='underheaven_thornward_armed_corridor'").fetchone()
    assert tuple(east_west)==('Eastwatch','Westgate'),tuple(east_west)
    # Channels see their frontier's issue pressure (the kinds are named differently; the lookup had silently read 0).
    from engine.conflict import _issue_pressure
    for key,a,b,kind in c.execute("SELECT channel_key,polity_a_id,polity_b_id,issue_kind FROM conflict_channels").fetchall():
        assert max(_issue_pressure(c,a,b,kind),_issue_pressure(c,b,a,kind))>0,key
    # Military geometry is projected from the new roads too.
    assert c.execute("SELECT COUNT(*) FROM conflict_geometries WHERE geometry_kind='civilian_route'").fetchone()[0]>=c.execute("SELECT COUNT(*) FROM travel_routes").fetchone()[0]-5

    # Every route records its basis and certainty.
    assert c.execute("""SELECT COUNT(*) FROM travel_routes WHERE json_extract(metadata_json,'$.authority')='ROUTES01_CANON_NETWORK'
                        AND (json_extract(metadata_json,'$.basis') IS NULL OR json_extract(metadata_json,'$.certainty') IS NULL)""").fetchone()[0]==0
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    n=c.execute("SELECT COUNT(*) FROM travel_routes").fetchone()[0]
    c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('ROUTES-01 canon network: PASS',{'routes':n})

if __name__=='__main__': run()
