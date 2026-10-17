from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "standing.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine.relationships import ensure_relationship
        from engine.standing import STAGE_READINGS, standing

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            ids = [int(r[0]) for r in conn.execute(
                """SELECT a.id FROM actors a JOIN cultivation_profiles c ON c.actor_id=a.id
                   WHERE a.actor_type='character' AND a.home_location_id IS NOT NULL ORDER BY a.id LIMIT 40""")]
            plain = [int(r[0]) for r in conn.execute(
                """SELECT a.id FROM actors a WHERE a.actor_type='character'
                   AND NOT EXISTS (SELECT 1 FROM kinship_links k WHERE a.id IN (k.actor_a_id,k.actor_b_id))
                   AND NOT EXISTS (SELECT 1 FROM relationships r WHERE a.id IN (r.actor_a_id,r.actor_b_id))
                   AND NOT EXISTS (SELECT 1 FROM institution_memberships m WHERE m.member_actor_id=a.id)
                   AND NOT EXISTS (SELECT 1 FROM household_members h WHERE h.actor_id=a.id)
                   AND NOT EXISTS (SELECT 1 FROM underworld_personnel u WHERE u.actor_id=a.id)
                   ORDER BY a.id LIMIT 5""")]
            toll = int(conn.execute("SELECT id FROM locations WHERE name LIKE 'Toll%'").fetchone()[0])
            saltmere = int(conn.execute("SELECT id FROM locations WHERE name='Saltmere'").fetchone()[0])

            def setup(aid, sex, born_years_ago, stage=None):
                conn.execute("UPDATE actor_life_profiles SET demographic_sex=?,birth_day=? WHERE actor_id=?",
                             (sex, day - int(born_years_ago * 365), aid))
                if stage is not None:
                    conn.execute("UPDATE cultivation_profiles SET current_stage=? WHERE actor_id=?", (stage, aid))

            def link(a, b, kind):
                conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?,?,?,0)",
                             (a, b, kind, "recognized"))

            a, b, c, d = ids[0], ids[1], ids[2], ids[3]

            # Kin both ways: a is the father of b.
            for x in (a, b, c, d):
                conn.execute("DELETE FROM kinship_links WHERE ? IN (actor_a_id,actor_b_id)", (x,))
            setup(a, "male", 55); setup(b, "female", 25)
            link(a, b, "parent"); link(b, a, "child")
            assert standing(conn, b, a, toll)["kin"] == "your father", standing(conn, b, a, toll)
            assert standing(conn, a, b, toll)["kin"] == "your daughter", standing(conn, a, b, toll)
            assert standing(conn, b, a, toll)["age"] == "middle-aged"
            assert standing(conn, a, b, toll)["age"] == "young adult"

            # In-law one step: the wife's father.
            setup(c, "male", 24)
            link(b, c, "spouse"); link(c, b, "spouse")  # c is the husband of a's daughter b
            assert standing(conn, a, c, toll)["kin"] == "your daughter's husband", standing(conn, a, c, toll)
            link(d, c, "parent"); link(c, d, "child")
            setup(d, "male", 52)
            assert standing(conn, b, d, toll)["kin"] == "your husband's father", standing(conn, b, d, toll)

            # Elder sibling who is the weaker: still "your elder brother" to the Sixth younger sibling.
            e, f = ids[4], ids[5]
            for x in (e, f):
                conn.execute("DELETE FROM kinship_links WHERE ? IN (actor_a_id,actor_b_id)", (x,))
            setup(e, "male", 40, "Temper"); setup(f, "female", 30, "Sixth")
            link(e, f, "sibling"); link(f, e, "sibling")
            assert standing(conn, f, e, toll)["kin"] == "your elder brother"
            assert standing(conn, e, f, toll)["kin"] == "your younger sister"

            # Household service term: the steward of the observer's house.
            hh = conn.execute("SELECT household_id,actor_id FROM household_members WHERE role='head' AND status='active' ORDER BY household_id LIMIT 1").fetchone()
            head = int(hh["actor_id"])
            steward = plain[0]
            conn.execute("INSERT INTO household_service_terms(household_id,actor_id,service_role,start_day,review_day,loyalty,satisfaction,renewal_bias,status) "
                         "VALUES (?,?,?,0,365,60,60,0,'active')", (int(hh["household_id"]), steward, "steward"))
            assert standing(conn, head, steward, toll)["house"] == "your steward"
            conn.execute("UPDATE household_service_terms SET service_role='servant' WHERE actor_id=?", (steward,))
            assert standing(conn, head, steward, toll)["house"] == "a servant of your house"
            assert "house" not in standing(conn, head, plain[1], toll)

            # Hostile relationship: the subject fears and resents the observer.
            x, y = plain[2], plain[3]
            ensure_relationship(conn, x, y, day, stance=-60, trust=-50, fear=70, resentment=60, familiarity=40)
            t = standing(conn, y, x, toll)
            assert "hostile" in t["toward"] and "fears you" in t["toward"] and "resents you" in t["toward"], t
            assert t["knows"] == "knows you", t

            # A stranger: sensible defaults, no error, no "None", no bearing, no kin, no origin.
            z = plain[4]
            s = standing(conn, y, z, toll)
            assert s["knows"] == "does not know you", s
            assert "bearing" not in s and "kin" not in s and "house" not in s and "from" not in s, s
            assert not any("None" in str(v) for v in s.values()), s
            assert standing(conn, y, z, None)["knows"] == "does not know you"
            assert standing(conn, None, z, toll).get("knows") is None

            # Stranger with a Stage: the Stage is not read off them (Presence is not a scanner).
            conn.execute("UPDATE cultivation_profiles SET current_stage='Third' WHERE actor_id=?", (z,)) if conn.execute(
                "SELECT 1 FROM cultivation_profiles WHERE actor_id=?", (z,)).fetchone() else None
            assert "bearing" not in standing(conn, y, z, toll)

            # A Hearth Third reads stronger outside the Hearth than inside it (known person, via kin).
            g, h = ids[6], ids[7]
            for q in (g, h):
                conn.execute("DELETE FROM kinship_links WHERE ? IN (actor_a_id,actor_b_id)", (q,))
            setup(g, "male", 45, "Third"); setup(h, "female", 20)
            link(g, h, "parent"); link(h, g, "child")
            inside, outside = standing(conn, h, g, toll)["bearing"], standing(conn, h, g, saltmere)["bearing"]
            assert inside != outside and outside == STAGE_READINGS[STAGE_READINGS.index(inside) + 1], (inside, outside)

            # A person with visible rank is read even by a stranger.
            conn.execute("DELETE FROM institution_memberships WHERE member_actor_id=?", (g,))
            conn.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status) "
                         "SELECT id,?, 'member','Sect Head.','active' FROM actors WHERE actor_type<>'character' LIMIT 1", (g,))
            v = standing(conn, y, g, toll)
            assert v["bearing"] == inside and v["station"] == "Sect Head", v

            # Outsider status needs a home polity that differs from the place's polity.
            conn.execute("UPDATE actors SET home_location_id=? WHERE id=?", (saltmere, g))
            assert "outsider here" in standing(conn, y, g, toll)["from"]
            assert "from" not in standing(conn, y, g, saltmere)
            conn.execute("UPDATE actors SET home_location_id=NULL WHERE id=?", (g,))
            assert "from" not in standing(conn, y, g, toll)
    print("standing_test passed")


if __name__ == "__main__":
    run()
