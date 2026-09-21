from __future__ import annotations
import os, shutil, sqlite3, tempfile
os.environ.setdefault('CAERNESS_TEST_MODE','1')
from engine.coverage import ten_year_gate
from engine.activation import CURRENT_CANON_ACTIVATION_VERSION
from engine.db import connect

def run():
    c=connect()
    try:
        g=ten_year_gate(c)
        assert g['opening_activation_passed'] is True, g
        assert int(g['current_canon_activation_version']) >= CURRENT_CANON_ACTIVATION_VERSION
        assert c.execute('select count(*) from background_person_profiles').fetchone()[0] > 0
        assert c.execute('select count(*) from professional_profiles').fetchone()[0] > 0
        assert c.execute('select count(*) from institutional_authority_slots').fetchone()[0] > 0
    finally:
        c.close()
    with tempfile.TemporaryDirectory() as td:
        src=os.environ.get('CAERNESS_DB_PATH') or 'data/caerness.db'; p=os.path.join(td,'stale.db'); shutil.copy2(src,p)
        d=sqlite3.connect(p); d.row_factory=sqlite3.Row
        d.execute("insert or replace into engine_meta(key,value) values ('current_canon_activation_version','17')"); d.commit()
        g=ten_year_gate(d)
        assert g['pass'] is False and g['opening_activation_passed'] is False
        assert any(x['domain_key']=='opening_activation' for x in g['failures'])
        assert d.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not d.execute('pragma foreign_key_check').fetchall()
        d.close()
    print('TENYEAR02 opening activation gate PASS', {'required':CURRENT_CANON_ACTIVATION_VERSION})
if __name__=='__main__': run()
