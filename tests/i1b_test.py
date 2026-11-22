"""I1b: claims and audiences (information phase 1b).

Run: PYTHONPATH=. python tests/i1b_test.py
The protagonist lives under the same rules: claims, audiences, the circle's reactions and the answer to a damaging claim take any observer
and subject, and each test that acts on the protagonist is paired with the same act on someone else.
"""
from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect  # noqa: E402

from engine import bearing as B  # noqa: E402
from engine import claims as C  # noqa: E402
from engine import texture as T  # noqa: E402
from engine.information import register_event_information  # noqa: E402
from engine.player import set_player  # noqa: E402
from engine.relationships import adjust_relationship  # noqa: E402
from tests.i1a_test import _family, _gather  # noqa: E402


@contextmanager
def figs(**over):
    """Change presence figures for a test (the data stays as it is)."""
    real = B.fig
    B.fig = lambda conn, name: float(over[name]) if name in over else real(conn, name)
    try:
        yield
    finally:
        B.fig = real


def _day(conn) -> int:
    return B._day(conn)


def _set_day(conn, d: int) -> None:
    conn.execute("UPDATE world_state SET current_day=? WHERE id=1", (int(d),))


def mk_event(conn, subject, etype, summary, wits=(), severity=3, vis="limited", day=None):
    day = _day(conn) if day is None else day
    loc = conn.execute("SELECT current_location_id FROM actors WHERE id=?", (subject,)).fetchone()[0]
    eid = int(conn.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id,source_actor_id) VALUES (?,?,?,?,?,?,?)",
                           (day, etype, summary[:40], summary, severity, loc, subject)).lastrowid)
    register_event_information(conn, eid, day=day, visibility=vis)
    for w in wits:
        conn.execute("INSERT OR REPLACE INTO event_witnesses(event_id,actor_id,witness_type,confidence,learned_day) VALUES (?,?,?,?,?)", (eid, w, "observer", 0.9, day))
    return eid


def _setup(conn):
    return _family(conn)


def _org_of(conn, aid):
    return int(conn.execute("SELECT org_actor_id FROM org_seats WHERE actor_id=? AND status='active' ORDER BY level DESC LIMIT 1", (aid,)).fetchone()[0])


def _week(conn, n=1):
    for _ in range(n):
        _set_day(conn, _day(conn) + 7)
        C.weekly(conn, _day(conn))


def test_claims_stand_alone_and_veto(conn):
    boss, sol, assoc, _ = _setup(conn)
    s, a, b = sol[0], sol[1], sol[2]
    C.propose(conn, "pays on time", s, holder=a, source="saw", confidence=0.8, valence=0.3)
    C.propose(conn, "takes envelopes", s, holder=a, source="told", confidence=0.6, valence=-0.4)
    assert conn.execute("SELECT COUNT(*) FROM claims WHERE subject_actor_id=? AND holder_id=? AND holder_kind='actor'", (s, a)).fetchone()[0] == 2, "claims about one subject stand alone"
    eid = mk_event(conn, s, "hit", "He did it in the road.", wits=[a])
    for bad, why in ((lambda: C.propose(conn, "x", s, holder=b, source="saw", truth_event_id=eid), "he was not there"),
                     (lambda: C.propose(conn, "x", s, holder="no such audience or man", source="saw"), "unknown holder"),
                     (lambda: C.propose(conn, "x", s, holder=a, confidence=1.5), "confidence"),
                     (lambda: C.propose(conn, "x", sol[3], holder=a, source="told", truth_event_id=eid), "event about another man"),
                     (lambda: C.propose(conn, "x", s, holder=a, source="gossip"), "source")):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("not vetoed: " + why)
    conn.execute("UPDATE actors SET status='dead' WHERE id=?", (b,))
    try:
        C.propose(conn, "x", s, holder=b)
        raise AssertionError("the dead hold claims")
    except ValueError:
        pass
    C.propose(conn, "he was there", s, holder=a, source="saw", truth_event_id=eid)  # a witness may
    print("ok claims stand alone; vetoes only contradictions")


