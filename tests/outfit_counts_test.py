"""Task B12, Saint Jude half: men are made from the dependants, the counts stay true (generic layers `org_lifecycle`
and `org_membership`, driven by the Saint Jude package data).

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/outfit_counts_test.py   (builds scratch Saint Jude openings)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, drives, forced_roll, open_world, rel


def _fig_key(conn, org):
    from engine import org_motives
    key = conn.execute("SELECT package_key FROM org_profiles WHERE org_actor_id=?", (org,)).fetchone()[0]
    return org_motives._sphere_data(conn)["outfits"][key]["members_figure"]


def _made(conn, org):
    return conn.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND inducted_day IS NOT NULL AND status='active'", (org,)).fetchone()[0]


def _today(conn):
    return int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])


def _seat(conn, a):
    return conn.execute("SELECT * FROM org_seats WHERE actor_id=?", (a,)).fetchone()


def _open(conn, actor, kind, subject=None):
    q, a = "SELECT * FROM org_agenda WHERE actor_id=? AND kind=? AND status='open'", [actor, kind]
    if subject is not None:
        q += " AND subject_id=?"
        a.append(subject)
    return conn.execute(q, a).fetchall()


def _imposed(conn, a) -> bool:
    r = conn.execute("SELECT forced_tier,forced_until_day FROM simulation_profiles WHERE actor_id=?", (a,)).fetchone()
    return r is not None and r[0] == "ACTIVE" and int(r[1] or 0) > 0


def _clear(conn, *ids):
    for a in ids:
        conn.execute("UPDATE simulation_profiles SET forced_tier=NULL,forced_until_day=NULL WHERE actor_id=?", (a,))


def _dependants(conn, unit):
    return [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE unit_id=? AND role_key='associate' AND status='active' ORDER BY actor_id", (unit,))]


def test_death_can_open_books_and_an_associate_is_made():
    """The head weighs opening the books after a death (here the draw goes his way) and the capos and the head answer through
    the agenda; whether he makes a man is a weighed decision too, so the count is one short or back at the figure."""
    from engine import design, outfit_choices
    from engine.simulation import advance_connection
    w = open_world()
    c = w.conn
    fig = round(design.figure(c, _fig_key(c, w.org)))
    assert _made(c, w.org) == fig, (_made(c, w.org), fig)
    day = _today(c)
    outfit_choices.kill(c, w.boss, w.soldier, day, sanctioned=True)
    assert _made(c, w.org) == fig - 1
    with forced_roll("open_books"):
        advance_connection(c, 60)
    kinds = {r[0] for r in c.execute("SELECT kind FROM org_agenda WHERE created_day>=?", (day,))}
    assert {"open_books", "propose_member"} <= kinds, kinds
    assert fig - 2 <= _made(c, w.org) <= fig + 1, (_made(c, w.org), fig)
    for new in c.execute("SELECT * FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND status='active' AND inducted_day>?", (w.org, day)).fetchall():
        assert new["joined_day"] < new["inducted_day"] and new["unit_id"] is not None, dict(new)  # he was an associate first, with a record
        assert new["superior_actor_id"] is not None and _seat(c, new["superior_actor_id"])["role_key"] == "capo"


def test_made_men_come_from_the_italian_group():
    from engine import org_membership
    from engine.person_ecology import _group_families
    w = open_world()
    c = w.conn
    fams = set(_group_families(c, "italian"))
    ids = org_membership.eligible(c, w.org, w.unit, DAY)
    assert ids
    name = lambda a: str(c.execute("SELECT name FROM actors WHERE id=?", (a,)).fetchone()[0]).split()[-1]  # noqa: E731
    out = [a for a in ids if name(a) not in fams]
    inn = [a for a in ids if name(a) in fams]
    assert out and inn, "the crew should have both kinds of name to test with"
    # the usual rule is a strong weight: an outsider of the same standing ranks below an Italian name
    c.execute("UPDATE org_seats SET standing=0.5 WHERE actor_id IN (%s)" % ",".join(str(a) for a in ids))
    got = org_membership.eligible(c, w.org, w.unit, DAY)
    assert got.index(out[0]) > got.index(inn[0])
    # ... but not a refusal: an outsider far better than every other name is put forward first
    c.execute("UPDATE org_seats SET standing=0.0 WHERE actor_id IN (%s)" % ",".join(str(a) for a in ids))
    c.execute("UPDATE org_seats SET standing=1.0 WHERE actor_id=?", (out[0],))
    assert org_membership.eligible(c, w.org, w.unit, DAY)[0] == out[0]


def test_age_only_weighs_on_a_nomination():
    from engine import org_membership
    w = open_world()
    c = w.conn
    ids = org_membership.eligible(c, w.org, w.unit, DAY)
    a = ids[0]
    c.execute("UPDATE actor_life_profiles SET birth_day=? WHERE actor_id=?", (DAY - 20 * 365, a))  # twenty: under the usual age
    young = org_membership.nomination_score(c, w.org, a, DAY)
    c.execute("UPDATE actor_life_profiles SET birth_day=? WHERE actor_id=?", (DAY - 40 * 365, a))
    assert org_membership.nomination_score(c, w.org, a, DAY) > young
    assert a in org_membership.eligible(c, w.org, w.unit, DAY)  # never refused


def test_the_best_standing_is_proposed_and_the_man_is_made():
    from engine import org_choices, org_membership
    w = open_world()
    c = w.conn
    cands = org_membership.eligible(c, w.org, w.unit, DAY)
    best = cands[0]
    c.execute("UPDATE org_seats SET standing=0.99 WHERE actor_id=?", (best,))
    assert org_membership.eligible(c, w.org, w.unit, DAY)[0] == best
    c.execute("UPDATE org_seats SET superior_actor_id=? WHERE actor_id=?", (w.soldier, best))
    # a recruit of his stays under the soldier who vouched for them until he is made
    kid = _dependants(c, w.unit)[0] if _dependants(c, w.unit)[0] != best else _dependants(c, w.unit)[1]
    c.execute("UPDATE org_seats SET superior_actor_id=? WHERE actor_id=?", (w.soldier, kid))
    c.execute("INSERT INTO org_incidents(day,kind,offender_actor_id,status,metadata_json) VALUES (?, 'recruits', ?, 'done', ?)", (DAY - 5, best, json.dumps({"recruit": kid})))
    _clear(c, best, kid, w.capo, w.boss)
    got = org_membership.induct(c, w.org, best, w.capo, DAY)
    s = _seat(c, best)
    assert got == best and s["role_key"] == "soldier" and s["inducted_day"] == DAY and s["superior_actor_id"] == w.capo
    assert _seat(c, kid)["superior_actor_id"] == best  # the men he brought in re-parent to him
    assert _imposed(c, best) and _imposed(c, kid)  # imposed on him and on the re-parented
    assert c.execute("SELECT history_due FROM org_seats WHERE actor_id=?", (best,)).fetchone()[0] == 1
    assert c.execute("SELECT 1 FROM org_agenda WHERE actor_id=? AND kind='history'", (best,)).fetchone()
    assert "Soldier" in c.execute("SELECT role_text FROM institution_memberships WHERE institution_actor_id=? AND member_actor_id=?", (w.org, best)).fetchone()[0]


def test_the_figure_is_a_preference_not_a_cap_and_a_count_outside_the_range_is_flagged():
    from engine import design, org_membership
    w = open_world()
    c = w.conn
    key = _fig_key(c, w.org)
    lo, hi = design.package_figures(c)[key]["range"]
    assert org_membership.preferred(c, w.org) == round(design.figure(c, key))
    # more men than the range allows are inducted (as if the head made them): nothing refuses
    extra = hi - _made(c, w.org) + 2
    ids = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='associate' AND status='active' ORDER BY standing DESC LIMIT ?", (w.org, extra))]
    c.execute("UPDATE org_seats SET inducted_day=?, role_key='soldier' WHERE actor_id IN (%s) AND org_actor_id=?" % ",".join(str(i) for i in ids), (DAY - 5, w.org))
    assert _made(c, w.org) > hi
    assert org_membership.flag_unusual(c, DAY) == 1
    row = c.execute("SELECT cause,new_value FROM design_figure_log WHERE key=? AND cause LIKE 'unusual:%' ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    assert row is not None and "needs a cause" in row[0] and int(row[1]) == _made(c, w.org)
    assert org_membership.flag_unusual(c, DAY + 7) == 0  # the same count is flagged once
    # and the books can still open above the range: the head weighs it, and a head drawn to it does it
    with forced_roll("open_books"):
        assert org_membership.after_gone(c, w.org, DAY)
    assert _open(c, w.boss, "open_books")
    n = len(_open(c, w.boss, "open_books"))
    with forced_roll("open_books"):
        org_membership.after_gone(c, w.org, DAY)
    assert len(_open(c, w.boss, "open_books")) == n  # not twice
    # a head who is not drawn to it does not open them
    w2 = open_world()
    with forced_roll():
        assert not org_membership.after_gone(w2.conn, w2.org, DAY)


def test_the_pressure_to_open_the_books_follows_its_drivers():
    from engine import org_membership
    w = open_world()
    c = w.conn
    base = org_membership.books_pressure(c, w.org, DAY, w.boss)
    c.execute("UPDATE org_seats SET inducted_day=NULL, role_key='associate' WHERE id IN (SELECT id FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND status='active' ORDER BY id LIMIT 8)", (w.org,))
    assert org_membership.books_pressure(c, w.org, DAY, w.boss) > base  # men short of the figure
    short = org_membership.books_pressure(c, w.org, DAY, w.boss)
    men = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND inducted_day IS NOT NULL AND status='active' LIMIT 12", (w.org,))]
    for m in men:  # law heat: open cases against the family's made men
        c.execute("INSERT INTO crime_reports(day,crime_kind,offender_actor_id,public,status,metadata_json) VALUES (?,?,?,0,'open','{}')", (DAY, "test", m))
    assert org_membership.books_pressure(c, w.org, DAY, w.boss) < short


def test_hidden_line_can_be_caught():
    from engine import org_membership
    w = open_world()
    c = w.conn
    holding = int(c.execute("SELECT id FROM org_holdings WHERE org_actor_id=? LIMIT 1", (w.org,)).fetchone()[0])
    c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,weekly_take,hidden,started_day) VALUES (?,?,?,?,?,1,?)",
              (holding, w.unit, w.soldier, "a kept-back book", 600.0, DAY - 140))
    line = int(c.execute("SELECT MAX(id) FROM org_lines").fetchone()[0])
    _clear(c, w.soldier, w.boss)
    with forced_roll():  # every roll fails: nothing is caught
        org_membership.discover_hidden(c, DAY)
    assert not _open(c, w.boss, "discipline") and c.execute("SELECT hidden FROM org_lines WHERE id=?", (line,)).fetchone()[0] == 1
    with forced_roll("hidden_discovery"):
        n = org_membership.discover_hidden(c, DAY)
    assert n >= 1
    items = _open(c, w.boss, "discipline", w.soldier)
    assert len(items) == 1 and json.loads(items[0]["metadata_json"])["line"] == line
    assert c.execute("SELECT hidden FROM org_lines WHERE id=?", (line,)).fetchone()[0] == 0
    assert _imposed(c, w.soldier)  # the discipline subject
    with forced_roll("hidden_discovery"):
        org_membership.discover_hidden(c, DAY + 7)
    assert len(_open(c, w.boss, "discipline", w.soldier)) == 1  # a line is caught once


def test_a_cautious_man_is_caught_less_often():
    from engine import org_membership
    w = open_world()
    c = w.conn
    drives(c, w.soldier, risk_tolerance=0.2)
    cautious = org_membership.discovery_chance(c, w.soldier, 7)
    drives(c, w.soldier, risk_tolerance=1.0)
    bold = org_membership.discovery_chance(c, w.soldier, 7)
    assert 0.0 < cautious < bold <= 0.05 * 7 / 28 + 1e-9, (cautious, bold)


def _discipline_case(w, holder_standing, aggression, repeat=False):
    from engine import org_choices
    c = w.conn
    holding = int(c.execute("SELECT id FROM org_holdings WHERE org_actor_id=? LIMIT 1", (w.org,)).fetchone()[0])
    c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,weekly_take,hidden,started_day) VALUES (?,?,?,?,?,0,?)",
              (holding, w.unit, w.soldier, "a kept-back book", 500.0, DAY - 70))
    line = int(c.execute("SELECT MAX(id) FROM org_lines").fetchone()[0])
    c.execute("UPDATE org_seats SET standing=? WHERE actor_id=?", (holder_standing, w.soldier))
    drives(c, w.boss, aggression=aggression)
    if repeat:  # he was disciplined before
        c.execute("INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,status,resolved_day,metadata_json) VALUES (?,?,?,?,?,?,'resolved',?,?)",
                  (w.boss, "discipline", DAY - 200, "actor", w.soldier, DAY - 200, DAY - 199, json.dumps({"org": w.org, "line": line, "holder": w.soldier})))
    aid = int(__import__("engine.orgs", fromlist=["x"]).add_agenda(c, w.boss, "discipline", DAY, subject_kind="actor", subject_id=w.soldier,
                                                                   metadata={"org": w.org, "line": line, "holder": w.soldier}))
    item = c.execute("SELECT * FROM org_agenda WHERE id=?", (aid,)).fetchone()
    offers = org_choices.AGENDA_ACTIONS["discipline"](c, w.boss, item, DAY)
    return line, aid, offers


def _kill_raw(w, standing, aggression, repeat=False, take=500.0, weeks=10):
    """The head's raw pull toward killing (unclamped), for a line of `take` a week hidden `weeks` weeks."""
    from engine import org_membership
    line, aid, _ = _discipline_case(w, standing, aggression, repeat)
    c = w.conn
    c.execute("UPDATE org_lines SET weekly_take=?, started_day=? WHERE id=?", (take, DAY - 7 * weeks, line))
    item = c.execute("SELECT * FROM org_agenda WHERE id=?", (aid,)).fetchone()
    return org_membership.kill_weight(c, item, w.org, w.soldier, _seat(c, w.soldier), w.boss, DAY)


