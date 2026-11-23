"""P1 Task 10: the field shifts: weakening, splits, absorption, after an organisation.

Run: PYTHONPATH=. python tests/p1_field_shift_test.py"""
from __future__ import annotations

import json
import re
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


def _trial(c, seed, fn):
    c.execute("SAVEPOINT trial")
    try:
        c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed,))
        return fn()
    finally:
        c.execute("ROLLBACK TO trial")
        c.execute("RELEASE trial")


def test_defeat_weakens_backer():
    from engine import civic_field, civic_shift
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    base = civic_shift.pressure(c, "org", machine, 200)
    oid = int(c.execute("SELECT id FROM offices WHERE office_key=?", (MAYOR,)).fetchone()[0])
    rid = int(c.execute("INSERT INTO races(office_id,election_day,stage,status,result_json) VALUES (?,?,?,?,?)",
                        (oid, 150, "result", "decided", json.dumps({"winner": w.soldier}))).lastrowid)
    c.execute("INSERT INTO race_candidates(race_id,actor_id,party_org_id,filed_day) VALUES (?,?,?,?)", (rid, w.capo, machine, 100))
    after = civic_shift.pressure(c, "org", machine, 200)
    assert after["defeat"] == base["defeat"] + 1
    before_strength = civic_field.strength(c, "org", machine)
    lower = []
    for s in range(1, 120):
        def go():
            civic_shift.weekly_shift(c, 200)
            return civic_field.strength(c, "org", machine)
        lower.append(_trial(c, s, go) < before_strength)
    assert any(lower) and not all(lower), sum(lower)  # it slips some weeks, not every week


def test_walkout_makes_a_new_org_with_its_stakes():
    from engine import civic_field, civic_shift
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    u = c.execute("SELECT id,leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id LIMIT 1", (machine,)).fetchone()
    stakes = [dict(s) for s in civic_shift._unit_stakes(c, machine, int(u["leader_actor_id"]))]
    assert stakes, "a unit leader has stakes in his districts"
    new = civic_shift.factional_walkout(c, machine, int(u["id"]), 300)
    assert new is not None and new != machine
    assert c.execute("SELECT org_kind FROM org_profiles WHERE org_actor_id=?", (new,)).fetchone()[0] == "party"
    held = {(r["stake_kind"], r["stake_ref"]) for r in civic_field.holdings_of(c, "org", new)}
    mine = {(r["stake_kind"], r["stake_ref"]) for r in civic_field.holdings_of(c, "org", machine)}
    wanted = {(s["stake_kind"], s["stake_ref"]) for s in stakes}
    assert wanted <= held and not (wanted & mine)


def test_end_carries_or_closes_everything():
    from engine import civic_seams, civic_shift
    w = _open_world()
    c = w.conn
    for successor_given in (True, False):
        def go():
            club, machine = _org(c, "reform_clubs"), _org(c, "county_party")
            e = civic_seams.ledger_entry(c, w.soldier, w.capo, kind="favour", terms={"amount_usd": 10.0, "breach_word": "grudge"}, due_day=50, day=40)
            c.execute("UPDATE agreement_terms SET debtor_ref=? WHERE id=?", (f"org:{club}", e))
            out = civic_shift.carry_on_end(c, club, 400, machine if successor_given else None)
            ref = f"org:{club}"
            assert c.execute("SELECT COUNT(*) FROM field_holdings WHERE holder_kind='org' AND holder_id=? AND ended_day IS NULL", (club,)).fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active'", (club,)).fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM agreement_terms WHERE status='active' AND (debtor_ref=? OR creditor_ref=?)", (ref, ref)).fetchone()[0] == 0
            assert out["ledger"] >= 1 and out["told"] >= 1
            return True
        assert _trial(c, 1, go)


def test_successor_shapes_vary_by_seed():
    from engine import civic_field, civic_shift, civic_votes, offices, races
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    shapes = {}
    for seed in (3, 7, 11):
        def run():
            for r in civic_field.holdings_of(c, "org", machine):
                civic_field.weaken(c, int(r["id"]), 99.0, day=5, cause_kind="indictments")
            d = 0
            while d < 4 * 365:
                d += 7
                races.advance(c, d)
                civic_shift.weekly_shift(c, d)
                offices.process_vacancies(c, d)
                civic_votes.advance(c, d)
            held = {}
            for key in [MAYOR] + [f"office:party:ward-leader-{i}" for i in range(1, 11)]:
                h = civic_field.holder_of(c, "party_office", key) or civic_field.holder_of(c, "sponsor", key)
                held[key] = None if h is None else h[1]
            return (offices.holder(c, MAYOR), tuple(sorted({v for v in held.values() if v is not None})))
        shapes[seed] = _trial(c, seed, run)
    assert len(set(shapes.values())) > 1, shapes  # variety, not any particular outcome


def test_no_actor_named_in_shift_code():
    keys = set()
    d = json.load(open(ROOT / "worlds" / "saintjude" / "politics.json", encoding="utf-8"))
    for h in d["holdings_1975"]:
        for v in h["holder"].values():
            keys.add(v)
    for f in ("civic_shift.py", "civic_field.py"):
        text = (ROOT / "engine" / f).read_text(encoding="utf-8")
        for k in keys:
            assert not re.search(rf"[\"']{re.escape(k)}[\"']", text), (f, k)


def test_protagonist_can_lead_a_walkout():
    from engine import orgs, player, races
    from engine import civic_shift
    w = _open_world()
    c = w.conn
    machine = _org(c, "county_party")
    u = c.execute("SELECT id,leader_actor_id FROM org_units WHERE org_actor_id=? AND leader_actor_id IS NOT NULL ORDER BY id LIMIT 1", (machine,)).fetchone()
    lead = int(u["leader_actor_id"])
    player.set_player(c, lead)
    assert races._is_player(c, lead)
    # the engine never walks him out by itself, however hard the pressure
    hard = {"lost": 50.0, "defeat": 50.0, "indicted": 50.0, "impression": 0.0}
    for s in range(1, 8):
        civic_shift._walk_draws(c, machine, hard, 100 + s)
    assert c.execute("SELECT 1 FROM org_seats WHERE actor_id=? AND org_actor_id=? AND status='active'", (lead, machine)).fetchone()  # he stays: nobody walks him
    # but by his own act he may
    new = civic_shift.factional_walkout(c, machine, int(u["id"]), 300)
    assert new is not None and orgs.head_of(c, new) == lead


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
