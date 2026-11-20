"""Task B12b: appointments, the head's heir, the succession contest, coups, plots, civil war and a split (generic layers
`org_succession` and `org_coup`, driven by the Saint Jude package data; the generic firm test runs on the minimal test package).

Run: CAERNESS_DB_PATH=<scratch db> PYTHONPATH=. python tests/org_succession_test.py   (builds scratch Saint Jude openings)
"""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, drives, forced_roll, open_world, rel


@contextlib.contextmanager
def rolls(fn):
    """fn(stream) -> the draw for that stream (0..1); every draw in the weighed decisions goes through it."""
    from engine import org_motives
    old = org_motives._roll
    org_motives._roll = lambda conn, actor, day, stream: fn(str(stream))
    try:
        yield
    finally:
        org_motives._roll = old


def _quiet(stream):
    return 0.99


class Cast:
    pass


def cast(w, trial_seed: int | None = None) -> Cast:
    from engine import orgs
    c = w.conn
    k = Cast()
    k.conn, k.org, k.boss = c, w.org, w.boss
    k.under = int(orgs.members(c, w.org, "underboss")[0]["actor_id"])
    k.cons = int(orgs.members(c, w.org, "consigliere")[0]["actor_id"])
    k.capos = [int(r["actor_id"]) for r in orgs.members(c, w.org, "capo")]
    k.day = int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) + 5
    if trial_seed is not None:
        c.execute("UPDATE world_state SET rng_seed=?", (trial_seed,))
    return k


def _set_all(c, backers, target, **cols):
    for b in backers:
        if b != target:
            rel(c, b, target, **cols)


def _rows(c, kind, status=None):
    q, a = "SELECT * FROM org_agenda WHERE kind=?", [kind]
    if status:
        q += " AND status=?"
        a.append(status)
    return c.execute(q + " ORDER BY id", a).fetchall()


def _die(c, a):
    c.execute("UPDATE actors SET status='dead' WHERE id=?", (a,))


def _slay(c, a):
    """Dead and his seats say so (what a killing does), for the tests that start from the dead head directly."""
    _die(c, a)
    c.execute("UPDATE org_seats SET status='dead' WHERE actor_id=?", (a,))


def _run_weeks(k, n, start=None):
    from engine import org_lifecycle
    d = k.day if start is None else start
    for i in range(n):
        org_lifecycle.process_due(k.conn, d + 7 * i)
    return d + 7 * n


def _backers(k):
    from engine import org_succession
    return org_succession.backers(k.conn, k.org)


def _contest_done(c):
    rows = _rows(c, "contest")
    return rows and all(r["status"] == "resolved" for r in rows)


def _meta(row):
    return json.loads(row["metadata_json"] or "{}")


# ---- appointments ----

