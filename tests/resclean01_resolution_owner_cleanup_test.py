"""RESCLEAN-01 — resolution ownership/type cleanup acceptance."""
from __future__ import annotations
import os, tempfile
from pathlib import Path

from engine.db import reset_db, init_db, connect, SCHEMA_VERSION, _migration_76, _seed_resolution_from_profiles
from engine.current_seed import import_current_seed
from engine.activation import activate_existing_loops


def run() -> dict:
    path=Path(tempfile.gettempdir())/'caerness_resclean01.db'
    os.environ['CAERNESS_DB_PATH']=str(path); os.environ['CAERNESS_TEST_MODE']='1'
    reset_db(force=True,backup=False); init_db(); c=connect(); import_current_seed(c); activate_existing_loops(c); c.commit()
    assert SCHEMA_VERSION >= 76
    # Current compatibility seeding must classify profiles by actual actor type.
    _seed_resolution_from_profiles(c); c.commit()
    mis=int(c.execute("""select count(*) from entity_resolution er join actors a on a.id=er.entity_id
                         where er.entity_kind='actor' and a.actor_type='institution'""").fetchone()[0])
    assert mis==0,mis
    cohort_due=int(c.execute("select count(*) from entity_resolution where entity_kind='cohort' and next_review_day is not null").fetchone()[0])
    assert cohort_due==0,cohort_due

    # Manufacture the exact legacy defect, then prove the migration is idempotent cleanup.
    inst=c.execute("select id from actors where actor_type='institution' order by id limit 1").fetchone()[0]
    proper=c.execute("select * from entity_resolution where entity_kind='institution' and entity_id=?",(inst,)).fetchone(); assert proper
    c.execute("""insert or replace into entity_resolution(entity_kind,entity_id,resolution_level,reason,review_cadence_days,next_review_day,last_changed_day,metadata_json)
                 values('actor',?,'STRUCTURAL','legacy duplicate',180,90,0,'{}')""",(inst,))
    c.execute("update entity_resolution set review_cadence_days=365,next_review_day=365 where entity_kind='cohort'")
    _migration_76(c); _migration_76(c); c.commit()
    legacy=c.execute("select * from entity_resolution er join actors a on a.id=er.entity_id where er.entity_kind='actor' and a.actor_type='institution' and er.entity_id=?",(inst,)).fetchone(); assert legacy is not None
    assert legacy['next_review_day'] is None and legacy['review_cadence_days'] is None
    assert c.execute("select count(*) from entity_resolution where entity_kind='cohort' and next_review_day is not null").fetchone()[0]==0
    assert c.execute("select count(*) from entity_resolution where entity_kind='institution' and entity_id=?",(inst,)).fetchone()[0]==1
    out={'schema_version':SCHEMA_VERSION,'misclassified_institution_rows':0,'cohort_due_rows':0,'integrity':c.execute('pragma integrity_check').fetchone()[0],'foreign_keys':len(c.execute('pragma foreign_key_check').fetchall())}
    assert out['integrity']=='ok' and out['foreign_keys']==0
    c.close(); print(out); return out

if __name__=='__main__': run()
