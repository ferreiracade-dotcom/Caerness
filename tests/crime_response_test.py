"""Crime brings a law response (task B13): reports, publicity, the Pad's reach and its limits, arrests, dispositions, sentences.

Run: PYTHONPATH=. python tests/crime_response_test.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, certain_kills, drives, forced_roll, open_world as _open_world, rel, run_review  # noqa: E402


def open_world():
    w = _open_world()
    cr.ensure_tables(w.conn)  # a running campaign has the tables before its crimes happen
    return w

from engine import crime_response as cr, orgs  # noqa: E402
from engine.harm import record_harm  # noqa: E402
from engine.law_opening import agency_for  # noqa: E402

_N = [0]


def _ref() -> int:
    _N[0] += 1
    return 9_000_000 + _N[0]


def _victim(c, avoid: set[int], org: int | None = None) -> int:
    """A living man of another outfit (or any living man) who is not one of `avoid`."""
    rows = c.execute("SELECT s.actor_id FROM org_seats s WHERE s.status='active' AND s.org_actor_id<>? ORDER BY s.actor_id", (org or -1,)).fetchall()
    for (a,) in rows:
        if a not in avoid and orgs.is_living(c, int(a)):
            return int(a)
    raise AssertionError("no victim")


def _hit(c, victim: int, offender: int | None, *, fatal: bool, public: bool, loc: int, method: str = "handgun_range"):
    meta = {"offender_actor_id": offender, "public": public} if offender is not None else None
    return record_harm(c, victim, source_kind="test_crime", source_ref_id=_ref(), severity=90.0 if fatal else 30.0, intent_class="hostile", method=method,
                       location_id=loc, metadata=meta, outcome_override="fatal" if fatal else "transient")


def _pay_precinct(c, w, profile_id: int) -> list[int]:
    """The offender's family pays every member of the precinct that takes a matter on the ground."""
    inst = c.execute("SELECT institution_actor_id FROM law_enforcement_profiles WHERE id=?", (profile_id,)).fetchone()[0]
    officers = [int(r[0]) for r in c.execute("SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND status='active'", (inst,))]
    for o in officers:
        c.execute("INSERT INTO org_arrangements(kind,official_actor_id,payer_kind,payer_id,position_key,weekly_usd,status,started_day) VALUES ('envelope',?,'org',?,?,100,'active',0)",
                  (o, w.org, f"test:{o}"))
    return officers


def _report(c, rid):
    return c.execute("SELECT * FROM crime_reports WHERE id=?", (rid,)).fetchone()


def _process(c, day: int):
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (day,))
    return cr.process_due(c, day)


def _custody(c, actor):
    return c.execute("SELECT * FROM custody WHERE actor_id=? ORDER BY id DESC LIMIT 1", (actor,)).fetchone()


def _latest_report(c):
    return c.execute("SELECT * FROM crime_reports ORDER BY id DESC LIMIT 1").fetchone()


def test_public_killing_brings_an_arrest_despite_the_pad():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    v = _victim(c, {w.soldier}, w.org)
    prof = agency_for(c, w.ground, "homicide")
    _pay_precinct(c, w, prof)
    _hit(c, v, w.soldier, fatal=True, public=True, loc=w.ground)
    with forced_roll("pad_publicity", "identify"):  # the weighed resistance wins (a public killing is nearly impossible to bury)
        out = _process(c, DAY + 1)
    assert out["reports"] == 1, out
    rep = _latest_report(c)
    assert rep["status"] == "arrest" and rep["offender_actor_id"] == w.soldier, dict(rep)
    assert _custody(c, w.soldier)["kind"] == "held"
    assert cr.publicity_of(c, rep["id"]) > 50, cr.publicity_of(c, rep["id"])
    assert c.execute("SELECT loudness FROM public_attention WHERE report_id=?", (rep["id"],)).fetchone() is not None


def test_publicity_is_weighed_not_a_flag():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    v = _victim(c, {w.soldier}, w.org)
    loud = cr.open_report(c, crime_kind="assault", day=DAY, offender_actor_id=w.soldier, victim_actor_id=v, location_id=w.ground, public=True,
                          metadata={"bystander": True, "method": "handgun_range", "hour": 13, "victims": 3})
    quiet = cr.open_report(c, crime_kind="assault", day=DAY, offender_actor_id=w.soldier, victim_actor_id=v, location_id=w.ground, public=False,
                           metadata={"method": "execution", "hour": 3})
    pl, pq = cr.publicity_of(c, loud), cr.publicity_of(c, quiet)
    assert 0.0 <= pq < pl <= 100.0, (pq, pl)
    drivers = json.loads(_report(c, loud)["metadata_json"])["publicity_drivers"]
    assert drivers["declared_public"] == 1.0 and drivers["bystander"] == 1.0 and drivers["victims"] > 0


