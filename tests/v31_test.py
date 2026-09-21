from __future__ import annotations
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import ENGINE_VERSION, SCHEMA_VERSION, connect, init_db, reset_db
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops

SEED=ROOT/'game'/'seeds'/'Caerness_Initial_World_State_Seed_v1_4.json'

def run():
    assert ENGINE_VERSION in {'0.31.0','0.32.0','0.33.0','0.34.0','0.35.0','0.36.0','0.37.0','0.38.0','0.39.0','0.40.0','0.41.0','0.42.0','0.43.0','0.44.0','0.45.0','0.46.0','0.47.0','0.56.0','0.58.0','0.59.0','0.60.0'} and SCHEMA_VERSION >= 31
    reset_db(); init_db()
    with connect() as c:
        result=import_current_seed(c,SEED)
        assert result['places']==133,result
        # Place existence is separate from exact placement/coordinates.
        cols={r[1] for r in c.execute('PRAGMA table_info(locations)').fetchall()}
        assert {'identity_certainty','placement_certainty','coordinate_status','source_anchor'} <= cols
        assert c.execute("SELECT COUNT(*) FROM locations WHERE coordinate_status='OPEN_NOT_REQUIRED'").fetchone()[0] >= 100

        expected={
            'White Laurel Heights':'The Spine',
            'Brackwater Springs':'Fellmarch',
            'The Red Yard':'Toll’s Reach',
            'Oldstone Hall':'Aldenmoor',
            'Anatomy Quarter':'Lysmere',
            'The Waystone':'Waymeet',
            'Inner Palace':'Crownhold',
        }
        for name,parent in expected.items():
            row=c.execute("""SELECT p.name,parent.name,p.identity_certainty,p.placement_certainty
                             FROM locations p LEFT JOIN locations parent ON parent.id=p.parent_location_id
                             WHERE p.name=?""",(name,)).fetchone()
            assert row and row[1]==parent,(name,row)
            assert row[2] != 'UNSPECIFIED' and row[3] != 'UNSPECIFIED'

        # Canon display-name mismatches are reconciled without changing stable source ids.
        for name in ['Deepwell Basin','Stonewake Caverns','The Long Stair']:
            assert c.execute('SELECT 1 FROM locations WHERE name=?',(name,)).fetchone(),name
        assert not c.execute("SELECT 1 FROM locations WHERE name IN ('Deepwell','Stonewake','Long Stair')").fetchone()

        # The old route-only duplicate is gone; one Northern Fellmarch identity serves both containment and travel.
        assert c.execute("SELECT COUNT(*) FROM locations WHERE lower(name)='northern fellmarch'").fetchone()[0]==1
        nf=c.execute("SELECT id FROM locations WHERE name='Northern Fellmarch'").fetchone()[0]
        assert c.execute('SELECT 1 FROM travel_routes WHERE from_location_id=? OR to_location_id=?',(nf,nf)).fetchone()

        # Explicitly unresolved placement stays unresolved rather than receiving invented coordinates.
        clear=c.execute("SELECT placement_certainty,parent_location_id FROM locations WHERE name='Clearwell'").fetchone()
        assert clear and clear[0]=='UNRESOLVED_WITHIN_REGION' and clear[1] is not None
        assert c.execute("SELECT placement_certainty FROM locations WHERE name='Aster'").fetchone()[0]=='WORKING_RELATIVE'

        # Canon-system activation must populate existing owners without inventing open detail.
        first=activate_existing_loops(c)
        counts1={
            'ecology': c.execute('SELECT COUNT(*) FROM location_environment_profiles').fetchone()[0],
            'knowledge': c.execute("SELECT COUNT(*) FROM knowledge_assets WHERE status='extant'").fetchone()[0],
            'religion': c.execute('SELECT COUNT(*) FROM religious_institutions').fetchone()[0],
            'culture': c.execute("SELECT COUNT(*) FROM cultural_institution_profiles WHERE status='active'").fetchone()[0],
            'channels': c.execute('SELECT COUNT(*) FROM information_channels').fetchone()[0],
            'polities': c.execute('SELECT COUNT(*) FROM political_polities').fetchone()[0],
            'territory': c.execute('SELECT COUNT(*) FROM territorial_control').fetchone()[0],
            'objects': c.execute('SELECT COUNT(*) FROM cultural_objects').fetchone()[0],
            'observances': c.execute('SELECT COUNT(*) FROM religious_observances').fetchone()[0],
        }
        assert counts1['ecology'] >= 17, counts1
        assert counts1['knowledge'] >= 8, counts1
        assert counts1['religion'] >= 4 and counts1['culture'] >= 1, counts1
        assert counts1['channels'] >= 4 and counts1['polities'] == 7 and counts1['territory'] > 0, counts1
        assert counts1['objects'] >= 3 and counts1['observances'] == 0, counts1
        assert c.execute('SELECT COUNT(*) FROM religious_traditions').fetchone()[0] == 10
        assert not c.execute("SELECT 1 FROM religious_traditions WHERE tradition_key='true_faith'").fetchone()
        # Sunreach remains a confederacy without pretending the First Convenor is a monarch.
        sun=c.execute("""SELECT p.ruler_actor_id,p.succession_method FROM political_polities p
                             JOIN actors a ON a.id=p.institution_actor_id WHERE a.name='Sunreach Confederacy'""").fetchone()
        assert sun and sun[0] is None and sun[1]=='custom'
        # Underheaven sovereignty is political state; this test does not seed Churn social influence as sovereignty.
        assert c.execute("""SELECT COUNT(*) FROM territorial_control tc JOIN political_polities p ON p.id=tc.controller_polity_id
                                 JOIN actors a ON a.id=p.institution_actor_id WHERE a.name='Underheaven Empire'""").fetchone()[0] > 0

        # Re-running activation is idempotent for persistent seed structures.
        second=activate_existing_loops(c)
        counts2={
            'ecology': c.execute('SELECT COUNT(*) FROM location_environment_profiles').fetchone()[0],
            'knowledge': c.execute("SELECT COUNT(*) FROM knowledge_assets WHERE status='extant'").fetchone()[0],
            'religion': c.execute('SELECT COUNT(*) FROM religious_institutions').fetchone()[0],
            'culture': c.execute("SELECT COUNT(*) FROM cultural_institution_profiles WHERE status='active'").fetchone()[0],
            'channels': c.execute('SELECT COUNT(*) FROM information_channels').fetchone()[0],
            'polities': c.execute('SELECT COUNT(*) FROM political_polities').fetchone()[0],
            'territory': c.execute('SELECT COUNT(*) FROM territorial_control').fetchone()[0],
            'objects': c.execute('SELECT COUNT(*) FROM cultural_objects').fetchone()[0],
            'observances': c.execute('SELECT COUNT(*) FROM religious_observances').fetchone()[0],
        }
        assert counts2==counts1,(counts1,counts2,first,second)
        c.commit()
    print('v0.31.0 prose-geography completion regression PASS')

if __name__=='__main__': run()
