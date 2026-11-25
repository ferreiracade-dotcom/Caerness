"""P2.1: ordinary people's lives happen to everyone, from their own state, whether or not the protagonist is anywhere near.

90 days on a Saint Jude opening: matters of several kinds open, they leave real traces (money, ties, health, the law),
they move through stages, they are not centred on the protagonist, and the protagonist is never made to act.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect  # noqa: E402

DAYS = 90


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = build_saintjude(Path(tmp))
        os.environ["CAERNESS_DB_PATH"] = str(db)
        os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
        conn = connect(db)
        try:
            from engine import life_matters, simulation
            assert life_matters.enabled(conn), "the package declares life matters"
            # a protagonist, so the 'never made to act' rule has someone to hold for
            me = int(conn.execute("""SELECT a.id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
                                     WHERE lp.life_status='living' AND lp.demographic_sex='male' AND a.id IN (SELECT actor_id FROM enterprise_staff)
                                     ORDER BY a.id LIMIT 1""").fetchone()[0])
            conn.execute("DELETE FROM player_state")
            conn.execute("INSERT INTO player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) VALUES (1,?,NULL,'t',1)", (me,))
            conn.commit()

            start = int(conn.execute("SELECT current_day FROM world_state").fetchone()[0])
            simulation.advance_connection(conn, DAYS)
            conn.commit()

            rows = conn.execute("SELECT * FROM life_matters WHERE opened_day>?", (start,)).fetchall()
            kinds = {r["kind"] for r in rows}
            subjects = {int(r["subject_actor_id"]) for r in rows}
            print(f"{len(rows)} matters, kinds {sorted(kinds)}, {len(subjects)} subjects")
            assert {"money", "romance", "quarrel", "illness", "work"} <= kinds, f"several kinds must open: {kinds}"

            # not centred on the protagonist: the great majority of subjects have no tie to him at all
            circle = {int(r[0]) for r in conn.execute("SELECT actor_b_id FROM relationships WHERE actor_a_id=?", (me,))} | {me}
            outside = subjects - circle
            assert len(outside) > len(subjects) * 0.9, "matters are generated for the world, not for the protagonist"

            # they move: some have a second step
            steps = conn.execute("SELECT matter_id,COUNT(*) n FROM life_matter_steps GROUP BY matter_id").fetchall()
            assert any(r["n"] >= 2 for r in steps), "matters move through stages"
            # every step names living-or-once-living actors that exist
            bad = conn.execute("""SELECT COUNT(*) FROM life_matters m LEFT JOIN actors a ON a.id=m.subject_actor_id
                                  LEFT JOIN actors b ON b.id=m.other_actor_id
                                  WHERE a.id IS NULL OR (m.other_actor_id IS NOT NULL AND b.id IS NULL)""").fetchone()[0]
            assert bad == 0

            # real effects
            loans = conn.execute("SELECT COUNT(*) FROM economic_flows WHERE metadata_json LIKE '%personal loan%'").fetchone()[0]
            assert loans > 0, "money matters move money"
            rel = conn.execute("SELECT COUNT(*) FROM relationship_history WHERE source_kind='life_matter'").fetchone()[0]
            assert rel > 0, "matters move relationships"
            ill = conn.execute("SELECT COUNT(*) FROM health_conditions WHERE condition_kind='illness'").fetchone()[0]
            assert ill > 0, "illness reaches the health system"

            # the protagonist is never made to act: no money he lent or borrowed by the engine, no blow he struck, no romance he began
            acted = conn.execute("""SELECT * FROM economic_flows WHERE metadata_json LIKE '%(matter %'
                                    AND source_actor_id=? AND day>?""", (me, start)).fetchall()
            assert not acted, f"the engine spent the protagonist's money: {[dict(r) for r in acted]}"
            struck = conn.execute("""SELECT COUNT(*) FROM life_matters m JOIN harm_incidents h ON h.source_kind='life_matter' AND h.source_ref_id=m.id
                                     WHERE m.other_actor_id=? AND h.actor_id=m.subject_actor_id AND h.actor_id<>?""", (me, me)).fetchone()[0]
            assert struck == 0, "the protagonist struck someone offscreen"
        finally:
            conn.close()
    print("PASS p2_life_matters_test")


if __name__ == "__main__":
    main()