def test_an_appointment_can_go_to_a_favourite_over_the_most_senior_man():
    """The head weighs each man of the vacant unit (trust, kin, favours, money, merit, fear); a favourite he trusts and owes can
    outweigh the senior man, and the choice is on his agenda so it can be proposed otherwise."""
    from engine import orgs, outfit_choices
    from engine.org_succession import appointment_offers
    w = open_world()
    k = cast(w)
    c = k.conn
    unit = w.unit
    leader = int(c.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (unit,)).fetchone()[0])
    men = [int(r["actor_id"]) for r in orgs.members(c, w.org, "soldier") if r["unit_id"] == unit]
    assert len(men) >= 2
    senior, fav = men[0], men[1]
    c.execute("UPDATE org_seats SET standing=0.95, inducted_day=? WHERE actor_id=?", (-9000, senior))
    c.execute("UPDATE org_seats SET standing=0.15, inducted_day=? WHERE actor_id=?", (k.day - 400, fav))
    for m in men:
        if m not in (senior, fav):
            c.execute("UPDATE org_seats SET standing=0.1 WHERE actor_id=?", (m,))
    rel(c, k.boss, senior, trust=0, loyalty=0, obligation=0, fear=0, resentment=20)
    rel(c, k.boss, fav, trust=95, loyalty=90, obligation=70, fear=0, resentment=0)
    for m in men:
        if m not in (senior, fav):
            rel(c, k.boss, m, trust=0, loyalty=0, obligation=0)
    drives(c, k.boss, pragmatism=0.5, loyalty=0.8)
    outfit_choices.kill(c, k.boss, leader, k.day, sanctioned=True)
    item = _rows(c, "fill_unit_leader_seat", "open")[0]
    assert item["actor_id"] == k.boss
    offers = {o["target_actor_id"]: o for o in appointment_offers(c, k.boss, item, k.day + 3)}
    assert set(men) <= set(offers)
    assert offers[fav]["utility"] > offers[senior]["utility"], (offers[fav]["utility"], offers[senior]["utility"])
    # the head's own choice is carried out, and the man passed over resents him
    before = c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (senior, k.boss)).fetchone()
    res = outfit_choices.execute_fill_unit_leader_seat(c, k.boss, "fill_unit_leader_seat", {"unit_id": unit, "candidate": fav}, k.day + 3)
    assert c.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (unit,)).fetchone()[0] == fav, res
    assert orgs.seat_of(c, fav, w.org)["role_key"] == "capo"
    after = c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (senior, k.boss)).fetchone()
    assert after is not None and (before is None or after[0] > before[0])


def test_a_leaders_nomination_for_the_books_weighs_every_man_of_his_unit():
    from engine import org_membership, orgs
    w = open_world()
    k = cast(w)
    c = k.conn
    capo = int(c.execute("SELECT leader_actor_id FROM org_units WHERE id=?", (w.unit,)).fetchone()[0])
    deps = org_membership.eligible(c, w.org, w.unit, k.day)
    assert len(deps) >= 2
    a, b = deps[0], deps[1]
    rel(c, capo, a, trust=0, loyalty=0, obligation=0)
    rel(c, capo, b, trust=95, loyalty=95, obligation=80)
    for x in deps[2:]:
        rel(c, capo, x, trust=0, loyalty=0, obligation=0)
    item = {"id": 1, "metadata_json": json.dumps({"org": w.org}), "subject_id": w.org}
    offers = {o["target_actor_id"]: o for o in org_membership.proposal_offers(c, capo, item, k.day)}
    assert set(deps) <= set(offers) and len(offers) >= 2
    assert offers[b]["utility"] > offers[a]["utility"]


# ---- the heir ----

def test_a_head_forms_an_heir_over_time_and_can_show_it():
    from engine import org_succession as su
    w = open_world()
    k = cast(w)
    c = k.conn
    assert su.heir_row(c, k.boss) is None
    with rolls(lambda s: 0.0 if s in ("heir_form", "heir_show") else 0.99):
        su._heirs(c, k.day)
    row = su.heir_row(c, k.boss)
    assert row is not None
    heir = int(row["subject_id"])
    assert su.active_seat(c, heir, k.org) is not None
    assert _meta(row)["shown"] is True
    assert su.heir_of(c, k.org, k.boss, shown_only=True) == heir
    # shown: the leaders' trust in him moved
    assert c.execute("SELECT COUNT(*) FROM relationships WHERE actor_b_id=? AND updated_day=?", (heir, k.day)).fetchone()[0] > 0


def test_a_head_who_names_nobody_leaves_the_contest_open():
    from engine import design, org_succession as su
    w = open_world()
    k = cast(w)
    c = k.conn
    design.set_figure(c, "heir_min_score", 0.99, cause="test: no one is worth naming", exception=True)
    with rolls(lambda s: 0.0 if s in ("heir_form",) else 0.99):
        su._heirs(c, k.day)
    assert su.heir_row(c, k.boss) is None
    _die(c, k.boss)
    _run_weeks(k, 1)
    cont = _rows(c, "contest")[0]
    assert _meta(cont)["heir"] is None and cont["status"] == "open"