def test_discipline_follows_temperament():
    w = open_world()
    best = lambda offers: max(offers, key=lambda o: o["utility"])["kind"]  # noqa: E731
    _, _, calm = _discipline_case(w, 0.8, 0.2)
    assert {o["kind"] for o in calm} == {"discipline_fine", "discipline_demote", "discipline_kill"}
    assert best(calm) == "discipline_fine"  # the ordinary answer: fined
    # every driver moves the pull the way the data says; no one of them is a gate
    base = _kill_raw(open_world(), 0.5, 0.5)
    assert _kill_raw(open_world(), 0.5, 0.9) > base                       # a hotter head
    assert _kill_raw(open_world(), 0.1, 0.5) > base                       # a man of less standing
    assert _kill_raw(open_world(), 0.5, 0.5, take=5000.0) > base          # a bigger skim
    assert _kill_raw(open_world(), 0.5, 0.5, weeks=90) > base             # one that ran longer
    assert _kill_raw(open_world(), 0.5, 0.5, repeat=True) > base          # a repeat offence
    # a first offence can end in death, but only when much adds up: a big, long skim, a nobody, a hot head
    w2 = open_world()
    _kill_raw(w2, 0.0, 0.97, take=5000.0, weeks=100)
    _, _, hot = _discipline_case(w2, 0.0, 0.97)
    c2 = w2.conn
    c2.execute("UPDATE org_lines SET weekly_take=5000, started_day=? WHERE id=(SELECT MAX(id) FROM org_lines)", (DAY - 700,))
    item = c2.execute("SELECT * FROM org_agenda WHERE kind='discipline' ORDER BY id DESC LIMIT 1").fetchone()
    from engine import org_choices
    assert best(org_choices.AGENDA_ACTIONS["discipline"](c2, w2.boss, item, DAY)) == "discipline_kill"
    # an ordinary first offence under the same hot head is a fine
    assert best(_discipline_case(open_world(), 0.6, 0.97)[2]) != "discipline_kill"
    # and a repeat offence is likelier to end in death than the same first offence
    assert _kill_raw(open_world(), 0.5, 0.8, repeat=True) - _kill_raw(open_world(), 0.5, 0.8) >= 0.25