def test_named_people_update_four_ways(conn):
    boss, sol, assoc, _ = _setup(conn)
    s, w, t_high, t_low, r1, r2 = sol[0], sol[1], sol[2], sol[3], sol[4], sol[5]
    day = _day(conn)
    C.weekly(conn, day)  # sets the cursors
    eid = mk_event(conn, s, "hit", "He did it in the road.", wits=[w])
    C.weekly(conn, day)
    mine = conn.execute("SELECT * FROM claims WHERE subject_actor_id=? AND holder_id=? AND holder_kind='actor'", (s, w)).fetchone()
    assert mine and mine["source"] == "saw" and int(mine["costly"]) == 1 and mine["truth_event_id"] == eid, "witnessing"
    adjust_relationship(conn, r1, t_high, day, trust_delta=70)
    adjust_relationship(conn, r2, t_low, day, trust_delta=-60)
    C.hear(conn, r1, s, "he is hard", 0.8, -0.4, 0, False, "told", teller=t_high)
    C.hear(conn, r2, s, "he is hard", 0.8, -0.4, 0, False, "told", teller=t_low)
    hi = conn.execute("SELECT confidence FROM claims WHERE holder_id=? AND subject_actor_id=?", (r1, s)).fetchone()[0]
    lo = conn.execute("SELECT confidence FROM claims WHERE holder_id=? AND subject_actor_id=?", (r2, s)).fetchone()[0]
    assert hi > lo + 0.2, ("being told is discounted by the teller's credibility", hi, lo)
    C.record(conn, s, "actor", sol[6], "reads as careful", "read", 0.5, 0.2)
    C.record(conn, s, "actor", sol[6], "reads as careful", "saw", 0.5, 0.2)
    assert conn.execute("SELECT source FROM claims WHERE holder_id=? AND subject_actor_id=?", (sol[6], s)).fetchone()[0] == "saw", "first-hand outranks"
    C.record(conn, s, "actor", sol[7], "must be well in", "inferred", 0.4, 0.2)
    print("ok named people update: witnessed, told (discounted), read, inferred", round(hi, 2), round(lo, 2))


def test_drivers(conn):
    boss, sol, assoc, _ = _setup(conn)
    s = sol[0]
    day = _day(conn)
    a = C.record(conn, s, "actor", sol[1], "talk", "told", 0.5, -0.5, 0, False)
    b = C.record(conn, s, "actor", sol[1], "act", "saw", 0.5, -0.5, 0, True)
    g = C.record(conn, s, "actor", sol[1], "good talk", "told", 0.5, 0.5, 0, False)
    row = lambda i: conn.execute("SELECT * FROM claims WHERE id=?", (i,)).fetchone()
    assert C.weigh(conn, row(b), day) > C.weigh(conn, row(a), day), "a costly act is believed over talk"
    assert C.weigh(conn, row(a), day) > C.weigh(conn, row(g), day), "bad news sticks harder"
    later = day + 240
    assert C.weigh(conn, row(a), later) < 0.5 * C.weigh(conn, row(a), day) * 1.01, "time decays an unreinforced claim"
    assert C.weigh(conn, row(b), later) / C.weigh(conn, row(b), day) > C.weigh(conn, row(a), later) / C.weigh(conn, row(a), day), "stigma persists"
    C.record(conn, s, "actor", sol[1], "talk", "told", 0.5, -0.5, day=later)
    assert row(a)["day"] == later and C.weigh(conn, row(a), later) > 0.5 * C.weigh(conn, row(a), day) * 1.01, "reinforcement renews it"
    friend, stranger, rival = sol[2], sol[3], sol[4]
    adjust_relationship(conn, friend, s, day, affection_delta=80, trust_delta=80)
    adjust_relationship(conn, rival, s, day, resentment_delta=80)
    cs = lambda h, v: conn.execute("SELECT confidence FROM claims WHERE holder_id=? AND subject_actor_id=? AND text=?", (h, s, v)).fetchone()[0]
    for h in (friend, stranger, rival):
        C.hear(conn, h, s, "bad one", 0.8, -0.5, 0, False, "told", teller=None)
        C.hear(conn, h, s, "good one", 0.8, 0.5, 0, False, "told", teller=None)
    assert cs(friend, "bad one") < cs(stranger, "bad one"), "closeness resists bad news"
    assert cs(rival, "good one") < cs(stranger, "good one"), "a rival discounts good news"
    teller_f, teller_r = sol[5], sol[6]
    adjust_relationship(conn, teller_r, s, day, resentment_delta=80)
    for t in (teller_f, teller_r):
        for o in sol[10:50]:
            adjust_relationship(conn, t, o, day, familiarity_delta=50)
    for k in range(8):  # several claims each, so the comparison is of rates and not of one draw
        C.record(conn, s, "actor", teller_f, f"he skims {k}", "saw", 0.9, -0.5, 0, False)
        C.record(conn, s, "actor", teller_r, f"he skims on the side {k}", "saw", 0.9, -0.5, 0, False)
    with figs(tell_rate=0.2):
        n = C.spread(conn, day)
    told = lambda t: conn.execute("SELECT COUNT(*) FROM claims WHERE source_ref=? AND subject_actor_id=?", (t, s)).fetchone()[0]
    assert told(teller_r) > told(teller_f) >= 0 and n > 0, ("a rival spreads it", told(teller_r), told(teller_f))
    kid = conn.execute("SELECT confidence,hops FROM claims WHERE source_ref=? AND subject_actor_id=? LIMIT 1", (teller_r, s)).fetchone()
    assert int(kid["hops"]) >= 1 and float(kid["confidence"]) < 0.9, "second-hand is discounted"
    C.record(conn, s, "actor", sol[20], "old", "told", 0.05, -0.1, day=day - 2000)
    assert C.prune(conn, day) >= 1
    print("ok drivers: costly>talk, bad sticks, decay/reinforce/stigma, closeness, rivals, hops, forgetting")