def test_the_named_heir_usually_wins_and_the_contest_takes_weeks():
    from engine import org_succession as su
    wins = 0
    trials = 10
    weeks_seen = []
    for t in range(trials):
        w = open_world()
        k = cast(w, 1000 + t)
        c = k.conn
        su.put_row(c, k.boss, "heir", k.day, k.under, {"org": k.org, "shown": True, "formed": k.day})
        for b in _backers(k):
            if b != k.under:
                rel(c, b, k.under, trust=40, loyalty=40)
        _die(c, k.boss)
        d = _run_weeks(k, 1)
        assert not _contest_done(c), "the contest cannot be over the same week the head died"
        assert su.acting_marker(c, k.org) is not None
        for _ in range(30):
            d = _run_weeks(k, 1, d)
            if _contest_done(c):
                break
        assert _contest_done(c)
        m = _meta(_rows(c, "contest")[0])
        weeks_seen.append(m["weeks"])
        wins += 1 if m.get("winner") == k.under else 0
        assert m["weeks"] >= 2
        from engine import orgs
        assert orgs.head_of(c, k.org) == m["winner"]
    assert wins >= 7, (wins, trials)
    assert min(weeks_seen) >= 2


def test_an_unaccepted_heir_loses_and_is_challenged():
    """The leaders do not trust the named heir (resentment, no trust) and back a rival they fear and owe: the rival wins, the
    heir having been shown. A rival who was passed over also plots against the shown heir while the head lives."""
    from engine import orgs, org_succession as su, org_coup
    lost = 0
    trials = 8
    for t in range(trials):
        w = open_world()
        k = cast(w, 2000 + t)
        c = k.conn
        su.put_row(c, k.boss, "heir", k.day, k.cons, {"org": k.org, "shown": True, "formed": k.day})
        rival = k.under
        for b in _backers(k):
            if b != k.cons:
                rel(c, b, k.cons, trust=-60, loyalty=-40, resentment=80, fear=0)
            if b != rival:
                rel(c, b, rival, trust=80, loyalty=70, obligation=60, fear=50, resentment=0)
        _die(c, k.boss)
        d = _run_weeks(k, 1)
        for _ in range(30):
            d = _run_weeks(k, 1, d)
            if _contest_done(c):
                break
        m = _meta(_rows(c, "contest")[0])
        assert m["heir"] == k.cons and m["heir_shown"]
        lost += 1 if m.get("winner") not in (None, k.cons) else 0
    assert lost >= 7, (lost, trials)
    # before the death: a man passed over plots against the shown heir
    w = open_world()
    k = cast(w)
    c = k.conn
    su.put_row(c, k.boss, "heir", k.day, k.cons, {"org": k.org, "shown": True, "formed": k.day})
    plotter = k.under
    c.execute("UPDATE actor_drives SET ambition=0.1")
    c.execute("UPDATE org_seats SET standing=0.9 WHERE actor_id=?", (plotter,))
    drives(c, plotter, ambition=0.95, risk_tolerance=0.9)
    rel(c, plotter, k.boss, loyalty=100, resentment=0)  # loyal to the head, bitter at the heir
    rel(c, plotter, k.cons, resentment=90, loyalty=0, trust=-30)
    with rolls(lambda s: 0.0 if s.startswith("plot:") else 0.99):
        org_coup._plots(c, k.day)
    rows = [r for r in _rows(c, "plot", "open") if r["actor_id"] == plotter]
    assert rows and rows[0]["subject_id"] == k.cons, [dict(r) for r in _rows(c, "plot")]


# ---- plots and coups ----