def test_inducted_men_have_standing_from_years_role_and_earnings():
    w = open_world()
    c = w.conn
    rows = {r[0]: r[1] for r in c.execute("SELECT role_key,AVG(standing) FROM org_seats WHERE inducted_day IS NOT NULL AND org_actor_id IN (SELECT org_actor_id FROM org_profiles WHERE org_kind NOT IN ('party','political_club','interest')) GROUP BY 1")}
    assert all(v > 0.2 for v in rows.values()), rows
    assert rows["boss"] > rows["soldier"] and rows["capo"] > rows["soldier"], rows
    assert not [r for r in c.execute("SELECT 1 FROM org_seats WHERE inducted_day IS NOT NULL AND standing=0 AND org_actor_id IN (SELECT org_actor_id FROM org_profiles WHERE org_kind NOT IN ('party','political_club','interest'))")]


def test_inducted_standing_moves_weekly():
    from engine import org_membership
    w = open_world()
    c = w.conn
    s0 = float(_seat(c, w.soldier)["standing"])
    c.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,amount,org_actor_id) VALUES (?,?,?,?,?,?)", (DAY - 3, "kickup", w.soldier, w.capo, 100.0, w.org))
    org_membership.move_standing(c, DAY)
    s1 = float(_seat(c, w.soldier)["standing"])
    assert s1 > s0 and s1 - s0 < 0.01, (s0, s1)  # passing money up on time raises it, slowly
    c.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held','test',?,?)", (w.soldier, DAY - 2, DAY + 20))
    org_membership.move_standing(c, DAY + 1)
    s2 = float(_seat(c, w.soldier)["standing"])
    assert s2 < s1 - 0.05, (s1, s2)  # an arrest lowers it


