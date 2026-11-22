"""P1 Task 4: patronage jobs follow the office; favours are ledger entries.

Run: PYTHONPATH=. python tests/p1_patronage_test.py"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

MAYOR = "office:city-hall:mayor"


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def _gid(c, key):
    return int(c.execute("SELECT id FROM voter_groups WHERE group_key=?", (key,)).fetchone()[0])


def _club_member(c, club):
    return int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY id LIMIT 1", (club,)).fetchone()[0])


def test_jobs_follow_the_office_not_the_org():
    from engine import civic_field, civic_patronage, electorate
    w = _open_world()
    c = w.conn
    machine, club = _org(c, "county_party"), _org(c, "reform_clubs")
    assert len(civic_patronage.lines_of(c, MAYOR)) > 0
    gid = _gid(c, "ward-1:irish-catholic-working")
    before = electorate.delivery(c, gid, "org", machine)
    jobs_before = electorate.jobs_held(c, machine)
    new_mayor = _club_member(c, club)
    moved = civic_patronage.follow(c, MAYOR, new_mayor, day=30)
    assert moved > 0
    assert civic_field.holder_of(c, "patronage", MAYOR) == ("org", club)
    assert electorate.jobs_held(c, machine) < jobs_before
    assert electorate.jobs_held(c, club) >= moved
    assert electorate.delivery(c, gid, "org", machine) < before
    assert civic_patronage.follow(c, MAYOR, new_mayor, day=31) == 0  # already his side's


def test_favour_is_a_ledger_entry():
    from engine import civic_patronage, civic_seams, offices
    w = _open_world()
    c = w.conn
    mayor = offices.holder(c, MAYOR)
    assert mayor is not None
    line = civic_patronage.hand_out(c, MAYOR, w.soldier, day=40, why="for the ward work")
    assert c.execute("SELECT holder_actor_id FROM org_lines WHERE id=?", (line,)).fetchone()[0] == w.soldier
    assert civic_patronage.owed(c, mayor, w.soldier) == 1.0 and civic_patronage.owed(c, w.soldier, mayor) == -1.0
    e = civic_seams.ledger_open(c, w.soldier, kind="favour")
    assert len(e) == 1 and e[0]["debtor_ref"] == f"person:{w.soldier}"
    civic_seams.ledger_breach(c, int(e[0]["id"]), w.soldier, 50, "voted against")
    assert civic_patronage.owed(c, mayor, w.soldier) == 0.0
    assert c.execute("SELECT COUNT(*) FROM agreement_breaches").fetchone()[0] >= 1


def test_cut_weakens_holds():
    from engine import civic_patronage
    w = _open_world()
    c = w.conn
    n = len(civic_patronage.lines_of(c, MAYOR))
    ended = civic_patronage.cut(c, MAYOR, 0.3, day=60, cause="budget")
    assert ended == round(n * 0.3) and len(civic_patronage.lines_of(c, MAYOR)) == n - ended
    # the same seed ends the same lines
    ids = sorted(int(r[0]) for r in c.execute("SELECT id FROM org_lines WHERE status='ended' AND ended_day=60"))
    w2 = _open_world()
    civic_patronage.cut(w2.conn, MAYOR, 0.3, day=60, cause="budget")
    assert ids == sorted(int(r[0]) for r in w2.conn.execute("SELECT id FROM org_lines WHERE status='ended' AND ended_day=60"))
    assert civic_patronage.cut(c, MAYOR, 1.0, day=61, cause="budget") == n - ended  # not capped: all can go


def test_protagonist_gives_and_owes_alike():
    from engine import civic_field, civic_patronage, offices, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    civic_patronage.follow(c, MAYOR, w.capo, day=10)  # a man in no party takes the office: the stake is his own
    assert civic_field.holder_of(c, "patronage", MAYOR) == ("actor", w.capo)
    offices.seat_holder(c, MAYOR, w.capo, how="succeeded", day=11)
    civic_patronage.hand_out(c, MAYOR, w.soldier, day=12, why="loyalty")
    assert civic_patronage.owed(c, w.capo, w.soldier) == 1.0
    # and he owes: an NPC mayor hands him a job
    civic_patronage.favour(c, w.boss, w.capo, "a job", day=13)
    assert civic_patronage.owed(c, w.capo, w.boss) == -1.0


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