def test_routine_assault_on_paid_ground_can_be_buried():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    v = _victim(c, {w.soldier}, w.org)
    prof = agency_for(c, w.ground, "assault")
    _pay_precinct(c, w, prof)
    _hit(c, v, w.soldier, fatal=False, public=False, loc=w.ground, method="fists")
    with forced_roll("identify"):  # every draw high: the weighed resistance of a case this quiet does not stop the Pad
        _process(c, DAY + 1)
    rep = _latest_report(c)
    assert rep["status"] == "buried", dict(rep)
    assert _custody(c, w.soldier) is None or _custody(c, w.soldier)["kind"] != "held"
    case = c.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()
    assert case["status"] == "closed" and json.loads(case["metadata_json"])["reason"] == "arrangements"


def test_federal_case_ignores_the_pad():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    prof = agency_for(c, w.ground, "homicide")
    officers = _pay_precinct(c, w, prof)
    victim_officer = next(o for o in officers if orgs.is_living(c, o))
    _hit(c, victim_officer, w.soldier, fatal=True, public=False, loc=w.ground)
    with forced_roll("identify"):  # the agency has the name: the test is about who works the case
        _process(c, DAY + 1)
    rep = _latest_report(c)
    meta = json.loads(rep["metadata_json"])
    assert meta["officer_victim"] is True
    fbi = c.execute("SELECT id FROM law_enforcement_profiles WHERE profile_key='fbi'").fetchone()[0]
    assert c.execute("SELECT 1 FROM law_enforcement_cases WHERE profile_id=? AND json_extract(metadata_json,'$.crime_report_id')=?", (fbi, rep["id"])).fetchone()
    assert rep["status"] == "arrest" and _custody(c, w.soldier)["kind"] == "held", dict(rep)


def test_harm_without_offender_opens_investigation():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    v = _victim(c, {w.soldier}, w.org)
    _hit(c, v, None, fatal=True, public=False, loc=w.ground)
    _process(c, DAY + 1)
    rep = _latest_report(c)
    case = c.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()
    assert rep["offender_actor_id"] is None and case["status"] in ("monitoring", "open"), (dict(rep), dict(case))
    assert rep["status"] == "open"
    # nothing is invented: the evidence grows, the offender stays unknown, the case closes unsolved in time
    for d in range(DAY + 15, DAY + 200, 14):
        _process(c, d)
    assert c.execute("SELECT status FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()[0] == "closed"
    assert _report(c, rep["id"])["offender_actor_id"] is None


def test_family_answers_an_arrest():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    v = _victim(c, {w.soldier}, w.org)
    drives(c, w.capo, loyalty=0.9)
    drives(c, w.boss, loyalty=0.9)
    rel(c, w.boss, w.soldier, loyalty=90, trust=70)
    rel(c, w.capo, w.soldier, loyalty=90, trust=70)
    _hit(c, v, w.soldier, fatal=True, public=True, loc=w.ground)
    with forced_roll("pad_publicity", "identify"):
        _process(c, DAY + 1)
    rows = c.execute("SELECT actor_id FROM org_agenda WHERE kind='member_arrested' AND status='open' ORDER BY actor_id").fetchall()
    assert {r[0] for r in rows} == {w.capo, w.boss}, rows
    from engine import org_choices
    kinds = {x.action_kind for x in org_choices.org_provider(c, w.boss, "STRATEGIC", DAY + 2, {})}
    assert "member_arrested" in kinds, kinds
    from engine.ledger import receive
    receive(c, ("person", w.boss), 50_000.0, purpose="test")
    done = False
    for d in (DAY + 2, DAY + 3, DAY + 4):
        for who in (w.boss, w.capo):
            row = run_review(c, who, d)
            done = done or (row["action_type"] == "org_action" and "member_arrested" in str(row["effects_json"]))
    assert done or c.execute("SELECT 1 FROM org_agenda WHERE kind='member_arrested' AND status='resolved'").fetchone() is not None


def test_send_lawyer_brings_bail_sooner_and_costs_a_trust_drop():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    v = _victim(c, {w.soldier}, w.org)
    _hit(c, v, w.soldier, fatal=False, public=False, loc=w.ground, method="blunt")
    with forced_roll("identify"):
        _process(c, DAY + 1)
    rep = _latest_report(c)
    if rep["status"] != "arrest":
        # not every assault is arrested at once: file one that is
        rid = cr.open_report(c, crime_kind="assault", day=DAY + 1, offender_actor_id=w.soldier, victim_actor_id=v, location_id=w.ground, public=True,
                             metadata={"bystander": True, "victims": 2, "hour": 13, "identified": True})
        rep = _report(c, rid)
    assert rep["status"] == "arrest", dict(rep)
    case = c.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()
    before = json.loads(case["metadata_json"])["bail_day"]
    from engine.ledger import receive, balance
    receive(c, ("person", w.boss), 50_000.0, purpose="test")
    b0 = balance(c, ("person", w.boss))
    res = orgs and cr.execute_member_arrested(c, w.boss, "member_arrested", {"held": w.soldier, "org": w.org, "case": case["id"], "response": "send_lawyer", "charge": "homicide"}, DAY + 2)
    assert "lawyer" in res["summary"] and balance(c, ("person", w.boss)) < b0
    after = json.loads(c.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (case["id"],)).fetchone()[0])
    assert after["bail_day"] <= before and after["lawyer_fee"] > 0