def test_being_caught_lowers_standing():
    from engine import org_membership
    w = open_world()
    c = w.conn
    holding = int(c.execute("SELECT id FROM org_holdings WHERE org_actor_id=? LIMIT 1", (w.org,)).fetchone()[0])
    c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,weekly_take,hidden,started_day) VALUES (?,?,?,?,?,1,?)", (holding, w.unit, w.soldier, "x", 600.0, DAY - 140))
    s0 = float(_seat(c, w.soldier)["standing"])
    with forced_roll("hidden_discovery"):
        org_membership.discover_hidden(c, DAY)
    assert float(_seat(c, w.soldier)["standing"]) < s0


def test_the_fine_is_the_kick_up_back_and_the_line_is_taken_or_the_man_killed():
    from engine import ledger, org_choices
    w = open_world()
    c = w.conn
    line, aid, offers = _discipline_case(w, 0.5, 0.3)
    c.execute("UPDATE org_seats SET standing=0.5 WHERE actor_id=?", (w.soldier,))
    ledger.receive(c, ("person", w.soldier), 100_000.0, purpose="test purse")
    before_h, before_b = ledger.balance(c, ("person", w.soldier)), ledger.balance(c, ("person", w.boss))
    _clear(c, w.soldier)
    offer = next(o for o in offers if o["kind"] == "discipline_fine")
    out = org_choices.execute(c, w.boss, "discipline_fine", {**offer["payload"], "agenda_id": aid}, DAY)
    paid = before_h - ledger.balance(c, ("person", w.soldier))
    assert paid > 0 and abs(ledger.balance(c, ("person", w.boss)) - before_b - paid) < 1e-6, (paid, out)
    weeks = 70 / 7
    assert paid >= 500.0 * weeks * 0.30 - 1e-6  # at least the kick-up that was kept back
    assert c.execute("SELECT status FROM org_agenda WHERE id=?", (aid,)).fetchone()[0] == "resolved"
    assert _seat(c, w.soldier)["standing"] < 0.5 and _imposed(c, w.soldier)
    assert c.execute("SELECT COUNT(*) FROM org_money WHERE from_actor_id=? AND to_actor_id=?", (w.soldier, w.boss)).fetchone()[0] >= 1
    # demote: the line is taken (goes to the capo), standing falls
    w = open_world()
    c = w.conn
    line, aid, offers = _discipline_case(w, 0.5, 0.3)
    _clear(c, w.soldier)
    offer = next(o for o in offers if o["kind"] == "discipline_demote")
    org_choices.execute(c, w.boss, "discipline_demote", offer["payload"], DAY)
    assert c.execute("SELECT holder_actor_id FROM org_lines WHERE id=?", (line,)).fetchone()[0] == w.capo
    assert _imposed(c, w.soldier)
    # kill
    w = open_world()
    c = w.conn
    line, aid, offers = _discipline_case(w, 0.5, 0.3)
    offer = next(o for o in offers if o["kind"] == "discipline_kill")
    org_choices.execute(c, w.boss, "discipline_kill", offer["payload"], DAY)
    from engine import orgs
    assert not orgs.is_living(c, w.soldier) and _seat(c, w.soldier)["status"] == "dead"


