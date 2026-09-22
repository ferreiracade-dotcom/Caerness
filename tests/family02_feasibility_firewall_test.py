"""FAMILY-02: kinship and biological-reproduction feasibility are mutation-time invariants."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.db import reset_db, init_db, connect, SCHEMA_VERSION
from engine.household_life import set_life_profile, add_kinship, create_union, update_family_plan, register_birth


def bootstrap():
    path=Path(tempfile.gettempdir())/f'caerness_family02_{os.getpid()}.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); return connect(),path


def actor(c,name,sex='unspecified',age=30):
    aid=int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')",(name,)).lastrowid)
    set_life_profile(c,aid,birth_day=-age*365,demographic_sex=sex,family_formation_eligible=True)
    return aid


def expect_reject(fn, token):
    try:
        fn()
    except ValueError as exc:
        assert token in str(exc),str(exc)
        return
    raise AssertionError('expected ValueError')


def run():
    assert SCHEMA_VERSION>=105
    c,path=bootstrap()

    # Shared-parent sibling relation must be detected even without an explicit sibling row.
    parent=actor(c,'[F02] Parent','female',55)
    sib_a=actor(c,'[F02] Sibling A','male',30); sib_b=actor(c,'[F02] Sibling B','female',28)
    add_kinship(c,parent,sib_a,'parent',reciprocal_kind='child')
    add_kinship(c,parent,sib_b,'parent',reciprocal_kind='child')
    expect_reject(lambda:create_union(c,sib_a,sib_b), 'close known kin')

    # Direct parent/child and aunt/uncle-to-niece/nephew are also hard failures.
    child=actor(c,'[F02] Direct Child','female',20)
    add_kinship(c,sib_a,child,'parent',reciprocal_kind='child')
    expect_reject(lambda:create_union(c,sib_a,child), 'close known kin')
    expect_reject(lambda:create_union(c,sib_b,child), 'close known kin')

    # A resolved female/male unrelated pair may form a union and produce a biological child.
    female=actor(c,'[F02] Female Partner','female',27); male=actor(c,'[F02] Male Partner','male',29)
    u=create_union(c,female,male)
    update_family_plan(c,u,auto_children=True,birth_parent_actor_id=female,desired_children=1)
    child_id=register_birth(c,u,child_name='[F02] Valid Child',demographic_sex='female')
    assert c.execute("SELECT demographic_sex,birth_day FROM actor_life_profiles WHERE actor_id=?",(child_id,)).fetchone()['demographic_sex']=='female'

    # Same-sex union may exist socially, but it cannot fabricate a biological birth through this union.
    f1=actor(c,'[F02] F1','female',26); f2=actor(c,'[F02] F2','female',26)
    u2=create_union(c,f1,f2)
    expect_reject(lambda:register_birth(c,u2,child_name='[F02] Impossible Same Sex Birth'), 'resolved female/male reproductive pair')

    # Missing demographic sex is incomplete state, not permission to invent a birth parent.
    unknown=actor(c,'[F02] Unknown','unspecified',30); known=actor(c,'[F02] Known Male','male',31)
    u3=create_union(c,unknown,known)
    expect_reject(lambda:register_birth(c,u3,child_name='[F02] Impossible Unknown Birth'), 'resolved female/male reproductive pair')

    assert c.execute("SELECT COUNT(*) FROM harm_incidents").fetchone()[0]==0
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
    c.commit(); c.close()
    try:path.unlink()
    except FileNotFoundError:pass
    print('FAMILY-02 feasibility firewall: PASS')

if __name__=='__main__': run()
