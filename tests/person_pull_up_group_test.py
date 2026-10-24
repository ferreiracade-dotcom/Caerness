"""Pulling people up from the background by name group and in batches (Saint Jude mob minimum, task 4)."""
from __future__ import annotations
import os, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sj_fixture import build_saintjude, connect
from engine.person_ecology import resolve_background_people
from engine.world_package import package_for

KW = dict(reason="t", demand_kind="t", subtype=None, min_age=18, max_age=60, demographic_sex="male", pick_seed="t")


def _setup():
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    conn = connect(path)
    city = int(conn.execute("SELECT id FROM locations WHERE name='Saint Jude'").fetchone()[0])
    return conn, city, package_for(conn)


def _unlinked(conn) -> int:
    return int(conn.execute("""SELECT COUNT(*) FROM background_person_profiles p LEFT JOIN background_population_identity_links l
        ON l.partition_id=p.partition_id AND l.local_uid=p.local_uid WHERE p.status='background' AND l.actor_id IS NULL""").fetchone()[0])


def _profiles(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM background_person_profiles").fetchone()[0])


def _surname(conn, aid: int) -> str:
    return str(conn.execute("SELECT family_name FROM background_person_profiles WHERE actor_id=?", (aid,)).fetchone()[0])


def test_name_group_filter_only_returns_that_group():
    conn, city, pkg = _setup()
    italian = set(pkg.name_groups["italian"]["family"])
    ids = resolve_background_people(conn, 50, location_id=city, name_group="italian", **KW)
    assert len(ids) == 50 and len(set(ids)) == 50
    assert all(_surname(conn, i) in italian for i in ids)
    for i in ids:
        a = conn.execute("SELECT name,current_location_id FROM actors WHERE id=?", (i,)).fetchone()
        assert a["current_location_id"] == city and a["name"].split()[1] in italian, dict(a)
    try:
        resolve_background_people(conn, 1, location_id=city, name_group="nope", **KW)
        raise AssertionError("an unknown group must be refused")
    except ValueError:
        pass


def test_each_pulled_person_has_one_link_and_conserves_the_sample():
    conn, city, pkg = _setup()
    before_unlinked, before_profiles = _unlinked(conn), _profiles(conn)
    ids = resolve_background_people(conn, 30, location_id=city, name_group="italian", **KW)
    grown = _profiles(conn) - before_profiles
    assert len(ids) == 30 and grown > 0
    assert _unlinked(conn) == before_unlinked + grown - 30
    for i in ids:
        assert conn.execute("SELECT COUNT(*) FROM background_population_identity_links WHERE actor_id=?", (i,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM person_resolution_provenance WHERE actor_id=?", (i,)).fetchone()[0] == 1


def test_pull_up_is_idempotent_per_profile():
    conn, city, pkg = _setup()
    ids = resolve_background_people(conn, 5, location_id=city, name_group="italian", **KW)
    again = resolve_background_people(conn, 5, location_id=city, name_group="italian", **KW)
    assert len(again) == 5 and not set(ids) & set(again)
    # one profile, one actor: no profile is linked twice
    assert conn.execute("SELECT COUNT(*) FROM (SELECT partition_id,local_uid FROM background_population_identity_links "
                        "GROUP BY partition_id,local_uid HAVING COUNT(*)>1)").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM background_person_profiles WHERE status='resolved' AND actor_id IN (%s)"
                        % ",".join("?" * 10), ids + again).fetchone()[0] == 10


def test_batch_is_fast():
    conn, city, pkg = _setup()
    italian = set(pkg.name_groups["italian"]["family"])
    p0 = _profiles(conn)
    t = time.time()
    ids = resolve_background_people(conn, 1200, location_id=city, name_group="italian", min_age=17, max_age=45,
                                    demographic_sex="male", reason="t", demand_kind="t", subtype=None, pick_seed="t")
    dt = time.time() - t
    print(f"1200 italian men: {len(ids)} pulled in {dt:.1f}s, sample grew by {_profiles(conn) - p0}")
    assert len(ids) == 1200 and dt < 15
    assert all(_surname(conn, i) in italian for i in ids)


def test_criminal_weight_biases_toward_familiarity():
    conn, city, pkg = _setup()
    kw = dict(location_id=city, name_group="italian", **KW)
    def mean_cf(ids):
        return sum(float(conn.execute("SELECT criminal_familiarity FROM background_person_profiles WHERE actor_id=?", (i,)).fetchone()[0]) for i in ids) / len(ids)
    plain = resolve_background_people(conn, 40, **kw)
    heavy = resolve_background_people(conn, 40, criminal_weight=5.0, **{**kw, "pick_seed": "u"})
    assert mean_cf(heavy) > mean_cf(plain)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("person_pull_up_group_test: ok")
