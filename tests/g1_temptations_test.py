"""G1: temptations. Now and then the world puts a concrete chance in the protagonist's way: tied to something he wants, with
a price and a last day, drawn from real places and people in the save, brought by someone he knows or passed in the street.
Nothing sets a beat: chances come the more he wants a thing and the more he is about. Other people take chances on the same
rules, coarsely, so one he sits on can go to someone else, and the record says who. It hangs on the weekly life cadence,
and what is before him is his to take or leave."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude  # noqa: E402

PROTAGONIST = {"name": "Dominic Basile", "sex": "male", "age": 24, "place": "South Hill", "work": "mechanic, engine tuning",
               "family": {"parents": {"father": "alive", "mother": "alive"}, "siblings": 2}, "accept": True}
_n = [0]


def cid() -> str:
    _n[0] += 1
    return f"t{_n[0]:03d}"


def eager(conn) -> None:
    """Make every kind of chance come up at once, and nobody else get to it first (the package data is cached in-process)."""
    from engine import wants
    for rule in wants.data(conn)["wants"]:
        if "comes" in rule:
            rule["comes"], rule["contest"] = 50.0, 0.0


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = build_saintjude(Path(tmp))
        os.environ["CAERNESS_CAMPAIGN_DIR"] = str(Path(tmp) / "campaigns")
        for name in ("CAERNESS_BACKUP_DIR", "CAERNESS_WORLDS_DIR", "CAERNESS_SHELVED_WORLDS"):
            os.environ.pop(name, None)
        from connector import campaign, server
        from engine import org_lifecycle, price_book, temptations, wants
        from engine.db import connect

        campaign._packaged_db = lambda pkg_id: base
        campaign.open_campaign("g1t", package="saintjude")
        server.author(cid(), "protagonist", PROTAGONIST)
        assert temptations.weekly in [fn for _, fn in org_lifecycle._WEEKLY], "it runs on the weekly life cadence"

        # a year of weeks: chances come as the world throws them up, each concrete and real
        with connect() as conn:
            me = conn.execute("SELECT player_actor_id FROM player_state").fetchone()[0]
            start = conn.execute("SELECT current_day FROM world_state").fetchone()[0]
            conn.execute("SAVEPOINT year")
            wanted = {w["key"] for w in wants.derive(conn, me)}
            book = {i["key"]: i for i in price_book.items(conn)}
            rules = {r["key"]: r for r in wants.data(conn)["wants"]}
            count = lambda: conn.execute("SELECT COUNT(*) FROM temptations").fetchone()[0]
            for day in range(start, start + 364, 7):
                temptations.weekly(conn, day)
                before = count()
                temptations.weekly(conn, day)  # the same week twice brings nothing more
                assert count() == before, day
                assert not conn.execute("SELECT 1 FROM temptations WHERE status='open' AND expires_day<?", (day,)).fetchone()
            rows = [dict(r) for r in conn.execute("SELECT * FROM temptations WHERE actor_id=? ORDER BY id", (me,))]
            # an outcome to watch, not a figure to aim at: somewhere about one every two or three weeks
            assert 10 <= len(rows) <= 40, len(rows)
            gaps = {b["opened_day"] - a["opened_day"] for a, b in zip(rows, rows[1:])}
            assert len(gaps) > 1, "never on a fixed beat"
            assert any(r["status"] == "lapsed" for r in rows)
            for r in rows:
                assert r["want_key"] in wanted, r
                assert r["expires_day"] > r["opened_day"] and "{" not in r["text"], r
                where = conn.execute("SELECT name FROM locations WHERE id=?", (r["location_id"],)).fetchone()[0]
                assert where in r["text"], (where, r["text"])
                if r["business_id"] is not None:
                    name = conn.execute("SELECT name FROM civilian_enterprises WHERE id=?", (r["business_id"],)).fetchone()[0]
                    assert name in r["text"], (name, r["text"])
                if r["carrier_actor_id"] is not None:
                    name = conn.execute("""SELECT a.name FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                                           WHERE a.id=? AND p.life_status='living'""", (r["carrier_actor_id"],)).fetchone()[0]
                    assert name in r["text"] and r["carrier_actor_id"] != me, (name, r["text"])
                cheapest = min(book[k]["low"] for k in rules[r["want_key"]]["items"])
                dearest = max(book[k]["high"] for k in rules[r["want_key"]]["items"])
                assert cheapest <= r["price"] <= dearest, (r["price"], r["want_key"])
                assert f"${r['price']:,.0f}" in r["text"] or f"${r['price']:,.2f}" in r["text"], r
            assert any(r["carrier_actor_id"] is not None for r in rows), "some come by word of mouth"
            assert any(r["carrier_actor_id"] is None for r in rows), "some he passes"
            assert any(r["business_id"] is not None for r in rows)

            # what he sat on went to someone real, who has it now
            gone = [r for r in rows if r["status"] == "gone"]
            assert gone, "someone else gets there first now and then"
            for r in gone:
                taker = r["taker_actor_id"]
                assert taker != me and conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status='living'",
                                                    (taker,)).fetchone(), r
                theirs = conn.execute("SELECT * FROM temptations WHERE actor_id=? AND want_key=? AND status='taken' AND price=?",
                                      (taker, r["want_key"], r["price"])).fetchone()
                assert theirs, r

            # everyone else takes chances too, on the same rules, only for what they want badly
            others = [dict(r) for r in conn.execute("SELECT * FROM temptations WHERE actor_id<>?", (me,))]
            assert len({r["actor_id"] for r in others}) >= 50, len(others)
            assert all(r["status"] == "taken" and r["price"] > 0 and "{" not in r["text"] for r in others)
            for key in ("car", "show_car", "television"):
                one = next((r for r in others if r["want_key"] == key), None)
                if one:
                    assert conn.execute("SELECT 1 FROM bearing_marks WHERE actor_id=? AND status='active'", (one["actor_id"],)).fetchone(), one
                    assert key not in {w["key"] for w in wants.derive(conn, one["actor_id"])}, "having it, they no longer want it"
            conn.execute("ROLLBACK TO year")
            conn.execute("RELEASE year")

            # the more he wants a thing and the more he is about, the more of it comes his way
            wants.refresh(conn, me)
            car = next(w for w in wants.standing(conn, me) if w["key"] == "car")
            plain = temptations.odds(conn, me, car, rules["car"])
            assert 0 < plain < 1
            assert temptations.odds(conn, me, {**car, "status": "matters"}, rules["car"]) > plain
            assert temptations.odds(conn, me, {**car, "strength": car["strength"] / 2}, rules["car"]) < plain
            conn.execute("DELETE FROM relationships WHERE actor_a_id=?", (me,))
            conn.execute("DELETE FROM kinship_links WHERE actor_a_id=? OR actor_b_id=?", (me, me))
            assert temptations.odds(conn, me, car, rules["car"]) < plain, "a man who knows nobody hears of less"
            conn.rollback()

        # open chances are in the scene, with what they cost and how long they stand
        with connect() as conn:
            eager(conn)
            wants.refresh(conn, me)
            temptations.weekly(conn, start)
            conn.commit()
        shown = server.scene()["market"]["chances"]
        assert shown and {"id", "chance", "price", "days_left", "want"} <= set(shown[0]), shown
        assert server.resume()["scene"]["market"]["chances"]

        # a refused chance is gone; the want stays
        one = shown[0]
        assert server.note(cid(), "x", kind="chance", field="perhaps", subject_id=one["id"]).get("error")
        assert not server.note(cid(), "Not for him.", kind="chance", field="refused", subject_id=one["id"]).get("error")
        assert one["id"] not in {c["id"] for c in server.scene()["market"].get("chances", [])}
        assert server.note(cid(), "x", kind="chance", field="taken", subject_id=one["id"]).get("error"), "it is no longer open"
        assert one["want"] in {w["want"] for w in server.lookup("wants")["wants"]}

        # days passed bring the news of new ones; a taken one meets the want
        out = server.advance(cid(), 15, "work at the garage", interrupt="critical_only", from_day=server.scene()["day"])
        assert not out.get("error"), out
        news = out["chances"]
        assert news and all({"id", "chance", "price", "days_left"} <= set(c) for c in news), out
        taken = news[-1]
        assert not server.note(cid(), "He takes it.", kind="chance", field="taken", subject_id=taken["id"]).get("error")
        with connect() as conn:
            row = conn.execute("SELECT status,want_key FROM temptations WHERE id=?", (taken["id"],)).fetchone()
            assert row["status"] == "taken"
            assert conn.execute("SELECT status FROM wants WHERE actor_id=? AND key=?", (me, row["want_key"])).fetchone()[0] == "met"

        # one that went to someone else is told: what it was and who took it
        with connect() as conn:
            today = conn.execute("SELECT current_day FROM world_state").fetchone()[0]
            taker = conn.execute("""SELECT a.id,a.name FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id
                                    WHERE a.actor_type='character' AND p.life_status='living' AND a.id<>? ORDER BY a.id LIMIT 1""",
                                 (me,)).fetchone()
            conn.execute("""INSERT INTO temptations(actor_id,want_key,text,price,location_id,opened_day,expires_day,status,
                            taker_actor_id,updated_day) VALUES (?,'car','A car sat at the kerb',300,1,?,?,'gone',?,?)""",
                         (me, today - 5, today + 3, taker[0], today))
            conn.commit()
        lost = server.scene()["market"]["chances_gone"]
        assert any(c["taken_by"] == taker[1] and c["chance"] == "A car sat at the kerb" for c in lost), lost

        # nothing is passed in the street behind walls: nobody held inside comes upon a chance or takes one
        with connect() as conn:
            day = conn.execute("SELECT current_day FROM world_state").fetchone()[0]
            conn.execute("""INSERT INTO inmate_stays(actor_id,facility_id,since_day)
                            SELECT id,(SELECT MIN(id) FROM facilities),? FROM actors WHERE actor_type='character'""", (day,))
            eager(conn)
            before = conn.execute("SELECT COALESCE(MAX(id),0) FROM temptations").fetchone()[0]
            temptations.weekly(conn, day + 7)
            new = conn.execute("SELECT actor_id,text FROM temptations WHERE id>? LIMIT 5", (before,)).fetchall()
            assert not new, [tuple(r) for r in new]
            conn.rollback()

        # a want he waved off brings no chances
        with connect() as conn:
            conn.execute("DELETE FROM temptations")
            conn.execute("UPDATE wants SET status='dropped' WHERE actor_id=?", (me,))
            day = conn.execute("SELECT current_day FROM world_state").fetchone()[0]
            temptations.weekly(conn, day + 7)
            assert not conn.execute("SELECT 1 FROM temptations WHERE actor_id=?", (me,)).fetchone()
            conn.rollback()
    print("PASS g1_temptations_test")


if __name__ == "__main__":
    main()
