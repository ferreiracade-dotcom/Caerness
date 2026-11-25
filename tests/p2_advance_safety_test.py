"""P2: a skip cannot be applied twice, the last skip can be undone, and a new chat is told what has already passed."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}}, "accept": True}


def day_of() -> int:
    from engine.db import connect
    with connect() as conn:
        return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        os.environ.pop("CAERNESS_BACKUP_DIR", None)
        os.environ.pop("CAERNESS_WORLDS_DIR", None)
        from connector import campaign, server

        campaign._packaged_db = lambda pkg_id: base
        db = campaign.open_campaign("undo", package="saintjude")
        made = server.author("c1", "protagonist", PROTAGONIST)
        assert "error" not in made and made.get("actor_id"), made
        start = day_of()

        # the day the skip starts from must be stated, so a repeat cannot pass the days twice
        missing = server.advance("a0", 3, "work at the garage")
        assert "from_day" in missing.get("error", ""), missing
        assert day_of() == start

        first = server.advance("a1", 3, "work at the garage", from_day=start)
        assert "error" not in first and first["day_started"] == start, first
        after = day_of()
        assert after > start

        again = server.advance("a1-retry-new-id", 3, "work at the garage", from_day=start)
        assert again.get("status") == "refused" and day_of() == after, again
        assert again["already_advanced"]["operation_id"] == "a1", again
        assert str(after) in again["reason"], again
        same = server.advance("a1", 3, "work at the garage", from_day=start)  # the very same call still replays
        assert same.get("replayed") and day_of() == after, same

        told = server.resume_current()
        last = told["recent_advances"][-1]
        assert (last["from_day"], last["to_day"]) == (start, after) and "garage" in last["purpose"], told["recent_advances"]

        # undo: first what would be lost, then only on confirm
        noted = server.note("n1", "He keeps the spare key under the vise.")
        assert "error" not in noted, noted
        preview = server.advance("u1", 0, "", undo=True)
        assert preview["status"] == "preview" and preview["restores_day"] == start and day_of() == after, preview
        assert [x["tool"] for x in preview["would_lose"]] == ["advance", "note"], preview
        done = server.advance("u2", 0, "", undo=True, confirm=True)
        assert done["status"] == "undone" and done["day"] == start and day_of() == start, done
        from engine.db import connect
        with connect() as conn:
            assert not conn.execute("SELECT 1 FROM gm_notes WHERE text LIKE '%vise%'").fetchone()
            assert not conn.execute("SELECT 1 FROM connector_calls WHERE call_id='a1'").fetchone()
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        replay = server.advance("u2", 0, "", undo=True, confirm=True)
        assert replay.get("replayed") and day_of() == start, replay
        nothing = server.advance("u3", 0, "", undo=True, confirm=True)
        assert nothing["status"] == "refused" and day_of() == start, nothing

        # only the newest few undo points are kept, and they undo in order
        marks = []
        for i in range(5):
            marks.append(day_of())
            r = server.advance(f"b{i}", 1, "a quiet day", from_day=marks[-1])
            assert "error" not in r, r
        kept = sorted((db.parent / "undo").glob("undo-*.db"))
        assert len(kept) == 3, kept
        back = server.advance("u4", 0, "", undo=True, confirm=True)
        assert back["day"] == marks[-1] == day_of(), back
        back = server.advance("u5", 0, "", undo=True, confirm=True)
        assert back["day"] == marks[-2] == day_of(), back
        assert not [s for s in campaign.list_saves("saintjude") if s["save"] != "undo"], "undo points are not saves"
    print("PASS p2_advance_safety_test")


if __name__ == "__main__":
    main()