def test_audiences_impressions_and_spill(conn):
    boss, sol, assoc, _ = _setup(conn)
    s = sol[0]
    auds = {a["key"]: a for a in C.audiences_of(conn, s)}
    assert {"outfit", "circle"} <= set(auds), auds.keys()
    nb = auds.get("neighbourhood")
    plant = "he talks to the law"
    if nb:
        C.record(conn, s, "audience", nb["id"], plant, "told", 0.9, -0.8, -0.3, False, check=False)
    for m in sol[1:6]:   # the outfit's men are close to him and resist it
        adjust_relationship(conn, m, s, _day(conn), affection_delta=70, trust_delta=70)
        C.hear(conn, m, s, plant, 0.9, -0.8, -0.3, False, "told", teller=None)
        C.record(conn, s, "actor", m, "he is solid", "saw", 0.8, 0.6, 0.2, False)
    out = C.impression(conn, auds["outfit"], s)
    if nb:
        hood = C.impression(conn, nb, s)
        assert hood["regard"] < 0, ("the neighbourhood believes it", hood)
        assert out["regard"] > hood["regard"] + 0.1, ("the outfit doubts it", out, hood)
        mine = conn.execute("SELECT confidence FROM claims WHERE holder_kind='actor' AND holder_id=? AND subject_actor_id=? AND text=?", (sol[1], s, plant)).fetchone()[0]
        theirs = conn.execute("SELECT confidence FROM claims WHERE holder_kind='audience' AND holder_id=? AND text=?", (nb["id"], plant)).fetchone()[0]
        assert mine < theirs - 0.2, "the close men doubt it where the street believes it"
        stranger = conn.execute("SELECT id FROM actors WHERE COALESCE(home_location_id,current_location_id)=? AND id<>? AND status<>'dead' "
                                "AND id NOT IN (SELECT holder_id FROM claims WHERE holder_kind='actor') LIMIT 1", (nb["ref"], s)).fetchone()
        if stranger:
            r, _, _ = C.regard_of(conn, int(stranger[0]), s)
            assert r < 0, "a man of the neighbourhood with no claims of his own takes its impression"
    conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,started_day) VALUES (?,?,?,0)", (s, assoc[0], "spouse"))
    C.record(conn, s, "audience", auds["circle"]["id"], "he is a butcher", "told", 0.9, -0.7, 0.6, True, check=False)
    assert conn.execute("SELECT COUNT(*) FROM claims WHERE subject_actor_id=? AND spilled=1", (assoc[0],)).fetchone()[0] >= 1, "a claim spills onto his family"
    assert conn.execute("SELECT COUNT(*) FROM claims WHERE subject_actor_id=? AND spilled=1", (_org_of(conn, s),)).fetchone()[0] >= 1, "and onto the outfit"
    before = conn.execute("SELECT COUNT(*) FROM claims WHERE holder_kind='audience' AND holder_id=?", (auds["outfit"]["id"],)).fetchone()[0]
    C.record(conn, s, "actor", sol[30], "he made his bones", "saw", 0.9, 0.5, 0.5, True)
    after = conn.execute("SELECT COUNT(*) FROM claims WHERE holder_kind='audience' AND holder_id=?", (auds["outfit"]["id"],)).fetchone()[0]
    assert after > before, "what a member holds reaches his outfit's impression"
    print("ok audiences: believed/doubted impressions, draw on the audience, spill to family and outfit")


