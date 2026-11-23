"""P1 Task 11: the tick, the GM view, the push.

Run: PYTHONPATH=. python tests/p1_tick_test.py"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

COUNCIL = "office:council:body"
WARD3 = "office:council:ward-3"
MAYOR = "office:city-hall:mayor"


def _today(c):
    return int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def test_tick_is_noop_without_package():
    from engine import civic_tick, simulation
    from tools.build_opening import build_opening
    seed = ROOT / "game" / "seeds" / "Caerness_Initial_World_State_Seed_v1_4.json"
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "caerness.db"
        os.environ["CAERNESS_DB_PATH"] = str(db)
        build_opening(db, seed)
        from engine.db import connect
        conn = connect()
        try:
            assert not civic_tick.enabled(conn)
            before_day = _today(conn)
            simulation.advance_connection(conn, 30)
            assert _today(conn) == before_day + 30
            for t in ("offices", "office_terms", "races", "civic_items", "field_holdings", "voter_groups", "sponsorships"):
                assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
            assert conn.execute("SELECT COUNT(*) FROM engine_meta WHERE key LIKE 'civic_%'").fetchone()[0] == 0
            assert civic_tick.process_due(conn, before_day + 31) == {} and civic_tick.next_due_day(conn, before_day, before_day + 400) is None
        finally:
            conn.close()


def _filer(c, w, race_id, day):
    from engine import races
    for who in (w.capo, w.boss, w.soldier):
        try:
            races.file(c, who, race_id, day)
            return who
        except ValueError:
            continue
    return None


def test_skip_interrupts_for_protagonist_office():
    from engine import civic_tick, civic_votes, offices, player, races, timeskip
    w = _open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=150 WHERE id=1")
    races.schedule(c, 150)
    rid = int(c.execute("SELECT r.id FROM races r JOIN offices o ON o.id=r.office_id WHERE o.office_key=? ORDER BY r.election_day LIMIT 1", (MAYOR,)).fetchone()[0])
    who = _filer(c, w, rid, 150)
    assert who is not None, "one of the three can file for mayor"
    player.set_player(c, who)
    offices.seat_holder(c, WARD3, who, how="elected", day=1)
    ms = [a for _, _, a in offices.members(c, COUNCIL)]
    civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": who, "title": "his bill"}, vote_day=170, day=150)
    primary = int(races.race(c, rid)["primary_day"])
    seen = []
    for _ in range(4):
        run = timeskip.prepare_time_skip(c, who, 120)
        out = timeskip.resolve_time_skip(c, run)
        if out["status"] != "interrupted":
            break
        hit = out["summary"]["interruption"]
        seen.append((hit["day"], hit["reason"]))
        if _today(c) >= primary:
            break
    days = [d for d, _ in seen]
    assert 170 in days and primary in days, (seen, primary)
    assert any("his bill" in r for d, r in seen if d == 170)


def test_view_respects_firewall():
    from engine import civic_corruption, civic_tick, offices, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    npc = offices.holder(c, "office:council:ward-1")
    civic_corruption.put_on(c, "actor", w.soldier, npc, 300.0, day=5)  # not his business
    mine = civic_corruption.put_on(c, "actor", w.capo, offices.holder(c, "office:council:ward-2"), 200.0, day=6)
    v = civic_tick.view(c, w.capo, 10)
    pay = v.get("payments") or []
    assert len(pay) == 1 and pay[0]["weekly_usd"] == 200.0, v
    assert mine and not any(p["official"] == c.execute("SELECT name FROM actors WHERE id=?", (npc,)).fetchone()[0] for p in pay)


def test_push_on_election_night():
    from engine import civic_tick, offices, player, races
    w = _open_world()
    c = w.conn
    el = offices.day_of(c, 1975, 11, 4)
    races.schedule(c, 150)
    rid = int(c.execute("SELECT r.id FROM races r JOIN offices o ON o.id=r.office_id WHERE o.office_key=? ORDER BY r.election_day LIMIT 1", (MAYOR,)).fetchone()[0])
    c.execute("UPDATE world_state SET current_day=150 WHERE id=1")
    who = _filer(c, w, rid, 150)
    assert who is not None
    player.set_player(c, who)
    d = 150
    while d < el:
        d = min(el, d + 7)
        civic_tick.process_due(c, d)
    rows = c.execute("SELECT text,first_day FROM delivery_ledger WHERE viewer_actor_id=? AND kind='election'", (who,)).fetchall()
    assert len(rows) == 1 and int(rows[0]["first_day"]) == el, [tuple(r) for r in rows]


def test_next_due_day_names_dated_events():
    from engine import civic_tick, civic_votes, offices
    w = _open_world()
    c = w.conn
    ms = [a for _, _, a in offices.members(c, COUNCIL)]
    civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": ms[0], "title": "x"}, vote_day=33, day=10)
    got = civic_tick.next_due_day(c, 10, 400)
    assert got is not None and got <= 33
    civic_tick.process_due(c, 33)
    out = civic_tick.process_due(c, 40)
    assert civic_votes.item(c, 1)["status"] in ("passed", "failed")
    assert out is not None


if __name__ == "__main__":
    failed = 0
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f()
                print("PASS", n)
            except Exception:
                failed += 1
                print("FAIL", n)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
