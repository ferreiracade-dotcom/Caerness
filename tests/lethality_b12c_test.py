"""Task B12c: lethality of hits, harm, incidents and retaliation is data, with no survival lean and no ceilings in code.

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/lethality_b12c_test.py   (builds a scratch Saint Jude opening)
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world


def _share(conn, p, lethal, n=3000, **kw):
    from engine import underworld_aggression as ag
    rng = random.Random(11)
    c = {"failed": 0, "wounded": 0, "maimed": 0, "killed": 0}
    for _ in range(n):
        c[ag.hit_band(p, rng, lethal, conn, **kw)] += 1
    return {k: v / n for k, v in c.items()}


# ---- 1. planned hits ----

def test_default_config_keeps_the_old_hit_curve():
    """Caerness (no package lethality data) keeps its current figures: the engine default file holds them."""
    from engine import lethality
    cfg = lethality.config(None)
    assert cfg["hit"]["floor"] == 0.3 and cfg["hit"]["exp"] == 1.3 and cfg["hit"]["nonlethal_scale"] == 0.15
    assert cfg["fatal"]["lethal"]["cap"] == 0.82 and cfg["fatal"]["hostile"]["cap"] == 0.22


def test_a_planned_hit_that_lands_kills_at_a_plausible_rate():
    w = open_world()
    s = _share(w.conn, 0.7, True, style="hired_killing")
    landed = 1 - s["failed"]
    assert s["killed"] / landed > 0.82, s
    s_pb = _share(w.conn, 0.9, True, style="hired_killing")
    assert s_pb["killed"] / (1 - s_pb["failed"]) > 0.85, s_pb


def test_a_low_chance_or_a_guarded_target_lowers_the_kill_share():
    w = open_world()
    hi = _share(w.conn, 0.8, True, style="hired_killing")
    lo = _share(w.conn, 0.15, True, style="hired_killing")
    assert lo["killed"] / max(1e-9, 1 - lo["failed"]) < 0.8 * hi["killed"] / (1 - hi["failed"]), (lo, hi)
    g = _share(w.conn, 0.8, True, style="hired_killing", guard=1.0)
    assert g["killed"] / (1 - g["failed"]) < hi["killed"] / (1 - hi["failed"]) - 0.05, (g, hi)


def test_a_beating_is_a_different_intent_from_a_hit():
    w = open_world()
    b = _share(w.conn, 0.9, False)
    k = _share(w.conn, 0.9, True, style="hired_killing")
    assert b["killed"] < 0.2 * k["killed"], (b, k)


def test_the_non_lethal_scale_differs_per_outfit_class():
    from engine import lethality
    w = open_world()
    cfg = lethality.hit_cfg(w.conn, cls="street")
    cfg2 = lethality.hit_cfg(w.conn, cls="durable")
    assert cfg["nonlethal_scale"] != cfg2["nonlethal_scale"]


def test_hit_methods_are_picked_from_the_styles_mix():
    from engine import lethality
    w = open_world()
    rng = random.Random(3)
    picks = {lethality.pick_method(w.conn, "hired_killing", None, rng) for _ in range(200)}
    assert "handgun_point_blank" in picks and None not in picks, picks
    assert lethality.pick_method(None, "hired_killing", None, rng) is None, "no config, no method (Caerness)"


# ---- 2. harm ----

def _victim(conn, resilience=70.0):
    from engine.health import ensure_health_profile
    from engine.household_life import set_life_profile
    aid = int(conn.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')", (f"[B12c] v{random.random()}",)).lastrowid)
    set_life_profile(conn, aid, birth_day=-30 * 365, demographic_sex="male", family_formation_eligible=True)
    ensure_health_profile(conn, aid, baseline_health=80)
    return aid


def _fatal_share(conn, intent, method, severity, n=400, base=1000):
    from engine.harm import record_harm
    dead = 0
    for i in range(n):
        v = _victim(conn)
        r = record_harm(conn, v, source_kind="b12c_probe", source_ref_id=base + i, severity=severity, intent_class=intent, method=method)
        dead += int(r["outcome"] == "fatal")
    return dead / n


def test_the_ceilings_are_gone_for_saint_jude():
    w = open_world()
    assert _fatal_share(w.conn, "lethal", None, 100, n=300) > 0.84, "a severity 100 lethal blow is no longer capped at 0.82"
    assert _fatal_share(w.conn, "hostile", "blade", 100, n=300, base=5000) > 0.22, "the hostile 0.22 ceiling is gone"


def test_methods_have_their_own_lethality():
    w = open_world()
    shares = {m: _fatal_share(w.conn, "hostile", m, 60, n=300, base=10000 + 1000 * i)
              for i, m in enumerate(("fists", "blunt", "blade", "handgun_range", "handgun_point_blank", "execution"))}
    order = ["fists", "blunt", "blade", "handgun_range", "handgun_point_blank", "execution"]
    for a, b in zip(order, order[1:]):
        assert shares[a] <= shares[b] + 0.04, shares
    assert shares["fists"] < 0.05 and shares["handgun_point_blank"] > 0.6 and shares["execution"] > 0.85, shares


def test_a_champions_duel_can_kill():
    from engine.harm import record_harm
    w = open_world()
    dead = 0
    for i in range(300):
        v = _victim(w.conn)
        r = record_harm(w.conn, v, source_kind="b12c_duel", source_ref_id=i, severity=78, intent_class="hostile", method="blade")
        dead += int(r["outcome"] == "fatal")
    assert dead / 300 > 0.05, dead


def test_serious_untreated_wounds_can_kill_later():
    from engine.harm import record_harm
    w = open_world()
    v = _victim(w.conn)
    r = record_harm(w.conn, v, source_kind="b12c_wound", source_ref_id=1, severity=70, intent_class="hostile", method="handgun_range",
                    outcome_override="persistent")
    cond = w.conn.execute("SELECT fatality_pressure FROM health_conditions WHERE id=?", (r["condition_id"],)).fetchone()
    assert float(cond[0]) > 0.0, "a gunshot wound at severity ~60 carries death pressure (it was 0 below 72)"


def test_caerness_defaults_are_unchanged():
    from engine import harm
    from engine.harm import _fatal_probability
    assert abs(_fatal_probability(None, "lethal", 100.0) - 0.82) < 1e-9
    assert abs(_fatal_probability(None, "hostile", 100.0) - 0.22) < 1e-9
    assert _fatal_probability(None, "hostile", 70.0) == 0.0


# ---- 3. weekly incidents ----

def test_an_incident_has_a_severity_tail_and_a_method_mix():
    from engine import lethality
    w = open_world()
    rng = random.Random(5)
    rolls = [lethality.incident_roll(w.conn, "sabatini", 10.0, rng) for _ in range(4000)]
    tail = [r for r in rolls if r[2]]
    assert 0.03 < len(tail) / len(rolls) < 0.10, len(tail) / len(rolls)
    assert all(r[0] >= 40.0 for r in tail) and min(r[0] for r in rolls if not r[2]) == 10.0
    assert {r[1] for r in tail} >= {"blade", "handgun_range"}, {r[1] for r in tail}
    assert {r[1] for r in rolls if not r[2]} >= {"fists", "blunt"}
    assert lethality.incident_roll(None, "sabatini", 10.0, rng) == (10.0, None, False), "no data, no draw"


def test_a_weekly_incident_can_kill_and_can_hurt_a_bystander():
    from engine import org_happenings as oh
    w = open_world()
    c = w.conn
    a = int(c.execute("SELECT actor_id FROM org_seats WHERE role_key='associate' AND superior_actor_id=? AND status='active' ORDER BY actor_id LIMIT 1", (w.soldier,)).fetchone()[0])
    dead = hurt = by = 0
    for d in range(DAY, DAY + 500):
        r = oh.happen(c, a, "incident", d, victim_kind="civilian")
        if not r or r.get("skipped"):
            continue
        row = c.execute("SELECT outcome FROM harm_incidents WHERE source_kind='org_incident' AND source_ref_id=?", (r["incident_id"],)).fetchone()
        dead += int(row[0] == "fatal")
        hurt += 1
        by += c.execute("SELECT COUNT(*) FROM harm_incidents WHERE source_kind='org_incident_bystander' AND source_ref_id=?", (r["incident_id"],)).fetchone()[0]
        assert "harm" in r, "deaths and injuries are reported with the happening"
    assert hurt > 300 and dead >= 1, (hurt, dead)
    assert by >= 1, "a shot sometimes reaches someone else"


# ---- 4. a killing inside or across outfits; retaliation ----

def test_an_internal_killing_stays_certain_unless_the_package_gives_it_a_landing_chance():
    from engine.outfit_choices import kill
    w = open_world()
    c = w.conn
    for i in range(40):
        v = _victim(c)
        kill(c, w.soldier, v, DAY + i, sanctioned=True)
        assert c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (v,)).fetchone()[0] == "deceased"
    dead = alive = 0
    for i in range(80):
        v = _victim(c)
        kill(c, w.soldier, v, DAY + 100 + i, sanctioned=True, land=0.96)
        st = c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (v,)).fetchone()[0]
        dead += st == "deceased"
        alive += st != "deceased"
    assert alive >= 1, "a hit can be botched"
    assert dead / 80 > 0.75, (dead, alive)


def _killing(w, sanctioned=True, role="soldier"):
    from engine import org_choices
    from engine.outfit_choices import kill
    c = w.conn
    other = int(c.execute("""SELECT p.org_actor_id FROM org_profiles p WHERE p.org_actor_id<>? AND p.org_kind=(SELECT org_kind FROM org_profiles WHERE org_actor_id=?)
                             ORDER BY p.org_actor_id LIMIT 1""", (w.org, w.org)).fetchone()[0])
    vic = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key=? AND status='active' ORDER BY actor_id LIMIT 1", (other, role)).fetchone()[0])
    vhead = int(c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND role_key='boss'", (other,)).fetchone()[0])
    # make the hit land: the question here is what the head does, not whether the killer is a poor shot
    from engine import underworld_aggression as ag
    real, ag.hit_band = ag.hit_band, lambda *a, **k: "killed"
    try:
        kill(c, w.soldier, vic, DAY, sanctioned=sanctioned)
    finally:
        ag.hit_band = real
    item = c.execute("SELECT * FROM org_agenda WHERE kind='respond_killing' AND actor_id=?", (vhead,)).fetchone()
    return item, vhead, vic, other


def test_an_unsanctioned_killing_weighs_toward_retaliation():
    from engine import org_choices
    a, b = open_world(), open_world()
    ia, ha, _, _ = _killing(a, sanctioned=True)
    ib, hb, _, _ = _killing(b, sanctioned=False)
    ua = {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](a.conn, ha, ia, DAY + 2)}
    ub = {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](b.conn, hb, ib, DAY + 2)}
    assert ub["retaliate"]["utility"] > ua["retaliate"]["utility"]


def test_kin_of_the_dead_man_weigh_toward_retaliation():
    from engine import org_choices
    a, b = open_world(), open_world()
    for w in (a, b):
        pass
    ia, ha, va, _ = _killing(a)
    ib, hb, vb, _ = _killing(b)
    # b: the dead man had a living brother (kin links survive his death)
    bro = _victim(b.conn)
    b.conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,legal_status,started_day) VALUES (?,?,?,?,0)", (min(bro, vb), max(bro, vb), "sibling", "recognized"))
    ua = {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](a.conn, ha, ia, DAY + 2)}
    ub = {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](b.conn, hb, ib, DAY + 2)}
    assert ub["retaliate"]["utility"] > ua["retaliate"]["utility"]


def _reply_size(role):
    from engine import org_choices
    w = open_world()
    item, vhead, vic, other = _killing(w, role=role)
    offers = {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](w.conn, vhead, item, DAY + 2)}
    org_choices.execute(w.conn, vhead, "retaliate", offers["retaliate"]["payload"], DAY + 2)
    return w.conn.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='hit' AND subject_id=? AND status='open'", (w.soldier,)).fetchone()[0]


def test_the_reply_is_a_team_and_scales_with_the_victims_rank():
    low, high = _reply_size("soldier"), _reply_size("capo")
    assert low >= 1 and high >= 2 and high > low, (low, high)


def test_a_retaliation_can_fail():
    from engine.outfit_choices import kill
    w = open_world()
    c = w.conn
    dead = alive = 0
    for i in range(80):
        v = _victim(c)
        kill(c, w.soldier, v, DAY + i, sanctioned=True, retaliation=True)
        st = c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (v,)).fetchone()[0]
        dead += st == "deceased"
        alive += st != "deceased"
    assert alive / 80 > 0.15, (dead, alive)


def test_retaliation_has_no_cap():
    """The reply, when it lands, is itself a killing across outfits: the killer's own head answers it in turn, and nothing
    but the motives stops the chain."""
    from engine import org_choices, underworld_aggression as ag
    w = open_world()
    c = w.conn
    item, vhead, vic, other = _killing(w)
    offers = {o["kind"]: o for o in org_choices.AGENDA_ACTIONS["respond_killing"](c, vhead, item, DAY + 2)}
    org_choices.execute(c, vhead, "retaliate", offers["retaliate"]["payload"], DAY + 2)
    first = c.execute("SELECT * FROM org_agenda WHERE kind='hit' AND subject_id=? AND status='open' ORDER BY id", (w.soldier,)).fetchone()
    assert first is not None
    assert not c.execute("SELECT 1 FROM org_agenda WHERE kind='respond_killing' AND actor_id=?", (w.boss,)).fetchone()
    real, ag.hit_band = ag.hit_band, lambda *a, **k: "killed"
    try:
        hit = org_choices.AGENDA_ACTIONS["hit"](c, int(first["actor_id"]), first, DAY + 3)[0]
        org_choices.execute(c, int(first["actor_id"]), "hit", hit["payload"], DAY + 3)
    finally:
        ag.hit_band = real
    assert c.execute("SELECT 1 FROM org_agenda WHERE kind='respond_killing' AND actor_id=? AND status='open'", (w.boss,)).fetchone(), "the chain goes on"


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
