"""Generated people get a given name that fits their recorded sex; schema 109 repairs older worlds."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, SCHEMA_VERSION
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops
from engine.person_ecology import FIRST_FEMALE, FIRST_MALE, repair_generated_name_sex


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_names_sex_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect()
    import_current_seed(c); activate_existing_loops(c); c.commit()
    return c,path


def pool(sex):
    return FIRST_FEMALE if sex=='female' else FIRST_MALE


def mismatches(c):
    bad=[]
    for given,sex in c.execute("SELECT given_name,demographic_sex FROM background_person_profiles"):
        if given not in pool(sex): bad.append(('profile',given,sex))
    for name,sex in c.execute("""SELECT a.name,lp.demographic_sex FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
                                 WHERE json_extract(lp.metadata_json,'$.source')='PERSONECO01'"""):
        if name.split()[0] not in pool(sex): bad.append(('actor',name,sex))
    return bad


def run():
    c,path=bootstrap()
    # New worlds: every background identity, revealed or not, has a name of its own sex.
    assert c.execute("SELECT COUNT(*) FROM background_person_profiles").fetchone()[0]>100
    assert mismatches(c)==[], mismatches(c)[:5]

    # A caller may ask the population for someone of a given sex; nobody is manufactured.
    from engine.person_ecology import resolve_background_person
    for want in ('male','female'):
        got=resolve_background_person(c,reason='test',min_age=20,max_age=60,demographic_sex=want)
        assert c.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?",(got,)).fetchone()[0]==want
    # A taken name gives way to another name of the same sex, not a visible number.
    from engine.person_ecology import _unique_actor_name
    prof=c.execute("SELECT * FROM background_person_profiles WHERE status='background' AND demographic_sex='male' LIMIT 1").fetchone()
    c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",
              (f"{prof['given_name']} {prof['family_name']}",int(c.execute("SELECT id FROM locations LIMIT 1").fetchone()[0])))
    nm=_unique_actor_name(c,prof)
    assert not any(ch.isdigit() for ch in nm) and nm.split()[0] in FIRST_MALE and nm.endswith(prof['family_name']), nm
    # Newborns get a real given name of their sex and the father's family name, never a placeholder.
    from engine.household_life import set_life_profile, create_union, register_birth
    from engine.demographic_sex import FEMALE_GIVEN_NAMES, MALE_GIVEN_NAMES
    loc0=int(c.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()[0])
    def adult(name,sex):
        x=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",(name,loc0)).lastrowid)
        set_life_profile(c,x,birth_day=-30*365,demographic_sex=sex,family_formation_eligible=True); return x
    u=create_union(c,adult('Maren Holt','female'),adult('Edgar Brannock','male'))
    kids=[register_birth(c,u,demographic_sex=sx) for sx in ('female','male','male')]
    for kid,sx in zip(kids,('female','male','male')):
        nm=c.execute("SELECT name FROM actors WHERE id=?",(kid,)).fetchone()[0]
        assert '[' not in nm and nm.endswith(' Brannock') and nm.split()[0] in (FEMALE_GIVEN_NAMES if sx=='female' else MALE_GIVEN_NAMES), nm
    assert len({c.execute("SELECT name FROM actors WHERE id=?",(k,)).fetchone()[0] for k in kids})==3
    assert not c.execute("SELECT 1 FROM life_events WHERE event_kind='birth' AND summary LIKE '[%'").fetchone()

    # Businesses that form during play are named after their operator, not a structural label.
    from engine.civilian import _emergent_business_name
    nm=_emergent_business_name(c,kids[0] and adult('Hollis Varr','male'),'inn',loc0)
    assert nm=="Varr's inn", nm
    c.execute("INSERT INTO civilian_enterprises(name,enterprise_kind,location_id,created_day,updated_day) VALUES (?,'service',?,0,0)",(nm,loc0))
    assert _emergent_business_name(c,adult('Ivo Varr','male'),'inn',loc0)=="Ivo Varr's inn"

    # Old worlds: recreate the bug on one revealed identity and repair it.
    aid,given,family,sex,pid,uid=c.execute(
        """SELECT a.id,p.given_name,p.family_name,p.demographic_sex,p.partition_id,p.local_uid
           FROM background_person_profiles p JOIN background_population_identity_links l
             ON l.partition_id=p.partition_id AND l.local_uid=p.local_uid JOIN actors a ON a.id=l.actor_id
           ORDER BY a.id LIMIT 1""").fetchone()
    wrong=next(w for w in (FIRST_MALE if sex=='female' else FIRST_FEMALE) if not c.execute('SELECT 1 FROM actors WHERE name=?',(f'{w} {family}',)).fetchone())  # a name nobody has
    old=f"{wrong} {family}"
    c.execute("UPDATE background_person_profiles SET given_name=? WHERE partition_id=? AND local_uid=?",(wrong,pid,uid))
    c.execute("UPDATE actors SET name=? WHERE id=?",(old,aid))
    loc=int(c.execute("SELECT id FROM locations ORDER BY id LIMIT 1").fetchone()[0])
    other=int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,status) VALUES (?,'character',?,'active')",(f"{old} 70001",loc)).lastrowid)
    c.execute("INSERT INTO households(name,created_day,updated_day) VALUES (?,0,0)",(f"{old} household",))
    c.execute("INSERT INTO life_events(day,actor_id,event_kind,summary) VALUES (0,?,'other',?)",(aid,f"{old} married; {old} 70001 attended."))
    c.execute("INSERT INTO households(name,created_day,updated_day) VALUES (?,0,0)",(f"{old}ow household",))  # "Marr" vs "Marrow"

    counts=repair_generated_name_sex(c)
    assert counts['actors_renamed']==1 and counts['profiles_renamed']>=1, counts
    new=c.execute("SELECT name FROM actors WHERE id=?",(aid,)).fetchone()[0]
    assert new.split()[0] in pool(sex) and new.endswith(family), new
    assert c.execute("SELECT name FROM actors WHERE id=?",(other,)).fetchone()[0]==f"{old} 70001"  # a different person
    assert c.execute("SELECT 1 FROM households WHERE name=?",(f"{new} household",)).fetchone()
    assert c.execute("SELECT 1 FROM households WHERE name=?",(f"{old}ow household",)).fetchone()  # a longer name is someone else
    assert c.execute("SELECT summary FROM life_events WHERE event_kind='other' AND summary LIKE '%70001 attended.'").fetchone()[0]==f"{new} married; {old} 70001 attended."
    assert mismatches(c)==[]
    assert sum(repair_generated_name_sex(c).values())==0  # idempotent
    # Canon people are never renamed.
    assert c.execute("SELECT 1 FROM actors WHERE name='Queen Maud Ternwell'").fetchone()

    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()

    # The migration runs the repair on a world saved at schema 108.
    c=connect(); c.execute("UPDATE background_person_profiles SET given_name=? WHERE partition_id=? AND local_uid=?",(wrong,pid,uid))
    c.execute("UPDATE engine_meta SET value='108' WHERE key='schema_version'"); c.execute("DELETE FROM schema_migrations WHERE version>=109"); c.commit(); c.close()
    init_db(); c=connect()
    assert mismatches(c)==[]
    assert c.execute("SELECT value FROM engine_meta WHERE key='schema_version'").fetchone()[0]==str(SCHEMA_VERSION)
    c.close()
    for suffix in ('','-wal','-shm'):
        try: Path(str(path)+suffix).unlink()
        except FileNotFoundError: pass
    print('names_follow_sex_test: ok')


if __name__=='__main__':
    run()
