"""G1: wants. What a person would like to have, worked out from his age, sex, temperament, work, household and circle, each
with a rough price and a reason. The protagonist's are kept, the player says which matter, and scene and resume show the
few that press most."""
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
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"w{_n[0]:03d}"


def keys(rows) -> set[str]:
    return {r["key"] for r in rows}


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        for name in ("CAERNESS_BACKUP_DIR", "CAERNESS_WORLDS_DIR", "CAERNESS_SHELVED_WORLDS"):
            os.environ.pop(name, None)
        from connector import campaign, server
        from engine import wants
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("g1w", package="saintjude")
        server.author(cid(), "protagonist", PROTAGONIST)
        with connect() as conn:
            me = conn.execute("SELECT player_actor_id FROM player_state").fetchone()[0]
            day = conn.execute("SELECT current_day FROM world_state").fetchone()[0]
            mine = wants.derive(conn, me)
        got = keys(mine)
        # a young single mechanic with no shop and no car: a shop, a car, tools, clothes for going out
        assert {"own_shop_garage", "car", "tools", "going_out_clothes"} <= got, got
        assert "own_shop_store" not in got and "house" not in got and "ring" not in got, got
        for w in mine:
            assert w["what"] and w["reason"] and w["price"] > 0 and 0 < w["strength"] <= 1.5, w
            assert "{" not in w["what"] + w["reason"], w
        assert mine == sorted(mine, key=lambda w: (-w["strength"], w["key"]))
        shop = next(w for w in mine if w["key"] == "own_shop_garage")
        assert shop["item"] == "lease_garage" and shop["per"] == "a month", shop

        # scene and resume show the few that press most, as things on his mind
        shown = server.scene()["market"]["wants"]
        assert 1 <= len(shown) <= 3, shown
        assert all({"id", "want", "why", "price"} <= set(w) for w in shown), shown
        assert all(w["price"].startswith("$") for w in shown), shown
        assert server.resume()["scene"]["market"]["wants"]
        with connect() as conn:
            kept = [dict(r) for r in conn.execute("SELECT * FROM wants WHERE actor_id=?", (me,))]
        assert {r["key"] for r in kept} == got and all(r["status"] == "open" and r["price"] > 0 and r["reason"] for r in kept), kept

        # the player decides which matter: one he cares about leads, one he waves off is gone and stays gone
        last = shown[-1]
        assert not server.note(cid(), "He keeps coming back to it.", kind="want", field="matters", subject_id=last["id"]).get("error")
        first = shown[0]
        assert not server.note(cid(), "He does not care.", kind="want", field="drop", subject_id=first["id"]).get("error")
        now = server.scene()["market"]["wants"]
        assert now[0]["id"] == last["id"] and now[0]["matters"] is True, now
        assert first["id"] not in {w["id"] for w in now}, now
        server.scene()
        with connect() as conn:
            assert conn.execute("SELECT status FROM wants WHERE id=?", (first["id"],)).fetchone()[0] == "dropped"

        # something he says he wants that no rule would guess is kept in his words
        assert not server.note(cid(), "A boat to take out past the harbour light", kind="want", field="matters").get("error")
        now = server.scene()["market"]["wants"]
        assert any("boat" in w["want"] for w in now), now

        # an unknown want id or word is refused
        assert server.note(cid(), "x", kind="want", field="matters", subject_id=999999).get("error")
        assert server.note(cid(), "x", kind="want", field="maybe", subject_id=last["id"]).get("error")

        # wants follow what is true: once he has a car, he no longer wants one
        server.note(cid(), "an old Buick", kind="bearing", field="drives")
        with connect() as conn:
            assert "car" not in keys(wants.derive(conn, me))

        # keeping one's head down hides what one shows; it does not undo having it
        with connect() as conn:
            from engine import db, news_choices
            news_choices.execute_quiet(conn, me, "go_quiet", {}, day)
            assert conn.execute("SELECT status FROM bearing_marks WHERE actor_id=? AND kind='drives'", (me,)).fetchone()[0] == "quiet"
            assert "car" not in keys(wants.derive(conn, me))
            conn.rollback()
            # a save from before this gains the same when it is brought up to date, keeping every mark
            now = conn.execute("SELECT sql FROM sqlite_master WHERE name='bearing_marks'").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM bearing_marks").fetchone()[0]
            conn.execute("ALTER TABLE bearing_marks RENAME TO marks_now")
            conn.execute(now.replace("'active','gone','quiet'", "'active','gone'"))
            conn.execute("INSERT INTO bearing_marks SELECT * FROM marks_now")
            conn.execute("DROP TABLE marks_now")
            db._MIGRATIONS[131][2](conn)
            db._MIGRATIONS[131][2](conn)  # safe to run again
            assert conn.execute("SELECT COUNT(*) FROM bearing_marks").fetchone()[0] == count > 0
            news_choices.execute_quiet(conn, me, "go_quiet", {}, day)
            assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_bearing_marks_actor'").fetchone()
            conn.rollback()

        # having taken a chance quiets that want for as long as the thing lasts, then it can come back
        with connect() as conn:
            today = conn.execute("SELECT current_day FROM world_state").fetchone()[0]
            lasts = next(r for r in wants.data(conn)["wants"] if r["key"] == "tools")["lasts_days"]
            conn.execute("""INSERT INTO temptations(actor_id,want_key,text,price,opened_day,expires_day,status,updated_day)
                            VALUES (?,'tools','A chest of tools',150,?,?,'taken',?)""", (me, today, today, today))
            wants.refresh(conn, me)
            assert "tools" not in keys(wants.derive(conn, me))
            assert "tools" not in keys(wants.standing(conn, me))
            conn.execute("UPDATE temptations SET updated_day=? WHERE actor_id=?", (today - lasts, me))
            conn.execute("UPDATE wants SET status='met',updated_day=? WHERE actor_id=? AND key='tools'", (today - lasts + 1, me))
            wants.refresh(conn, me)
            assert "tools" not in keys(wants.standing(conn, me)), "still within what lasts"
            conn.execute("UPDATE wants SET updated_day=? WHERE actor_id=? AND key='tools'", (today - lasts, me))
            wants.refresh(conn, me)
            assert "tools" in keys(wants.standing(conn, me))
            conn.rollback()

        # anyone can be asked about, without anything being stored for him
        with connect() as conn:
            woman = conn.execute("""SELECT a.id,a.name FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                                    WHERE a.actor_type='character' AND a.status='active' AND p.demographic_sex='female'
                                    AND p.life_status='living' AND p.birth_day BETWEEN ? AND ? ORDER BY a.id LIMIT 1""",
                                 (day - 26 * 365, day - 19 * 365)).fetchone()
            hers = wants.derive(conn, woman[0])
            assert hers and "going_out_dress" in keys(hers) and "going_out_clothes" not in keys(hers), hers
            assert conn.execute("SELECT COUNT(*) FROM wants WHERE actor_id=?", (woman[0],)).fetchone()[0] == 0
            assert not any(" he " in f" {w['reason']} ".lower() for w in hers), hers
        out = server.lookup(f"wants {woman[1]}")
        assert out["found"] and out["who"] == woman[1] and out["wants"], out
        assert server.lookup("wants")["who"] == "Dominic Basile"
        assert not server.lookup("wants Nobody Atall")["found"]
    print("PASS g1_wants_test")


if __name__ == "__main__":
    main()
