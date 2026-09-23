"""FAMILY-02 sex resolution: canon text, canon rule, given name, then seeded roll; newborns are resolved."""
from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.demographic_sex import seeded_sex, resolve_missing_demographic_sex
from engine.household_life import set_life_profile, create_union, register_birth


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_family02_sex_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect()
    import_current_seed(c); activate_existing_loops(c); c.commit()
    return c,path


def sex_of(c,name):
    r=c.execute("""SELECT lp.demographic_sex,json_extract(lp.metadata_json,'$.demographic_sex_basis')
                   FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.name=?""",(name,)).fetchone()
    return (r[0],r[1]) if r else None


def run():
    c,path=bootstrap()
    # Every named character leaves activation resolved; nothing stays 'unspecified'.
    assert c.execute("""SELECT COUNT(*) FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
                        WHERE a.actor_type='character' AND (lp.demographic_sex IS NULL OR lp.demographic_sex='unspecified')""").fetchone()[0]==0

    # Evidence order: canon title beats everything; the Mantle rule makes Hollow heirs male;
    # a surname that looks like a title ("Opal King") is not a title; ambiguous names roll.
    assert sex_of(c,'Queen Maud Ternwell')==('female','canon_text')
    assert sex_of(c,'Crown Prince Theodric Varen')==('male','canon_text')
    assert sex_of(c,'Malric Vell')==('male','canon_rule') and sex_of(c,'Dravik')==('male','canon_rule')
    assert sex_of(c,'Opal King')==('female','given_name')
    assert sex_of(c,'Meriel Halloway')==('female','given_name')
    assert sex_of(c,'Robin Mears')[1]=='seeded_roll'

    # Seeded roll is stable, and re-running resolution changes nothing.
    assert sex_of(c,'Robin Mears')[0]==seeded_sex('person:robin-mears')
    assert sum(resolve_missing_demographic_sex(c).values())==0

    # Newborns are resolved by a seeded roll, never left 'unspecified'.
    loc=int(c.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()[0])
    def adult(name,sex):
        aid=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",(name,loc)).lastrowid)
        set_life_profile(c,aid,birth_day=-30*365,demographic_sex=sex,family_formation_eligible=True); return aid
    u=create_union(c,adult('[F02S] Mother','female'),adult('[F02S] Father','male'))
    child=register_birth(c,u,child_name='[F02S] Child')
    assert c.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?",(child,)).fetchone()[0] in {'female','male'}

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('FAMILY-02 sex resolution: PASS', json.dumps({'robin_mears':seeded_sex('person:robin-mears')}))

if __name__=='__main__': run()