def test_held_capo_drops_to_weekly_and_returns():
    from engine import org_lifecycle, orgs
    w = open_world()
    c = w.conn
    d = _today(c)
    assert orgs.seat_of(c, w.capo, w.org)["level"] == 4
    c.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held','test',?,?)", (w.capo, d, d + 60))
    with forced_roll():
        org_lifecycle.process_due(c, d + 35)
    assert orgs.seat_of(c, w.capo, w.org)["level"] == 4  # his superior did not take it away
    with forced_roll("held_level"):
        org_lifecycle.process_due(c, d + 35)
    assert orgs.seat_of(c, w.capo, w.org)["level"] == 3
    c.execute("UPDATE custody SET kind='released' WHERE actor_id=?", (w.capo,))
    org_lifecycle.process_due(c, d + 42)
    assert orgs.seat_of(c, w.capo, w.org)["level"] == 4


def test_a_head_who_has_stepped_back_is_weekly():
    from engine import org_lifecycle, orgs
    w = open_world()
    c = w.conn
    d = _today(c)
    orgs.add_agenda(c, w.boss, "retired", d, subject_kind="actor", subject_id=w.boss)
    org_lifecycle.process_due(c, d + 7)
    assert orgs.seat_of(c, w.boss, w.org)["level"] == 3
    c.execute("UPDATE org_agenda SET status='resolved' WHERE actor_id=? AND kind='retired'", (w.boss,))
    org_lifecycle.process_due(c, d + 14)
    assert orgs.seat_of(c, w.boss, w.org)["level"] == 4