def test_an_insider_with_backing_takes_over_after_killing_the_head():
    """He set it up beforehand (a plot that the leaders joined), killed the head, and holds the seat; the loyalists accept him."""
    from engine import orgs, outfit_choices, org_succession as su, org_coup
    w = open_world()
    k = cast(w)
    c = k.conn
    killer = k.under
    pid = org_coup.start_plot(c, k.org, killer, k.boss, k.day)
    joined = [b for b in _backers(k) if b != killer]
    row = _rows(c, "plot", "open")[0]
    su.save_meta(c, int(row["id"]), {**_meta(row), "joined": joined, "sounded": joined})
    _set_all(c, joined, killer, trust=70, loyalty=60)
    outfit_choices.kill(c, killer, k.boss, k.day, sanctioned=False)
    with rolls(lambda s: 0.0 if s.startswith("loyalist") else 0.99):  # each loyalist (none are left outside the plot) takes the first option
        _run_weeks(k, 1)
    assert orgs.head_of(c, k.org) == killer
    cont = _rows(c, "contest")[0]
    m = _meta(cont)
    assert m["outcome"] == "coup" and m["cause"] == "killed_inside" and m["winner"] == killer
    assert su.acting_marker(c, k.org) is None
    assert all(r["status"] == "resolved" for r in _rows(c, "plot"))
    # everyone who answered to the dead head answers to him
    assert not [r for r in orgs.members(c, k.org) if r["superior_actor_id"] == k.boss]


def test_an_insider_without_backing_starts_a_civil_war():
    from engine import orgs, outfit_choices, org_succession as su
    w = open_world()
    k = cast(w)
    c = k.conn
    killer = k.under
    bs = [b for b in _backers(k) if b != killer]
    _set_all(c, bs, killer, trust=-80, loyalty=-80, resentment=90, fear=0)
    for b in bs:
        if b != k.cons:
            rel(c, b, k.cons, trust=70, loyalty=60)
    outfit_choices.kill(c, killer, k.boss, k.day, sanctioned=False)
    with rolls(lambda s: 0.0 if s.startswith("unbacked") else 0.99):
        _run_weeks(k, 1)
    cont = _rows(c, "contest")[0]
    m = _meta(cont)
    assert m["outcome"] == "civil_war" and m["cause"] == "killed_inside"
    war = _rows(c, "civil_war", "open")
    assert len(war) == 1
    f = _meta(war[0])["factions"]
    assert len(f) == 2 and f[0]["leader"] == killer and f[1]["leader"] != killer
    assert orgs.head_of(c, k.org) is not None  # someone holds the seat meanwhile


def test_loyalists_can_kill_an_unbacked_killer_quickly():
    from engine import orgs, outfit_choices
    w = open_world()
    k = cast(w)
    c = k.conn
    killer = k.under
    bs = [b for b in _backers(k) if b != killer]
    _set_all(c, bs, killer, trust=-80, loyalty=-80, resentment=90, fear=0)
    for b in bs:
        drives(c, b, aggression=0.9)
    outfit_choices.kill(c, killer, k.boss, k.day, sanctioned=False)
    with rolls(lambda s: 0.5 if s.startswith("unbacked") else 0.99):
        _run_weeks(k, 1)
    # the killer is dead and a contest runs on without him
    assert not orgs.is_living(c, killer)
    m = _meta(_rows(c, "contest")[0])
    assert m.get("avenged_by") is not None


def test_a_plot_against_a_living_head_is_sounded_and_struck():
    """Ambition before any vacancy: an ambitious, passed-over man sounds out the backers one by one, and with enough of them
    behind him strikes; the coup follows at once."""
    from engine import orgs, org_coup
    w = open_world()
    k = cast(w)
    c = k.conn
    plotter = k.under
    c.execute("UPDATE actor_drives SET ambition=0.1")
    c.execute("UPDATE org_seats SET standing=0.9 WHERE actor_id=?", (plotter,))
    drives(c, plotter, ambition=0.95, risk_tolerance=0.9, aggression=0.9)
    rel(c, plotter, k.boss, resentment=80, loyalty=0, trust=0)
    bs = [b for b in _backers(k) if b != plotter]
    for b in bs:
        rel(c, b, plotter, trust=90, loyalty=80, fear=60, obligation=60)
        rel(c, b, k.boss, loyalty=0, trust=0)
        drives(c, b, ambition=0.9, loyalty=0.1)
        c.execute("UPDATE org_seats SET reliability=0.1 WHERE actor_id=?", (b,))

    def fn(s):
        if s.startswith("plot:") or s.startswith("strike:") or s.startswith("soundweek:"):
            return 0.0
        if s.startswith("leak:"):
            return 0.99
        if s.startswith("sound:"):
            return 0.0  # join
        if s.startswith("loyalist"):
            return 0.0
        return 0.5
    with rolls(fn):
        for i in range(30):
            out = org_coup._plots(c, k.day + 7 * i)
            if out["plots_struck"]:
                break
    assert not orgs.is_living(c, k.boss)
    assert orgs.head_of(c, k.org) == plotter
    plot = [r for r in _rows(c, "plot") if r["actor_id"] == plotter][0]
    assert _meta(plot)["joined"] and _meta(plot).get("struck")


