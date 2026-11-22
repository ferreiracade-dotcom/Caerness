"""P1 Task 6: agenda votes, deals, tenders, approvals, ordinance effects.

Run: PYTHONPATH=. python tests/p1_votes_test.py"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

COUNCIL = "office:council:body"
WORKS = "office:works:board"


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def _members(c, body):
    from engine import offices
    return [a for _, _, a in offices.members(c, body)]


def _force(monkey_votes):
    """Replace member_vote with fixed votes (member -> vote), returning the restore function."""
    from engine import civic_votes
    real = civic_votes.member_vote

    def fake(conn, item_id, member, day, *, salt=""):
        v = monkey_votes(member, salt) if callable(monkey_votes) else monkey_votes.get(member, "no")
        return v, {"forced": True}
    civic_votes.member_vote = fake
    return lambda: setattr(civic_votes, "member_vote", real)


def test_vote_counts_members():
    from engine import civic_votes
    w = _open_world()
    c = w.conn
    ms = _members(c, COUNCIL)
    assert len(ms) == 15, len(ms)
    sponsor = ms[0]
    iid = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": sponsor, "title": "a curfew", "grievances": ["police"]}, vote_day=50, day=40)
    out = civic_votes.decide(c, iid, 50)
    rows = c.execute("SELECT vote,COUNT(*) FROM civic_item_votes WHERE item_id=? GROUP BY 1", (iid,)).fetchall()
    assert sum(r[1] for r in rows) == 15
    status = civic_votes.item(c, iid)["status"]
    present = out["present"]
    assert (status == "passed") == (out["yes"] * 2 > present) or out.get("tie"), (status, out)
    # nothing fixed: the leans differ member to member
    zs = {json.loads(r[0])["z"] for r in c.execute("SELECT why_json FROM civic_item_votes WHERE item_id=?", (iid,)) if "z" in json.loads(r[0])}
    assert len(zs) > 1


def test_deal_breach_runs_ledger():
    from engine import civic_votes, offices
    w = _open_world()
    c = w.conn
    machine, club = _org(c, "county_party"), _org(c, "reform_clubs")
    leader = int(c.execute("SELECT leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id LIMIT 1", (machine,)).fetchone()[0])
    offices.seat_holder(c, "office:council:ward-3", leader, how="elected", day=1)
    from engine import orgs
    other = orgs.head_of(c, club)  # the chair holds the club's purse
    iid = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": other, "title": "x"}, vote_day=50, day=40)
    first, _ = civic_votes.member_vote(c, iid, leader, 50)
    opposite = "no" if first == "yes" else "yes"
    deal = civic_votes.pre_vote_deal(c, iid, leader, other, {"amount_usd": 5000.0, "vote": opposite}, 40)
    # the promised vote leans him (the deal term is in his weighing)
    v, why = civic_votes.member_vote(c, iid, leader, 50)
    assert why["deal"] is True
    restore = _force({leader: first})
    try:
        civic_votes.decide(c, iid, 50)
    finally:
        restore()
    b = c.execute("SELECT path,effect_json FROM agreement_breaches WHERE term_id=?", (deal,)).fetchone()
    assert b is not None and b[0] == "tension", b
    assert json.loads(b[1]).get("tension_delta", 0) > 0
    assert c.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind='breach'").fetchone()[0] >= 1 if "kind" in {r[1] for r in c.execute("PRAGMA table_info(org_tension_acts)")} else True


def test_tie_and_quorum_follow_data():
    from engine import civic_votes, offices
    w = _open_world()
    c = w.conn
    ms = _members(c, COUNCIL)
    for m in ms[:8]:
        c.execute("INSERT INTO custody(actor_id,kind,charge,since_day) VALUES (?,?,?,?)", (m, "held", "test", 1))
    iid = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": ms[-1], "title": "q"}, vote_day=50, day=40)
    out = civic_votes.decide(c, iid, 50)
    assert out["reason"] == "quorum" and civic_votes.item(c, iid)["status"] == "failed", out
    c.execute("DELETE FROM custody")
    # a built tie, by each rule: council (chair votes), board (failure), works (re-vote)
    chair = offices.holder(c, "office:city-hall:mayor")
    voters = ms[:14]

    def tie_votes(member, salt):
        if member == chair:
            return "yes" if salt == "chair" else "absent"
        return "yes" if voters.index(member) % 2 == 0 else "no" if member in voters else "absent"
    restore = _force(tie_votes)
    try:
        # the 15th member abstains: 14 present, 7-7
        def seven_seven(member, salt):
            if member == ms[14]:
                return "absent"
            return "yes" if ms.index(member) % 2 == 0 else "no"
        civic_votes.member_vote = lambda conn, i, m, d, *, salt="": (("yes" if salt == "chair" else seven_seven(m, salt)), {})
        iid2 = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": ms[0], "title": "tie"}, vote_day=60, day=50)
        out2 = civic_votes.decide(c, iid2, 60)
        assert out2["tie"] == "chair_votes" and civic_votes.item(c, iid2)["status"] == "passed", out2
        zb = "office:zoning:board"
        zm = _members(c, zb)
        assert len(zm) >= 2
        half = len(zm) // 2
        civic_votes.member_vote = lambda conn, i, m, d, *, salt="": (("yes" if zm.index(m) < half else "no") if zm.index(m) < 2 * half else "absent", {})
        iid3 = civic_votes.open_item(c, zb, "zoning_variance", {"sponsor": ms[0], "title": "tie z"}, vote_day=60, day=50)
        out3 = civic_votes.decide(c, iid3, 60)
        assert out3["tie"] == "failure" and civic_votes.item(c, iid3)["status"] == "failed", out3
    finally:
        restore()


def test_tender_follows_arrangements_not_always():
    from engine import civic_votes
    w = _open_world()
    c = w.conn
    board = _members(c, WORKS)
    assert board, "the board has members"
    a, b = w.soldier, w.capo
    for m in board:
        c.execute("INSERT INTO org_arrangements(kind,official_actor_id,payer_kind,payer_id,position_key,weekly_usd,status) VALUES ('kickback',?,'actor',?,'p',100,'active')", (m, a))
    wins = {a: 0, b: 0}
    for seed in range(60):
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed + 1,))
        iid = civic_votes.open_tender(c, WORKS, {"title": "a sewer", "sponsor": None}, close_day=100, day=90)
        civic_votes.add_bid(c, iid, a, 1_000_000.0, day=91)
        civic_votes.add_bid(c, iid, b, 1_000_000.0, day=91)
        wins[civic_votes.award_tender(c, iid, 100)["winner"]] += 1
    assert wins[a] > wins[b] and wins[b] > 0, wins


def test_approvals_answered():
    from engine import civic_seams, civic_votes
    w = _open_world()
    c = w.conn
    pid = civic_seams.open_venture(c, "open_business", w.soldier, meta={"title": "a bar", "budget_usd": 1000.0, "day": 10})
    assert civic_seams.approval_requests(c, 10)
    n = civic_votes.decide_approvals(c, 10)
    assert n >= 1
    row = c.execute("SELECT status,reason FROM venture_approvals WHERE project_id=?", (pid,)).fetchone()
    assert row[0] in ("granted", "refused")
    why = json.loads(row[1])
    assert why["office"] and "item_id" in why


def test_ordinance_effect_readable():
    from engine import civic_votes
    w = _open_world()
    c = w.conn
    ms = _members(c, COUNCIL)
    restore = _force(lambda m, s: "yes")
    try:
        iid = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": ms[0], "title": "no bars after one",
                                                              "effects": [{"effect_key": "ordinance", "value": {"closing": 1}, "from_day": 200}]}, vote_day=60, day=50)
        civic_votes.decide(c, iid, 60)
    finally:
        restore()
    assert civic_votes.effects_on(c, "ordinance", 150) == []
    got = civic_votes.effects_on(c, "ordinance", 200)
    assert len(got) == 1 and got[0]["value"] == {"closing": 1} and got[0]["source_id"] == iid


def test_protagonist_as_member_and_as_petitioner():
    from engine import civic_votes, offices, player
    w = _open_world()
    c = w.conn
    player.set_player(c, w.capo)
    ms = _members(c, COUNCIL)
    npc = ms[0]
    offices.seat_holder(c, "office:council:ward-3", w.capo, how="elected", day=1)
    iid = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": ms[1], "title": "t", "grievances": ["jobs"]}, vote_day=60, day=50)
    v1, why1 = civic_votes.member_vote(c, iid, w.capo, 60)
    v2, why2 = civic_votes.member_vote(c, iid, npc, 60)
    assert v1 in ("yes", "no") and v2 in ("yes", "no") and set(why1) == set(why2)
    # as petitioner: the same weighing applies to a council that is lobbied by him
    iid2 = civic_votes.open_item(c, COUNCIL, "ordinance", {"sponsor": w.capo, "title": "his"}, vote_day=60, day=50)
    out = civic_votes.decide(c, iid2, 60)
    assert out["members"] == 15 and w.capo in _members(c, COUNCIL) and civic_votes.item(c, iid2)["status"] in ("passed", "failed")


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
