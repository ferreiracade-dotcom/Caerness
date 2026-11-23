"""Prison J1.6: parole, appeals, pardons and release through the law, for NPCs and the protagonist alike.

Run: PYTHONPATH=. python tests/j1_review_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.crime_response_test import _hit, _latest_report, _process, _victim  # noqa: E402
from tests.j1_admission_test import _convict, _men, _run, _stay  # noqa: E402
from tests.outfit_choice_fixture import DAY, forced_roll, open_world  # noqa: E402

from engine import crime_response as cr, orgs, prison, prison_review as pr  # noqa: E402
from engine.player import set_player  # noqa: E402


class _Prob:
    """Pin the chance of a hearing's going the man's way."""

    def __init__(self, p):
        self.p, self.orig = p, pr.probability

    def __enter__(self):
        pr.probability = lambda conn, kind, s, day, p=self.p: p

    def __exit__(self, *a):
        pr.probability = self.orig


def _setup(term=1000, n=1, protagonist=False):
    w = open_world()
    c = w.conn
    prison.ensure_facilities(c)
    men = _men(c, n)
    if protagonist:
        set_player(c, men[0])
    sids = [_convict(c, m, term) for m in men]
    _run(c)
    return c, men, sids


def _sentence(c, sid):
    return c.execute("SELECT * FROM sentences WHERE id=?", (sid,)).fetchone()


def _reviews(c, sid, kind="parole"):
    return c.execute("SELECT * FROM law_reviews WHERE sentence_id=? AND kind=? ORDER BY id", (sid, kind)).fetchall()


def _infractions(c, a, n, day=DAY + 2):
    fac = c.execute("SELECT id FROM facilities LIMIT 1").fetchone()[0]
    for i in range(n):
        c.execute("INSERT INTO prison_events(day,facility_id,actor_id,kind,summary) VALUES (?,?,?,'infraction','test')", (day + i, fac, a))


def test_parole_hearing_on_its_day_inside_a_skip():
    for protagonist in (False, True):
        c, (a,), (sid,) = _setup(term=90, protagonist=protagonist)
        s = _sentence(c, sid)
        hearing = int(s["earliest_release_day"])
        end = DAY + 60
        visited, d = [], DAY + 1
        with _Prob(0.0):
            while True:
                c.execute("UPDATE world_state SET current_day=? WHERE id=1", (d,))
                prison.process_due(c, d)
                nxt = prison.next_due_day(c, d, end)
                if nxt is None:
                    break
                visited.append(nxt)
                d = nxt
        assert hearing in visited, (hearing, visited)  # a 60-day skip stops on the hearing day
        rv = _reviews(c, sid)[0]
        assert rv["hearing_day"] == hearing and rv["status"] == "heard" and rv["outcome"] == "denied", dict(rv)
        assert c.execute("SELECT COUNT(*) FROM prison_events WHERE kind='hearing_parole' AND day=?", (hearing,)).fetchone()[0] == 1


def test_denied_then_reheard_after_reset_and_granted():
    for protagonist in (False, True):
        c, (a,), (sid,) = _setup(term=2000, protagonist=protagonist)
        s = _sentence(c, sid)
        first = int(s["earliest_release_day"])
        with _Prob(0.0):
            pr.process(c, DAY + 1)
            pr.process(c, first)
            assert pr.next_due_day(c, first, first + 5) == first + 1  # the next hearing is yet to be set: tomorrow
            pr.process(c, first + 1)
        reset = int(pr._figure(pr._cfg(c)["parole"]["reset_days"]))
        rvs = _reviews(c, sid)
        assert [r["outcome"] for r in rvs] == ["denied", None]
        assert rvs[1]["hearing_day"] == first + reset  # heard again one reset span later
        with _Prob(1.0):
            pr.process(c, first + reset)
        assert _reviews(c, sid)[1]["outcome"] == "granted"
        s2 = _sentence(c, sid)
        assert s2["status"] == "paroled" and json.loads(s2["metadata_json"])["parole"]["until"] == int(s2["end_day"])
        assert _stay(c, a) is None
        assert c.execute("SELECT COUNT(*) FROM custody WHERE actor_id=? AND kind='held'", (a,)).fetchone()[0] == 0


def test_conduct_moves_the_odds():
    c, (a,), (sid,) = _setup(term=1000)
    s = _sentence(c, sid)
    clean = pr.probability(c, "parole", s, DAY + 400)
    _infractions(c, a, 5)
    dirty = pr.probability(c, "parole", s, DAY + 400)
    assert dirty < clean
    # a man who cooperated is heard more kindly than one who did not
    c.execute("DELETE FROM prison_events")
    base = pr.probability(c, "parole", s, DAY + 400)
    org = orgs.seat_of(c, a, c.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' LIMIT 1", (a,)).fetchone()[0])["org_actor_id"]
    c.execute("INSERT INTO org_informers(informer_actor_id,org_actor_id,turned_by_kind,turned_by_id,since_day) VALUES (?,?,?,?,?)", (a, org, "law", None, DAY))
    assert pr.probability(c, "parole", s, DAY + 400) > base


def test_an_outfit_man_is_heard_less_kindly_than_a_man_with_no_outfit():
    c, (a,), (sid,) = _setup(term=1000)
    s = _sentence(c, sid)
    with_outfit = pr.probability(c, "parole", s, DAY + 400)
    c.execute("UPDATE org_seats SET status='out' WHERE actor_id=? AND org_actor_id NOT IN (SELECT org_actor_id FROM facility_groups)", (a,))
    assert pr.probability(c, "parole", s, DAY + 400) > with_outfit  # boards did not want mobsters meeting


def test_mandatory_release_at_end_with_good_time():
    for protagonist in (False, True):
        c, (a,), (sid,) = _setup(term=300, protagonist=protagonist)
        s = _sentence(c, sid)
        clean = pr.release_day(c, s)
        assert clean < int(s["end_day"])  # good time earned
        _infractions(c, a, 6)
        dirty = pr.release_day(c, s)
        assert clean < dirty <= int(s["end_day"])  # infractions take it away, never past the end
        c.execute("DELETE FROM prison_events")
        with _Prob(0.0):
            pr.process(c, clean - 1)
            assert _sentence(c, sid)["status"] == "serving" and _stay(c, a) is not None
            out = pr.process(c, clean)
        assert out["released"] == 1
        assert _sentence(c, sid)["status"] == "released" and _stay(c, a) is None
        assert c.execute("SELECT COUNT(*) FROM custody WHERE actor_id=? AND kind='held'", (a,)).fetchone()[0] == 0


def _chain_sentence(c, w):
    """A real conviction through the law's chain (a public killing, an arrest, a plea): returns the sentence row."""
    v = _victim(c, {w.soldier}, w.org)
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    _hit(c, v, w.soldier, fatal=True, public=True, loc=w.ground)
    with forced_roll("pad_publicity", "identify"):
        _process(c, DAY + 1)
    rep = _latest_report(c)
    assert rep["status"] == "arrest"
    case = c.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (rep["case_id"],)).fetchone()
    due = json.loads(case["metadata_json"])["disposition_day"]
    orig = cr._rng

    class _High:
        def random(self):
            return 0.99  # not dismissed, not tried: a plea

    cr._rng = lambda conn, stream, key: _High() if stream == "disposition" else orig(conn, stream, key)
    try:
        day = DAY + 2
        while day <= due + 1:
            _process(c, day)
            day += 1
    finally:
        cr._rng = orig
    s = c.execute("SELECT * FROM sentences WHERE actor_id=? AND status='serving'", (w.soldier,)).fetchone()
    assert s is not None, "the chain did not convict"
    return s, case, due + 1


