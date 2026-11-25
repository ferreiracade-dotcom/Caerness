"""In a world with ordinary-life matters, news about other people reaches the protagonist through somebody he knows or not at
all, what has gone stale is never delivered, and what he saw or learned for himself is kept.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server
        from engine import life_matters as lm
        from engine import texture
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("news", package="saintjude")
        made = server.author("a1", "protagonist", {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill",
                                                   "work": "mechanic", "accept": True,
                                                   "people": [{"name": "Rosa Quattrone", "relation": "friend", "age": 23, "sex": "female"}]})
        assert made["status"] == "created", made
        me = made["actor_id"]
        with connect() as conn:
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
            rosa = int(conn.execute("SELECT id FROM actors WHERE name='Rosa Quattrone'").fetchone()[0])
            texture.ingest(conn, me, None, day)  # whatever was waiting from the opening
            conn.execute("DELETE FROM delivery_ledger WHERE viewer_actor_id=?", (me,))
            circ = texture.circle(conn, me)
            known = lm.known_by(conn, sorted(circ))
            others = [int(r[0]) for r in conn.execute(
                """SELECT a.id FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id WHERE lp.life_status='living'
                   ORDER BY a.id DESC LIMIT 400""")]
            strangers = [a for a in others if a != me and a not in circ and a not in known]
            theirs, nobody = strangers[0], strangers[1]
            conn.execute("""INSERT OR REPLACE INTO relationships(actor_a_id,actor_b_id,familiarity) VALUES (?,?,60)""", (theirs, rosa))

            def learned(text, about, ago=0, witness=False):
                eid = int(conn.execute("INSERT INTO events(day,event_type,title,summary,severity) VALUES (?,?,?,?,3)",
                                       (day - ago, "report", text, text)).lastrowid)
                conn.execute("INSERT INTO event_targets(event_id,actor_id,impact) VALUES (?,?,'x')", (eid, about))
                if witness:
                    conn.execute("""INSERT INTO event_witnesses(event_id,actor_id,witness_type,confidence,learned_day)
                                    VALUES (?,?,'observer',0.9,?)""", (eid, me, day))
                conn.execute("""INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,truth_event_id,learned_day)
                                VALUES (?,?,?,0.8,?,?)""", (me, f"event:{eid}", text, eid, day - ago))

            learned("Rosa is bringing in less", rosa)
            learned("Rosa moved house in the summer", rosa, ago=60)
            learned("A man Rosa knows lost a job", theirs)
            learned("A stranger is bringing in less", nobody)
            learned("He saw a stranger fall in the street", nobody, witness=True)
            conn.execute("""INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day)
                            VALUES (?,'own:1','The garage opens at seven',0.9,?)""", (me, day))
            for n in range(30):  # public happenings among people nobody around him knows
                eid = int(conn.execute("INSERT INTO events(day,event_type,title,summary,severity) VALUES (?,?,?,?,5)",
                                       (day, "report", f"Far {n}", f"Far {n}")).lastrowid)
                conn.execute("""INSERT INTO event_information(event_id,visibility,secrecy,rumorability,reliability,registered_day)
                                VALUES (?,'public',0,0.5,0.9,?)""", (eid, day))
                conn.execute("INSERT INTO event_targets(event_id,actor_id,impact) VALUES (?,?,'x')", (eid, nobody))
            conn.execute("""INSERT INTO delivery_ledger(viewer_actor_id,item_key,kind,text,via,significance,first_day)
                            VALUES (?,'old:1','news','Something from last season','from someone',99,?)""", (me, day - 109))
            conn.execute("""INSERT INTO delivery_ledger(viewer_actor_id,item_key,kind,text,via,significance,first_day)
                            VALUES (?,'old:2','about_him','Something said of him a while back','from someone',99,?)""", (me, day - 109))
            conn.execute("DELETE FROM bearing_marks WHERE actor_id=? AND kind='habit'", (me,))
            texture.ingest(conn, me, None, day)
            got = []
            while True:
                items = texture.deliver(conn, me, day)
                if not items:
                    break
                got += items
            said = {i["what"]: i["via"] for i in got}
            assert "Rosa" in said["Rosa is bringing in less"], said
            assert "Rosa" in said["A man Rosa knows lost a job"], said
            assert "A stranger is bringing in less" not in said, said
            assert "Rosa moved house in the summer" not in said, said
            assert "He saw a stranger fall in the street" in said, said
            assert "The garage opens at seven" in said, said
            assert not [w for w in said if w.startswith("Far ")], said
            assert "Something from last season" not in said and "Something said of him a while back" in said, said
    print("PASS p2_news_carriers_test")


if __name__ == "__main__":
    main()