def test_a_plot_found_is_the_heads_to_answer():
    from engine import orgs, org_coup
    w = open_world()
    k = cast(w)
    c = k.conn
    plotter = k.capos[0]
    org_coup.start_plot(c, k.org, plotter, k.boss, k.day)
    row = _rows(c, "plot", "open")[0]
    org_coup._found(c, k.org, row, _meta(row), "betrayed", k.day)
    item = _rows(c, "plot_found", "open")[0]
    assert item["actor_id"] == k.boss and item["subject_id"] == plotter
    offers = org_coup.plot_found_offers(c, k.boss, item, k.day)
    assert {o["kind"] for o in offers} == {"plot_kill", "plot_exile", "plot_pardon"}
    org_coup.execute_plot_exile(c, k.boss, "plot_exile", {"org": k.org, "holder": plotter, "agenda_id": item["id"]}, k.day)
    assert orgs.seat_of(c, plotter, k.org)["status"] == "out"


# ---- an outsider ----

def test_an_outsider_killing_the_head_starts_a_war_and_the_contest():
    from engine import orgs, outfit_choices
    w = open_world()
    k = cast(w)
    c = k.conn
    other = int(c.execute("SELECT org_actor_id FROM org_profiles WHERE org_actor_id<>? AND package_key IN ('pellegrino','sabatini','ferrante','vannucci') ORDER BY org_actor_id", (k.org,)).fetchone()[0])
    killer = orgs.head_of(c, other)
    outfit_choices.kill(c, killer, k.boss, k.day, sanctioned=False)
    _run_weeks(k, 1)
    cont = _rows(c, "contest", "open")
    assert cont and _meta(cont[0])["cause"] == "killed_outside" and _meta(cont[0])["war"] is True
    acting = orgs.head_of(c, k.org)
    assert acting is not None
    resp = [r for r in _rows(c, "respond_killing", "open") if r["actor_id"] == acting]
    assert resp and _meta(resp[0])["killer"] == killer
    assert c.execute("SELECT COUNT(*) FROM org_incidents WHERE kind='killing' AND raised_to_org_actor_id=?", (k.org,)).fetchone()[0] >= 1


def test_a_wartime_contest_weighs_muscle():
    from engine import org_succession as su
    w = open_world()
    k = cast(w)
    c = k.conn
    blk = su.block(c, k.org, "contest")
    cands = su.candidates(c, k.org, exclude=(k.boss,))
    a, b = k.under, k.capos[0]
    ctx_peace = {"customary": cands, "war": False}
    ctx_war = {"customary": cands, "war": True}
    gain = [su.weigh(c, k.org, k.cons, x, k.day, blk, ctx_war) - su.weigh(c, k.org, k.cons, x, k.day, blk, ctx_peace) for x in (a, b)]
    assert all(g >= 0 for g in gain) and max(gain) > 0


# ---- civil war and a split ----

def _war(k, size_a=None):
    from engine import org_coup
    c = k.conn
    a, b = k.under, k.cons
    bs = [x for x in _backers(k) if x not in (a, b)]
    half = len(bs) // 2 if size_a is None else size_a
    for i, x in enumerate(bs):
        win, lose = (a, b) if i < half else (b, a)
        rel(c, x, win, trust=90, loyalty=90)
        rel(c, x, lose, trust=-90, loyalty=-90, resentment=60)
    org_coup.start_civil_war(c, k.org, [a, b], k.day, cause="test")
    return _rows(c, "civil_war", "open")[0], a, b