def test_seat_standing_follows_the_outfit_impression(conn):
    boss, sol, assoc, by = _setup(conn)
    caps = by["capo"]
    for who in (caps[0], caps[1], sol[0]):   # the first capo stands in for the protagonist; the same act on others
        org = _org_of(conn, who)
        up = conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=?", (who, org)).fetchone()[0]
        aud = next(a for a in C.audiences_of(conn, who) if a["key"] == "outfit")
        members = [m for m in C.members(conn, aud) if m != who][:20]
        for m in members:
            C.record(conn, who, "actor", m, "carries himself well", "saw", 0.9, 0.9, 0.3, True)
        for _ in range(4):
            _week(conn)
        now = conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=?", (who, org)).fetchone()[0]
        assert now > up + 0.01 or up > 0.95, ("standing follows the outfit's claims up", up, now)
        for m in members:
            C.record(conn, who, "actor", m, "turned out a rat", "saw", 0.95, -0.95, -0.5, True)
        for _ in range(8):
            _week(conn)
        end = conn.execute("SELECT standing FROM org_seats WHERE actor_id=? AND org_actor_id=?", (who, org)).fetchone()[0]
        assert end < now, ("and down", now, end)
    print("ok seat standing moves with the outfit's claims (protagonist stand-in and others)")


def test_room_read_from_claims(conn):
    boss, sol, assoc, _ = _setup(conn)
    s = by_capo = _setup(conn)[3]["capo"][0]
    o = next(x for x in sol if x != s and B.recognises(conn, x, s)[0])   # one who places him
    C.record(conn, s, "actor", o, "keeps his word", "saw", 0.8, 0.7, 0.2, True)
    conn.execute("DELETE FROM room_reads")
    conn.execute("DELETE FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (o, s))
    placed = B.recognises(conn, o, s)[0]
    rr = B.room_read(conn, s, o)
    if placed:
        assert rr["from"] == "saw" and rr.get("holds") == "keeps his word", rr
        assert rr["stance"], "a stance from regard when dealings give none"
    print("ok room read draws on claims", rr.get("from"), rr.get("stance"), placed)


def test_circle_reactions_and_how_they_reach_him(conn):
    boss, sol, assoc, by = _setup(conn)
    caps = by["capo"]
    other_rows = 0
    for who in (caps[0], caps[1]):    # the protagonist and the same act on someone else
        wife, child = assoc[0 if who == caps[0] else 2], assoc[1 if who == caps[0] else 3]
        for p, k in ((wife, "spouse"), (child, "child")):
            conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,started_day) VALUES (?,?,?,0)", (who, p, k))
        shops = int(conn.execute("SELECT id FROM locations WHERE kind IN ('club','bar','restaurant') ORDER BY id LIMIT 1").fetchone()[0])
        home = int(conn.execute("SELECT id FROM locations WHERE id<>? ORDER BY id LIMIT 1", (shops,)).fetchone()[0])
        _gather(conn, shops, [wife, child] + sol[10:16])
        _gather(conn, home, [who])
        if who == caps[0]:
            set_player(conn, who)
        for h in sol[10:16]:
            C.record(conn, who, "actor", h, "is said to have killed a man", "told", 0.9, -0.7, 0.6, True)
        with figs(react_rate=50.0, tell_rate=0.0):
            _week(conn)
        rows = conn.execute("SELECT * FROM circle_reactions WHERE subject_actor_id=?", (who,)).fetchall()
        assert rows, "the connected people met it in their own days"
        assert {int(r["person_actor_id"]) for r in rows} <= {wife, child}
        assert all(r["routing"] == "cutaway" for r in rows), "he was not there"
        assert all(json.loads(r["present_json"]) for r in rows), "who was present"
        assert any(r["regard"] < 0 for r in rows)
        spilled = conn.execute("SELECT stance FROM relationships WHERE actor_a_id IN (%s) AND actor_b_id=?" % ",".join(map(str, sol[10:16])), (wife,)).fetchall()
        assert spilled and any(float(x[0]) < 0 for x in spilled), "the spill driver moved how they treat his people"
        if who == caps[0]:
            T.block(conn, who, home, [])
            ledger = conn.execute("SELECT text FROM delivery_ledger WHERE viewer_actor_id=? AND item_key LIKE 'reaction:%'", (who,)).fetchall()
            assert not ledger, "not his knowledge until it is told"
            assert conn.execute("SELECT COUNT(*) FROM circle_reactions WHERE subject_actor_id=? AND cutaway_day IS NOT NULL", (who,)).fetchone()[0] == len(rows), "each cutaway shown to the GM once"
            _gather(conn, home, [wife])                         # she comes home
            with figs(react_rate=0.0, tell_rate=0.0):
                _week(conn)
            assert conn.execute("SELECT COUNT(*) FROM circle_reactions WHERE subject_actor_id=? AND told_day IS NOT NULL", (who,)).fetchone()[0] >= 1, "it comes home"
            T.block(conn, who, home, [])
            got = conn.execute("SELECT text FROM delivery_ledger WHERE viewer_actor_id=? AND item_key LIKE 'reaction:%'", (who,)).fetchall()
            assert got, "pushed through the ledger"
            _gather(conn, shops, [who])
            for h in sol[10:16]:
                C.record(conn, who, "actor", h, "was seen at it again", "saw", 0.9, -0.7, 0.6, True)
            with figs(react_rate=50.0, tell_rate=0.0):
                _week(conn)
            assert conn.execute("SELECT COUNT(*) FROM circle_reactions WHERE subject_actor_id=? AND routing='first_hand'", (who,)).fetchone()[0] >= 1, "first-hand when he is there"
        else:
            other_rows = len(rows)
    assert other_rows
    print("ok circle: reactions in their own days (cutaway, home, first-hand), spill, pushed; same for another man", other_rows)