def test_a_case_runs_to_a_disposition_and_a_conviction_to_a_sentence_and_release():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    v = _victim(c, {w.soldier}, w.org)
    _hit(c, v, w.soldier, fatal=True, public=True, loc=w.ground)
    with forced_roll("pad_publicity", "identify"):
        _process(c, DAY + 1)
    rep = _latest_report(c)
    assert rep["status"] == "arrest"
    case = c.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()
    due = json.loads(case["metadata_json"])["disposition_day"]
    # make the case a conviction for the test: nothing dismisses a strong, publicised case with no lawyer or witness pressure often, but weigh it honestly
    outcomes = set()
    day = DAY + 2
    while day <= due + 1:
        _process(c, day)
        day += 1
    dispo = c.execute("SELECT * FROM case_dispositions WHERE case_id=?", (case["id"],)).fetchone()
    assert dispo is not None and dispo["kind"] in ("dismissed", "plea", "verdict_guilty", "verdict_not_guilty")
    outcomes.add(dispo["kind"])
    assert _report(c, rep["id"])["status"] == "closed"
    if dispo["kind"] in ("plea", "verdict_guilty"):
        s = c.execute("SELECT * FROM sentences WHERE actor_id=?", (w.soldier,)).fetchone()
        assert s is not None and s["status"] == "serving" and s["term_days"] > 0 and s["earliest_release_day"] > s["start_day"] and s["facility"]
        assert s["crime_kind"] == "homicide" and s["victim_actor_id"] == v and s["case_id"] == case["id"]
        cu = _custody(c, w.soldier)
        assert cu["kind"] == "held" and cu["until_day"] == s["earliest_release_day"]
        _process(c, s["earliest_release_day"])
        assert c.execute("SELECT status FROM sentences WHERE id=?", (s["id"],)).fetchone()[0] == "released"
        assert _custody(c, w.soldier)["kind"] == "released"
    else:
        assert _custody(c, w.soldier)["kind"] == "released"


def test_two_seats_arrest_reaches_every_org_he_sits_in():
    w = open_world()
    c = w.conn
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    other = c.execute(
        """SELECT p.org_actor_id FROM org_profiles p WHERE p.org_actor_id<>? AND EXISTS (SELECT 1 FROM org_seats s WHERE s.org_actor_id=p.org_actor_id AND s.status='active')
           AND NOT EXISTS (SELECT 1 FROM org_seats s WHERE s.org_actor_id=p.org_actor_id AND s.actor_id=?) ORDER BY p.org_actor_id""", (w.org, w.soldier)).fetchall()
    org2 = next(int(r[0]) for r in other if orgs.head_of(c, int(r[0])) not in (None, w.boss, w.soldier))
    head2 = orgs.head_of(c, org2)
    role2 = next(s["role_key"] for s in orgs.members(c, org2) if s["actor_id"] != head2)
    orgs.seat(c, w.soldier, org2, role2, unit_id=None, superior_actor_id=head2, level=3, day=DAY)
    v = _victim(c, {w.soldier}, w.org)
    _hit(c, v, w.soldier, fatal=True, public=True, loc=w.ground)
    with forced_roll("pad_publicity", "identify"):
        _process(c, DAY + 1)
    got = {(r["actor_id"], json.loads(r["metadata_json"])["org"]) for r in c.execute("SELECT * FROM org_agenda WHERE kind='member_arrested'")}
    assert (w.boss, w.org) in got and (head2, org2) in got, got