def test_a_civil_war_ends_in_a_win_and_the_losers_are_dealt_with():
    from engine import orgs, org_coup
    w = open_world()
    k = cast(w)
    c = k.conn
    _slay(c, k.boss)
    row, a, b = _war(k, size_a=999)  # everyone with one side
    side = org_coup._factions(c, k.org, _meta(row))
    assert sum(1 for i in side.values() if i == 0) > sum(1 for i in side.values() if i == 1)
    with rolls(lambda s: 0.99):
        out = None
        for i in range(1, 12):
            out = org_coup.tick_war(c, _rows(c, "civil_war")[0], k.day + 7 * i) if _rows(c, "civil_war", "open") else out
            if out:
                break
    done = _meta(_rows(c, "civil_war")[0])
    assert done["how"] == "win" and orgs.head_of(c, k.org) == a
    assert "dealt" in done and sum(done["dealt"].values()) >= 0


def test_a_civil_war_can_end_in_a_settlement():
    from engine import orgs, org_coup
    w = open_world()
    k = cast(w)
    c = k.conn
    _slay(c, k.boss)
    row, a, b = _war(k)
    with rolls(lambda s: 0.0 if s.startswith("settle:") else 0.99):
        out = None
        for i in range(2, 14):
            if not _rows(c, "civil_war", "open"):
                break
            out = org_coup.tick_war(c, _rows(c, "civil_war", "open")[0], k.day + 7 * i)
    assert _meta(_rows(c, "civil_war")[0])["how"] == "settle"
    assert orgs.head_of(c, k.org) in (a, b)


def test_a_civil_war_can_end_in_a_split_that_creates_a_working_outfit():
    from engine import orgs, org_coup, org_membership
    from engine.simulation import advance_connection
    w = open_world()
    k = cast(w)
    c = k.conn
    _slay(c, k.boss)
    row, a, b = _war(k)
    before = c.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (k.org,)).fetchone()[0]
    with rolls(lambda s: 0.0 if s.startswith("split:") else 0.99):
        for i in range(2, 14):
            if not _rows(c, "civil_war", "open"):
                break
            org_coup.tick_war(c, _rows(c, "civil_war", "open")[0], k.day + 7 * i)
    meta = _meta(_rows(c, "civil_war")[0])
    assert meta["how"] == "split" and meta.get("new_org")
    new = int(meta["new_org"])
    prof = c.execute("SELECT * FROM org_profiles WHERE org_actor_id=?", (new,)).fetchone()
    assert prof["org_kind"] == c.execute("SELECT org_kind FROM org_profiles WHERE org_actor_id=?", (k.org,)).fetchone()[0]
    head = orgs.head_of(c, new)
    assert head is not None and head != orgs.head_of(c, k.org)
    men = c.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (new,)).fetchone()[0]
    left = c.execute("SELECT COUNT(*) FROM org_seats WHERE org_actor_id=? AND status='active'", (k.org,)).fetchone()[0]
    assert men >= 4 and men + left >= before - 2, (men, left, before)
    assert c.execute("SELECT COUNT(*) FROM org_units WHERE org_actor_id=?", (new,)).fetchone()[0] >= 1
    lines = c.execute("SELECT COUNT(*) FROM org_lines l JOIN org_holdings h ON h.id=l.holding_id WHERE h.org_actor_id=? AND l.status='active'", (new,)).fetchone()[0]
    assert lines >= 1
    assert org_membership._spec(c, new) is not None  # the books, replacements and discipline run on it
    assert c.execute("SELECT COUNT(*) FROM institution_memberships WHERE institution_actor_id=? AND status='active'", (new,)).fetchone()[0] >= men - 1
    advance_connection(c, 70)  # the new outfit lives: the layers run on it without a fault and money moves through its lines
    assert c.execute("SELECT COUNT(*) FROM org_money WHERE org_actor_id=? AND day>?", (new, k.day)).fetchone()[0] > 0


