"""Task B11: an associate's weeks, good, neutral and bad, and how they reach the families (generic layer `org_happenings`).

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/org_happenings_test.py   (builds a scratch Saint Jude opening)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, drives, open_world, rel


def _dependent(w, boss_unit=True):
    c = w.conn
    r = c.execute("SELECT actor_id FROM org_seats WHERE role_key='associate' AND superior_actor_id=? AND status='active' ORDER BY actor_id LIMIT 1",
                  (w.soldier,)).fetchone()
    return int(r[0])


def _standing(c, a):
    return float(c.execute("SELECT standing FROM org_seats WHERE actor_id=?", (a,)).fetchone()[0])


def _forced(c, a) -> bool:
    r = c.execute("SELECT forced_tier,forced_until_day FROM simulation_profiles WHERE actor_id=?", (a,)).fetchone()
    return r is not None and r[0] == "ACTIVE" and int(r[1] or 0) > 0


def _other_org(w):
    c = w.conn
    r = c.execute("""SELECT p.org_actor_id FROM org_profiles p WHERE p.org_actor_id<>? AND p.org_kind=(SELECT org_kind FROM org_profiles WHERE org_actor_id=?)
                     ORDER BY p.org_actor_id LIMIT 1""", (w.org, w.org)).fetchone()
    return int(r[0])


def _line_for(w, org, loc):
    c = w.conn
    holding = int(c.execute("SELECT id FROM org_holdings WHERE org_actor_id=? LIMIT 1", (org,)).fetchone()[0])
    holder = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key<>'associate' AND unit_id IS NOT NULL ORDER BY actor_id LIMIT 1", (org,)).fetchone()[0])
    c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,location_id,weekly_take,started_day) VALUES (?,?,?,?,?,?,0)",
              (holding, None, holder, "a book on the edge", loc, 400.0))
    return int(c.execute("SELECT MAX(id) FROM org_lines").fetchone()[0]), holder


def test_good_happenings_raise_standing():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    before = _standing(c, a)
    lines = c.execute("SELECT COUNT(*) FROM org_lines WHERE holder_actor_id=?", (w.soldier,)).fetchone()[0]
    res = oh.happen(c, a, "bring_earner", DAY)
    assert res and res["kind"] == "bring_earner" and res["group"] == "good", res
    assert c.execute("SELECT COUNT(*) FROM org_lines WHERE holder_actor_id=?", (w.soldier,)).fetchone()[0] == lines + 1
    cp = res["counterpart"]
    assert c.execute("SELECT 1 FROM actors WHERE id=?", (cp,)).fetchone(), "the counterpart is a real man pulled up"
    assert _standing(c, a) > before
    row = c.execute("SELECT * FROM org_incidents WHERE kind='bring_earner' AND offender_actor_id=?", (a,)).fetchone()
    assert row is not None and row["matters"] == 0


def test_each_good_kind_does_its_work():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    s0 = _standing(c, a)
    r = oh.happen(c, a, "score", DAY)
    assert r["group"] == "good" and _standing(c, a) > s0
    s1 = _standing(c, a)
    oh.happen(c, a, "proves_himself", DAY)
    assert _standing(c, a) > s1
    n = c.execute("SELECT COUNT(*) FROM org_seats WHERE superior_actor_id=? AND role_key='associate'", (w.soldier,)).fetchone()[0]
    r = oh.happen(c, a, "recruits", DAY)
    assert r and c.execute("SELECT COUNT(*) FROM org_seats WHERE superior_actor_id=? AND role_key='associate'", (w.soldier,)).fetchone()[0] == n + 1
    new = r["recruit"]
    assert c.execute("SELECT unit_id FROM org_seats WHERE actor_id=?", (new,)).fetchone()[0] == w.unit
    r = oh.happen(c, a, "favour", DAY)
    assert r and r["group"] == "good" and r.get("for_actor")


def test_neutral_kinds():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    s0 = _standing(c, a)
    oh.happen(c, a, "drifts", DAY)
    assert _standing(c, a) < s0
    other = c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND actor_id<>? AND status='active' ORDER BY actor_id LIMIT 1",
                      (w.org, w.soldier)).fetchone()[0]
    rel(c, w.soldier, a, resentment=0)
    res = oh.happen(c, a, "switches", DAY, to=int(other))
    assert c.execute("SELECT superior_actor_id FROM org_seats WHERE actor_id=?", (a,)).fetchone()[0] == other
    assert float(c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (w.soldier, a)).fetchone()[0]) > 0, res
    b = c.execute("SELECT actor_id FROM org_seats WHERE role_key='associate' AND status='active' AND actor_id<>? ORDER BY actor_id LIMIT 1", (a,)).fetchone()[0]
    oh.happen(c, int(b), "goes_straight", DAY)
    assert c.execute("SELECT status FROM org_seats WHERE actor_id=?", (int(b),)).fetchone()[0] == "out"


def test_mix_is_mostly_not_trouble():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    for k in range(52):
        oh.process_due(c, DAY + 7 * k)
    kinds = {r[0]: r[1] for r in c.execute("SELECT kind,COUNT(*) FROM org_incidents GROUP BY kind")}
    groups = oh.group_of(c)
    tot = sum(kinds.values())
    wrong = sum(n for k, n in kinds.items() if groups.get(k) == "wrong")
    assert tot > 50, kinds
    assert (tot - wrong) > wrong, kinds
    missing = [k for k in groups if k not in ("informs", "recruits") and k not in kinds]  # informs needs an open case; recruits a unit short of its ratio (both have their own tests)
    assert not missing, (missing, kinds)


def test_informing_needs_pressure():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    c.execute("DELETE FROM crime_reports WHERE offender_actor_id=?", (a,))
    drives(c, a, loyalty=0.8)
    oh.forget_readings()
    assert oh.kind_weights(c, a, DAY)["informs"] == 0.0, "no open case, loyalty 0.8"
    drives(c, a, loyalty=0.1)
    oh.forget_readings()
    assert oh.kind_weights(c, a, DAY)["informs"] == 0.0, "no open case at all"
    c.execute("INSERT INTO crime_reports(day,crime_kind,offender_actor_id,status) VALUES (?,?,?,'open')", (DAY - 3, "racket", a))
    oh.forget_readings()
    assert oh.kind_weights(c, a, DAY)["informs"] > 0.0
    drives(c, a, loyalty=0.9)
    oh.forget_readings()
    hi = oh.kind_weights(c, a, DAY)["informs"]
    drives(c, a, loyalty=0.1)
    oh.forget_readings()
    assert oh.kind_weights(c, a, DAY)["informs"] > hi, "less loyal, likelier"


def test_informing_files_a_report_and_discovery_imposes():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    res = oh.happen(c, a, "informs", DAY)
    assert res["group"] == "wrong"
    rep = c.execute("SELECT * FROM crime_reports WHERE offender_actor_id=? AND json_extract(metadata_json,'$.informant') IS NOT NULL", (w.soldier,)).fetchone()
    assert rep is not None and json.loads(rep["metadata_json"]).get("informant") == a  # a case the law opened (it may be open, buried by a paid precinct, or an arrest)
    assert rep["case_id"] is not None
    c.execute("UPDATE simulation_profiles SET forced_tier=NULL, forced_until_day=NULL WHERE actor_id IN (?,?)", (a, w.soldier))
    oh.discover_informers(c, DAY + 1, force=True)
    assert _forced(c, w.soldier), "the named superior is looked at when it is found out"
    assert c.execute("SELECT 1 FROM org_agenda WHERE kind='respond_incident' AND status='open'").fetchone() is not None


def test_civilian_incident_stays_quiet():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    res = oh.happen(c, a, "incident", DAY, victim_kind="civilian")
    row = c.execute("SELECT * FROM org_incidents WHERE id=?", (res["incident_id"],)).fetchone()
    assert row["matters"] == 0 and row["raised_to_org_actor_id"] is None
    assert c.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='respond_incident'").fetchone()[0] == 0
    assert _forced(c, a) and _forced(c, row["victim_actor_id"]) or not c.execute("SELECT 1 FROM org_seats WHERE actor_id=?", (row["victim_actor_id"],)).fetchone()


def test_far_off_spark_reaches_the_other_family():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    other = _other_org(w)
    line, holder = _line_for(w, other, w.ground)
    res = oh.happen(c, a, "incident", DAY, victim_kind="other_line")
    row = c.execute("SELECT * FROM org_incidents WHERE id=?", (res["incident_id"],)).fetchone()
    assert row["matters"] == 1 and row["victim_actor_id"] == holder and row["victim_line_id"] == line
    head = c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='boss'", (other,)).fetchone()[0]
    assert row["raised_to_org_actor_id"] == other
    item = c.execute("SELECT * FROM org_agenda WHERE kind='respond_incident' AND actor_id=? AND status='open'", (head,)).fetchone()
    assert item is not None and item["subject_id"] == row["id"]
    assert _forced(c, a), "the offender is looked at tomorrow"
    assert _forced(c, holder), "so is the man he hit"


def test_officer_victim_leaves_a_harm_row():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    res = oh.happen(c, a, "incident", DAY, victim_kind="officer")
    if res.get("skipped"):
        return  # a package with no officers on file: nothing to hit
    row = c.execute("SELECT * FROM org_incidents WHERE id=?", (res["incident_id"],)).fetchone()
    assert row["matters"] == 1
    assert c.execute("SELECT 1 FROM harm_incidents WHERE actor_id=? AND source_kind='org_incident'", (row["victim_actor_id"],)).fetchone()


def test_response_moves_the_relationship():
    from engine import org_choices, ledger, org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    other = _other_org(w)
    line, holder = _line_for(w, other, w.ground)
    res = oh.happen(c, a, "incident", DAY, victim_kind="other_line")
    vhead = c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='boss'", (other,)).fetchone()[0]
    item = c.execute("SELECT * FROM org_agenda WHERE kind='respond_incident' AND actor_id=?", (vhead,)).fetchone()
    offers = org_choices.AGENDA_ACTIONS["respond_incident"](c, vhead, item, DAY + 2)
    assert {o["kind"] for o in offers} == {"sit_down", "kill_offender", "let_it_go"}
    ohead = w.boss
    r0 = c.execute("SELECT respect,resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (ohead, vhead)).fetchone()
    p = next(o["payload"] for o in offers if o["kind"] == "sit_down")
    org_choices.execute(c, vhead, "sit_down", {**p, "agenda_id": item["id"]}, DAY + 2)
    pay = c.execute("SELECT * FROM org_agenda WHERE kind='pay_or_refuse' AND actor_id=? AND status='open'", (ohead,)).fetchone()
    assert pay is not None and "agenda_id" not in json.loads(pay["metadata_json"]), "a new item does not carry the old item's id"
    assert _forced(c, ohead)
    offs = org_choices.AGENDA_ACTIONS["pay_or_refuse"](c, ohead, pay, DAY + 5)
    assert {o["kind"] for o in offs} == {"pay", "refuse"}
    ledger.receive(c, ("person", ohead), 500000.0, purpose="test purse")
    bal_v = ledger.balance(c, ("person", vhead))
    pp = next(o["payload"] for o in offs if o["kind"] == "pay")
    org_choices.execute(c, ohead, "pay", {**pp, "agenda_id": pay["id"]}, DAY + 5)
    assert ledger.balance(c, ("person", vhead)) > bal_v, "the victim's boss was paid"
    assert c.execute("SELECT status FROM org_agenda WHERE id=?", (pay["id"],)).fetchone()[0] == "resolved", "the demand is answered once"
    assert c.execute("SELECT 1 FROM org_agenda WHERE kind='pay_or_refuse' AND actor_id=? AND status='open'", (ohead,)).fetchone() is None
    r1 = c.execute("SELECT respect,resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (vhead, ohead)).fetchone()
    assert r1 is not None
    # refusing sours it
    item2 = c.execute("SELECT id FROM org_agenda WHERE kind='respond_incident' AND status='open'").fetchone()
    res2 = oh.happen(c, a, "incident", DAY + 9, victim_kind="other_line")
    org_choices.execute(c, vhead, "sit_down", {**p, "incident_id": res2["incident_id"], "agenda_id": None}, DAY + 11)
    pay2 = c.execute("SELECT * FROM org_agenda WHERE kind='pay_or_refuse' AND actor_id=? AND status='open'", (ohead,)).fetchone()
    before = float(c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (vhead, ohead)).fetchone()[0])
    refuse = next(o["payload"] for o in org_choices.AGENDA_ACTIONS["pay_or_refuse"](c, ohead, pay2, DAY + 14) if o["kind"] == "refuse")
    org_choices.execute(c, ohead, "refuse", refuse, DAY + 14)
    after = float(c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (vhead, ohead)).fetchone()[0])
    assert after > before


def test_kill_offender_goes_through_the_killing_path():
    from engine import org_choices, orgs, org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    other = _other_org(w)
    _line_for(w, other, w.ground)
    oh.happen(c, a, "incident", DAY, victim_kind="other_line")
    vhead = c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='boss'", (other,)).fetchone()[0]
    item = c.execute("SELECT * FROM org_agenda WHERE kind='respond_incident' AND actor_id=?", (vhead,)).fetchone()
    offers = org_choices.AGENDA_ACTIONS["respond_incident"](c, vhead, item, DAY + 2)
    p = next(o["payload"] for o in offers if o["kind"] == "kill_offender")
    from tests.outfit_choice_fixture import certain_kills
    with certain_kills():
        org_choices.execute(c, vhead, "kill_offender", p, DAY + 2)
    assert not orgs.is_living(c, a)


def test_busted_holds_him_and_opens_a_racket_report():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    res = oh.happen(c, a, "busted", DAY)
    assert res["group"] == "wrong"
    assert c.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held'", (a,)).fetchone()
    rep = c.execute("SELECT * FROM crime_reports WHERE offender_actor_id=? AND crime_kind='racket' AND status='open'", (a,)).fetchone()
    assert rep is not None
    assert _forced(c, a)
    oh.process_due(c, DAY + 60)
    assert c.execute("SELECT 1 FROM custody WHERE actor_id=? AND kind='held'", (a,)).fetchone() is None, "a small arrest ends"


def test_holds_out_is_noticed_in_time():
    from engine import ledger, org_happenings as oh
    w = open_world()
    c = w.conn
    a = _dependent(w)
    bal = ledger.balance(c, ("person", a))
    res = oh.happen(c, a, "holds_out", DAY)
    assert ledger.balance(c, ("person", a)) > bal
    inc = c.execute("SELECT status FROM org_incidents WHERE id=?", (res["incident_id"],)).fetchone()
    assert inc["status"] == "open"
    for k in range(1, 200):
        oh.process_due(c, DAY + 7 * k, only_checks=True)
        if c.execute("SELECT status FROM org_incidents WHERE id=?", (res["incident_id"],)).fetchone()[0] != "open":
            break
    assert c.execute("SELECT status FROM org_incidents WHERE id=?", (res["incident_id"],)).fetchone()[0] == "noticed"
    assert _forced(c, a)


def test_noise_is_bounded():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    for k in range(52):
        oh.process_due(c, DAY + 7 * k)
    n = c.execute("SELECT COUNT(*) FROM org_incidents WHERE matters=1 AND day<=?", (DAY + 7 * 52,)).fetchone()[0]
    assert 5 <= n <= 300, n


def test_same_seed_same_weeks():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    snap = [dict(r) for r in c.execute("SELECT id FROM actors LIMIT 1")]
    k1 = oh.kind_weights(c, _dependent(w), DAY)
    k2 = oh.kind_weights(c, _dependent(w), DAY)
    assert k1 == k2 and snap
    assert oh.draw_kind(c, _dependent(w), DAY) == oh.draw_kind(c, _dependent(w), DAY)


def test_bring_earner_uses_an_existing_person_where_one_fits():
    from engine import org_happenings as oh, orgs
    w = open_world()
    c = w.conn
    a = _dependent(w)
    seat = orgs.seat_of(c, a, w.org)
    spec = oh._kinds(c)["bring_earner"]
    import random
    near = oh._nearby(c, a, seat, DAY, spec, random.Random(1), oh._counterparts_used(c))
    assert near is not None, "an unseated person of the right age lives in the city"
    before = c.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
    res = oh.happen(c, a, "bring_earner", DAY)
    assert c.execute("SELECT COUNT(*) FROM actors").fetchone()[0] == before, "no one new was pulled up"
    assert not c.execute("SELECT 1 FROM org_seats WHERE actor_id=?", (res["counterpart"],)).fetchone()
    assert json.loads(c.execute("SELECT metadata_json FROM org_incidents WHERE id=?", (res["incident_id"],)).fetchone()[0])["new_person"] is False
    # a counterpart is not used twice
    assert res["counterpart"] not in {oh._nearby(c, a, seat, DAY, spec, random.Random(k), oh._counterparts_used(c)) for k in range(20)}


def _two_heads(w):
    c = w.conn
    other = _other_org(w)
    vic = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND status='active' ORDER BY actor_id LIMIT 1", (other,)).fetchone()[0])
    vhead = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='boss'", (other,)).fetchone()[0])
    return other, vic, vhead


def test_cross_family_killing_goes_to_the_dead_mans_head():
    from engine import org_choices, orgs
    from engine.outfit_choices import kill
    w = open_world()
    c = w.conn
    other, vic, vhead = _two_heads(w)
    sup = c.execute("SELECT superior_actor_id FROM org_seats WHERE actor_id=?", (vic,)).fetchone()[0]
    kill(c, w.soldier, vic, DAY, sanctioned=True)
    item = c.execute("SELECT * FROM org_agenda WHERE kind='respond_killing' AND actor_id=? AND status='open'", (vhead,)).fetchone()
    assert item is not None, "the dead man's head has to answer"
    assert c.execute("SELECT 1 FROM org_incidents WHERE kind='killing' AND offender_actor_id=? AND victim_actor_id=?", (w.soldier, vic)).fetchone()
    assert _forced(c, vhead) and _forced(c, sup), "his head and the dead man's superior are looked at tomorrow"
    offers = org_choices.AGENDA_ACTIONS["respond_killing"](c, vhead, item, DAY + 2)
    assert {o["kind"] for o in offers} == {"accept_killing", "demand_redress", "sit_down_peace", "retaliate"}


def test_killing_inside_one_organisation_asks_no_one():
    from engine.outfit_choices import kill
    w = open_world()
    c = w.conn
    mate = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND actor_id<>? AND status='active' ORDER BY actor_id LIMIT 1", (w.org, w.soldier)).fetchone()[0])
    kill(c, w.soldier, mate, DAY, sanctioned=True)
    assert c.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='respond_killing'").fetchone()[0] == 0


def _answers(w, **kw):
    from engine import org_choices
    from engine.outfit_choices import kill
    c = w.conn
    other, vic, vhead = _two_heads(w)
    if kw.get("refused"):
        c.execute("INSERT INTO org_incidents(day,kind,offender_actor_id,matters,status) VALUES (?,?,?,1,'refused')", (DAY - 5, "incident", vic))
    kill(c, w.soldier, vic, DAY, sanctioned=True)
    item = c.execute("SELECT * FROM org_agenda WHERE kind='respond_killing' AND actor_id=?", (vhead,)).fetchone()
    return {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](c, vhead, item, DAY + 2)}, vhead, vic


def test_a_man_in_the_wrong_makes_acceptance_likelier_and_retaliation_less():
    a1, _, _ = _answers(open_world())
    a2, _, _ = _answers(open_world(), refused=True)
    assert a2["accept_killing"]["utility"] > a1["accept_killing"]["utility"]
    assert a2["retaliate"]["utility"] < a1["retaliate"]["utility"], "a prior sit-down held (a refused one) lowers 'no sit-down'"


def test_each_answer_moves_the_heads_relationship_and_works():
    from engine import org_choices
    for choice in ("accept_killing", "demand_redress", "retaliate"):
        w = open_world()
        c = w.conn
        offers, vhead, vic = _answers(w)
        killer_head = w.boss
        before = c.execute("SELECT respect,resentment,fear FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (vhead, killer_head)).fetchone()
        b = tuple(before) if before else (0, 0, 0)
        org_choices.execute(c, vhead, choice, offers[choice]["payload"], DAY + 2)
        if choice == "demand_redress":
            assert c.execute("SELECT 1 FROM org_agenda WHERE kind='pay_or_refuse' AND actor_id=? AND status='open'", (killer_head,)).fetchone()
        if choice == "retaliate":
            assert c.execute("SELECT 1 FROM org_agenda WHERE kind='hit' AND subject_id=? AND status='open'", (w.soldier,)).fetchone()
        a = c.execute("SELECT respect,resentment,fear FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (vhead, killer_head)).fetchone()
        a2 = c.execute("SELECT respect,resentment,fear FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (killer_head, vhead)).fetchone()
        assert (a is not None and tuple(a) != b) or a2 is not None, choice


def test_informing_can_run_through_the_real_tables():
    """Open cases name every associate, loyalty is low: the gate passes through the real crime_reports and drives."""
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    men = oh._roster(c)
    for m in men:
        c.execute("INSERT INTO crime_reports(day,crime_kind,offender_actor_id,status) VALUES (?,?,?,'open')", (DAY - 3, "racket", m))
        c.execute("UPDATE actor_drives SET loyalty=0.05 WHERE actor_id=?", (m,))
    for k in range(40):
        oh.process_due(c, DAY + 7 * k)
    inf = c.execute("SELECT * FROM org_incidents WHERE kind='informs'").fetchall()
    assert inf, "informing happened"
    rep = c.execute("SELECT * FROM crime_reports WHERE json_extract(metadata_json,'$.informant') IS NOT NULL").fetchone()
    assert rep is not None and rep["agency_profile_id"] is not None, "the agency was given the evidence"
    done = c.execute("SELECT * FROM crime_reports WHERE json_extract(metadata_json,'$.discovered')=1").fetchall()
    assert done, "some of it was found out in time"
    inc = c.execute("SELECT * FROM org_incidents WHERE kind='informs' AND matters=1").fetchone()
    assert inc is not None and c.execute("SELECT 1 FROM org_agenda WHERE kind='respond_incident' AND json_extract(metadata_json,'$.kind')='informs'").fetchone()


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad.append(t.__name__)
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, repr(e)[:300])
        else:
            print("ok  ", t.__name__)
    print(f"{len(TESTS) - len(bad)}/{len(TESTS)} passed")
    sys.exit(1 if bad else 0)
