from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _j(x) -> int:
    return len(json.dumps(x, ensure_ascii=False))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "views.db"
        shutil.copy2(ROOT / "data" / "caerness.db", db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine.player import set_player
        from connector.store import add_note, ensure_connector_schema
        from connector.views import compact_scene, lookup

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            ensure_connector_schema(conn)
            row = conn.execute(
                "SELECT id FROM actors WHERE actor_type='character' AND current_location_id IS NOT NULL ORDER BY id LIMIT 1"
            ).fetchone()
            set_player(conn, int(row["id"]))
            conn.commit()
            packets_before = conn.execute("SELECT COUNT(*) FROM scene_packets").fetchone()[0]

            s = compact_scene(conn)
            for k in ("day", "location", "protagonist", "present", "pending", "news", "competence", "condition", "notes", "recent_operations"):
                assert k in s, k
            for k in ("narrator_rules", "embodiment", "canon", "player", "scene_packet_id"):
                assert k not in s, k
            assert _j(s) <= 4000, _j(s)
            assert not any(v is None for v in s.values())
            assert s["protagonist"]["id"] == int(row["id"]) and s["location"]["name"]
            assert len(s["present"]) >= 1, "opening location should have people present"
            # People and organisations are separate lists (owner play check 2026-10-16).
            ids = [a["id"] for a in s["present"]]
            kinds = {r[0] for r in conn.execute(f"SELECT actor_type FROM actors WHERE id IN ({','.join('?'*len(ids))})", ids)}
            assert kinds == {"character"}, kinds
            assert "institutions_here" in s
            assert conn.execute("SELECT COUNT(*) FROM scene_packets").fetchone()[0] == packets_before

            who = s["present"][0]
            r = lookup(conn, who["name"])
            assert r["found"] is True and r["kind"] == "actor" and r["name"] == who["name"]
            assert _j(r) <= 2000, _j(r)
            assert "truth_event_id" not in json.dumps(r)
            assert lookup(conn, str(who["id"]))["id"] == who["id"]
            assert lookup(conn, "zzzz-nobody") == {"found": False, "candidates": []}
            part = lookup(conn, who["name"].split()[0][:4])
            assert part["found"] in (True, False)
            assert len(part.get("candidates", [])) <= 5

            # Non-ASCII names round-trip exactly (the opening world has some in location names).
            odd = conn.execute(
                "SELECT name FROM actors WHERE name GLOB '*[^ -~]*' UNION ALL SELECT name FROM locations WHERE name GLOB '*[^ -~]*' LIMIT 1"
            ).fetchone()
            assert odd is not None, "opening world should contain a non-ASCII name"
            lr = lookup(conn, odd[0])
            assert lr["found"] is True and lr["name"] == odd[0]
            assert json.loads(json.dumps(lr, ensure_ascii=False))["name"] == odd[0]

            add_note(conn, "actor", who["id"], "owes the miller two sacks", "n1")
            conn.commit()
            s2 = compact_scene(conn)
            assert any("owes the miller" in n["text"] and n["about"] == who["name"] for n in s2["notes"])
            assert "owes the miller" in json.dumps(lookup(conn, who["name"])["notes"])
            assert _j(s2) <= 4000

            # A spouse is described as whose spouse, never a bare "spouse" (owner play check 2026-10-16).
            from connector.views import _who
            sp = conn.execute(
                """SELECT a.* FROM actors a JOIN household_unions u ON a.id IN (u.actor_a_id,u.actor_b_id)
                   WHERE a.subtype='spouse' AND u.status='active' LIMIT 1""").fetchone()
            partner = conn.execute(
                """SELECT b.name FROM household_unions u JOIN actors b ON b.id=CASE WHEN u.actor_a_id=? THEN u.actor_b_id ELSE u.actor_a_id END
                   WHERE ? IN (u.actor_a_id,u.actor_b_id) AND u.status='active'""", (sp["id"], sp["id"])).fetchone()[0]
            assert _who(conn, sp).startswith(f"spouse of {partner} ("), _who(conn, sp)

            # What the protagonist owns and runs is in the scene (owner play check 2026-10-16).
            from engine.civilian import create_enterprise
            from engine.merchant import add_enterprise_staff
            me = int(row["id"])
            eid = create_enterprise(conn, "Test Lantern House", "service", owner_actor_id=me,
                                    location_id=s["location"]["id"], capital=31, cash=12, debt=2)
            add_enterprise_staff(conn, eid, who["id"], role="manager")
            conn.commit()
            h = compact_scene(conn)["holdings"]
            biz = [b for b in h["businesses"] if b["name"] == "Test Lantern House"]
            assert biz and biz[0]["capital"] == 31 and biz[0]["cash"] == 12, h
            assert biz[0]["standing"].startswith("capital ") and "businesses" in biz[0]["standing"], biz
            assert any(st["name"] == who["name"] and st["role"] == "manager" for st in biz[0]["staff"]), biz
            lb = lookup(conn, "Test Lantern House")
            assert lb["found"] and lb["kind"] == "business" and lb["basics"]["owner"], lb
            assert _j(compact_scene(conn)) <= 4000
    print("connector_views_test passed")


if __name__ == "__main__":
    run()