def test_appeal_overturn_reopens_the_case():
    for protagonist in (False, True):
        w = open_world()
        c = w.conn
        cr.ensure_tables(c)  # a running campaign has the tables before its crimes happen
        prison.ensure_facilities(c)
        if protagonist:
            set_player(c, w.soldier)
        s, case, day = _chain_sentence(c, w)
        prison.process_due(c, day)
        assert _stay(c, w.soldier) is not None
        assert file_ok(pr.file_appeal(c, int(s["id"]), day, hearing_day=day + 1))
        with _Prob(1.0):
            out = pr.process(c, day + 1)
        assert out["hearings"] == 1
        assert _sentence(c, int(s["id"]))["status"] == "vacated"
        assert _stay(c, w.soldier) is None
        assert c.execute("SELECT kind FROM custody WHERE actor_id=? ORDER BY id DESC LIMIT 1", (w.soldier,)).fetchone()[0] == "bailed"
        cs = c.execute("SELECT * FROM law_enforcement_cases WHERE id=?", (case["id"],)).fetchone()
        m = json.loads(cs["metadata_json"])
        assert cs["status"] == "actionable" and m["stage"] == "disposition" and cs["next_review_day"] > day + 1
        # the chain runs the disposition again: a new sentence is a new row, the old one stays vacated
        orig = cr._rng

        class _High:
            def random(self):
                return 0.99

        cr._rng = lambda conn, stream, key: _High() if stream == "disposition" else orig(conn, stream, key)
        try:
            d = day + 2
            while d <= int(cs["next_review_day"]) + 1:
                _process(c, d)
                d += 1
        finally:
            cr._rng = orig
        again = c.execute("SELECT * FROM sentences WHERE actor_id=? AND status='serving'", (w.soldier,)).fetchone()
        assert again is not None and int(again["id"]) != int(s["id"])
        assert _sentence(c, int(s["id"]))["status"] == "vacated"


def file_ok(x):
    return x is not None