def test_npc_hears_and_answers_and_the_protagonist_is_no_different(conn):
    from engine import org_choices
    boss, sol, assoc, by = _setup(conn)
    caps = by["capo"]
    out = []
    for who in (caps[0], caps[1]):
        if who == caps[0]:
            set_player(conn, who)
        teller = sol[5] if who == caps[0] else sol[6]
        adjust_relationship(conn, who, teller, _day(conn), familiarity_delta=60)
        C.hear(conn, who, who, "has been talking to the law", 0.9, -0.8, -0.4, False, "told", teller=teller, hops=1)
        item = conn.execute("SELECT * FROM org_agenda WHERE actor_id=? AND kind='answer_name' AND status='open'", (who,)).fetchone()
        assert item is not None, "he hears of it and it goes on his list"
        offers = org_choices.AGENDA_ACTIONS["answer_name"](conn, who, item, _day(conn))
        kinds = {o["kind"] for o in offers}
        assert {"answer_claim", "go_quiet"} <= kinds, kinds
        ans = next(o for o in offers if o["kind"] == "answer_claim")
        f0 = conn.execute("SELECT fear FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (teller, who)).fetchone()
        org_choices.execute(conn, who, "answer_claim", ans["payload"], _day(conn))
        f1 = conn.execute("SELECT fear FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (teller, who)).fetchone()
        assert float(f1[0]) > float(f0[0] if f0 else 0), "leaning on him frightened him"
        assert conn.execute("SELECT status FROM org_agenda WHERE id=?", (item["id"],)).fetchone()[0] == "resolved"
        out.append(ans["utility"])
    s1, s2 = sol[20], sol[21]
    for s, f in ((s1, -0.8), (s2, 0.8)):
        for m in sol[22:30]:
            C.record(conn, s, "actor", m, "how he is held", "saw", 0.9, 0.0, f, True)
    assert C.deterrence(conn, s1) < C.deterrence(conn, s2), "a man held weak is the one with more reason to answer"
    print("ok NPC and protagonist both hear, weigh, answer through the choices path", [round(x, 1) for x in out])


def test_unprompted_stretch_family_carries_the_reputation(conn):
    boss, sol, assoc, by = _setup(conn)
    me = by["capo"][0]
    set_player(conn, me)
    wife, child = assoc[5], assoc[6]
    for p, k in ((wife, "spouse"), (child, "child")):
        conn.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,started_day) VALUES (?,?,?,0)", (me, p, k))
    shops = int(conn.execute("SELECT id FROM locations WHERE kind IN ('club','bar','restaurant') ORDER BY id LIMIT 1").fetchone()[0])
    home = int(conn.execute("SELECT id FROM locations WHERE id<>? ORDER BY id LIMIT 1", (shops,)).fetchone()[0])
    _gather(conn, shops, [wife, child] + sol[10:16] + assoc[10:16])
    _gather(conn, home, [me])
    C.weekly(conn, _day(conn))
    mk_event(conn, me, "hit", "He settled it in the open, in front of the street.", wits=sol[10:16] + assoc[10:16], severity=4, vis="public")
    texts = []
    with figs(react_rate=4.0):
        for w in range(8):
            _week(conn)
            if w == 3:
                _gather(conn, home, [wife])     # she comes home and tells him
            blk = T.block(conn, me, home, [])
            for it in (blk or {}).get("news", []):
                texts.append(it["what"])
    reactions = conn.execute("SELECT COUNT(*) FROM circle_reactions WHERE subject_actor_id=?", (me,)).fetchone()[0]
    assert reactions >= 1, "the family's lives carried it"
    assert len(texts) == len(set(texts)), "nothing repeated"
    assert any("what is said of" in t for t in texts), ("the family's day reached him, unasked", texts)
    print("ok unprompted stretch: reactions", reactions, "items pushed", len(texts))


def test_organisation_incidents_become_claims(conn):
    boss, sol, assoc, by = _setup(conn)
    C.weekly(conn, _day(conn))
    off, victim = sol[0], sol[1]
    conn.execute("INSERT INTO org_incidents(day,kind,offender_actor_id,victim_actor_id,matters,raised_to_org_actor_id,status,metadata_json) VALUES (?,?,?,?,1,?, 'open', ?)",
                 (_day(conn), "informs", off, victim, _org_of(conn, off), json.dumps({"summary": "an informant gave the police evidence"})))
    C.weekly(conn, _day(conn))
    assert conn.execute("SELECT COUNT(*) FROM claims WHERE subject_actor_id=? AND holder_id=? AND holder_kind='actor'", (off, victim)).fetchone()[0] == 1, "the one it was done to holds it"
    print("ok organisation incidents become claims")


def test_notes_and_lookup(conn):
    from connector import store, views
    from connector.store import ensure_connector_schema
    ensure_connector_schema(conn)
    boss, sol, assoc, by = _setup(conn)
    me = by["capo"][0]
    set_player(conn, me)
    r = store.record(conn, "claim", "he keeps his word", "call-1", subject_id=sol[0], field="holder=outfit; source=told; confidence=0.7; valence=0.4; costly")
    assert r["saved"] == "claim"
    store.record(conn, "claim", "they say he is careful", "call-2", subject_id=sol[0], field=f"holder={me}; source=told; confidence=0.6; valence=0.2")
    conn.execute("UPDATE actors SET name='Zeno Testa' WHERE id=?", (sol[0],))
    out = views.lookup(conn, "Zeno Testa")
    assert out.get("held_of_him"), list(out)
    print("ok note kind=claim and lookup shows what he holds")


def test_hygiene(conn):
    sys.path.insert(0, str(ROOT / "tests"))
    from no_world_words_test import WORDS, code_lines
    for f in ("claims.py", "news_choices.py"):
        text = (ROOT / "engine" / f).read_text(encoding="utf-8")
        assert "get_player" not in text and "player_actor_id" not in text, f"{f} knows the protagonist"
        bad = [(n, t.strip()) for n, t in code_lines(ROOT / "engine" / f) if WORDS.search(t)]
        assert not bad, (f, bad[:3])
    from engine import world_package
    assert world_package.load_package("caerness").data.get("presence") is None
    print("ok no protagonist, no world words; Caerness has no presence data")


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tests = [test_claims_stand_alone_and_veto, test_named_people_update_four_ways, test_drivers, test_audiences_impressions_and_spill,
                 test_seat_standing_follows_the_outfit_impression, test_room_read_from_claims, test_circle_reactions_and_how_they_reach_him,
                 test_npc_hears_and_answers_and_the_protagonist_is_no_different, test_unprompted_stretch_family_carries_the_reputation,
                 test_organisation_incidents_become_claims, test_notes_and_lookup, test_hygiene]
        only = sys.argv[1:]
        for t in tests:
            if only and t.__name__ not in only:
                continue
            conn = connect(build_saintjude(Path(tmp)))
            try:
                t(conn)
            finally:
                conn.close()
    print("PASS i1b")


if __name__ == "__main__":
    main()
