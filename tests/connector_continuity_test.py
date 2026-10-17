from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "continuity.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine.player import set_player
        from connector import store

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            store.ensure_connector_schema(conn)
            me = int(conn.execute("SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()[0])
            set_player(conn, me)
            conn.commit()

            args = {"k": "recap"}
            first = lambda: store.record(conn, "recap", "Willem rode in at dusk.", "c1", threads=["Rooks probing the Green Table", "x" * 500])
            r = store.run_once(conn, "c1", "note", args, first)
            assert r["saved"] == "recap", r
            store.run_once(conn, "c1", "note", args, first)
            assert conn.execute("SELECT COUNT(*) FROM campaign_recaps").fetchone()[0] == 1  # retry stores once
            for i in range(4):
                store.record(conn, "recap", f"moment {i} " + "y" * 900, f"r{i}", threads=[f"t{j}" for j in range(12)])
            cont = store.continuity(conn)
            assert [t[:8] for t in cont["live_thread"]["recent"]] == ["moment 1", "moment 2", "moment 3"], cont
            assert all(len(t) <= 600 for t in cont["live_thread"]["recent"])
            assert cont["live_thread"]["open_threads"] == [f"t{j}" for j in range(8)]  # latest recap, max 8

            store.record(conn, "sheet", "Heavy-set, grey at the temples.", "s1", field="appearance")
            store.record(conn, "sheet", "Heavy-set, close-cropped grey hair.", "s2", field="appearance")
            assert store.continuity(conn)["character_sheet"] == {"appearance": "Heavy-set, close-cropped grey hair."}
            store.record(conn, "rule", "Never ask me to name subordinates.", "u1")
            assert store.continuity(conn)["standing_rules"] == ["Never ask me to name subordinates."]
            # Rules can be retired, and at most the 8 newest are returned.
            store.record(conn, "rule", "Never ask me to name subordinates.", "u1r", field="retire")
            assert "standing_rules" not in store.continuity(conn)
            try:
                store.record(conn, "rule", "no such rule", "u1x", field="retire"); raise AssertionError("accepted")
            except ValueError as e:
                assert "no active rule" in str(e), e
            for i in range(11):
                store.record(conn, "rule", f"rule {i}", f"u{i+10}")
            assert store.continuity(conn)["standing_rules"] == [f"rule {i}" for i in range(3, 11)]
            assert len(store.record(conn, "sheet", "z" * 900, "s3", field="voice") and store.continuity(conn)["character_sheet"]["voice"]) <= 300
            store.record(conn, "error", "Engine placed Vera in Rivermoor.", "e1")
            assert conn.execute("SELECT status FROM error_reports").fetchone()[0] == "open"
            # Review 3: open error reports reach the GM as `corrections` (newest first, at most 5, text only), and note closes them.
            assert store.continuity(conn)["corrections"] == ["Engine placed Vera in Rivermoor."], store.continuity(conn)
            for i in range(6):
                store.record(conn, "error", f"Flagged {i}", f"e{i + 2}")
            assert store.continuity(conn)["corrections"] == [f"Flagged {i}" for i in (5, 4, 3, 2, 1)], store.continuity(conn)["corrections"]
            done = store.record(conn, "error", "Flagged 5", "e20", field="fixed")
            assert done["fixed"] is True and "Flagged 5" not in store.continuity(conn)["corrections"], done
            assert store.continuity(conn)["corrections"][0] == "Flagged 4"
            rid = conn.execute("SELECT id FROM error_reports WHERE text='Flagged 4'").fetchone()[0]
            store.record(conn, "error", str(rid), "e21", field="fixed")  # by id as well as by text
            assert conn.execute("SELECT status FROM error_reports WHERE id=?", (rid,)).fetchone()[0] == "fixed"
            try:
                store.record(conn, "error", "no such report", "e22", field="fixed"); raise AssertionError("accepted")
            except ValueError as e:
                assert "no open error report" in str(e), e
            for t in ("Flagged 3", "Flagged 2", "Flagged 1", "Flagged 0", "Engine placed Vera in Rivermoor."):
                store.record(conn, "error", t, "e-" + t, field="fixed")
            assert "corrections" not in store.continuity(conn)
            store.record(conn, "error", "Engine placed Vera in Rivermoor.", "e1b")
            assert store.record(conn, "detail", "limps", "d1", subject_kind="actor", subject_id=me)["subject_kind"] == "actor"
            for bad in (lambda: store.record(conn, "diary", "x", "b1"),
                        lambda: store.record(conn, "sheet", "x", "b2", field="shoe size")):
                try:
                    bad()
                    raise AssertionError("accepted")
                except ValueError as e:
                    assert "must be one of" in str(e), e

            # A campaign from before this change: tables absent until ensure_connector_schema runs, then empty continuity.
            for t in ("campaign_recaps", "standing_rules", "character_sheet", "error_reports"):
                conn.execute(f"DROP TABLE {t}")
            store.ensure_connector_schema(conn)
            assert store.continuity(conn) == {}
    print("connector_continuity_test passed")


if __name__ == "__main__":
    run()