def test_leaving_the_life_keeps_the_record():
    from engine import org_happenings, org_lifecycle
    w = open_world()
    c = w.conn
    a = _dependants(c, w.unit)[0]
    org_happenings.forget_readings()
    org_happenings.happen(c, a, "goes_straight", DAY)
    s = _seat(c, a)
    assert c.execute("SELECT 1 FROM actors WHERE id=?", (a,)).fetchone() and s["status"] == "out" and s["left_day"] is not None
    p = c.execute("SELECT tier,cadence_days,quiet_routine FROM simulation_profiles WHERE actor_id=?", (a,)).fetchone()
    assert p["tier"] == "DORMANT" and p["quiet_routine"] == 0 and p["cadence_days"] == 180


def test_lost_dependants_are_replaced_at_the_rate_alone():
    from engine import org_lifecycle, org_membership
    w = open_world()
    c = w.conn
    deps = _dependants(c, w.unit)
    assert len(deps) >= 4
    for a in deps[:3]:
        org_lifecycle.leave_life(c, a, w.org, DAY)
    n0 = len(_dependants(c, w.unit))
    with forced_roll():  # the chance does not fire
        org_membership.replace_dependants(c, DAY + 7)
    assert len(_dependants(c, w.unit)) == n0
    with forced_roll("replace_dependant"):  # one place draws well
        org_membership.replace_dependants(c, DAY + 7)
    assert len(_dependants(c, w.unit)) == n0 + 1
    new = [a for a in _dependants(c, w.unit) if a not in deps][0]
    s = _seat(c, new)
    assert s["role_key"] == "associate" and s["inducted_day"] is None and s["superior_actor_id"] is not None
    age = (DAY + 7 - c.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (new,)).fetchone()[0]) // 365
    assert 17 <= age <= 30, age
    with forced_roll("replace_dependant", "replace_dependant:1", "replace_dependant:2", "replace_dependant:3"):  # a crew that lost several takes more than one in a week
        org_membership.replace_dependants(c, DAY + 14)
    assert len(_dependants(c, w.unit)) >= n0 + 2


def test_standing_grows_for_dependants_who_earned():
    from engine import org_membership
    w = open_world()
    c = w.conn
    a, b = _dependants(c, w.unit)[:2]
    c.execute("UPDATE org_seats SET standing=0.3 WHERE actor_id IN (?,?)", (a, b))
    c.execute("INSERT INTO org_money(day,kind,from_actor_id,to_actor_id,amount,org_actor_id) VALUES (?,?,?,?,?,?)", (DAY - 3, "associate_earning", w.soldier, a, 100.0, w.org))
    org_membership.grow_standing(c, DAY)
    sa, sb = float(_seat(c, a)["standing"]), float(_seat(c, b)["standing"])
    assert sa > 0.3 and abs(sb - 0.3) < 1e-9, (sa, sb)
    assert sa - 0.3 < 0.02  # slowly: a reputation takes years


def test_counts_move_around_the_figure_over_a_year():
    from engine import design
    from engine.simulation import advance_connection
    w = open_world()
    c = w.conn
    advance_connection(c, 365)
    for org, key, in c.execute("SELECT org_actor_id,package_key FROM org_profiles WHERE org_kind='family' ORDER BY org_actor_id").fetchall():
        fig = round(design.figure(c, _fig_key(c, int(org))))
        assert 0.8 * fig <= _made(c, int(org)) <= 1.25 * fig, (key, _made(c, int(org)), fig)
    bad = c.execute(
        """SELECT s.actor_id FROM org_seats s LEFT JOIN org_seats sup ON sup.actor_id=s.superior_actor_id AND sup.org_actor_id=s.org_actor_id
           WHERE s.status='active' AND s.role_key IN ('associate','soldier') AND (sup.id IS NULL OR sup.status<>'active')""").fetchall()
    assert not bad, f"{len(bad)} active men without an active superior in their outfit"


