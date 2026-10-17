"""New character (gap 5): shared parts keep behaviour, lived past, proposal to protagonist, Ansel's repair."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

# sha of the opening family resolution on the packaged world, recorded on HEAD before the shared-parts refactor
PARITY_SHA = "a2980851321be4e5c3e1e7cf2fdb02c87309f6f8674909603551ead4afb8522a"


def open_copy(tmp, name="w.db"):
    db = Path(tmp) / name
    shutil.copy2(ROOT / "data" / "caerness.db", db)
    os.environ["CAERNESS_DB_PATH"] = str(db)
    from engine.db import connect, init_db
    init_db()
    conn = connect()
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def parity():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = open_copy(tmp)
        c.execute("UPDATE households SET wealth=0,liquidity=0")  # the recorded draw predates schema 115's household means
        ids = [r[0] for r in c.execute(
            """SELECT actor_id FROM actor_life_profiles WHERE json_extract(metadata_json,'$.marital_status_basis')='opening_draw'
               AND json_extract(metadata_json,'$.marital_status') IN ('widowed','never_married') ORDER BY actor_id LIMIT 80""")]
        for a in ids:
            c.execute("DELETE FROM latent_entities WHERE latent_kind='kin_group' AND json_extract(constraints_json,'$.parent_actor_id')=?", (a,))
            c.execute("UPDATE actor_life_profiles SET metadata_json=json_remove(metadata_json,'$.marital_status_basis','$.marital_status_authority') WHERE actor_id=?", (a,))
        from engine import opening_family as of
        of.resolve_opening_family(c)
        h = hashlib.sha256()
        drop = ("spouse_actor_id", "other_parent_actor_id")  # ids shift when schema 115 adds household staff
        for a in ids:
            m = json.loads(c.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?", (a,)).fetchone()[0])
            for k in drop:
                m.pop(k, None)
            h.update(json.dumps(m, sort_keys=True).encode())
        idset = set(ids)
        for r in c.execute("SELECT constraints_json,count_estimate FROM latent_entities WHERE latent_kind='kin_group' ORDER BY id"):
            cj = json.loads(r[0])
            if cj.get("parent_actor_id") not in idset:
                continue
            for k in drop:
                cj.pop(k, None)
            h.update(str((json.dumps(cj, sort_keys=True), r[1])).encode())
        q = ",".join(map(str, ids))
        h.update(str(c.execute(f"select count(*) from household_unions where actor_a_id in ({q}) or actor_b_id in ({q})").fetchone()[0]).encode())
        assert h.hexdigest() == PARITY_SHA, h.hexdigest()
        # people of any age can be revealed (13-17 used to fail on an invalid life_stage)
        from engine.person_ecology import resolve_background_person
        loc = int(c.execute("SELECT id FROM locations WHERE name LIKE 'Toll%Reach' ORDER BY id LIMIT 1").fetchone()[0])
        for lo, hi in ((0, 1), (5, 8), (13, 17), (16, 17)):
            aid = resolve_background_person(c, reason="t", location_id=loc, min_age=lo, max_age=hi)
            assert aid is not None, (lo, hi)
            st = c.execute("SELECT life_stage FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0]
            assert st in ("infant", "child", "youth"), (lo, hi, st)
        # the seeded pick is stable, and another seed can differ
        from engine.person_ecology import find_background_candidate
        a1 = find_background_candidate(c, location_id=loc, min_age=25, max_age=40, pick_seed="s1")
        a2 = find_background_candidate(c, location_id=loc, min_age=25, max_age=40, pick_seed="s1")
        assert a1["local_uid"] == a2["local_uid"] and a1["partition_id"] == a2["partition_id"]
        c.close()
    print("new_character_test::parity ok")


def _person(conn, age, key, sex="male", work="merchant", stage=None, place="Toll's Reach"):
    from engine import authoring, veto
    loc = veto.find_location(conn, place)
    return authoring.materialise_person(conn, loc=loc, sex=sex, age=age, work_domain=work, stage=stage, elsewhere=False, name=None,
                                        pick_seed=key, call_id=key), loc


def _snap(conn, ids):
    q = ",".join("?" * len(ids))
    return tuple(conn.execute(sql).fetchone()[0] for sql in (
        "SELECT COUNT(*) FROM actors", "SELECT COUNT(*) FROM knowledge", "SELECT COUNT(*) FROM kinship_links",
        "SELECT COUNT(*) FROM relationships", "SELECT COUNT(*) FROM actor_memories", "SELECT COUNT(*) FROM household_members",
        "SELECT COUNT(*) FROM latent_entities", "SELECT COALESCE(SUM(population_estimate),0) FROM background_population_sources"))


def lived_past():
    from engine import new_character as nc
    from engine.person_ecology import FIRST_FEMALE, FIRST_MALE
    from engine.veto import Contradiction
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = open_copy(tmp)
        pop0 = c.execute("SELECT SUM(population_estimate) FROM background_population_sources").fetchone()[0]
        before_actors = {r[0] for r in c.execute("SELECT id FROM actors")}
        aid, loc = _person(c, 42, "lp1")
        s0 = _snap(c, [aid])
        r = nc.fill_lived_past(c, aid, key="lp1", proposal={"work": "merchant"})
        d = r["digest"]
        assert d["knowledge"] >= 12 and d["neighbours"] >= 3 and d["memories"] >= 2, d
        new = {x[0] for x in c.execute("SELECT id FROM actors")} - before_actors
        # names follow sex; population totals unchanged
        for i, n, sx in c.execute("SELECT a.id,a.name,lp.demographic_sex FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id"):
            if i in new and i != aid:
                g = n.split(" ", 1)[0]
                assert g not in (FIRST_MALE if sx == "female" else FIRST_FEMALE), (n, sx)
        assert c.execute("SELECT SUM(population_estimate) FROM background_population_sources").fetchone()[0] == pop0
        # spouse is of the opposite sex and the union predates the first child
        sp = c.execute("SELECT actor_a_id a,actor_b_id b,started_day FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (aid, aid)).fetchone()
        for seed in range(2, 12):  # across seeds, some married men with children
            if sp:
                break
            a2, _ = _person(c, 42, f"lp{seed}")
            nc.fill_lived_past(c, a2, key=f"lp{seed}", proposal={"work": "merchant"})
            aid = a2
            sp = c.execute("SELECT actor_a_id a,actor_b_id b,started_day FROM household_unions WHERE status='active' AND (actor_a_id=? OR actor_b_id=?)", (aid, aid)).fetchone()
        assert sp, "no married draw in 11 seeds"
        other = sp["b"] if sp["a"] == aid else sp["a"]
        sx = lambda i: c.execute("SELECT demographic_sex FROM actor_life_profiles WHERE actor_id=?", (i,)).fetchone()[0]
        assert sx(aid) != sx(other)
        kids = [x[0] for x in c.execute("SELECT actor_b_id FROM kinship_links WHERE actor_a_id=? AND kin_kind='parent'", (aid,))]
        for k in kids:
            bd = c.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (k,)).fetchone()[0]
            assert sp["started_day"] <= bd, "union before first child"
        # no duplicate kin; every tie both ways; starts within life
        dup = c.execute("SELECT COUNT(*) FROM (SELECT actor_a_id,actor_b_id,kin_kind,COUNT(*) n FROM kinship_links GROUP BY 1,2,3 HAVING n>1)").fetchone()[0]
        assert dup == 0
        for a, b in c.execute("SELECT actor_a_id,actor_b_id FROM relationships WHERE actor_a_id=? OR actor_b_id=?", (aid, aid)).fetchall():
            assert c.execute("SELECT 1 FROM relationships WHERE actor_a_id=? AND actor_b_id=?", (b, a)).fetchone(), (a, b)
        birth = c.execute("SELECT birth_day FROM actor_life_profiles WHERE actor_id=?", (aid,)).fetchone()[0]
        for (sd,) in c.execute("SELECT started_day FROM kinship_links WHERE (actor_a_id=? OR actor_b_id=?) AND started_day IS NOT NULL", (aid, aid)):
            assert sd >= birth - 1, (sd, birth)
        # second call adds nothing
        s1 = _snap(c, [aid])
        assert nc.fill_lived_past(c, aid, key="lp1", proposal={"work": "merchant"})["already"]
        assert _snap(c, [aid]) == s1
        # a 12-year-old has a home with parents (most seeds), no spouse
        have = 0
        for seed in range(6):
            kid, _ = _person(c, 12, f"kid{seed}", work=None)
            nc.fill_lived_past(c, kid, key=f"kid{seed}", proposal={})
            assert not c.execute("SELECT 1 FROM household_unions WHERE actor_a_id=? OR actor_b_id=?", (kid, kid)).fetchone()
            have += c.execute("SELECT COUNT(*) FROM kinship_links WHERE actor_b_id=? AND kin_kind='parent'", (kid,)).fetchone()[0] > 0
        assert have >= 4, have
        # widowed at 25 is improbable (refused naming the clash), at 55 it works
        w25, _ = _person(c, 25, "w25", sex="female")
        try:
            nc.fill_lived_past(c, w25, key="w25", proposal={"family": {"spouse": "a widow"}})
            raise AssertionError("widowed at 25 accepted")
        except Contradiction as e:
            assert "widowed" in str(e) or "improbable" in str(e), e
        w55, _ = _person(c, 55, "w55", sex="female")
        nc.fill_lived_past(c, w55, key="w55", proposal={"family": {"spouse": "a widow"}})
        m = json.loads(c.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?", (w55,)).fetchone()[0])
        assert m["marital_status"] == "widowed", m
        c.close()
    print("new_character_test::lived_past ok")


FANE = {"age": 45, "sex": "male", "place": "Toll's Reach", "work": "gang boss", "stage": "Third", "draw": 0, "from_elsewhere": True,
        "affiliation": {"name": "The Fane Combine", "role": "boss", "new": True, "type": "gang"},
        "holdings": [{"kind": "brothel", "amount": "modest"}, {"kind": "gambling den"}, {"kind": "lending"}]}


def _counts(c):
    return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
        "actors", "latent_entities", "engine_meta", "knowledge", "kinship_links", "relationships", "households", "household_members",
        "background_population_identity_links", "player_state", "underworld_organizations", "civilian_enterprises", "resources"))


def proposal():
    from engine import new_character as nc
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = open_copy(tmp)
        c.commit()
        n0 = _counts(c)
        prev = nc.create_protagonist(c, {**FANE}, "p1")
        assert prev["status"] == "draft" and "actor_id" not in prev and prev["summary"]["who"], prev
        assert _counts(c) == n0, "a preview left rows behind"
        prev2 = nc.create_protagonist(c, {**FANE}, "p2")
        assert prev2["summary"] == prev["summary"]
        done = nc.create_protagonist(c, {**FANE, "accept": True}, "p4")
        assert done["status"] == "created", done
        assert done["summary"] == prev["summary"], "accept made a different person from the preview"
        me = done["actor_id"]
        assert c.execute("SELECT player_actor_id FROM player_state").fetchone()[0] == me
        row = c.execute("SELECT * FROM underworld_organizations WHERE current_leader_actor_id=?", (me,)).fetchone()
        assert row and row["name"] == "The Fane Combine" and json.loads(row["metadata_json"])["authored"], dict(row) if row else None
        assert c.execute("SELECT COUNT(*) FROM underworld_racket_sites WHERE organization_id=?", (row["id"],)).fetchone()[0] == 3
        assert c.execute("SELECT 1 FROM underworld_heat WHERE organization_id=?", (row["id"],)).fetchone()
        assert c.execute("SELECT COUNT(*) FROM households WHERE head_actor_id=?", (me,)).fetchone()[0] == 1
        meta = json.loads(c.execute("SELECT metadata_json FROM actor_life_profiles WHERE actor_id=?", (me,)).fetchone()[0])
        assert meta["source"] == "new_character" and meta["not_canon"] and meta["lived_past_key"]
        # a second protagonist is refused; the world runs and the outfit earns
        again = nc.create_protagonist(c, {**FANE, "accept": True}, "p5")
        assert again["status"] == "refused" and "already" in again["reason"]
        from engine.simulation import advance_connection
        advance_connection(c, 30)
        earned = c.execute("SELECT treasury FROM underworld_organizations WHERE id=?", (row["id"],)).fetchone()[0]
        flows = c.execute("SELECT COUNT(*) FROM economic_flows WHERE source_racket_id IS NOT NULL OR target_organization_id=?", (row["id"],)).fetchone()[0]
        assert earned > 0 or flows > 0, (earned, flows)
        c.close()

    # refusals each cite their clash; a corrected resubmit passes
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = open_copy(tmp)
        c.commit()
        base = {"age": 34, "sex": "male", "place": "Toll's Reach", "work": "lamp-lighter", "draw": 0}
        canon = c.execute("SELECT a.name FROM actors a JOIN source_identity_map m ON m.entity_id=a.id AND m.entity_kind='actor' WHERE a.actor_type='character' LIMIT 1").fetchone()[0]
        dead = c.execute("SELECT a.name FROM actors a JOIN actor_life_profiles p ON p.actor_id=a.id WHERE p.life_status<>'living' LIMIT 1").fetchone()[0]
        cases = [({"name": canon}, "canon figure", {"name": "Tam Underhill"}),
                 ({"age": 25, "work": "merchant", "stage": "Third"}, "unheard", {"age": 25, "work": "merchant"}),
                 ({"affiliation": {"name": "Stone Boars", "role": "boss"}}, "already has its leader", {"affiliation": {"name": "Stone Boars", "role": "member"}}),
                 ({"family": {"parents": [{"name": dead}]}}, "dead", {"family": {"parents": "gone"}}),
                 ({"family": {"spouse": "a husband"}}, "same-sex", {"family": {"spouse": "a wife"}})]
        whos = {nc.create_protagonist(c, {**base, "draw": d}, f"d{d}")["summary"]["who"] for d in range(4)}
        assert len(whos) >= 2, "another draw gives another person"
        for bad, needle, fix in cases:
            r = nc.create_protagonist(c, {**base, **bad}, "r1")
            assert r["status"] == "refused" and needle in r["reason"].lower(), (bad, r)
            ok = nc.create_protagonist(c, {**base, **fix}, "r2")
            assert ok["status"] == "draft", (fix, ok)
        # an absurd fortune is scaled down in words, not refused; weird free text passes; a child has no spouse
        big = nc.create_protagonist(c, {**base, "holdings": [{"kind": "cash", "amount": "fortune"}, {"kind": "tea house", "name": "Lamp Tea House", "amount": "fortune"}]}, "r3")
        assert big["status"] == "draft" and big["scaled_down"] and "town" in big["scaled_down"][0]["why"], big
        weird = nc.create_protagonist(c, {**base, "work": "keeper of the dawn bells", "family": {"spouse": "none"}, "concept": "x"}, "r4")
        assert weird["status"] == "draft", weird
        kid = nc.create_protagonist(c, {"age": 12, "place": "Toll's Reach", "draw": 0}, "r5")
        assert kid["status"] == "draft" and "parents' house" in kid["summary"]["household"], kid
        assert _counts(c) == _counts(c)
        # a drawn sex follows the power role: violent outfit ~0.92, trade ~0.85, vice ~0.70; a stated sex is respected
        for cls, text, lo, hi in (("violent", {"name": "The Rooks", "role": "boss", "new": True, "type": "gang"}, .88, .96),
                                  ("trade", {"name": "Weavers Guild", "role": "head", "new": True, "type": "guild"}, .80, .90),
                                  ("vice", {"name": "Velvet House", "role": "owner", "new": True, "type": "brothel"}, .64, .76)):
            assert nc.power_class({"affiliation": text}) == cls, cls
            share = sum(nc.resolve_sex(c, {"affiliation": text}, f"k{i}")[0] == "male" for i in range(300)) / 300
            assert lo <= share <= hi, (cls, share)
        assert nc.power_class({}) is None
        pop = sum(nc.resolve_sex(c, {}, f"k{i}")[0] == "male" for i in range(300)) / 300
        assert 0.4 < pop < 0.6, pop
        fem = nc.create_protagonist(c, {**base, "sex": "female", "work": "criminal"}, "r6")
        assert fem["status"] == "draft" and " woman " in fem["summary"]["who"], fem
        c.close()
    print("new_character_test::proposal ok")


def run(only=None):
    for fn in (parity, lived_past, proposal):
        if only is None or fn.__name__ in only:
            fn()


if __name__ == "__main__":
    run(sys.argv[1:] or None)
