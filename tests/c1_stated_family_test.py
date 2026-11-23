"""C1: what the player states about his own character is canon; what he leaves unsaid is filled; the response says which, field by field.

The transcript case (Saint_Jude_campaign_setup): a 23-year-old Italian-American on the Hill, both parents alive, two younger brothers
(21, 18), the father owns the garage and the three sons work in it. Run: PYTHONPATH=. python tests/c1_stated_family_test.py"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLACE = "San Lorenzo (the Hill)"
TRANSCRIPT = {
    "age": 23, "place": PLACE, "work": "mechanic", "sex": "male", "background": "Italian-American", "concept": "the eldest son at the family garage",
    "family": {"spouse": "none", "children": "none", "parents": "both alive, on the older side",
               "siblings": [{"sex": "male", "age": 21}, {"sex": "male", "age": 18}]},
    "family_business": {"name": "Family Auto Repair", "type": "garage", "owner": "father", "works": ["self", "siblings"]},
}


def _open(tmp):
    from tests.sj_fixture import build_saintjude, connect
    path = build_saintjude(Path(tmp))
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    return connect(path)


def _age(conn, aid):
    day = int(conn.execute("SELECT current_day FROM world_state").fetchone()[0])
    return (day - int(conn.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0])) // 365


def _kin(conn, a, b, kind):
    return conn.execute("SELECT 1 FROM kinship_links WHERE actor_a_id=? AND actor_b_id=? AND kin_kind=?", (a, b, kind)).fetchone() is not None


def _field(out, name):
    return next(x for x in out["as_stated"] + out["filled"] if x["field"] == name)


def test_transcript_case():
    from engine.new_character import create_protagonist
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        out = create_protagonist(c, {**copy.deepcopy(TRANSCRIPT), "accept": True}, "c1-t1")
        assert out["status"] == "created", out
        me = int(out["actor_id"])
        assert _age(c, me) == 23
        parents = [int(r[0]) for r in c.execute("SELECT actor_a_id FROM kinship_links WHERE actor_b_id=? AND kin_kind='parent'", (me,))]
        assert len(parents) == 2, parents
        sex = {p: c.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (p,)).fetchone()[0] for p in parents}
        assert sorted(sex.values()) == ["female", "male"], sex
        father = next(p for p, s in sex.items() if s == "male")
        for p in parents:  # both alive
            assert c.execute("SELECT life_status FROM actor_life_profiles WHERE actor_id=?", (p,)).fetchone()[0] == "living"
            assert c.execute("SELECT status FROM actors WHERE id=?", (p,)).fetchone()[0] == "active"
        sibs = sorted(int(r[0]) for r in c.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='sibling'", (me,)))
        assert sorted(_age(c, s) for s in sibs) == [18, 21], [_age(c, s) for s in sibs]
        for s in sibs:
            assert c.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (s,)).fetchone()[0] == "male"
            assert _kin(c, father, s, "parent"), "each brother is the father's son"
        # all four share a family name and the father's 'both parents' are a couple
        names = {c.execute("SELECT name FROM actors WHERE id=?", (x,)).fetchone()[0].split()[-1] for x in [me, father, *sibs]}
        assert len(names) == 1, names
        # the father owns the garage; the sons are staff; he owns and leads nothing
        biz = c.execute("SELECT id,owner_actor_id FROM civilian_enterprises WHERE json_extract(metadata_json,'$.stated_by_player')=1").fetchall()
        assert len(biz) == 1 and int(biz[0]["owner_actor_id"]) == father, [dict(b) for b in biz]
        staff = {int(r[0]): r[1] for r in c.execute("SELECT actor_id,role FROM enterprise_staff WHERE enterprise_id=? AND status='active'", (biz[0]["id"],))}
        assert set(staff) == {father, me, *sibs} and staff[father] == "owner" and all(staff[x] != "owner" for x in [me, *sibs]), staff
        place = c.execute("SELECT place_kind,owner_ref FROM place_details WHERE enterprise_id=?", (biz[0]["id"],)).fetchone()
        assert place and place["place_kind"] == "garage" and place["owner_ref"] == f"person:{father}", dict(place) if place else None
        assert c.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE owner_actor_id=?", (me,)).fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM underworld_organizations WHERE current_leader_actor_id=?", (me,)).fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM underworld_personnel WHERE actor_id=?", (me,)).fetchone()[0] == 0
        # the response accounts for every field
        fields = {x["field"] for x in out["as_stated"]}
        assert {"age", "father", "mother", "sibling 1", "sibling 2", "family business", "employment", "leads"} <= fields, fields
        assert _field(out, "age")["reason"].startswith("exactly as you said")
        assert any(x["field"] == "money" for x in out["filled"]) and not out["scaled"], out["scaled"]
        assert all(x["reason"] for x in out["as_stated"] + out["filled"])
        c.close()


def test_resubmission_keeps_the_stated_facts():
    from engine.new_character import create_protagonist
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        seen = []
        for variant in ({}, {"draw": 1}, {"holdings": [{"kind": "savings", "amount": "small"}]}, {"concept": "another sentence"}):
            out = create_protagonist(c, {**copy.deepcopy(TRANSCRIPT), **variant}, "c1-t2")
            assert out["status"] == "draft", out
            stated = [(x["field"], x["value"].split(",")[-1].strip() if x["field"].startswith("sibling") else x["value"]) for x in out["as_stated"]
                      if x["field"] in ("age", "sex", "work", "leads", "spouse and children")]
            sib_ages = sorted(x["value"].split(",")[-1].strip() for x in out["as_stated"] if x["field"].startswith("sibling"))
            parents = sorted((x["field"], x["value"].split(",")[0]) for x in out["as_stated"] if x["field"] in ("father", "mother"))
            seen.append((stated, sib_ages, parents))
        assert all(s == seen[0] for s in seen), seen
        # and the identical proposal twice gives the identical people
        a = create_protagonist(c, copy.deepcopy(TRANSCRIPT), "c1-t2b")
        b = create_protagonist(c, copy.deepcopy(TRANSCRIPT), "c1-t2c")
        assert a["as_stated"] == b["as_stated"] and a["summary"] == b["summary"]
        c.close()


def test_implausible_is_refused_with_a_reason():
    from engine.new_character import create_protagonist
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        young_father = copy.deepcopy(TRANSCRIPT)
        young_father["family"]["parents"] = [{"as": "father", "alive": True, "age": 31}, {"as": "mother", "alive": True}]
        out = create_protagonist(c, young_father, "c1-t3")
        assert out["status"] == "refused" and "father" in out["reason"] and "15" in out["reason"], out
        dead_owner = copy.deepcopy(TRANSCRIPT)
        dead_owner["family"]["parents"] = "father dead, mother alive"
        out = create_protagonist(c, dead_owner, "c1-t3b")
        assert out["status"] == "refused" and "dead" in out["reason"] and "father" in out["reason"], out
        twins_far = copy.deepcopy(TRANSCRIPT)
        twins_far["family"]["siblings"] = [{"sex": "male", "age": 21}, {"sex": "female", "age": 62}]
        out = create_protagonist(c, twins_far, "c1-t3c")
        assert out["status"] == "refused" and "mother" in out["reason"], out
        # nothing was made by any refusal
        assert c.execute("SELECT COUNT(*) FROM civilian_enterprises WHERE json_extract(metadata_json,'$.stated_by_player')=1").fetchone()[0] == 0
        c.close()


def test_unsaid_is_filled_and_said_so():
    from engine.new_character import create_protagonist
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        out = create_protagonist(c, {"age": 31, "place": PLACE, "work": "bartender", "concept": "x"}, "c1-t4")
        assert out["status"] == "draft", out
        stated = {x["field"] for x in out["as_stated"]}
        filled = {x["field"] for x in out["filled"]}
        assert "age" in stated and "work" in stated and "sex" in filled, (stated, filled)
        assert {"father", "mother"} <= filled | stated and "money" in filled
        for x in out["filled"]:
            assert x["reason"], x
        c.close()


def test_npc_age_is_as_said():
    from engine import authoring
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        me = int(c.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id LIMIT 1").fetchone()[0])
        for i, age in enumerate((24, 37, 52)):
            out = authoring.author(c, me, "person", {"age": age, "sex": "male", "work": "mechanic", "place": PLACE}, f"c1-npc{i}")
            assert out["age"] == age and _age(c, out["actor_id"]) == age, out
            assert any(x["field"] == "age" for x in out["as_stated"]), out
        c.close()


def test_no_cultivation_leaks_into_the_family():
    """Nobody the protagonist's creation makes carries a Stage, a core or any cultivation row: the world has none."""
    from engine.new_character import create_protagonist
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        out = create_protagonist(c, {**copy.deepcopy(TRANSCRIPT), "accept": True, "stage": "Temper"}, "c1-t6")
        assert out["status"] == "created", out
        assert c.execute("SELECT COUNT(*) FROM cultivation_profiles WHERE actor_id IN (SELECT actor_b_id FROM kinship_links WHERE kin_kind='sibling')"
                         ).fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM cultivation_profiles WHERE actor_id=?", (out["actor_id"],)).fetchone()[0] == 0
        assert not any("stage" in x["field"].lower() or "temper" in str(x["value"]).lower() for x in out["as_stated"] + out["filled"])
        c.close()