def _holdout(w, amount, aggression=0.5, standing=0.3, repeat=False, weeks=2):
    """A dependant noticed keeping money back: the item his patron gets, and its offers."""
    from engine import org_choices, org_membership
    c = w.conn
    dep = _dependants(c, w.unit)[0]
    patron = _seat(c, dep)["superior_actor_id"]
    c.execute("UPDATE org_seats SET standing=? WHERE actor_id=?", (standing, dep))
    drives(c, int(patron), aggression=aggression)
    if repeat:
        c.execute("INSERT INTO org_agenda(actor_id,kind,due_day,subject_kind,subject_id,created_day,status,resolved_day,metadata_json) VALUES (?,?,?,?,?,?,'resolved',?,?)",
                  (int(patron), "discipline", DAY - 100, "actor", dep, DAY - 100, DAY - 99, json.dumps({"org": w.org, "holder": dep})))
    aid = org_membership.discipline_for_holdout(c, dep, w.org, amount, DAY - 7 * weeks, 1, DAY)
    item = c.execute("SELECT * FROM org_agenda WHERE id=?", (aid,)).fetchone()
    return dep, int(patron), item, org_choices.AGENDA_ACTIONS["discipline"](c, int(patron), item, DAY)


def test_a_dependant_caught_skimming_goes_to_his_patron_not_the_head():
    w = open_world()
    c = w.conn
    dep, patron, item, offers = _holdout(w, 400.0)
    assert int(item["actor_id"]) == patron and patron != w.boss  # no head's sanction is needed
    assert json.loads(item["metadata_json"])["status"] == "unprotected"
    assert {o["kind"] for o in offers} == {"discipline_pay_back", "discipline_cut_off", "discipline_kill"}
    assert _imposed(c, dep) and _imposed(c, patron)
    # a made man's discipline goes to the head
    holding = int(c.execute("SELECT id FROM org_holdings WHERE org_actor_id=? LIMIT 1", (w.org,)).fetchone()[0])
    c.execute("INSERT INTO org_lines(holding_id,unit_id,holder_actor_id,description,weekly_take,hidden,started_day) VALUES (?,?,?,?,?,1,?)", (holding, w.unit, w.soldier, "x", 500.0, DAY - 70))
    from engine import org_membership
    with forced_roll("hidden_discovery"):
        org_membership.discover_hidden(c, DAY)
    mine = _open(c, w.boss, "discipline", w.soldier)
    assert len(mine) == 1 and json.loads(mine[0]["metadata_json"])["status"] == "protected"


def test_pay_back_is_the_usual_answer_and_an_associate_can_be_killed_on_a_first_offence():
    best = lambda offers: max(offers, key=lambda o: o["utility"])["kind"]  # noqa: E731
    assert best(_holdout(open_world(), 200.0)[3]) == "discipline_pay_back"  # a small first skim: a beating and repayment
    assert best(_holdout(open_world(), 200.0, aggression=0.3, standing=0.5)[3]) == "discipline_pay_back"
    # a big skim, a violent patron, a nobody: killed, with no repeat offence behind it
    assert best(_holdout(open_world(), 9000.0, aggression=0.95, standing=0.0, weeks=20)[3]) == "discipline_kill"
    # the same man in a made man's place (the protected weights) is not: killing an unprotected man costs the family little
    from engine import org_membership
    w = open_world()
    dep, patron, item, _ = _holdout(w, 9000.0, aggression=0.95, standing=0.0, weeks=20)
    c = w.conn
    s = _seat(c, dep)
    du = org_membership.kill_weight(c, item, w.org, dep, s, patron, DAY)
    meta = json.loads(item["metadata_json"])
    protected_item = {"id": item["id"], "metadata_json": json.dumps({**meta, "status": "protected"})}
    assert du > org_membership.kill_weight(c, protected_item, w.org, dep, s, patron, DAY) + 0.2
    # every driver pulls the right way
    base = org_membership.kill_weight(*(lambda w2: (w2.conn,) + _kw(w2, 800.0))(open_world()))
    assert org_membership.kill_weight(*(lambda w2: (w2.conn,) + _kw(w2, 8000.0))(open_world())) > base  # a bigger skim
    assert org_membership.kill_weight(*(lambda w2: (w2.conn,) + _kw(w2, 800.0, aggression=0.95))(open_world())) > base  # a hotter patron
    assert org_membership.kill_weight(*(lambda w2: (w2.conn,) + _kw(w2, 800.0, repeat=True))(open_world())) > base  # a repeat offence
    assert org_membership.kill_weight(*(lambda w2: (w2.conn,) + _kw(w2, 800.0, standing=0.0))(open_world())) > base  # a man of no standing


def _kw(w, amount, **kw):
    from engine import org_membership
    dep, patron, item, _ = _holdout(w, amount, **kw)
    return item, w.org, dep, _seat(w.conn, dep), patron, DAY


