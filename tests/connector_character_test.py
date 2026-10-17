"""Connector: a campaign with no protagonist gets the creation text; the proposal previews, replays by call_id, refuses with a reason, and accepts."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def run():
    from new_character_test import open_copy
    from connector import store
    from connector.authoring import author
    from connector.session import resume
    from connector.views import compact_scene

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = open_copy(tmp)
        store.ensure_connector_schema(c)
        r = resume(c)
        assert set(r) == {"needs_character", "creation", "rulebook"} and len(r["creation"]) <= 1800, set(r)
        base = {"age": 38, "sex": "female", "place": "Toll's Reach", "work": "lamp-lighter", "draw": 0, "concept": "a quiet lamp-lighter"}
        n0 = c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        p1 = author(c, "c1", "protagonist", {**base})
        assert p1["status"] == "draft" and p1["summary"]["who"] and c.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == n0, p1
        assert author(c, "c1", "protagonist", {**base})["replayed"]
        bad = author(c, "c2", "protagonist", {**base, "name": c.execute(
            "SELECT a.name FROM actors a JOIN source_identity_map m ON m.entity_id=a.id AND m.entity_kind='actor' WHERE a.actor_type='character' LIMIT 1").fetchone()[0]})
        assert bad["status"] == "refused" and "canon" in bad["reason"] and bad["reason_kind"] == "contradiction", bad
        assert author(c, "c2b", "person", {"age": 30})["status"] == "refused"  # nobody to author for yet
        done = author(c, "c3", "protagonist", {**base, "accept": True})
        assert done["status"] == "created" and done["summary"] == p1["summary"], done
        assert "sheet" not in done
        assert author(c, "c4", "protagonist", {**base, "accept": True})["status"] == "refused"
        sheet = {r["field"] for r in c.execute("SELECT field FROM character_sheet")}
        assert {"history", "standing"} <= sheet, sheet
        r = resume(c)
        assert "rulebook" in r and "needs_character" not in r and len(json.dumps(r, ensure_ascii=False)) <= 20700
        sc = compact_scene(c)
        assert "error" not in sc and sc["protagonist"]["id"] == done["actor_id"]
        c.close()
    print("connector_character_test passed")


if __name__ == "__main__":
    run()
