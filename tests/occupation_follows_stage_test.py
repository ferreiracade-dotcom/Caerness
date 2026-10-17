"""Owner ruling: occupation follows Stage. High Stages mean a martial life; Third is martial bar a rare exception."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MARTIAL = ("soldier", "criminal")


def run():
    from engine.person_ecology import (_OCCUPATIONS, _pick, occupation_for_stage, occupation_with_past, redraw_unresolved_occupations)

    # Pure function
    assert occupation_for_stage(1, 1, "First", "physician") == "physician"
    assert occupation_for_stage(1, 1, "Temper", "labor") == "labor"
    assert occupation_for_stage(1, 1, None, "clerk") == "clerk"
    seen = set()
    for uid in range(400):
        for st in ("Breach", "Fifth"):
            o = occupation_for_stage(7, uid, st, "merchant")
            assert o in MARTIAL, o
            seen.add(o)
        assert occupation_for_stage(7, uid, "Breach", "soldier") == "soldier"
        assert occupation_for_stage(7, uid, "Fifth", "criminal") == "criminal"
    assert seen == set(MARTIAL)
    third = [occupation_for_stage(7, uid, "Third", "physician") for uid in range(2000)]
    share = sum(o == "physician" for o in third) / len(third)
    assert 0.06 < share < 0.18, share
    # Retired masters: only aged 45+, about a quarter, marked with a martial past; the young never keep a trade at Breach+
    old = [occupation_with_past(7, uid, "Breach", "physician", 60) for uid in range(2000)]
    kept = [o for o in old if o[0] == "physician"]
    assert all(past for _, past in kept) and 0.18 < len(kept) / len(old) < 0.32, len(kept)
    assert all(occupation_with_past(7, uid, "Fifth", "physician", 44)[0] in MARTIAL for uid in range(500))
    assert all(occupation_with_past(7, uid, "Breach", "physician", None)[0] in MARTIAL for uid in range(500))
    t_old = [occupation_with_past(7, uid, "Third", "physician", 60) for uid in range(2000)]
    assert 0.30 < sum(o == "physician" for o, _ in t_old) / len(t_old) < 0.40  # 12% genuine + 25% of the rest

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "o.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        init_db()
        c = connect()
        rows = c.execute("SELECT current_stage,occupation_domain,social_archetype FROM background_person_profiles WHERE status='background'").fetchall()
        assert rows
        day = c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
        for r in c.execute("""SELECT current_stage,occupation_domain,birth_day,json_extract(metadata_json,'$.martial_past') FROM background_person_profiles
                              WHERE status='background' AND current_stage IN ('Breach','Fifth')"""):
            assert r[1] in MARTIAL or ((day - r[2]) // 365 >= 45 and r[3] == 1), tuple(r)
        thirds = c.execute("""SELECT occupation_domain,json_extract(metadata_json,'$.martial_past') FROM background_person_profiles
                              WHERE status='background' AND current_stage='Third'""").fetchall()
        assert thirds and sum(r[0] not in MARTIAL and r[1] != 1 for r in thirds) / len(thirds) <= 0.20
        assert all(r[2] == f"ordinary_{r[1]}" for r in rows)
        # First/Temper/unstaged keep the pure draw
        n = 0
        for r in c.execute("""SELECT p.occupation_domain,p.local_uid,pt.seed FROM background_person_profiles p
                              JOIN background_population_partitions pt ON pt.id=p.partition_id
                              WHERE p.status='background' AND (p.current_stage IN ('First','Temper') OR p.current_stage IS NULL)"""):
            assert r[0] == _pick(_OCCUPATIONS, int(r[2]), int(r[1]), "occupation")
            n += 1
        assert n > 0

        # Deterministic: a second run changes nothing
        assert redraw_unresolved_occupations(c)["changed"] == 0

        # Corrupt background Breach rows; redraw repairs them. A resolved mismatch is reported, never changed.
        c.execute("""UPDATE background_person_profiles SET occupation_domain='physician',social_archetype='ordinary_physician'
                     WHERE status='background' AND current_stage='Breach'""")
        res = c.execute("SELECT partition_id,local_uid FROM background_person_profiles WHERE status='background' AND current_stage='Temper' LIMIT 1").fetchone()
        c.execute("""UPDATE background_person_profiles SET status='resolved',current_stage='Fifth',occupation_domain='labor',
                      social_archetype='ordinary_labor',birth_day=?,actor_id=(SELECT MIN(id) FROM actors WHERE actor_type='character')
                     WHERE partition_id=? AND local_uid=?""", (day - 30 * 365, res[0], res[1]))
        r1 = redraw_unresolved_occupations(c)
        assert r1["changed"] > 0, r1
        assert any(m["stage"] == "Fifth" and m["occupation"] == "labor" for m in r1["resolved_mismatches"]), r1["resolved_mismatches"][:3]
        assert tuple(c.execute("SELECT occupation_domain,status FROM background_person_profiles WHERE partition_id=? AND local_uid=?", (res[0], res[1])).fetchone()) == ("labor", "resolved")
        assert not c.execute("SELECT 1 FROM background_person_profiles WHERE status='background' AND current_stage IN ('Breach','Fifth') AND occupation_domain NOT IN ('soldier','criminal') "
                             "AND json_extract(metadata_json,'$.martial_past') IS NOT 1").fetchone()
        assert redraw_unresolved_occupations(c)["changed"] == 0
        c.close()
    print("occupation_follows_stage_test passed")


if __name__ == "__main__":
    run()
