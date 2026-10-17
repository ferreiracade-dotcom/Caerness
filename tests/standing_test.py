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
            setup(g, "male", 45, "Temper"); setup(h, "female", 20)
            link(g, h, "parent"); link(h, g, "child")
            inside, outside = standing(conn, h, g, toll)["bearing"], standing(conn, h, g, saltmere)["bearing"]
            from engine.standing import NONMARTIAL_READINGS
            def idx(w):
                w = w.replace("Churned ", "").replace("Churned, ", "")
                return (STAGE_READINGS if w in STAGE_READINGS else NONMARTIAL_READINGS).index(w)
            assert inside != outside and idx(outside) == idx(inside) + 1, (inside, outside)

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

            # Review 9: an office word inside a trade title is not a rank.
            m, n = ids[8], ids[9]
            for q in (m, n):
                conn.execute("DELETE FROM kinship_links WHERE ? IN (actor_a_id,actor_b_id)", (q,))
                conn.execute("DELETE FROM institution_memberships WHERE member_actor_id=?", (q,))
            setup(m, "male", 45, "Third"); setup(n, "male", 45, "Third")
            for who_, role_ in ((m, "Harbour master."), (n, "Head cook.")):
                conn.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status) "
                             "SELECT id,?, 'member',?,'active' FROM actors WHERE actor_type<>'character' LIMIT 1", (who_, role_))
                r9 = standing(conn, y, who_, toll)
                assert "bearing" not in r9, (role_, r9)
            conn.execute("UPDATE institution_memberships SET role_text='Sect Master.' WHERE member_actor_id=?", (m,))
            assert "bearing" in standing(conn, y, m, toll), standing(conn, y, m, toll)

            # Review 10: a servant seen by a stranger belongs to the head's family, not to the servant's own surname.
            hh2 = conn.execute("SELECT household_id,actor_id FROM household_members WHERE role='head' AND status='active' ORDER BY household_id LIMIT 1").fetchone()
            head2 = int(hh2["actor_id"])
            hn = conn.execute("SELECT name FROM actors WHERE id=?", (head2,)).fetchone()[0].split()[-1]
            servant = plain[0]
            sn = conn.execute("SELECT name FROM actors WHERE id=?", (servant,)).fetchone()[0].split()[-1]
            assert sn != hn, (sn, hn)
            seen = standing(conn, None, servant, toll)["house"]
            assert f"the {hn} household" in seen and sn not in seen, (seen, hn, sn)

            # Review 12: two people with a shared parent are siblings; with one shared parent, half-siblings.
            p1, p2, k1, k2, k3 = ids[10], ids[11], ids[12], ids[13], ids[14]
            for q in (p1, p2, k1, k2, k3):
                conn.execute("DELETE FROM kinship_links WHERE ? IN (actor_a_id,actor_b_id)", (q,))
            setup(p1, "male", 60); setup(p2, "female", 58); setup(k1, "female", 30); setup(k2, "male", 25); setup(k3, "male", 20)
            for par, kid in ((p1, k1), (p2, k1), (p1, k2), (p2, k2), (p1, k3)):
                link(par, kid, "parent"); link(kid, par, "child")
            assert standing(conn, k1, k2, toll)["kin"] == "your younger brother", standing(conn, k1, k2, toll)["kin"]
            assert standing(conn, k2, k1, toll)["kin"] == "your elder sister", standing(conn, k2, k1, toll)["kin"]
            assert standing(conn, k1, k3, toll)["kin"] == "your younger half-brother", standing(conn, k1, k3, toll)["kin"]

            # Review 14: Veinborn, cultivator, martial artist and Churned are separate labels.
            from engine.standing import NONMARTIAL_READINGS
            assert len(NONMARTIAL_READINGS) == 3 and NONMARTIAL_READINGS[0] == "lightly cultivated"
            doc, sectman, knight, veinborn = ids[15], ids[16], ids[17], ids[18]
            for q in (doc, sectman, knight, veinborn):
                for t_ in ("kinship_links", ):
                    conn.execute("DELETE FROM kinship_links WHERE ? IN (actor_a_id,actor_b_id)", (q,))
                conn.execute("DELETE FROM institution_memberships WHERE member_actor_id=?", (q,))
                conn.execute("DELETE FROM underworld_personnel WHERE actor_id=?", (q,))
                link(y, q, "parent"); link(q, y, "child")  # known to the observer, so the reading shows
                conn.execute("UPDATE cultivation_profiles SET core_state='Open-Core' WHERE actor_id=?", (q,))
            setup(doc, "female", 40, "First"); setup(sectman, "male", 45, "Third"); setup(knight, "male", 40, "Third"); setup(veinborn, "male", 40)
            conn.execute("UPDATE cultivation_profiles SET current_stage=NULL WHERE actor_id=?", (veinborn,))
            conn.execute("UPDATE actors SET subtype='physician' WHERE id=?", (doc,))
            conn.execute("UPDATE actors SET subtype='soldier' WHERE id=?", (knight,))
            inst = conn.execute("SELECT id FROM actors WHERE actor_type='institution' AND subtype='clan/house' ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (toll, inst))
            conn.execute("INSERT INTO institution_memberships(institution_actor_id,member_actor_id,membership_kind,role_text,status) VALUES (?,?, 'member','Disciple.','active')", (inst, sectman))
            assert standing(conn, y, doc, toll)["bearing"] == "lightly cultivated", standing(conn, y, doc, toll)
            assert "fighter" not in standing(conn, y, doc, saltmere)["bearing"] and "master" not in standing(conn, y, doc, saltmere)["bearing"]
            assert standing(conn, y, sectman, toll)["bearing"] == "a Churned seasoned master", standing(conn, y, sectman, toll)
            kb = standing(conn, y, knight, saltmere)["bearing"]
            assert "Churned" not in kb and kb in STAGE_READINGS, kb
            assert "bearing" not in standing(conn, y, veinborn, toll)
            setup(doc, "female", 40, "Breach")  # a non-martial Breach is unheard of: read as a martial artist
            assert standing(conn, y, doc, toll)["bearing"] in STAGE_READINGS, standing(conn, y, doc, toll)
    print("standing_test passed")


if __name__ == "__main__":
    run()
