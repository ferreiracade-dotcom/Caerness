"""Play begins with courtships and engagements already under way, enough for weddings to come at the world's rate from the
first day, and an older save is given them by its migration; the protagonist is never put into one.
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


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = build_saintjude(Path(tmp))
        os.environ["CAERNESS_DB_PATH"] = str(db)
        os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
        conn = connect(db)
        try:
            from engine import db as engine_db
            from engine import hearsay
            from engine import opening_family as of
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])

            def under_way():
                rows = conn.execute("SELECT * FROM life_matters WHERE kind='romance' AND status='open' ORDER BY id").fetchall()
                return [(r, json.loads(r["data_json"])) for r in rows]

            seeded = under_way()
            courting = [(r, d) for r, d in seeded if r["stage"] == "courting"]
            engaged = [(r, d) for r, d in seeded if r["stage"] == "engaged"]
            assert courting and engaged and len(courting) + len(engaged) == len(seeded), (len(courting), len(engaged), len(seeded))
            people = [a for r, _ in seeded for a in (r["subject_actor_id"], r["other_actor_id"])]
            assert len(people) == len(set(people)), "nobody is in two"
            marks = ",".join("?" * len(people))
            named = [r[0] for r in conn.execute(f"SELECT name FROM actors WHERE id IN ({marks}) AND name GLOB '* [A-Z]. *'", people)]
            assert not named, ("told apart by an initial", named[:5])
            for r, d in seeded:
                assert d["match"] == 1 and d["since"] < day and r["next_day"] > day, (dict(r), d)
            assert all(d["wed_day"] == r["next_day"] > day for r, d in engaged)
            # weddings due in the first quarter, against a quarter of a year's weddings at the draws' own rates
            partners = {int(r["other_actor_id"]) for r, _ in seeded}  # described for the courtship, so not part of the base rate
            rates = [of._marry_rate(conn, p, day) for p in of._person_rows(conn, day) if int(p["id"]) not in partners]
            yearly = sum(x[0] for x in rates if x)
            breaks = 0.12
            due = sum(1 for r, d in engaged if d["wed_day"] <= day + 90) * (1 - breaks)
            print(f"{len(courting)} courting, {len(engaged)} engaged; {due:.1f} weddings due in 90 days against {yearly * 90 / 365:.1f}")
            assert 0.5 * yearly * 90 / 365 <= due <= 1.7 * yearly * 90 / 365, (due, yearly)
            assert not of.seed_lived_courtships(conn), "once per world"

            # an older save, with a protagonist already in play
            mine = int(courting[0][0]["subject_actor_id"])
            conn.execute("DELETE FROM life_matter_steps WHERE matter_id IN (SELECT id FROM life_matters WHERE kind='romance')")
            conn.execute("DELETE FROM life_matters WHERE kind='romance'")
            conn.execute("DELETE FROM engine_meta WHERE key='lived_courtships_version'")
            conn.execute("DELETE FROM player_state")
            conn.execute("INSERT INTO player_state(id,player_actor_id,current_location_id,campaign_name,updated_day) VALUES (1,?,NULL,'t',1)", (mine,))
            conn.execute("UPDATE engine_meta SET value='131' WHERE key='schema_version'")
            conn.execute("DELETE FROM schema_migrations WHERE version>=132")
            conn.commit()
        finally:
            conn.close()
        os.environ["CAERNESS_TEST_MODE"] = "1"
        os.environ["CAERNESS_BACKUP_DIR"] = str(Path(tmp) / "backups")
        engine_db.init_db()
        conn = connect(db)
        try:
            rows = conn.execute("SELECT subject_actor_id,other_actor_id,stage FROM life_matters WHERE kind='romance' AND status='open'").fetchall()
            assert {r["stage"] for r in rows} == {"courting", "engaged"}, len(rows)
            assert not [r for r in rows if mine in (r["subject_actor_id"], r["other_actor_id"])]
            assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == engine_db.SCHEMA_VERSION
            # what was written down as past never arrives later as news
            viewer = int(conn.execute("""SELECT k.actor_b_id FROM kinship_links k JOIN life_matters m ON m.subject_actor_id=k.actor_a_id
                                         WHERE m.kind='romance' AND k.ended_day IS NULL ORDER BY m.id LIMIT 1""").fetchone()[0])
            hearsay.reach(conn, viewer, day)
            old = conn.execute("""SELECT s.day FROM knowledge k JOIN life_matter_steps s ON k.fact_key LIKE 'step:' || s.id || ':%'
                                  WHERE k.knower_actor_id=? AND s.day<?""", (viewer, day - 14)).fetchall()
            assert not old, [r[0] for r in old]
            conn.rollback()
        finally:
            conn.close()
    print("PASS p2_lived_courtships_test")


if __name__ == "__main__":
    main()
