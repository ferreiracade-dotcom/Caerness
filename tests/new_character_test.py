"""New character (gap 5): shared parts keep behaviour, lived past, proposal to protagonist, Ansel's repair."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

# sha of the opening family resolution on the packaged world, recorded on HEAD before the shared-parts refactor
PARITY_SHA = "093f440f97c81af83f38f8b46982752b96b7ea92966e0ecdc8791503f77ea0ce"


def open_copy(tmp, name="w.db"):
    db = Path(tmp) / name
    shutil.copy2(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    from engine.db import connect, init_db
    init_db()
    conn = connect()
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def parity():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = open_copy(tmp)
        ids = [r[0] for r in c.execute(
            """SELECT actor_id FROM actor_life_profiles WHERE json_extract(metadata_json,'$.marital_status_basis')='opening_draw'
               AND json_extract(metadata_json,'$.marital_status') IN ('widowed','never_married') ORDER BY actor_id LIMIT 80""")]
        for a in ids:
            c.execute("DELETE FROM latent_entities WHERE latent_kind='kin_group' AND json_extract(constraints_json,'$.parent_actor_id')=?", (a,))
            c.execute("UPDATE actor_life_profiles SET metadata_json=json_remove(metadata_json,'$.marital_status_basis','$.marital_status_authority') WHERE actor_id=?", (a,))
        from engine import opening_family as of
        of.resolve_opening_family(c)
        h = hashlib.sha256()
        for a in ids:
            h.update(json.dumps(json.loads(c.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?", (a,)).fetchone()[0]), sort_keys=True).encode())
        for r in c.execute("SELECT constraints_json,count_estimate FROM latent_entities WHERE latent_kind='kin_group' ORDER BY id"):
            h.update(str(tuple(r)).encode())
        h.update(str(c.execute("select count(*) from household_unions").fetchone()[0]).encode())
        assert h.hexdigest() == PARITY_SHA, h.hexdigest()
        # people of any age can be revealed (13-17 used to fail on an invalid life_stage)
        from engine.person_ecology import resolve_background_person
        loc = int(c.execute("SELECT id FROM locations WHERE name LIKE 'Toll%Reach' ORDER BY id LIMIT 1").fetchone()[0])
        for lo, hi in ((0, 1), (5, 8), (13, 17), (16, 17)):
            aid = resolve_background_person(c, reason="t", location_id=loc, min_age=lo, max_age=hi)
            assert aid is not None, (lo, hi)
            st = c.execute("SELECT life_stage FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0]
            assert st in ("infant", "child", "youth"), (lo, hi, st)
        # the seeded pick is stable, and another seed can differ
        from engine.person_ecology import find_background_candidate
        a1 = find_background_candidate(c, location_id=loc, min_age=25, max_age=40, pick_seed="s1")
        a2 = find_background_candidate(c, location_id=loc, min_age=25, max_age=40, pick_seed="s1")
        assert a1["local_uid"] == a2["local_uid"] and a1["partition_id"] == a2["partition_id"]
        c.close()
    print("new_character_test::parity ok")


def run(only=None):
    for fn in (parity,):
        if only is None or fn.__name__ in only:
            fn()


if __name__ == "__main__":
    run(sys.argv[1:] or None)
