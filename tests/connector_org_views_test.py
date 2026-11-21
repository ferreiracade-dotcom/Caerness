"""Task B14: the GM sees a man's place in the life, an organisation's dealings and what is in the air, in words and under the firewall.

Run: PYTHONPATH=. python tests/connector_org_views_test.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import DAY, open_world


def _name(c, a):
    return c.execute("SELECT name FROM actors WHERE id=?", (a,)).fetchone()[0]


def _setup():
    w = open_world()
    c = w.conn
    from connector import store
    store.ensure_connector_schema(c)
    c.execute("UPDATE world_state SET current_day=? WHERE id=1", (DAY,))
    from engine.player import set_player
    set_player(c, w.soldier)
    return w, c


def _stranger(c, w):
    r = c.execute("""SELECT a.id FROM actors a WHERE a.actor_type='character' AND a.status='active' AND a.id NOT IN (SELECT actor_id FROM org_seats)
                     AND a.id NOT IN (SELECT knower_actor_id FROM knowledge WHERE 0) ORDER BY a.id LIMIT 1""").fetchone()
    return int(r[0])


def test_lookup_shows_the_record():
    from connector import views
    w, c = _setup()
    out = views.lookup(c, _name(c, w.capo))
    r = out["organisations"][0]
    assert r["role"] == "Capo", r
    assert r["lines"] and "$" in r["lines"][0], r
    assert "history_due" in r


def test_non_member_has_no_record():
    from connector import views
    w, c = _setup()
    out = views.lookup(c, _name(c, _stranger(c, w)))
    assert "organisations" not in out and "custody" not in out and "temperament" not in out, out


def test_history_due_is_flagged():
    from connector import views
    from engine.org_lifecycle import mark_for_history
    w, c = _setup()
    mark_for_history(c, w.capo, "was made", DAY)
    out = views.lookup(c, _name(c, w.capo))
    r = out["organisations"][0]
    assert r["history_due"] is True and r["history_reasons"] == ["was made"], r


def test_hidden_line_not_shown_to_others():
    from connector import views, org_views
    w, c = _setup()
    row = c.execute("SELECT id,description FROM org_lines WHERE holder_actor_id=? AND status='active' LIMIT 1", (w.capo,)).fetchone()
    c.execute("UPDATE org_lines SET hidden=1,description='a hidden book on Quill Street' WHERE id=?", (row[0],))
    out = views.lookup(c, _name(c, w.capo))
    assert "hidden book" not in json.dumps(out)
    from engine.player import set_player
    set_player(c, w.capo)
    assert any("hidden book" in x for x in org_views.record_view(c, w.capo)[0]["lines"])


def test_two_seats_both_shown():
    from connector import org_views
    w, c = _setup()
    other = int(c.execute("SELECT org_actor_id FROM org_seats WHERE org_actor_id<>? AND status='active' LIMIT 1", (w.org,)).fetchone()[0])
    c.execute("""INSERT INTO org_seats(actor_id,org_actor_id,role_key,level,joined_day,status)
                 SELECT ?,?,role_key,3,0,'active' FROM org_seats WHERE org_actor_id=? AND status='active' LIMIT 1""", (w.capo, other, other))
    recs = org_views.record_view(c, w.capo, me=w.soldier)
    # he shares the first organisation; the second is placed only if the protagonist has heard of him by name
    assert len(recs) >= 1
    c.execute("INSERT INTO knowledge(knower_actor_id,fact_key,belief_text,confidence,learned_day) VALUES (?,'t14',?,?,?)", (w.soldier, f"{_name(c, w.capo)} is with the other family", 0.8, DAY))
    assert len(org_views.record_view(c, w.capo, me=w.soldier)) == 2


def test_temperament_and_custody_in_words_no_numbers():
    from connector import views
    w, c = _setup()
    c.execute("UPDATE actor_drives SET aggression=0.9,risk_tolerance=0.1 WHERE actor_id=?", (w.capo,))
    c.execute("INSERT INTO custody(actor_id,case_id,kind,charge,since_day,until_day) VALUES (?,NULL,'held','assault',?,NULL)", (w.capo, DAY - 3))
    out = views.lookup(c, _name(c, w.capo))
    assert "hot-headed" in out["temperament"] and "careful" in out["temperament"], out["temperament"]
    assert out["custody"]["state"].startswith("locked up") and "assault" in out["custody"]["charge"], out["custody"]
    assert not re.search(r"\d", out["temperament"]) and not re.search(r"\d", out["custody"]["state"])


def test_custody_of_a_stranger_stays_hidden_unless_public():
    from connector import views
    w, c = _setup()
    s = _stranger(c, w)
    c.execute("INSERT INTO custody(actor_id,case_id,kind,charge,since_day) VALUES (?,NULL,'held','assault',?)", (s, DAY - 1))
    assert "custody" not in views.lookup(c, _name(c, s))
    c.execute("INSERT INTO crime_reports(day,crime_kind,public,case_id,status) VALUES (?,?,1,77,'open')", (DAY - 1, "assault"))
    c.execute("UPDATE custody SET case_id=77 WHERE actor_id=?", (s,))
    assert "custody" in views.lookup(c, _name(c, s))


def test_org_lookup_words_and_no_label():
    from connector import views
    from engine import org_tension, org_heat
    w, c = _setup()
    others = [int(r[0]) for r in c.execute("SELECT org_actor_id FROM org_profiles WHERE org_actor_id<>? AND sphere='underworld' ORDER BY 1", (w.org,))]
    pair = next(o for o in others if (w.org, o) in set(org_tension.pairs(c, DAY)))
    org_tension.add(c, w.org, pair, "squeeze", 40.0, DAY)
    org_heat.add(c, w.org, DAY, public=1e6)
    out = views.lookup(c, _name(c, w.org))
    d = out["dealings"]
    text = json.dumps(d)
    assert any(_name(c, pair) in x for x in d["with_others"]), d
    assert "squeezing" in text and not re.search(r"\d", text), text
    assert "iron balance" not in json.dumps(out).lower()
    assert d.get("heat") and d.get("led_by"), d


def test_scene_air():
    from connector import org_views
    from engine import org_heat, org_tension
    w, c = _setup()
    others = [int(r[0]) for r in c.execute("SELECT org_actor_id FROM org_profiles WHERE org_actor_id<>? AND sphere='underworld' ORDER BY 1", (w.org,))]
    pair = next(o for o in others if (w.org, o) in set(org_tension.pairs(c, DAY)))
    org_tension.add(c, w.org, pair, "killing", 500.0, DAY)
    org_heat.add(c, w.org, DAY, public=1e6)
    air = org_views.in_the_air(c)
    assert len(air) >= 2 and not any(re.search(r"\d", x) for x in air), air


def test_no_world_words_or_label_in_the_new_module():
    text = (ROOT / "connector" / "org_views.py").read_text(encoding="utf-8").lower()
    for word in ("iron balance", "sabatini", "vannucci", "capo", "soldier", "boss", "consigliere", "saint jude", "pad "):
        assert word not in text, word


def _run_all() -> int:
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc(limit=4)
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