# ---- the held head, the generic fixture, the data ----

def test_a_held_head_returns_to_his_seat_while_the_contest_runs():
    from engine import orgs, org_lifecycle
    w = open_world()
    k = cast(w)
    c = k.conn
    c.execute("INSERT INTO custody(actor_id,kind,charge,since_day,until_day) VALUES (?,'held','test',?,NULL)", (k.boss, k.day - 1))
    c.execute("UPDATE org_seats SET status='held', left_day=? WHERE actor_id=? AND org_actor_id=?", (k.day, k.boss, k.org))
    org_lifecycle.process_due(c, k.day)
    assert _rows(c, "contest", "open") and orgs.head_of(c, k.org) != k.boss
    c.execute("UPDATE custody SET kind='released' WHERE actor_id=?", (k.boss,))
    org_lifecycle.process_due(c, k.day + 7)
    assert orgs.head_of(c, k.org) == k.boss and not _rows(c, "contest", "open")
    assert orgs.seat_of(c, k.boss, k.org)["role_key"] == "boss"


def test_the_contest_runs_on_the_generic_firm_with_no_sphere_word():
    import os
    saved = {k: os.environ.get(k) for k in ("CAERNESS_DB_PATH", "CAERNESS_WORLDS_DIR", "CAERNESS_WORLD_PACKAGE")}
    try:
        _generic_firm()
    finally:
        for k, val in saved.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val


def _generic_firm():
    from engine import org_lifecycle, orgs
    from tests import org_core_fixture as fx
    f = fx.build()
    conn = f.conn
    rules = orgs.kind_rules(conn, f.firm)
    rules["lifecycle"] = {**rules["lifecycle"], "contest": {
        "customary": {"manager": 1.0}, "backer_roles": [], "stand_week": 1.0, "min_weeks": 1, "agree_share": 0.5, "agree_margin": 0.0, "max_weeks": 8,
        "weights": {"own": 1.0, "trust": 0.5}, "pick_temp": 0.1}}
    fx.kill(conn, f.chair)
    org_lifecycle.process_due(conn, 7)
    assert orgs.head_of(conn, f.firm) in f.managers  # an acting chair holds the seat meanwhile
    cont = conn.execute("SELECT * FROM org_agenda WHERE kind='contest'").fetchone()
    assert cont["status"] == "open"
    for i in range(2, 8):
        org_lifecycle.process_due(conn, 7 * i)
        if conn.execute("SELECT status FROM org_agenda WHERE kind='contest'").fetchone()[0] == "resolved":
            break
    meta = json.loads(conn.execute("SELECT metadata_json FROM org_agenda WHERE kind='contest'").fetchone()[0])
    assert meta["winner"] in f.managers and meta["weeks"] >= 1
    assert orgs.head_of(conn, f.firm) == meta["winner"]
    assert [m for m in f.managers if m != meta["winner"]] and orgs.seat_of(conn, [m for m in f.managers if m != meta["winner"]][0], f.firm)["role_key"] == "manager"


def test_every_rate_is_a_design_figure_with_its_reasoning():
    from engine.world_package import package_for
    from engine import design
    w = open_world()
    c = w.conn
    figs = design.package_figures(c)
    data = json.loads((ROOT / "worlds" / "saintjude" / "orgs.json").read_text(encoding="utf-8"))
    lc = data["kinds"]["family"]["lifecycle"]
    keys: set[str] = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str) and x.split("_")[0] in ("appoint", "heir", "succ", "contest", "coup", "plot", "war"):
            keys.add(x)
    for name in ("appoint", "heir", "contest", "coup", "plot", "civil_war"):
        walk(lc[name])
    assert len(keys) > 100
    for key in keys:
        assert key in figs, key
        assert figs[key]["mark"] == "Design proposal" and figs[key]["note"], key


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception:
                failed += 1
                print("FAIL", name)
                traceback.print_exc()
    sys.exit(1 if failed else 0)
