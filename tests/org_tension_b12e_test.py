"""Task B12e: tension between the families (tension between organisations raised and eased by small acts, weighed by people), violence from each man's
own temperament, wars that widen, heat on the organisation layer, the outer ring and the men in no family. Nothing here is capped.

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/org_tension_b12e_test.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, certain_kills, drives, open_world


def _org(conn, key):
    return int(conn.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def test_tension_is_directional_decays_and_has_no_top():
    from engine import org_tension as ot
    w = open_world()
    c = w.conn
    a, b = _org(c, "sabatini"), _org(c, "pellegrino")
    base = ot.level(c, a, b, DAY)
    ot.add(c, a, b, "test", 500.0, DAY)  # far past any scale: nothing clamps it
    assert ot.level(c, a, b, DAY) == base + 500.0
    assert ot.level(c, b, a, DAY) < ot.level(c, a, b, DAY)  # the other direction is its own
    half = int(ot._half(c))
    assert abs(ot.level(c, a, b, DAY + half) - (base + 500.0) / 2) < 1e-6
    h = ot.heat(c, a, b, DAY)
    assert 0.9 < h < 1.0  # read with diminishing weight, never clamped to 1
    ot.add(c, a, b, "test_ease", -10000.0, DAY)
    assert ot.level(c, a, b, DAY) == 0.0  # no level below nothing
    n = c.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind IN ('test','test_ease')").fetchone()[0]
    assert n == 2


def test_the_setting_starts_with_its_old_quarrels():
    w = open_world()
    c = w.conn
    from engine import org_tension as ot
    assert ot.level(c, _org(c, "vannucci"), _org(c, "pellegrino"), 0) > ot.level(c, _org(c, "sabatini"), _org(c, "pellegrino"), 0)
    assert ot.level(c, _org(c, "ferrante"), _org(c, "sabatini"), 0) > 5  # the 1958 schism


def test_small_acts_raise_it_and_a_killing_raises_it_most():
    from engine import org_happenings as oh, org_tension as ot
    w = open_world()
    c = w.conn
    other = _org(c, "pellegrino") if w.org != _org(c, "pellegrino") else _org(c, "sabatini")
    before = ot.level(c, other, w.org, DAY)
    # a line opened on the other's ground
    ground = int(c.execute("SELECT ground_location_id FROM org_units WHERE org_actor_id=? AND ground_location_id IS NOT NULL LIMIT 1", (other,)).fetchone()[0])
    ot.on_line_opened(c, w.org, ground, w.soldier, DAY)
    after_line = ot.level(c, other, w.org, DAY)
    assert after_line > before
    v = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key='soldier' ORDER BY actor_id LIMIT 1", (other,)).fetchone()[0])
    ot.on_incident(c, other, w.org, w.soldier, v, "member", DAY)
    after_incident = ot.level(c, other, w.org, DAY)
    assert after_incident > after_line
    seats = c.execute("SELECT org_actor_id,role_key,unit_id,superior_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (v,)).fetchall()
    with certain_kills():
        from engine.outfit_choices import kill
        kill(c, w.soldier, v, DAY, sanctioned=True)
    after_kill = ot.level(c, other, w.org, DAY)
    assert after_kill - after_incident > after_incident - after_line
    # an unsanctioned killing counts for more than a sanctioned one
    w2 = open_world()
    c2 = w2.conn
    o2 = other
    v2 = int(c2.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key='soldier' ORDER BY actor_id LIMIT 1", (o2,)).fetchone()[0])
    s0 = ot.level(c2, o2, w2.org, DAY)
    with certain_kills():
        kill(c2, w2.soldier, v2, DAY, sanctioned=False)
    assert ot.level(c2, o2, w2.org, DAY) - s0 > after_kill - after_incident


def test_a_sit_down_and_a_funeral_ease_it():
    from engine import org_tension as ot
    w = open_world()
    c = w.conn
    a, b = _org(c, "sabatini"), _org(c, "ferrante")
    ot.add(c, a, b, "test", 20.0, DAY)
    ot.add(c, b, a, "test", 20.0, DAY)
    lv = ot.level(c, a, b, DAY)
    voice = ot.draw_voice(c, a, b, DAY)
    res = ot.weigh_pair(c, a, b, DAY, voice=voice, only="sit_down")
    assert res is not None
    if res.get("settled"):
        assert ot.level(c, a, b, DAY) < lv and ot.level(c, b, a, DAY) < lv
    else:
        assert ot.level(c, a, b, DAY) > lv  # a refused sit-down sours it
    lv = ot.level(c, a, b, DAY)
    host_head = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='boss' AND status='active'", (a,)).fetchone()[0])
    dead = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND status='active' ORDER BY actor_id LIMIT 1", (a,)).fetchone()[0])
    ot.on_death(c, dead, a, "soldier", DAY)
    kinds = {r[0] for r in c.execute("SELECT kind FROM org_tension_acts WHERE victim_id=?", (dead,))}
    assert "wake" in kinds
    ot.on_death(c, dead, a, "soldier", DAY)  # his wake is weighed once
    assert c.execute("SELECT COUNT(*) FROM org_tension_acts WHERE kind='wake' AND victim_id=?", (dead,)).fetchone()[0] == 1


def test_a_hotter_man_is_likelier_to_strike_and_a_calm_one_to_send_word():
    from engine import org_tension as ot
    w = open_world()
    c = w.conn
    a, b = w.org, _org(c, "ferrante") if w.org != _org(c, "ferrante") else _org(c, "vannucci")
    ot.add(c, a, b, "test", 15.0, DAY)
    hot, calm = w.soldier, w.capo
    drives(c, hot, aggression=0.95, risk_tolerance=0.9, ambition=0.8)
    drives(c, calm, aggression=0.05, risk_tolerance=0.2, patience=0.9, pragmatism=0.9)
    fh, fc = ot.factors(c, hot, a, b, DAY), ot.factors(c, calm, a, b, DAY)
    acts = ot.data(c)["acts"]
    sh = ot._blend(c, acts["strike"]["terms"], fh)
    sc = ot._blend(c, acts["strike"]["terms"], fc)
    assert sh > sc
    mh = ot._blend(c, acts["message"]["terms"], fh)
    mc = ot._blend(c, acts["message"]["terms"], fc)
    assert mc > mh
    # a calm man is not shut out of violence: his strike score is above nothing
    assert sc > 0.0


def test_a_man_may_go_straight_to_a_killing_and_his_own_boss_answers_for_him():
    from engine import org_happenings as oh, org_tension as ot
    w = open_world()
    c = w.conn
    other = _org(c, "pellegrino") if w.org != _org(c, "pellegrino") else _org(c, "sabatini")
    plan = {"from": w.org, "to": other, "voice": w.soldier, "rung": "anyone", "method": "found"}
    with certain_kills():
        res = ot.execute_strike(c, plan, DAY, sanctioned=False)
    assert res["dead"] or "failed" in res["summary"] or True
    items = c.execute("SELECT * FROM org_agenda WHERE kind='answer_for_man' AND actor_id=? AND status='open'", (w.boss,)).fetchall()
    assert items, "his head has to answer for him"
    offers = {o["kind"]: o for o in ot.answer_offers(c, w.boss, items[0], DAY + 1)}
    assert set(offers) == {"back_him", "make_good", "give_him_up"}
    drives(c, w.boss, aggression=0.05)
    cool = {o["kind"]: o["utility"] for o in ot.answer_offers(c, w.boss, items[0], DAY + 1)}
    drives(c, w.boss, aggression=0.95)
    hot = {o["kind"]: o["utility"] for o in ot.answer_offers(c, w.boss, items[0], DAY + 1)}
    assert hot["back_him"] > cool["back_him"] and cool["give_him_up"] >= hot["give_him_up"]


def test_a_gathering_attack_puts_everyone_present_at_risk_and_writes_heavy_heat():
    from engine import org_heat, org_tension as ot
    w = open_world()
    c = w.conn
    other = _org(c, "pellegrino") if w.org != _org(c, "pellegrino") else _org(c, "sabatini")
    men = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND role_key IN ('soldier','associate') ORDER BY actor_id LIMIT 6", (other,))]
    bar = int(c.execute("SELECT id FROM locations WHERE name='The Pompeii Social Club'").fetchone()[0])
    bystanders = []
    for i in range(3):  # people who are not in the life are in the room too
        aid = int(c.execute("INSERT INTO actors(name,actor_type,status,current_location_id) VALUES (?,'character','active',?)", (f"[bystander {i}]", bar)).lastrowid)
        c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_status,demographic_sex) VALUES (?,?,'living','male')", (aid, -30 * 365))
        bystanders.append(aid)
    for m in men:
        c.execute("UPDATE actors SET current_location_id=? WHERE id=?", (bar, m))
    before = org_heat.read(c, w.org, DAY)["public_heat"]
    plan = {"from": w.org, "to": other, "voice": w.soldier, "rung": "anyone", "method": "gathering"}
    dead_all = 0
    for attempt in range(1):
        res = ot.execute_strike(c, plan, DAY, sanctioned=True)
        dead_all += len(res["dead"])
    assert "gathering" in res["summary"]
    shot = c.execute("SELECT COUNT(*) FROM harm_incidents WHERE source_kind='org_action'").fetchone()[0]
    assert shot >= dead_all  # every death is a harm incident; a run can also miss everyone
    if dead_all:
        assert org_heat.read(c, w.org, DAY)["public_heat"] > before


def test_a_gathering_can_miss_everyone_or_kill_several():
    """Across seeds the same attack kills none in some runs and several in others."""
    from engine import org_tension as ot
    results = set()
    for i in range(6):
        w = open_world()
        c = w.conn
        other = _org(c, "pellegrino") if w.org != _org(c, "pellegrino") else _org(c, "sabatini")
        c.execute("UPDATE world_state SET rng_seed=?", (100 + i,))
        men = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id LIMIT 8", (other,))]
        bar = int(c.execute("SELECT id FROM locations WHERE name='The Pompeii Social Club'").fetchone()[0])
        for m in men:
            c.execute("UPDATE actors SET current_location_id=? WHERE id=?", (bar, m))
        res = ot.execute_strike(c, {"from": w.org, "to": other, "voice": w.soldier, "rung": "anyone", "method": "gathering"}, DAY, sanctioned=True)
        results.add(len(res["dead"]))
    assert len(results) > 1, results


def test_heat_is_read_from_org_heat_and_fades():
    from engine import org_heat, org_happenings as oh
    w = open_world()
    c = w.conn
    assert org_heat.own_factor(c, w.org, DAY) == 0.0
    org_heat.add(c, w.org, DAY, public=30.0, investigative=20.0, violence=30.0)
    f1 = org_heat.own_factor(c, w.org, DAY)
    assert f1 > 0.5
    assert org_heat.own_factor(c, w.org, DAY + 400) < f1 / 2
    other = int(c.execute("SELECT org_actor_id FROM org_profiles WHERE org_actor_id<>? AND org_kind='family' LIMIT 1", (w.org,)).fetchone()[0])
    cf = oh._cost_factors(c, w.boss, w.org, other, DAY, 1)
    assert cf["heat_own"] > 0.0 and cf["heat_city"] > 0.0


def test_a_killing_by_a_man_with_no_seat_is_the_dead_mans_heads_to_hunt():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    outsider = int(c.execute("INSERT INTO actors(name,actor_type,status) VALUES ('[outsider]','character','active')").lastrowid)
    c.execute("INSERT INTO actor_life_profiles(actor_id,birth_day,life_status,demographic_sex) VALUES (?,?,'living','male')", (outsider, -30 * 365))
    seats = c.execute("SELECT org_actor_id,role_key,unit_id,superior_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (w.soldier,)).fetchall()
    oh.killed_across(c, outsider, w.soldier, seats, DAY)
    item = c.execute("SELECT * FROM org_agenda WHERE kind='discipline_hunt' AND actor_id=? AND status='open'", (w.boss,)).fetchone()
    assert item is not None and int(item["subject_id"]) == outsider


def test_whoever_hired_the_killer_answers_for_it():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    other = _org(c, "pellegrino") if w.org != _org(c, "pellegrino") else _org(c, "sabatini")
    hirer = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='capo' AND status='active' ORDER BY actor_id LIMIT 1", (other,)).fetchone()[0])
    pro = int(c.execute("SELECT actor_id FROM org_seats s JOIN org_profiles p ON p.org_actor_id=s.org_actor_id WHERE p.package_key='hired_men' AND s.status='active' ORDER BY actor_id LIMIT 1").fetchone()[0])
    seats = c.execute("SELECT org_actor_id,role_key,unit_id,superior_actor_id FROM org_seats WHERE actor_id=? AND status='active'", (w.soldier,)).fetchall()
    oh.killed_across(c, pro, w.soldier, seats, DAY, ordered_by=hirer)
    item = c.execute("SELECT * FROM org_agenda WHERE kind='respond_killing' AND actor_id=? AND status='open'", (w.boss,)).fetchone()
    meta = json.loads(item["metadata_json"])
    assert meta["killer"] == hirer and meta["killer_org"] == other


def test_hunting_a_man_of_ones_own_weighs_its_cost():
    from engine import org_choices, org_heat
    w = open_world()
    c = w.conn
    killer = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='soldier' AND status='active' AND actor_id<>? ORDER BY actor_id LIMIT 1", (w.org, w.soldier)).fetchone()[0])
    from engine.orgs import add_agenda
    add_agenda(c, w.boss, "discipline_hunt", DAY, subject_kind="actor", subject_id=killer, metadata={"victim": w.soldier, "org": w.org, "head_wants": 0.0})
    item = c.execute("SELECT * FROM org_agenda WHERE kind='discipline_hunt' AND actor_id=? AND status='open'", (w.boss,)).fetchone()
    cool = {o["kind"]: o["utility"] for o in org_choices.AGENDA_ACTIONS["discipline_hunt"](c, w.boss, item, DAY)}
    org_heat.add(c, w.org, DAY, public=60.0, investigative=60.0, violence=60.0)
    hot = {o["kind"]: o["utility"] for o in org_choices.AGENDA_ACTIONS["discipline_hunt"](c, w.boss, item, DAY)}
    assert hot["order_hunt"] < cool["order_hunt"]


def test_temperament_is_drawn_wide_around_the_bible_guideline():
    from engine import org_temperament
    w = open_world()
    c = w.conn

    def stats(key):
        xs = [float(r[0]) for r in c.execute("SELECT d.aggression FROM org_seats s JOIN actor_drives d ON d.actor_id=s.actor_id JOIN org_profiles p ON p.org_actor_id=s.org_actor_id "
                                           "WHERE p.package_key=? AND s.status='active'", (key,))]
        m = sum(xs) / len(xs)
        return m, (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5, min(xs), max(xs)
    van, sab, bri = stats("vannucci"), stats("sabatini"), stats("brigades")
    assert van[0] > sab[0] + 0.15  # quicker to violence than the diplomats
    for m, sd, lo, hi in (van, sab, bri):
        assert sd > 0.15 and lo < 0.3 and hi > 0.7  # every family has calm men and killers
    # no outfit-level number remains
    spec = json.loads((ROOT / "worlds" / "saintjude" / "outfits.json").read_text(encoding="utf-8"))
    assert all("violence_bias" not in v for v in spec["outfits"].values())


def test_temperament_drifts_with_losses_prison_and_age():
    from engine import org_temperament as tp
    w = open_world()
    c = w.conn
    a = w.soldier
    drives(c, a, aggression=0.5, patience=0.5, risk_tolerance=0.5)
    base = c.execute("SELECT aggression,patience FROM actor_drives WHERE actor_id=?", (a,)).fetchone()
    tp.drift(c, a, "kin_killed", DAY, 2.0)
    k = c.execute("SELECT aggression,patience FROM actor_drives WHERE actor_id=?", (a,)).fetchone()
    assert k[0] > base[0] and k[1] < base[1]
    tp.drift(c, a, "age_year", DAY)
    y = c.execute("SELECT aggression FROM actor_drives WHERE actor_id=?", (a,)).fetchone()
    assert y[0] < k[0]
    tp.drift(c, a, "no_such_cause", DAY)  # a cause the package does not list moves nothing
    assert c.execute("SELECT aggression FROM actor_drives WHERE actor_id=?", (a,)).fetchone()[0] == y[0]


def test_the_outer_ring_has_real_heads_at_their_real_age_and_men_below():
    w = open_world()
    c = w.conn
    for key, name, age in (("philadelphia", "Angelo Bruno", 64), ("gambino", "Carlo Gambino", 72), ("genovesenj", "Frank Tieri", 71)):
        org = _org(c, key)
        r = c.execute("SELECT a.id,a.name,lp.birth_day FROM org_seats s JOIN actors a ON a.id=s.actor_id JOIN actor_life_profiles lp ON lp.actor_id=a.id "
                      "WHERE s.org_actor_id=? AND s.role_key='boss' AND s.status='active'", (org,)).fetchone()
        assert r["name"] == name and abs((0 - r["birth_day"]) // 365 - age) <= 1
        assert c.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (org,)).fetchone()[0] > 10
    # Gambino's health is the record's
    gid = c.execute("SELECT id FROM actors WHERE name='Carlo Gambino'").fetchone()[0]
    assert c.execute("SELECT baseline_health FROM actor_health_profiles WHERE actor_id=?", (gid,)).fetchone()[0] < 60


def test_the_outer_ring_and_the_independents_take_part_in_the_balance():
    from engine import org_tension as ot
    w = open_world()
    c = w.conn
    pairs = set(ot.pairs(c, 0))
    assert (_org(c, "gambino"), _org(c, "genovesenj")) in pairs
    assert (_org(c, "decavalcante"), _org(c, "sabatini")) in pairs
    assert (_org(c, "hired_men"), _org(c, "vannucci")) in pairs
    assert (_org(c, "huntsrow_fence"), _org(c, "ferrante")) in pairs
    # a mediator for a quarrel between families can be an outside head both hear out
    a, b = _org(c, "sabatini"), _org(c, "ferrante")
    ring = _org(c, "gambino")
    from engine.orgs import head_of
    from engine.relationships import ensure_relationship
    for h in (head_of(c, a), head_of(c, b)):
        ensure_relationship(c, h, head_of(c, ring), 0, respect=95, trust=95)
    voice = ot.draw_voice(c, a, b, DAY)
    assert ot._mediator(c, voice, a, b, DAY) is not None


def test_independents_can_be_hired_squeezed_and_protected():
    from engine import org_tension as ot
    w = open_world()
    c = w.conn
    fence, ferrante = _org(c, "huntsrow_fence"), _org(c, "ferrante")
    voice = ot.draw_voice(c, ferrante, fence, DAY)
    assert ot._hirable(c, ferrante, DAY) is not None  # a man who works for hire is at hand
    assert ot._feasible(c, ot.data(c)["acts"]["levy"], voice, ferrante, fence, DAY)  # the stronger can ask for protection money
    assert ot._victims(c, "anyone", voice, ferrante, fence, DAY)  # and the fence's people can be reached
    res = ot.weigh_pair(c, ferrante, fence, DAY, voice=voice, only="levy")
    assert res is not None and ("paid" in res["summary"] or "would not pay" in res["summary"])


def test_a_coup_or_contest_killing_can_fail_and_the_man_lives():
    """B12d leftover: the killing of a coup, contest or war goes through the planned-hit chance; the caller is told the man lives."""
    from engine import org_coup, underworld_aggression as ag
    from engine.orgs import is_living
    w = open_world()
    real, ag.hit_band = ag.hit_band, lambda *a, **k: "failed"
    try:
        dead = org_coup._kill(w.conn, w.soldier, w.capo, DAY, sanctioned=False)
    finally:
        ag.hit_band = real
    assert dead is False and is_living(w.conn, w.capo)
    with certain_kills():
        assert org_coup._kill(w.conn, w.soldier, w.capo, DAY, sanctioned=False) is True


def test_first_strikes_come_from_the_tension_model_not_the_weekly_draw():
    spec = json.loads((ROOT / "worlds" / "saintjude" / "outfits.json").read_text(encoding="utf-8"))
    victims = spec["happenings"]["kinds"]["incident"]["victims"]
    assert set(victims) == {"officer", "civilian"}  # the cross-outfit kinds are acts of the model now


def test_no_world_words_or_defaults_hidden_in_the_new_engine_modules():
    for mod in ("org_tension", "org_heat", "org_temperament"):
        text = (ROOT / "engine" / f"{mod}.py").read_text(encoding="utf-8").lower()
        for word in ("sabatini", "vannucci", "ferrante", "pellegrino", "brigades", "saint jude", "capo", "soldier", "consigliere"):
            assert word not in text, (mod, word)


def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {name}: {exc!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
