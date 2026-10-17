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
            # The civil date and season are in the scene (gap 4a, canon "The calendar and dating convention").
            assert s["date"] == "1 First Month, 624 SV" and s["season"] == "Spring", (s["date"], s["season"])
            from engine.civil_calendar import season_for_day, format_sv_date
            assert (format_sv_date(100), season_for_day(100)) == ("10 Fourth Month, 624 SV", "Summer")
            assert [season_for_day(d) for d in (90, 91, 181, 182, 273, 364, 365)] == ["Spring", "Summer", "Summer", "Autumn", "Winter", "Winter", "Spring"]
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

            # Partial matches never surface engine stand-ins such as "[STRUCTURAL] ... grain hinterland".
            assert not any(n.startswith("[") for n in lookup(conn, "grain hinterland").get("candidates", [])), lookup(conn, "grain hinterland")
            assert lookup(conn, "grain hinterland")["found"] is False
            # Sex and organisation are shown, so the GM cannot guess them from names (owner play check 2026-10-16).
            for p in compact_scene(conn)["present"]:
                sex = conn.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (p["id"],)).fetchone()
                if sex and sex[0] in ("female", "male"):
                    assert p["sex"] in ({"female": ("woman", "girl"), "male": ("man", "boy")}[sex[0]]), p
            boss = conn.execute(
                """SELECT a.name,o.name,p.role_kind,lp.demographic_sex FROM underworld_personnel p
                   JOIN underworld_organizations o ON o.id=p.organization_id JOIN actors a ON a.id=p.actor_id
                   JOIN actor_life_profiles lp ON lp.actor_id=a.id
                   WHERE p.status='active' AND p.role_kind='crew_leader' ORDER BY a.id LIMIT 1""").fetchone()
            lb = lookup(conn, boss[0])["basics"]
            assert any(m.startswith(f"crew leader, {boss[1]}") for m in lb["member_of"]), lb
            assert lb["sex"] == ("woman" if boss[3] == "female" else "man"), lb
            member = conn.execute(
                """SELECT a.name,i.name FROM institution_memberships m JOIN actors a ON a.id=m.member_actor_id
                   JOIN actors i ON i.id=m.institution_actor_id WHERE m.status='active' AND a.actor_type='character'
                     AND (SELECT COUNT(*) FROM actors x WHERE x.name=a.name)=1 ORDER BY a.id LIMIT 1""").fetchone()
            if member:
                assert any(member[1] in m for m in lookup(conn, member[0])["basics"]["member_of"]), member

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
            from engine.ledger import SCALES
            mn = h["means"]
            assert mn["purse"] in set(SCALES) | {"nothing"}, mn
            assert mn["business_cash"]["Test Lantern House"] in set(SCALES) | {"nothing"}, mn
            assert not any(c.isdigit() for c in json.dumps(mn)), mn
            assert _j(compact_scene(conn)) <= 4000

            # Standing and manners (culture plan, Task 3): kin shows as kin, a stranger still gets words, the room has manners.
            base = compact_scene(conn)
            assert base["manners"] and len(base["manners"]) <= 300, base.get("manners")
            others = [p for p in base["present"] if p["id"] != me]
            kin_p = others[0]
            stranger = next(p for p in others[1:] if "knows" not in p)
            for q in (me, kin_p["id"]):
                conn.execute("DELETE FROM kinship_links WHERE ? IN (actor_a_id,actor_b_id) AND kin_kind IN ('parent','child')", (q,))
            conn.execute("UPDATE actor_life_profiles SET demographic_sex='male' WHERE actor_id=?", (kin_p["id"],))
            conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?, 'parent','recognized',0)",
                         (kin_p["id"], me))
            conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?, 'child','recognized',0)",
                         (me, kin_p["id"]))
            conn.commit()
            s3 = compact_scene(conn)
            byid = {p["id"]: p for p in s3["present"]}
            assert byid[kin_p["id"]]["kin"] == "your father", byid[kin_p["id"]]
            assert "knows" not in byid[kin_p["id"]]
            assert stranger["id"] != kin_p["id"] and "knows" not in byid[stranger["id"]], byid[stranger["id"]]
            assert "kin" not in byid[stranger["id"]] and "None" not in json.dumps(byid[stranger["id"]]), byid[stranger["id"]]
            assert all(len(json.dumps(p, ensure_ascii=False)) <= 330 for p in s3["present"]), max(len(json.dumps(p)) for p in s3["present"])
            lk = lookup(conn, kin_p["name"])
            assert lk["standing"]["kin"] == "your father" and "relationship" not in lk, lk
            assert not any(c.isdigit() for c in json.dumps(lk.get("standing", {}))), lk["standing"]
            assert not any(c.isdigit() for c in json.dumps(s3.get("you_here", {})))
            print("scene bytes", _j(s3), "per-person max", max(len(json.dumps(p, ensure_ascii=False)) for p in s3["present"]))
    print("connector_views_test passed")


if __name__ == "__main__":
    run()
