"""P2.21: nobody marries out of the blue. A marriage grows out of a courtship that lasted and goes through an engagement; every
step in the protagonist's circle reaches him, with an invitation to the wedding; the engine never marries him.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect  # noqa: E402

SINGLE = """SELECT a.id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE a.actor_type='character' AND a.status='active'
            AND lp.life_status='living' AND lp.life_stage='adult' AND lp.family_formation_eligible=1 AND lp.demographic_sex=?
            AND lp.birth_day BETWEEN ? AND ? AND a.current_location_id IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM household_unions u WHERE u.status='active' AND (u.actor_a_id=a.id OR u.actor_b_id=a.id))
            AND NOT EXISTS(SELECT 1 FROM kinship_links k WHERE k.actor_a_id=a.id OR k.actor_b_id=a.id) ORDER BY a.id"""


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = build_saintjude(Path(tmp))
        os.environ["CAERNESS_DB_PATH"] = str(db)
        os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
        conn = connect(db)
        try:
            from engine import domain_actions, hearsay, opening_family, texture
            from engine import life_matters as lm

            day0 = int(conn.execute("SELECT current_day FROM world_state").fetchone()[0])

            def singles(sex: str, young: int, old: int) -> list[int]:
                return [int(r[0]) for r in conn.execute(SINGLE, (sex, day0 - old * 365, day0 - young * 365))]

            men, women = singles("male", 22, 32), singles("female", 20, 30)
            me = int(conn.execute("SELECT actor_id FROM enterprise_staff WHERE status='active' ORDER BY actor_id").fetchone()[0])
            men, women = [m for m in men if m != me], [w for w in women if w != me]
            friends = men[:4]
            conn.execute("DELETE FROM player_state")
            conn.execute("INSERT INTO player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) VALUES (1,?,NULL,'t',?)",
                         (me, day0))
            for f in friends:
                lm.rel.adjust_relationship_pair(conn, me, f, day0, symmetric={"affection_delta": 70.0, "familiarity_delta": 80.0,
                                                                            "trust_delta": 50.0})
            close = texture.circle(conn, me)
            assert all(f in close for f in friends), close
            for f, w in zip(friends, women):
                lm.begin_courtship(conn, day0, f, w, match=True)

            d = day0 - day0 % 30 + 30
            end = d + 30 * 24
            while d <= end:
                for week in range(d - 23, d + 1, 7):
                    conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (week,))
                    lm.weekly(conn, week)
                conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (d,))
                opening_family.resolve_unnamed_marriages(conn, d)
                d += 30
            conn.commit()

            def steps(a: int, b: int) -> dict[str, int]:
                return {str(r[0]): int(r[1]) for r in conn.execute(
                    """SELECT s.stage,s.day FROM life_matter_steps s JOIN life_matters m ON m.id=s.matter_id WHERE m.kind='romance'
                       AND ((m.subject_actor_id=? AND m.other_actor_id=?) OR (m.subject_actor_id=? AND m.other_actor_id=?))""", (a, b, b, a))}

            unions = conn.execute("SELECT actor_a_id,actor_b_id,started_day FROM household_unions WHERE started_day>?", (day0,)).fetchall()
            print("weddings in two years:", len(unions))
            assert len(unions) >= 5
            for a, b, started in unions:
                s = steps(a, b)
                assert {"courting", "engaged", "wed"} <= set(s), (a, b, s)
                assert s["wed"] == started and s["engaged"] <= started - 60 and s["courting"] <= started - 150, (a, b, started, s)
                assert me not in (a, b)
            assert conn.execute("""SELECT 1 FROM life_matter_steps s JOIN life_matters m ON m.id=s.matter_id
                                   WHERE m.kind='romance' AND s.stage='engagement_off'""").fetchone(), "no engagement ever ends"

            # the circle: every step reaches him, and he is asked to the wedding
            reached = {int(str(r[0]).split(":")[1]) for r in conn.execute(
                "SELECT fact_key FROM knowledge WHERE knower_actor_id=? AND fact_key LIKE 'step:%'", (me,))}
            stops = {h["source_id"] for h in hearsay.stops(conn, me, day0, end)}
            weddings = 0
            for f, w in zip(friends, women):
                rows = conn.execute("""SELECT s.id,s.stage,s.actors FROM life_matter_steps s JOIN life_matters m ON m.id=s.matter_id
                                       WHERE m.kind='romance' AND m.subject_actor_id=? AND m.other_actor_id=?""", (f, w)).fetchall()
                assert rows and all(int(r["id"]) in reached for r in rows), [tuple(r) for r in rows]
                stages = {r["stage"]: r for r in rows}
                if "engaged" in stages:
                    assert int(stages["engaged"]["id"]) in stops
                    assert str(me) in str(stages["invited"]["actors"]).split(","), dict(stages["invited"])
                weddings += "wed" in stages
            assert weddings >= 1

            # a proposal needs a courtship, and acceptance is an engagement, not a marriage
            day = int(conn.execute("SELECT current_day FROM world_state").fetchone()[0])
            courting = {int(x) for r in conn.execute("SELECT subject_actor_id,other_actor_id FROM life_matters WHERE kind='romance'") for x in r if x}
            a = next(i for i in singles("male", 25, 40) if i not in courting and i != me)
            b = next(i for i in singles("female", 22, 38) if i not in courting and i != me)
            conn.execute("UPDATE actors SET current_location_id=(SELECT current_location_id FROM actors WHERE id=?) WHERE id=?", (a, b))
            lm.rel.adjust_relationship_pair(conn, a, b, day, symmetric={"trust_delta": 70.0, "stance_delta": 60.0, "familiarity_delta": 60.0})
            conn.execute("UPDATE relationships SET started_day=? WHERE actor_a_id IN (?,?) AND actor_b_id IN (?,?)", (day - 400, a, b, a, b))
            assert domain_actions._union_option(conn, a, day) is None, "proposed without courting"
            lm.begin_courtship(conn, day, a, b, since=day - 400)
            option = domain_actions._union_option(conn, a, day)
            assert option is not None and option.target_actor_id == b, option
            terms = {"domain_action": {"kind": "propose_union", "payload": option.payload, "initiator_actor_id": a}}
            result = domain_actions.apply_accepted_interaction_domain_action(
                conn, {"id": 0, "terms_json": json.dumps(terms), "proposer_actor_id": a, "recipient_actor_id": b}, day)
            assert not conn.execute("SELECT 1 FROM household_unions WHERE status='active' AND actor_a_id IN (?,?)", (a, b)).fetchone(), result
            assert lm.courtship(conn, a, b)["stage"] == "engaged", result
        finally:
            conn.close()
    print("PASS p2_unions_test")


if __name__ == "__main__":
    main()