def test_a_won_appeal_is_rare_by_its_drivers():
    c, (a,), (sid,) = _setup(term=1000)
    s = _sentence(c, sid)
    base = pr.probability(c, "appeal", s, DAY + 30)
    assert 0.0 < base < 0.2  # a man with no lawyer rarely wins
    case = c.execute("SELECT metadata_json FROM law_enforcement_cases WHERE id=?", (s["case_id"],)).fetchone()
    if case is None:
        c.execute("""INSERT INTO law_enforcement_cases(profile_id,subject_kind,subject_id,allegation_kind,evidence_score,status,opened_day,last_review_day,next_review_day,metadata_json)
                     VALUES (1,'actor',?,'test',50,'closed',0,0,0,?)""", (int(s["actor_id"]), json.dumps({"lawyer_fee": 5000})))
        c.execute("UPDATE sentences SET case_id=? WHERE id=?", (c.execute("SELECT MAX(id) FROM law_enforcement_cases").fetchone()[0], sid))
    else:
        c.execute("UPDATE law_enforcement_cases SET metadata_json=json_set(metadata_json,'$.lawyer_fee',5000) WHERE id=?", (s["case_id"],))
    assert pr.probability(c, "appeal", _sentence(c, sid), DAY + 30) > base  # a paid lawyer moves it, by weight not by flag


def test_pardon_is_rare_and_weighed():
    c, (a,), (sid,) = _setup(term=1000)
    s = _sentence(c, sid)
    base = pr.probability(c, "pardon", s, DAY + 500)
    assert 0.0 < base < 0.02, base
    parole = pr.probability(c, "parole", s, DAY + 500)
    assert base < parole
    c.execute("UPDATE org_seats SET standing=1.0 WHERE actor_id=? AND status='active'", (a,))
    assert pr.probability(c, "pardon", s, DAY + 500) > base  # standing outside is a connection
    c.execute("DELETE FROM law_reviews WHERE kind='parole'")  # the parole hearing is a separate matter
    rv = pr.file_pardon(c, sid, DAY + 500, hearing_day=DAY + 501)
    assert rv is not None
    with _Prob(1.0):
        pr.process(c, DAY + 501)
    assert _sentence(c, sid)["status"] == "pardoned" and _stay(c, a) is None


def test_release_carries_ties_and_drift():
    c, (a, b), (sa, sb) = _setup(term=300, n=2)
    stay_a, stay_b = _stay(c, a), _stay(c, b)
    fac = int(stay_a["facility_id"])
    c.execute("INSERT INTO prison_events(day,facility_id,actor_id,other_actor_id,kind,summary) VALUES (?,?,?,?,'fight','test')", (DAY + 3, fac, a, b))
    c.execute("UPDATE inmate_stays SET facility_id=? WHERE id=?", (fac, int(stay_b["id"])))
    before = c.execute("SELECT aggression,patience,loyalty FROM actor_drives WHERE actor_id=?", (a,)).fetchone()
    res0 = c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (a, b)).fetchone()
    pr.come_home(c, _sentence(c, sa), DAY + 200, "released")
    ties = c.execute("SELECT kind FROM inmate_ties WHERE actor_a_id=?", (a,)).fetchall()
    assert any(t[0] == "rival" for t in ties)
    after_rel = c.execute("SELECT resentment FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (a, b)).fetchone()
    assert after_rel[0] > (res0[0] if res0 else 0.0)
    after = c.execute("SELECT aggression,patience,loyalty FROM actor_drives WHERE actor_id=?", (a,)).fetchone()
    assert tuple(after) != tuple(before)  # the place changed him


def test_parole_condition_broken_opens_a_report():
    c, (a,), (sid,) = _setup(term=2000)
    pr.come_home(c, _sentence(c, sid), DAY + 100, "paroled")
    bar = json.loads(_sentence(c, sid)["metadata_json"])["parole"]["bar_orgs"]
    assert bar  # he is barred from the outfit he sits in
    # put a man of his outfit where he is
    mate = c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND status='active' AND actor_id<>? ORDER BY actor_id LIMIT 1", (bar[0], a)).fetchone()[0]
    here = c.execute("SELECT current_location_id FROM actors WHERE id=?", (a,)).fetchone()[0]
    c.execute("UPDATE actors SET current_location_id=? WHERE id=?", (here, mate))
    n0 = c.execute("SELECT COUNT(*) FROM crime_reports").fetchone()[0]
    saved = pr._figure
    pr._figure = lambda spec, default=None: 1000.0 if isinstance(spec, dict) and spec.get("why", "").startswith("Weekly chance, per log") else saved(spec, default)
    try:
        out = pr.weekly(c, DAY + 107)
    finally:
        pr._figure = saved
    assert out["violations"] == 1
    assert c.execute("SELECT COUNT(*) FROM crime_reports").fetchone()[0] == n0 + 1


def test_a_sentence_ends_its_parole_at_the_end_day():
    c, (a,), (sid,) = _setup(term=2000)
    pr.come_home(c, _sentence(c, sid), DAY + 100, "paroled")
    s = _sentence(c, sid)
    pr.process(c, int(s["end_day"]))
    assert _sentence(c, sid)["status"] == "released"


def test_the_module_names_no_player_branch():
    src = (ROOT / "engine" / "prison_review.py").read_text(encoding="utf-8")
    assert "get_player" not in src and "is_player" not in src


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