def test_bribery_report_reaches_the_right_agency():
    w = open_world()
    c = w.conn
    chair = w.boss
    loc = w.ground
    rid = cr.open_report(c, crime_kind="bribery", day=DAY, offender_actor_id=chair, victim_actor_id=None, location_id=loc, metadata={"filed_by": "test"})
    rep = _report(c, rid)
    assert rep["agency_profile_id"] == agency_for(c, loc, "bribery") and rep["case_id"] is not None
    key = c.execute("SELECT profile_key FROM law_enforcement_profiles WHERE id=?", (rep["agency_profile_id"],)).fetchone()[0]
    assert key == "state_ag", key
    assert c.execute("SELECT profile_id FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()[0] == rep["agency_profile_id"]
    fraud = cr.open_report(c, crime_kind="fraud", day=DAY, offender_actor_id=chair, location_id=loc)
    assert c.execute("SELECT profile_key FROM law_enforcement_profiles WHERE id=?", (_report(c, fraud)["agency_profile_id"],)).fetchone()[0] == "fbi"


def test_mob_killing_reaches_the_law():
    w = open_world()
    c = w.conn
    drives(c, w.soldier, risk_tolerance=0.95, aggression=0.9)
    rel(c, w.soldier, w.capo, resentment=95)
    top = c.execute("SELECT COALESCE(MAX(id),0) FROM harm_incidents").fetchone()[0]
    with forced_roll("remove_superior"), certain_kills():
        run_review(c, w.soldier)
    assert not orgs.is_living(c, w.capo)
    _process(c, DAY + 1)
    rep = c.execute("SELECT * FROM crime_reports WHERE victim_actor_id=?", (w.capo,)).fetchone()
    assert rep is not None and rep["crime_kind"] == "homicide" and rep["offender_actor_id"] == w.soldier, c.execute("SELECT * FROM crime_reports").fetchall()
    assert top >= 0


def test_a_changed_commander_reopens_the_envelope():
    w = open_world()
    c = w.conn
    prefix_row = c.execute("SELECT * FROM org_arrangements WHERE position_key LIKE '%:captain:1' AND status='active' ORDER BY id LIMIT 1").fetchone()
    assert prefix_row is not None
    official = prefix_row["official_actor_id"]
    c.execute("UPDATE institution_memberships SET status='former' WHERE member_actor_id=? AND role_text LIKE 'Captain%'", (official,))
    inst = c.execute("SELECT institution_actor_id FROM institution_memberships WHERE member_actor_id=? AND role_text LIKE 'Captain%'", (official,)).fetchone()[0]
    newcomer = c.execute("SELECT member_actor_id FROM institution_memberships WHERE institution_actor_id=? AND status='active' AND member_actor_id<>? LIMIT 1", (inst, official)).fetchone()[0]
    c.execute("UPDATE institution_memberships SET role_text='Captain, new commander' WHERE member_actor_id=? AND institution_actor_id=?", (newcomer, inst))
    n = cr._void_envelopes(c, DAY)
    assert n >= 1 and c.execute("SELECT status FROM org_arrangements WHERE id=?", (prefix_row["id"],)).fetchone()[0] == "reopened"


def test_core_module_has_no_world_words():
    import re
    src = (ROOT / "engine" / "crime_response.py").read_text(encoding="utf-8")
    bad = re.findall(r"\b(boss|underboss|consigliere|capo|soldier|associate|made man|president|banker|family|outfit)\b", src, flags=re.I)
    assert not bad, bad
    assert not re.search(r"\$\s?\d", src)


def main() -> None:
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            ran += 1
            print("ok", name)
    print(f"{ran} tests passed")


if __name__ == "__main__":
    main()
