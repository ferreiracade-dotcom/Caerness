"""Prison J1.8: the GM sees where a man is held and, for the man himself, his group, channels, hearing and visits; a stranger sees only where.

Run: PYTHONPATH=. python tests/j1_views_test.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.j1_admission_test import _convict, _run, _stay  # noqa: E402
from tests.outfit_choice_fixture import DAY, open_world  # noqa: E402

from connector import org_views, store, views  # noqa: E402
from engine import prison, prison_channels as pc  # noqa: E402
from engine.player import set_player  # noqa: E402


def _world(me: int | None = None):
    w = open_world()
    c = w.conn
    store.ensure_connector_schema(c)
    prison.ensure_facilities(c)
    _convict(c, w.soldier, 1000)
    _run(c)
    if me is not None:
        set_player(c, me)
    return w, c


def _outsider(c, w) -> int:
    return int(c.execute("""SELECT id FROM actors WHERE actor_type='character' AND status='active' AND id<>?
                            AND id NOT IN (SELECT actor_id FROM org_seats) ORDER BY id LIMIT 1""", (w.soldier,)).fetchone()[0])


def _fill(c, a):
    st = _stay(c, a)
    pc.open_channel(c, int(st["id"]), "lawyer", None, DAY + 1)
    other = int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' AND id<>? ORDER BY id DESC LIMIT 1", (a,)).fetchone()[0])
    cid = pc.open_channel(c, int(st["id"]), "visit", other, DAY + 1)
    c.execute("INSERT INTO prison_contacts(day,stay_id,channel_id,kind,from_actor_id,to_actor_id,summary) VALUES (?,?,?,?,?,?,?)",
              (DAY + 1, int(st["id"]), cid, "visit", other, a, "came"))
    c.execute("INSERT INTO law_reviews(kind,sentence_id,actor_id,filed_day,hearing_day,status) VALUES ('parole',?,?,?,?,'pending')",
              (int(st["sentence_id"] or 0), a, DAY, DAY + 200))
    return other


def test_view_shows_facility_channels_hearing_to_the_man_himself():
    for protagonist in (True, False):
        w, c = _world()
        a = w.soldier
        other = _fill(c, a)
        set_player(c, a if protagonist else other)
        v = org_views.custody_view(c, a, a)  # the man looking at himself (an NPC's own knowledge is the same call)
        assert v and v["facility"].startswith("held at "), v
        assert v["group"].startswith("keeps with "), v
        assert any("his lawyer" in x for x in v["channels"]), v
        assert any("visits" in x for x in v["channels"]), v
        assert v["next_hearing"].startswith("a parole hearing"), v
        assert v["visits"] and "came" in v["visits"][0], v


def test_other_mans_channels_hidden_from_a_stranger():
    w, c = _world()
    a = w.soldier
    _fill(c, a)
    for viewer in (w.capo, _outsider(c, w)):  # a man of his own outfit knows him; a stranger who has not heard of him knows nothing
        v = org_views.custody_view(c, a, viewer)
        if viewer == w.capo:
            assert v and v["facility"].startswith("held at "), v
        for k in ("group", "channels", "next_hearing", "visits"):
            assert k not in (v or {}), (k, v)
        assert "lawyer" not in json.dumps(v or {})


def test_scene_for_jailed_protagonist_has_custody_block():
    w, c = _world()
    a = w.soldier
    _fill(c, a)
    set_player(c, a)
    out = views.lookup(c, c.execute("SELECT name FROM actors WHERE id=?", (a,)).fetchone()[0])
    cu = out.get("custody")
    assert cu and cu.get("facility") and cu.get("channels") and cu.get("next_hearing"), out


def test_no_inside_words_no_block():
    w, c = _world()
    a = w.soldier
    _fill(c, a)
    old = org_views.words
    org_views.words = lambda conn: {"custody": {k: v for k, v in old(conn)["custody"].items() if k != "inside"}}
    try:
        v = org_views.custody_view(c, a, a)
    finally:
        org_views.words = old
    assert v and "facility" not in v and "channels" not in v


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
