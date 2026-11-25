"""P2.1: every kind of matter, opened and stepped through every branch many times, never breaks, always speaks the package's words,
and waits for the protagonist instead of acting for him.
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = build_saintjude(Path(tmp))
        os.environ["CAERNESS_DB_PATH"] = str(db)
        os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
        conn = connect(db)
        try:
            from engine import health
            from engine import life_matters as lm
            day = int(conn.execute("SELECT current_day FROM world_state").fetchone()[0])
            adults = [int(r[0]) for r in conn.execute(
                """SELECT a.id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE lp.life_status='living'
                   AND lp.birth_day<? ORDER BY a.id""", (day - 18 * 365,))]
            rng = random.Random(7)
            for a in rng.sample(adults, 1500):  # money in pockets, so loans and jobs can happen
                conn.execute("INSERT OR IGNORE INTO resources(actor_id,resource_type,amount) VALUES (?,'cash',?)", (a, rng.uniform(0, 600)))
            traders = [int(r[0]) for r in conn.execute("SELECT actor_id FROM enterprise_staff WHERE status='active' ORDER BY actor_id")]
            me = next(a for a in traders if a not in lm.open_courtships(conn))  # nobody he is already courting
            conn.execute("DELETE FROM resources WHERE actor_id=? AND resource_type='cash'", (me,))
            conn.execute("INSERT INTO resources(actor_id,resource_type,amount) VALUES (?,'cash',5000)", (me,))  # someone can be asked
            conn.execute("DELETE FROM player_state")
            conn.execute("INSERT INTO player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) VALUES (1,?,NULL,'t',1)", (me,))

            pools = {"money": adults, "romance": adults, "quarrel": adults, "illness": adults, "work": traders, "police": adults,
                     "rivalry": [int(r[0]) for r in conn.execute("SELECT owner_actor_id FROM civilian_enterprises WHERE owner_actor_id IS NOT NULL")]}
            for round_no in range(8):
                p = lm._Pass(conn, day)
                for kind, pool in pools.items():
                    subjects = rng.sample(pool, min(25, len(pool)))
                    if kind != "police":
                        subjects += [me]
                    for s in subjects:
                        if lm._living(conn, s):
                            lm.OPENERS[kind](p, s, random.Random(f"{round_no}:{kind}:{s}"))
                # and people close to the protagonist turn to him
                for s in lm.contacts(conn, me):
                    for kind in ("money", "romance", "quarrel", "work"):
                        if lm._living(conn, s):
                            lm.OPENERS[kind](p, s, random.Random(f"me:{round_no}:{kind}:{s}"))
                for _ in range(4):
                    day += 60
                    conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
                    health.process_due_health(conn, day)
                    lm._advance_open(lm._Pass(conn, day))
            conn.commit()

            stages = {(r[0], r[1]) for r in conn.execute("SELECT m.kind,s.stage FROM life_matter_steps s JOIN life_matters m ON m.id=s.matter_id")}
            print(sorted(stages))
            for want in [("money", "borrowed"), ("money", "refused"), ("money", "repaid"), ("money", "asks"), ("money", "short_self"),
                         ("romance", "courting"), ("romance", "serious"), ("romance", "broke_off"), ("romance", "interest_in_him"),
                         ("romance", "lapsed"), ("quarrel", "blows"), ("quarrel", "made_up"), ("quarrel", "grudge"), ("illness", "recovered"),
                         ("rivalry", "gains"), ("work", "done"), ("work", "lapsed"), ("police", "dropped")]:
                assert want in stages, f"branch never reached: {want}"
            unspoken = conn.execute("SELECT COUNT(*) FROM life_matter_steps WHERE text LIKE '%{%' OR text=''").fetchone()[0]
            assert unspoken == 0
            # every kind/stage the engine can record has words in the package
            words = lm.data(conn)["texts"]
            missing = [f"{k}.{s}" for k, s in stages if f"{k}.{s}" not in words]
            assert not missing, missing
            # the protagonist was never made to act
            assert not conn.execute("SELECT 1 FROM economic_flows WHERE source_actor_id=? AND metadata_json LIKE '%(matter %'", (me,)).fetchone()
            assert not conn.execute("""SELECT 1 FROM harm_incidents h JOIN life_matters m ON m.id=h.source_ref_id AND h.source_kind='life_matter'
                                       WHERE h.actor_id<>? AND (m.subject_actor_id=? OR m.other_actor_id=?)""", (me, me, me)).fetchone()
            assert not conn.execute("SELECT 1 FROM relationship_history WHERE source_kind='life_matter' AND source_actor_id=?", (me,)).fetchone()
            assert not conn.execute("""SELECT 1 FROM life_matters WHERE subject_actor_id=? AND kind IN ('romance','quarrel')""", (me,)).fetchone()
            assert not conn.execute("SELECT 1 FROM life_matters WHERE other_actor_id=? AND kind='work'", (me,)).fetchone()
            # but things happen to him too
            assert conn.execute("SELECT 1 FROM life_matters WHERE kind='illness' AND subject_actor_id=?", (me,)).fetchone()
            # the circle-outwards view of who knows whom says what the person-by-person view says
            those = sorted(lm.contacts(conn, me))[:20]
            back = lm.known_by(conn, those)
            for a in sorted(set(back) | set(those))[:150]:
                assert back.get(a, {}) == {c: w for c, w in lm.contacts(conn, a).items() if c in those}, a
            assert back, "someone knows the circle"
            # a quarrel with him is never made up (or held as settled) for him
            his = {r[0] for r in conn.execute("""SELECT s.stage FROM life_matter_steps s JOIN life_matters m ON m.id=s.matter_id
                                                 WHERE m.kind='quarrel' AND m.other_actor_id=?""", (me,))}
            assert "let_stand" in his and not his & {"made_up", "grudge"}, his
            # what two people fall out over follows what they are to each other: a parent and child never over a bar insult
            pair = conn.execute("""SELECT actor_a_id,actor_b_id FROM kinship_links WHERE kin_kind IN ('parent','child')
                                   AND ended_day IS NULL ORDER BY id LIMIT 1""").fetchone()
            p = lm._Pass(conn, day)
            drawn = {lm._topic(p, pair[0], pair[1], random.Random(n)) for n in range(120)}
            assert drawn <= set(lm.data(conn)["quarrel_topics"]["parent_child"]) and len(drawn) > 3, drawn
        finally:
            conn.close()
    print("PASS p2_life_matters_branches_test")


if __name__ == "__main__":
    main()
