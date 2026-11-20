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


def test_death_opens_books_and_an_associate_is_made():
    from engine import design, outfit_choices
    from engine.simulation import advance_connection
    w = open_world()
    c = w.conn
    fig = round(design.figure(c, _fig_key(c, w.org)))
    assert _made(c, w.org) == fig, (_made(c, w.org), fig)
    day = _today(c)
    outfit_choices.kill(c, w.boss, w.soldier, day, sanctioned=True)
    assert _made(c, w.org) == fig - 1
    advance_connection(c, 60)
    assert _made(c, w.org) == fig, (_made(c, w.org), fig)
    new = c.execute("SELECT * FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND status='active' AND inducted_day>? ORDER BY inducted_day DESC", (w.org, day)).fetchone()
    assert new is not None
    assert new["joined_day"] < new["inducted_day"] and new["unit_id"] is not None, dict(new)  # he was an associate first, with a record
    assert new["superior_actor_id"] is not None and _seat(c, new["superior_actor_id"])["role_key"] == "capo"
    # the books were opened by the head and answered by the capos through the agenda
    kinds = {r[0] for r in c.execute("SELECT kind FROM org_agenda WHERE created_day>=?", (day,))}
    assert {"open_books", "propose_member", "make_member"} <= kinds, kinds


def test_made_men_come_from_the_italian_group():
    from engine import org_membership
    from engine.person_ecology import _group_families
    w = open_world()
    c = w.conn
    fams = set(_group_families(c, "italian"))
    cands = org_membership.eligible(c, w.org, w.unit, DAY)
    assert cands, "no associate of the crew is eligible"
    for a in cands:
        assert str(c.execute("SELECT name FROM actors WHERE id=?", (a,)).fetchone()[0]).split()[-1] in fams
    # an associate of another group is never offered, however good his standing
    out = c.execute("SELECT actor_id FROM org_seats WHERE unit_id=? AND role_key='associate' AND status='active' ORDER BY actor_id", (w.unit,)).fetchall()
    outsider = next((int(r[0]) for r in out if str(c.execute("SELECT name FROM actors WHERE id=?", (int(r[0]),)).fetchone()[0]).split()[-1] not in fams), None)
    if outsider is not None:
        c.execute("UPDATE org_seats SET standing=1.0 WHERE actor_id=?", (outsider,))
        assert outsider not in org_membership.eligible(c, w.org, w.unit, DAY)


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


def test_the_books_do_not_open_above_the_range_top():
    from engine import design, org_lifecycle, org_membership
    w = open_world()
    c = w.conn
    key = _fig_key(c, w.org)
    lo, hi = design.package_figures(c)[key]["range"]
    c.execute("UPDATE design_figures SET value=? WHERE key=?", (hi + 3, key))  # moved with no cause
    design._EPOCH[0] += 1
    from engine import org_motives
    org_motives._snap(c)["figs"].clear()
    assert org_membership.limit(c, w.org) == hi
    design.set_figure(c, key, hi + 2, cause="the family took over a rival's crews (dated, test)", exception=True)
    assert org_membership.limit(c, w.org) == hi + 2
    # at the limit nothing opens; one below it opens the books
    c.execute("UPDATE design_figures SET value=? WHERE key=?", (hi, key))
    design._EPOCH[0] += 1
    org_motives._snap(c)["figs"].clear()
    c.execute("UPDATE org_seats SET inducted_day=NULL, role_key='associate' WHERE org_actor_id=? AND role_key='soldier' AND status='active' AND id IN "
              "(SELECT id FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND status='active' ORDER BY id LIMIT 100)", (w.org, w.org))
    # (men turned back into dependants: the count is now well under the figure)
    org_membership.after_gone(c, w.org, DAY)
    assert _open(c, w.boss, "open_books"), "the books did not open below the limit"
    n = len(_open(c, w.boss, "open_books"))
    org_membership.after_gone(c, w.org, DAY)
    assert len(_open(c, w.boss, "open_books")) == n  # not twice


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


def test_discipline_follows_temperament():
    w = open_world()
    best = lambda offers: max(offers, key=lambda o: o["utility"])["kind"]  # noqa: E731
    _, _, calm = _discipline_case(w, 0.8, 0.2)
    assert {o["kind"] for o in calm} == {"discipline_fine", "discipline_demote", "discipline_kill"}
    assert best(calm) == "discipline_fine"
    w2 = open_world()
    _, _, first = _discipline_case(w2, 0.0, 0.97)
    assert best(first) != "discipline_kill"  # a first offence is never answered by killing, however violent the head
    w3 = open_world()
    _, _, again = _discipline_case(w3, 0.0, 0.8, repeat=True)
    assert best(again) == "discipline_kill"
    w4 = open_world()
    _, _, mild = _discipline_case(w4, 0.0, 0.2, repeat=True)
    assert best(mild) != "discipline_kill"  # a calm head fines him again


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


def test_lost_dependants_are_replaced_one_a_week_a_crew():
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
    with forced_roll("replace_dependant"):
        made1 = org_membership.replace_dependants(c, DAY + 7)
    assert made1 >= 1 and len(_dependants(c, w.unit)) == n0 + 1  # one this week in this crew however short it is
    new = [a for a in _dependants(c, w.unit) if a not in deps][0]
    s = _seat(c, new)
    assert s["role_key"] == "associate" and s["inducted_day"] is None and s["superior_actor_id"] is not None
    age = (DAY + 7 - c.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (new,)).fetchone()[0]) // 365
    assert 17 <= age <= 30, age
    with forced_roll("replace_dependant"):
        org_membership.replace_dependants(c, DAY + 14)
    assert len(_dependants(c, w.unit)) == n0 + 2


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


def test_counts_add_up_over_a_year():
    from engine import design, org_membership
    from engine.simulation import advance_connection
    w = open_world()
    c = w.conn
    advance_connection(c, 365)
    for org, key, in c.execute("SELECT org_actor_id,package_key FROM org_profiles WHERE org_kind='family' ORDER BY org_actor_id").fetchall():
        fk = _fig_key(c, int(org))
        assert _made(c, int(org)) <= round(design.package_figures(c)[fk]["range"][1]), (key, _made(c, int(org)))
        assert _made(c, int(org)) <= org_membership.limit(c, int(org))
    bad = c.execute(
        """SELECT s.actor_id FROM org_seats s LEFT JOIN org_seats sup ON sup.actor_id=s.superior_actor_id AND sup.org_actor_id=s.org_actor_id
           WHERE s.status='active' AND s.role_key IN ('associate','soldier') AND (sup.id IS NULL OR sup.status<>'active')""").fetchall()
    assert not bad, f"{len(bad)} active men without an active superior in their outfit"


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