def test_entry_date_default_and_later_are_described_not_run():
    from engine import entry
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        d0 = entry.describe(c, {"years": 0.0001})
        assert d0["days"] == 0 or d0["days"] < 2
        later = entry.describe(c, {"date": "1980"})
        assert later["status"] == "draft" and later["years"] > 4.9 and "simulates" in later["note"] and later["to"].endswith("1980"), later
        assert c.execute("SELECT current_day FROM world_state").fetchone()[0] == 0, "describing runs nothing"
        for bad in ({"date": "1974"}, {"date": "soon"}, {"years": -1}):
            try:
                entry.describe(c, bad)
                raise AssertionError(bad)
            except entry.EntryRefused:
                pass
        c.close()


def test_entry_runs_in_chunks_and_stops_once_there():
    """A 20-day entry, not years: the chunking and the stop are the same as for five years, which tests never run."""
    from engine import entry
    from engine.new_character import create_protagonist
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = _open(tmp)
        out = entry.run_chunk(c, {"years": 20 / 365.25})
        assert out["status"] == "reached" and out["remaining_days"] == 0 and 19 <= out["day"] <= 21, out
        done = create_protagonist(c, {**copy.deepcopy(TRANSCRIPT), "accept": True}, "c1-t7")
        assert done["status"] == "created"
        try:
            entry.run_chunk(c, {"years": 1})
            raise AssertionError("an entry after the story began")
        except entry.EntryRefused:
            pass
        c.close()


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("ok  ", t.__name__)
        except Exception:
            failed += 1
            print("FAIL", t.__name__)
            traceback.print_exc()
    sys.exit(1 if failed else 0)
