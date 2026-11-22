"""I1a: bearing, the room read, what a man reads in others, the push and the delivery ledger (information phase 1a).

Run: PYTHONPATH=. python tests/i1a_test.py
The protagonist lives under the same rules: every system here takes an observer and a subject, and each test that acts on the
protagonist is paired with the same act on someone else.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect  # noqa: E402

from engine import bearing as B  # noqa: E402
from engine import texture as T  # noqa: E402
from engine.player import set_player  # noqa: E402


def _family(conn):
    """(boss, [soldiers], [associates], loc) of the first family that has all three."""
    for (org,) in conn.execute("SELECT org_actor_id FROM org_profiles WHERE org_kind='family' ORDER BY org_actor_id"):
        by = {}
        for r in conn.execute("SELECT actor_id,role_key,inducted_day FROM org_seats WHERE org_actor_id=? AND status='active' ORDER BY actor_id", (org,)):
            by.setdefault(r["role_key"], []).append(int(r["actor_id"]))
        if by.get("boss") and len(by.get("soldier", [])) > 10 and len(by.get("associate", [])) > 10:
            return by["boss"][0], by["soldier"], by["associate"], by
    raise RuntimeError("no family with a boss, soldiers and associates")


def _gather(conn, loc, ids):
    for i in ids:
        conn.execute("UPDATE actors SET current_location_id=? WHERE id=?", (loc, i))
    conn.commit()


def test_retinue_is_recorded_once_and_replaced(conn):
    boss, soldiers, assoc, _ = _family(conn)
    r1 = B.retinue(conn, boss)
    r2 = B.retinue(conn, boss)
    assert r1 == r2, "the crew persists"
    ids = [m["id"] for m in r1]
    assert all(i in soldiers + assoc for i in ids)
    if ids:
        conn.execute("UPDATE actors SET status='dead' WHERE id=?", (ids[0],))
        r3 = B.retinue(conn, boss)
        assert ids[0] not in [m["id"] for m in r3], "a man who dies leaves the crew"
        assert len(r3) >= len(ids) - 1
    print("ok retinue persists and is replaced", len(r1))


def test_forms_depend_on_time_and_induction(conn):
    boss, soldiers, assoc, _ = _family(conn)
    due = B.forms_due(conn, boss, soldiers[0])
    assert {f["key"] for f in due} >= {"stand", "hands", "own_title"}, [f["key"] for f in due]
    # a man of another organisation is owed the other title, not the own one
    other = next(int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE role_key='soldier' AND org_actor_id NOT IN "
                                                 "(SELECT org_actor_id FROM org_seats WHERE actor_id=?) ORDER BY actor_id", (boss,)))
    keys = {f["key"] for f in B.forms_due(conn, boss, other)}
    assert "other_title" in keys and "own_title" not in keys
    # made men know the forms far more often than green associates; recording a short time in the life lowers the odds
    sold, assc = soldiers[:80], assoc[:80]
    made = sum(B.form_known(conn, s, f) for s in sold for f in due) / (len(sold) * len(due))
    for a in assc:
        B.record_mark(conn, a, "in_the_life", "two months")
    green = sum(B.form_known(conn, a, f) for a in assc for f in due) / (len(assc) * len(due))
    assert made > 0.9 and green < made - 0.3, (made, green)
    # deterministic: the same man gets the same answer twice
    assert [B.form_known(conn, assoc[0], f) for f in due] == [B.form_known(conn, assoc[0], f) for f in due]
    print("ok forms: made", round(made, 2), "green", round(green, 2))


def test_recording_vetoes_and_persists(conn):
    boss, soldiers, assoc, _ = _family(conn)
    a = assoc[0]
    try:
        B.record_mark(conn, a, "in_the_life", "90 years")
        raise AssertionError("a time in the life longer than he has lived must be vetoed")
    except ValueError:
        pass
    out = B.record_mark(conn, a, "car", "a borrowed Buick, cost 99999")
    assert out.get("costs"), "display beyond his means is allowed but costs him"
    assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type='display_beyond_means' AND source_actor_id=?", (a,)).fetchone()[0] == 1
    assert any(s["text"].startswith("a borrowed Buick") and s.get("beyond_means") for s in B.signals(conn, a))
    assert any(s["text"].startswith("a borrowed Buick") for s in B.signals(conn, a)), "what was recorded persists"
    assert not any("car" in u for u in B.unrecorded(conn, a)), "recorded, so not asked for again"
    print("ok recording vetoes a contradiction and persists")


def test_room_read_and_placing(conn):
    boss, soldiers, assoc, _ = _family(conn)
    green = assoc[1]
    B.record_mark(conn, green, "in_the_life", "three weeks")
    rr = B.room_read(conn, boss, green)           # a green man reads the boss
    assert rr["from"] in ("saw", "heard", "read", "inferred") and "placed" in rr
    # a stranger with no dealings reads from signals alone and says how much shows
    stranger = next(int(r[0]) for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND id NOT IN "
                                                    "(SELECT actor_id FROM org_seats) ORDER BY id LIMIT 1"))
    rr2 = B.room_read(conn, boss, stranger)
    assert rr2["from"] == "inferred" and rr2["sure"] == "guessing"
    if not rr2["placed"]:
        assert rr2["reads_him_as"] in B.data(conn)["readings"]
    # the read is kept: a change shows (spending beyond his means and being known, here a changed stance)
    from engine.relationships import adjust_relationship
    B.room_read(conn, boss, soldiers[0])
    adjust_relationship(conn, soldiers[0], boss, 1, respect_delta=60.0, trust_delta=60.0)
    again = B.room_read(conn, boss, soldiers[0])
    assert again.get("changed", "").startswith("was") or again["stance"], again
    print("ok room read", rr2)


def test_green_man_misses_who_he_is(conn):
    """A green associate may not place the quiet old man; the engine returns what is due apart, marked outside his knowledge."""
    boss, soldiers, assoc, _ = _family(conn)
    missed = placed = 0
    for a in assoc[:60]:
        B.record_mark(conn, a, "in_the_life", "one month")
        r = B.reads_of(conn, a, boss)
        if r["read"]["placed"]:
            placed += 1
            assert "forms_he_knows" in r["read"] or "forms_he_is_unsure_of" in r["read"]
            assert r["hidden"] is None
        else:
            missed += 1
            assert r["hidden"] and r["hidden"]["he_does_not_read_this"] and r["hidden"]["due"], r
            assert "forms_he_knows" not in r["read"], "he is not told what he would not know"
    assert missed > 0 and placed >= 0
    # a made man places his own boss
    made_placed = sum(B.reads_of(conn, s, boss)["read"]["placed"] for s in soldiers[:60]) / len(soldiers[:60])
    assert made_placed > placed / len(assoc[:60]), (made_placed, placed)
    print("ok green men miss", missed, "of", len(assoc[:60]), "; made men place", round(made_placed, 2))


def test_same_rules_for_everyone(conn):
    """The protagonist is only the observer or subject of the scene: the same calls act on him and on anyone."""
    boss, soldiers, assoc, _ = _family(conn)
    me, other = assoc[2], assoc[3]
    set_player(conn, me)
    from engine.relationships import relationship_view
    for victim, actor in ((boss, me), (boss, other), (me, other), (other, me)):    # to or from the protagonist, and between others
        before = relationship_view(conn, victim, actor)
        out = B.form_outcome(conn, actor, victim, "wrong", "kept his seat when the old man came in")
        after = relationship_view(conn, victim, actor)
        assert after["resentment"] > before["resentment"] and after["respect"] < before["respect"], (victim, actor)
        right = B.form_outcome(conn, actor, victim, "shown", "stood and waited to be addressed")
        assert right["outcome"] == "shown"
    assert conn.execute("SELECT COUNT(*) FROM events WHERE event_type IN ('form_wrong','form_shown')").fetchone()[0] == 8, "each act becomes talk"
    # getting it right earns regard
    b4 = relationship_view(conn, boss, me)
    B.form_outcome(conn, me, boss, "shown")
    assert relationship_view(conn, boss, me)["respect"] > b4["respect"]
    # the room read and the reads work with him as subject and as observer, like anyone
    assert B.room_read(conn, me, boss)["from"] and B.room_read(conn, boss, me)["from"]
    assert B.reads_of(conn, me, boss)["read"] and B.reads_of(conn, boss, me)["read"] and B.reads_of(conn, other, me)["read"]
    # no code path of the new modules names the player
    for f in ("bearing.py", "texture.py"):
        src = (ROOT / "engine" / f).read_text(encoding="utf-8")
        assert "get_player" not in src and "player_actor_id" not in src, f
    print("ok same rules for everyone")


def test_texture_block_in_the_scene(conn):
    from connector import views
    from connector.store import ensure_connector_schema
    ensure_connector_schema(conn)
    boss, soldiers, assoc, by = _family(conn)
    me = by["capo"][0]
    set_player(conn, me)
    loc = int(conn.execute("SELECT id FROM locations WHERE kind IN ('club','bar','restaurant') ORDER BY id LIMIT 1").fetchone()[0])
    mine = [int(r[0]) for r in conn.execute("SELECT actor_id FROM org_seats WHERE superior_actor_id=? AND status='active' LIMIT 3", (me,))]
    _gather(conn, loc, [me, boss, *mine])
    s1 = views.compact_scene(conn)
    tex = s1["texture"]
    assert tex["bearing"].get("retinue"), tex["bearing"]
    assert tex.get("to_record") and any("dress" in t for t in tex["to_record"])
    assert tex.get("room"), "people in the scene are read without being asked"
    assert all("from" in r and "sure" in r for r in tex["room"]), tex["room"]
    assert {r["id"] for r in tex["room"]} <= {p["id"] for p in s1["present"]}
    print("ok texture in the scene; size", len(json.dumps(tex, ensure_ascii=False)), "bytes")
    return s1


def test_delivery_ledger_no_drop_no_repeat(conn):
    """A stretch with no prompting: crew, dress, deference and news appear unasked; every item is delivered exactly once."""
    from connector import views
    from connector.store import ensure_connector_schema
    ensure_connector_schema(conn)
    boss, soldiers, assoc, by = _family(conn)
    me = by["capo"][1]
    set_player(conn, me)
    loc = int(conn.execute("SELECT id FROM locations WHERE kind IN ('club','bar','restaurant') ORDER BY id LIMIT 1").fetchone()[0])
    _gather(conn, loc, [me, boss])
    B.record_mark(conn, me, "dress", "a good dark overcoat")
    views.compact_scene(conn)                       # first call: the cursor starts here
    day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
    entered = []
    wife = None
    for n in range(14):                             # public happenings: some touch him, some are about others
        sev = 1 + n % 5
        cur = conn.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id,source_actor_id) VALUES (?,?,?,?,?,?,?)",
                           (day, "arrest" if n % 2 else "report", f"Happening {n}", f"What happened {n}", sev, loc, boss if n % 3 == 0 else None))
        eid = int(cur.lastrowid)
        conn.execute("INSERT INTO event_information(event_id,visibility,secrecy,rumorability,reliability,registered_day) VALUES (?,?,?,?,?,?)", (eid, "public", 0.0, 0.5, 0.9, day))
        conn.execute("INSERT OR IGNORE INTO event_targets(event_id,actor_id,impact) VALUES (?,?,?)", (eid, me, "x"))   # each touches him, so each reaches him
        entered.append(f"event:{eid}")
    for n in range(5):                              # things he learned, about others
        conn.execute("INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,?,?,?,?)", (me, f"k{n}", f"He heard that Number {n} changed hands", 0.6, day))
    # family texture: a household member hears of him
    mate = conn.execute("SELECT actor_id FROM household_members WHERE status='active' AND household_id IN (SELECT household_id FROM household_members WHERE actor_id=?) AND actor_id<>? LIMIT 1", (me, me)).fetchone()
    if mate:
        conn.execute("INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,?,?,?,?)",
                     (int(mate[0]), "kfam", f"Someone at the shops said {B.name_of(conn, me)} is being talked about", 0.7, day))
        wife = int(mate[0])
    conn.commit()
    delivered, calls = [], 0
    while True:
        s = views.compact_scene(conn)
        calls += 1
        tex = s["texture"]
        items = tex.get("news") or []
        delivered += [i["what"] for i in items]
        assert tex["bearing"]["signals"] == ["a good dark overcoat"], "the dress he was recorded in appears unasked"
        if not tex.get("more_waiting"):
            break
        assert calls < 60, "pending items must drain"
    rows = conn.execute("SELECT item_key,delivered_count FROM delivery_ledger WHERE viewer_actor_id=?", (me,)).fetchall()
    assert rows and all(r["delivered_count"] == 1 for r in rows), "each item delivered exactly once"
    assert len(delivered) == len(rows) and len(set(delivered)) == len(delivered), "none dropped, none repeated"
    assert all(k in {r["item_key"] for r in rows} for k in entered), "every public happening that touches him was entered"
    if wife:
        assert any(r["item_key"].startswith("home:") for r in rows), "family texture where it exists"
    assert calls > 1, "the weight of what waits spreads over calls instead of arriving in one slab"
    after = views.compact_scene(conn)["texture"]
    assert "news" not in after, "a shown item is not repeated"
    print("ok ledger: delivered", len(delivered), "over", calls, "calls, none dropped or repeated")


def test_notes_record_through_the_connector(conn):
    from connector import store
    store.ensure_connector_schema(conn)
    boss, soldiers, assoc, by = _family(conn)
    me = by["capo"][2]
    set_player(conn, me)
    out = store.run_once(conn, "i1a-1", "note", {"x": 1}, lambda: store.record(conn, "bearing", "a grey suit and a black Lincoln", "i1a-1", field="dress"))
    assert out["saved"] == "bearing"
    out = store.run_once(conn, "i1a-2", "note", {"x": 2}, lambda: store.record(conn, "form", "kissed the old man's hand", "i1a-2", subject_id=boss, field="shown"))
    assert out["outcome"] == "shown"
    try:
        store.record(conn, "form", "x", "i1a-3", subject_id=boss, field="sideways")
        raise AssertionError("bad outcome must be refused")
    except ValueError:
        pass
    print("ok notes")


def test_no_world_words_and_caerness_untouched(conn):
    sys.path.insert(0, str(ROOT / "tests"))
    from no_world_words_test import WORDS, code_lines
    for f in ("bearing.py", "texture.py"):
        bad = [(n, t.strip()) for n, t in code_lines(ROOT / "engine" / f) if WORDS.search(t)]
        assert not bad, (f, bad[:3])
    # a package with no presence data gets no block (Caerness is unchanged)
    from engine import world_package
    assert world_package.load_package("caerness").data.get("presence") is None
    print("ok no world words; Caerness has no presence data")


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tests = [test_retinue_is_recorded_once_and_replaced, test_forms_depend_on_time_and_induction, test_recording_vetoes_and_persists,
                 test_room_read_and_placing, test_green_man_misses_who_he_is, test_same_rules_for_everyone, test_texture_block_in_the_scene,
                 test_delivery_ledger_no_drop_no_repeat, test_notes_record_through_the_connector, test_no_world_words_and_caerness_untouched]
        for t in tests:
            conn = connect(build_saintjude(Path(tmp)))   # a fresh copy per test
            try:
                t(conn)
            finally:
                conn.close()
    print("PASS i1a")


if __name__ == "__main__":
    main()
