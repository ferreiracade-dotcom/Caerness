from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "resume.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine.player import set_player
        from connector.session import load_rulebook, resume
        from connector.store import ensure_connector_schema

        rb = load_rulebook()
        for needle in ("Close third person, past tense", "Don't switch to italic reported speech", "narrate", "after `act`"):
            assert needle in rb or needle.lower() in rb.lower(), needle
        # Owner play check 2026-10-16: silence in the engine is not emptiness; no engine talk in the fiction.
        for needle in ("Where the engine is silent, invent", "lived history", "Never mention the engine",
                       "open straight into a scene", "through `lore`", "Don't invent visitors", "comes up in a chat", "No engine figure ever appears in the prose",
                       "The engine decides whether it works"):
            assert needle in rb, needle
        assert rb.startswith("You are the game master for Caerness.")
        spec = (ROOT / "docs/superpowers/specs/2026-10-16-claude-connector-design.md").read_text(encoding="utf-8")
        body = rb.split("\n\n", 1)[1].strip()
        assert body in spec, "rulebook must be Appendix A verbatim"

        init_db()
        with connect() as conn:
            ensure_connector_schema(conn)
            r = resume(conn)
            assert r == {"needs_setup": True, "how": r["how"]} and "setup_campaign.py" in r["how"]
            row = conn.execute(
                "SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1").fetchone()
            set_player(conn, int(row["id"]), campaign_name="resume-test")
            conn.commit()
            r = resume(conn)
            for k in ("rulebook", "campaign", "protagonist", "scene", "how_to_play"):
                assert k in r, k
            assert r["campaign"] == "resume-test" and r["protagonist"]["id"] == int(row["id"])
            assert r["how_to_play"].count("\n") == 4 and r["how_to_play"].startswith("1. Check established facts")
            assert len(json.dumps(r, ensure_ascii=False)) <= 12000
            assert conn.execute("SELECT value FROM connector_meta WHERE key='last_resume_at'").fetchone()
            # Nothing stored yet: no story, and the GM is asked to draft the sheet.
            assert "story" not in r and "sheet_missing" in r, r.keys()
            from connector import store
            store.record(conn, "recap", "Willem rode in at dusk.", "rr1", threads=["Rooks probing"])
            store.record(conn, "rule", "Never ask me to name subordinates.", "rr2")
            store.record(conn, "sheet", "Heavy-set, close-cropped grey hair.", "rr3", field="appearance")
            conn.commit()
            r = resume(conn)
            assert r["story"]["live_thread"]["open_threads"] == ["Rooks probing"], r["story"]
            assert r["story"]["standing_rules"] == ["Never ask me to name subordinates."]
            assert "sheet_missing" not in r
            assert len(json.dumps(r, ensure_ascii=False)) <= 14000
            # Fully loaded continuity stays inside the resume budget.
            for i in range(3):
                store.record(conn, "recap", "r" * 900, f"full-r{i}", threads=["t" * 300] * 12)
            for f in store.SHEET_FIELDS:
                store.record(conn, "sheet", "s" * 900, f"full-s-{f}", field=f)
            for i in range(20):
                store.record(conn, "rule", "u" * 900 + str(i), f"full-u{i}")
            conn.commit()
            size = len(json.dumps(resume(conn), ensure_ascii=False))
            assert size <= 19000, size
    print("connector_resume_test passed")


if __name__ == "__main__":
    run()