def test_the_associates_own_outcomes_are_carried_out():
    from engine import ledger, org_choices, orgs
    w = open_world()
    c = w.conn
    dep, patron, item, offers = _holdout(w, 400.0)
    ledger.receive(c, ("person", dep), 5000.0, purpose="test purse")
    before_p, before_d = ledger.balance(c, ("person", patron)), ledger.balance(c, ("person", dep))
    st = float(_seat(c, dep)["standing"])
    _clear(c, dep, patron)
    offer = next(o for o in offers if o["kind"] == "discipline_pay_back")
    org_choices.execute(c, patron, "discipline_pay_back", {**offer["payload"], "agenda_id": int(item["id"])}, DAY)
    paid = before_d - ledger.balance(c, ("person", dep))
    assert paid > 0 and abs(ledger.balance(c, ("person", patron)) - before_p - paid) < 1e-6
    assert c.execute("SELECT COUNT(*) FROM harm_incidents WHERE actor_id=?", (dep,)).fetchone()[0] >= 1  # the beating went through the harm path
    assert float(_seat(c, dep)["standing"]) < st and _imposed(c, dep) and _imposed(c, patron)
    assert c.execute("SELECT status FROM org_agenda WHERE id=?", (int(item["id"]),)).fetchone()[0] == "resolved"
    # cut off: the seat goes out (or another crew takes him at the bottom); the record stays
    w = open_world()
    c = w.conn
    dep, patron, item, offers = _holdout(w, 400.0)
    _clear(c, dep, patron)
    offer = next(o for o in offers if o["kind"] == "discipline_cut_off")
    with forced_roll():
        org_choices.execute(c, patron, "discipline_cut_off", {**offer["payload"], "agenda_id": int(item["id"])}, DAY)
    s = _seat(c, dep)
    assert c.execute("SELECT 1 FROM actors WHERE id=?", (dep,)).fetchone() and s["status"] == "out" and s["left_day"] is not None
    assert c.execute("SELECT tier FROM simulation_profiles WHERE actor_id=?", (dep,)).fetchone()[0] == "DORMANT"
    assert _imposed(c, patron)
    # kill: the existing kill path, the patron as the killer
    w = open_world()
    c = w.conn
    dep, patron, item, offers = _holdout(w, 400.0)
    offer = next(o for o in offers if o["kind"] == "discipline_kill")
    org_choices.execute(c, patron, "discipline_kill", {**offer["payload"], "agenda_id": int(item["id"])}, DAY)
    assert not orgs.is_living(c, dep) and _seat(c, dep)["status"] == "dead"


def test_a_made_man_going_straight_is_not_a_clean_exit():
    from engine import org_choices, org_lifecycle
    w = open_world()
    c = w.conn
    day = _today(c)
    org_lifecycle.leave_life(c, w.soldier, w.org, day)
    org_lifecycle.process_due(c, day + 7)
    items = _open(c, w.boss, "discipline", w.soldier)
    assert len(items) == 1 and json.loads(items[0]["metadata_json"])["reason"] == "left"
    offers = org_choices.AGENDA_ACTIONS["discipline"](c, w.boss, items[0], day + 7)
    assert {o["kind"] for o in offers} == {"drop_discipline", "discipline_kill"}
    kill = next(o for o in offers if o["kind"] == "discipline_kill")["utility"]
    # a man who talks easily and a hot head make killing him likelier
    drives(c, w.boss, aggression=0.95)
    drives(c, w.soldier, loyalty=0.0)
    c.execute("UPDATE org_seats SET reliability=0.0 WHERE actor_id=?", (w.soldier,))
    hot = next(o for o in org_choices.AGENDA_ACTIONS["discipline"](c, w.boss, items[0], day + 7) if o["kind"] == "discipline_kill")["utility"]
    assert hot > kill
    # an associate leaving stays low-key: no discipline item
    dep = _dependants(c, w.unit)[0]
    sup = _seat(c, dep)["superior_actor_id"]
    org_lifecycle.leave_life(c, dep, w.org, day + 8)
    org_lifecycle.process_due(c, day + 14)
    assert not _open(c, int(sup), "discipline") and not _open(c, w.boss, "discipline", dep)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    bad = []
    for t in TESTS:
        try:
            t()
        except Exception:  # noqa: BLE001
            import traceback
            bad.append(t.__name__)
            traceback.print_exc()
        else:
            print("ok", t.__name__, flush=True)
    if bad:
        print("FAILED", bad)
        sys.exit(1)
    print("outfit_counts_test OK", len(TESTS))
