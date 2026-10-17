"""Schema 112: former outfit members read as ordinary; retired masters keep a trade at high Stage; the Reckoning sits at Waymeet."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "m.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        raw = sqlite3.connect(db)
        raw.row_factory = sqlite3.Row
        # Make it a schema-111 save with the old state of the world.
        raw.execute("DELETE FROM schema_migrations WHERE version>=112")
        raw.execute("DELETE FROM engine_meta WHERE key='schema112_report'")
        raw.execute("UPDATE engine_meta SET value='111' WHERE key='schema_version'")
        rk = raw.execute("SELECT id FROM actors WHERE name='The Reckoning'").fetchone()[0]
        seth = raw.execute("SELECT id FROM actors WHERE name='Seth Carrick'").fetchone()[0]
        way = raw.execute("SELECT id FROM locations WHERE name='Waymeet'").fetchone()[0]
        other = raw.execute("SELECT id FROM locations WHERE name<>'Waymeet' ORDER BY id LIMIT 1").fetchone()[0]
        raw.execute("DELETE FROM underworld_network_presence WHERE institution_actor_id=?", (rk,))
        raw.execute("DELETE FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=?", (rk, seth))
        raw.execute("UPDATE actors SET home_location_id=?,current_location_id=? WHERE id=?", (other, other, seth))
        # A former member (subtype set by schema 110) with a spouse, and one with no background profile.
        pair = raw.execute("""SELECT u.actor_a_id a,u.actor_b_id b FROM household_unions u JOIN actors x ON x.id=u.actor_a_id JOIN actors y ON y.id=u.actor_b_id
                              WHERE u.status='active' AND x.name<>'Seth Carrick' AND y.name<>'Seth Carrick' AND x.actor_type='character' AND y.actor_type='character'
                              AND NOT EXISTS (SELECT 1 FROM underworld_personnel p WHERE p.actor_id IN (u.actor_a_id,u.actor_b_id) AND p.status='active')
                              ORDER BY u.id LIMIT 1""").fetchone()
        a, b = int(pair["a"]), int(pair["b"])
        raw.execute("UPDATE actors SET subtype='resolved_criminal' WHERE id=?", (a,))
        raw.execute("UPDATE actors SET subtype='spouse' WHERE id=?", (b,))
        # A resolved retired master (aged 55, Breach, innkeeper) and a young resolved Breach labourer.
        day = raw.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]
        vs = raw.execute("""SELECT p.partition_id,p.local_uid,p.actor_id FROM background_person_profiles p WHERE p.status<>'background' AND p.actor_id IS NOT NULL
                            AND p.actor_id NOT IN (?,?) ORDER BY p.actor_id LIMIT 2""", (a, b)).fetchall()
        assert len(vs) == 2
        old_id, young_id = int(vs[0]["actor_id"]), int(vs[1]["actor_id"])
        for r, age, occ in ((vs[0], 55, "hospitality"), (vs[1], 30, "labor")):
            raw.execute("""UPDATE background_person_profiles SET current_stage='Breach',occupation_domain=?,birth_day=?,
                           metadata_json=json_remove(COALESCE(metadata_json,'{}'),'$.martial_past') WHERE partition_id=? AND local_uid=?""",
                        (occ, day - age * 365, r["partition_id"], r["local_uid"]))
        raw.commit()
        raw.close()

        from engine.db import connect, init_db, SCHEMA_VERSION
        init_db()
        c = connect()
        assert SCHEMA_VERSION >= 112
        assert c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] >= 112
        rep = json.loads(c.execute("SELECT value FROM engine_meta WHERE key='schema112_report'").fetchone()[0])

        # A: nobody is 'resolved_criminal' without an active underworld role
        assert not c.execute("""SELECT 1 FROM actors a WHERE a.subtype='resolved_criminal'
                                AND NOT EXISTS (SELECT 1 FROM underworld_personnel p WHERE p.actor_id=a.id AND p.status='active')""").fetchone()
        sub = c.execute("SELECT subtype FROM actors WHERE id=?", (a,)).fetchone()[0]
        assert sub.startswith("resolved_") and sub != "resolved_criminal", sub
        from connector import store
        store.ensure_connector_schema(c)
        from connector.views import _who, lookup
        who = _who(c, c.execute("SELECT * FROM actors WHERE id=?", (b,)).fetchone())
        assert who.startswith("spouse of ") and "criminal" not in who and "resolved" not in who and "_" not in who, who
        trade = who[who.index("(") + 1:-1]
        assert trade in ("labourer", "artisan", "merchant", "clerk", "soldier", "teacher", "physician", "artist", "carter", "innkeeper"), who
        assert "resolved" not in _who(c, c.execute("SELECT * FROM actors WHERE id=?", (a,)).fetchone())
        name = c.execute("SELECT name FROM actors WHERE id=?", (a,)).fetchone()[0]
        lk = json.dumps(lookup(c, name))
        assert "criminal" not in lk and "resolved" not in lk, lk

        # Retired masters: aged 45+ marked (job unchanged); the young one is reported
        assert c.execute("SELECT occupation_domain FROM background_person_profiles WHERE actor_id=?", (old_id,)).fetchone()[0] == "hospitality"
        assert json.loads(c.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?", (old_id,)).fetchone()[0]).get("martial_past") is True
        assert json.loads(c.execute("SELECT metadata_json FROM background_person_profiles WHERE actor_id=?", (old_id,)).fetchone()[0]).get("martial_past") is True
        assert any(m["actor_id"] == young_id for m in rep["resolved_mismatches"])
        assert all(m["age"] < 45 and m["stage"] in ("Breach", "Fifth") for m in rep["resolved_mismatches"])
        assert not any(m["actor_id"] == old_id for m in rep["resolved_mismatches"])
        assert not c.execute("SELECT 1 FROM background_person_profiles WHERE status='background' AND current_stage IN ('Breach','Fifth') "
                             "AND occupation_domain NOT IN ('soldier','criminal') AND json_extract(metadata_json,'$.martial_past') IS NOT 1").fetchone()
        tv = c.execute("SELECT occupation_domain,current_stage,birth_day FROM background_person_profiles WHERE actor_id=587").fetchone()
        print("Tomas Verran (587):", dict(tv) if tv else None, "age", (day - tv["birth_day"]) // 365 if tv else None,
              "marked" if tv and json.loads(c.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=587").fetchone()[0]).get("martial_past") else "reported/other")

        # B: the Reckoning at Waymeet, Seth its elder
        pres = {r[0]: r[1] for r in c.execute("SELECT l.name,p.strength FROM underworld_network_presence p JOIN locations l ON l.id=p.location_id WHERE p.institution_actor_id=?", (rk,))}
        assert pres == {"Waymeet": "strong", "Cairnholt": "present", "Crownhold": "thin"}, pres
        s = c.execute("SELECT home_location_id,current_location_id FROM actors WHERE id=?", (seth,)).fetchone()
        assert s[0] == way and s[1] == way
        m = c.execute("SELECT role_text,status FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=?", (rk, seth)).fetchone()
        assert tuple(m) == ("elder", "active")
        assert not c.execute("SELECT 1 FROM underworld_personnel WHERE actor_id=?", (seth,)).fetchone()
        assert not c.execute("SELECT 1 FROM underworld_organizations WHERE current_leader_actor_id=? OR founder_actor_id=?", (seth, seth)).fetchone()
        from engine.player import set_player
        from connector import store
        store.ensure_connector_schema(c)
        me = int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND id NOT IN (?) ORDER BY id LIMIT 1", (seth,)).fetchone()[0])
        c.execute("UPDATE actors SET current_location_id=? WHERE id=?", (way, me))
        set_player(c, me)
        c.commit()
        from connector.views import compact_scene
        inst = {i["name"]: i for i in compact_scene(c)["institutions_here"]}
        assert "The Reckoning" in inst, list(inst)
        # Idempotent: rerunning the placement changes nothing
        from engine.underworld_ecology import place_reckoning
        place_reckoning(c)
        assert c.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=?", (rk, seth)).fetchone()[0] == 1
        c.close()
    print("schema112_test passed")


if __name__ == "__main__":
    run()
