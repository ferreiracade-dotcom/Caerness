"""L1 task 1: the whole Saint Jude opening population has households and kin, at the package's rates, and canon stands."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def _conn(tmp):
    return connect(build_saintjude(Path(tmp)))


def test_adults_have_households_and_kin():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        adults = c.execute("""SELECT COUNT(*) FROM actors a JOIN actor_life_profiles lp ON lp.actor_id=a.id
                              JOIN world_state w ON w.id=1
                              WHERE a.actor_type='character' AND lp.birth_day<=w.current_day-18*365""").fetchone()[0]
        unions = c.execute("SELECT COUNT(*) FROM household_unions WHERE status='active'").fetchone()[0]
        kin = c.execute("SELECT COUNT(*) FROM kinship_links WHERE ended_day IS NULL").fetchone()[0]
        children = c.execute("SELECT COALESCE(SUM(count_estimate),0) FROM latent_entities WHERE archetype='children'").fetchone()[0]
        assert unions * 2 >= 0.5 * adults, (unions, adults)   # a majority of adults are in a union, as in 1975
        assert kin > 1000, kin
        assert children > 1000, children
        c.close()


def test_unions_are_sound():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        # nobody in two active unions
        dup = c.execute("""SELECT x FROM (SELECT actor_a_id x FROM household_unions WHERE status='active'
                           UNION ALL SELECT actor_b_id FROM household_unions WHERE status='active') GROUP BY x HAVING COUNT(*)>1""").fetchall()
        assert not dup, dup[:5]
        # unions are between a man and a woman (the opening draws no other kind)
        bad = c.execute("""SELECT u.id FROM household_unions u JOIN actor_life_profiles a ON a.actor_id=u.actor_a_id
                           JOIN actor_life_profiles b ON b.actor_id=u.actor_b_id
                           WHERE u.status='active' AND a.demographic_sex=b.demographic_sex""").fetchall()
        assert not bad, bad[:5]
        # canon: the seed's own named people got no invented day-0 spouse
        seeded = c.execute("""SELECT COUNT(*) FROM household_unions u JOIN source_identity_map m ON m.entity_kind='actor'
                              AND m.entity_id IN (u.actor_a_id,u.actor_b_id) WHERE u.metadata_json LIKE '%opening_draw%'""").fetchone()[0]
        assert seeded == 0, seeded
        # the Saint Jude path draws no Core or Stage for anyone
        assert c.execute("SELECT COUNT(*) FROM cultivation_profiles").fetchone()[0] == 0
        c.close()


def test_group_rates_follow_the_package():
    from engine.opening_family import marriage_curve_for
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        shares = {}
        for sur, grp in (("Vannucci", "italian"), ("Holloway", "black")):
            r = c.execute("SELECT id FROM actors WHERE actor_type='character' AND name LIKE ? LIMIT 1", (f"% {sur}",)).fetchone()
            assert r, sur
            curve, tags = marriage_curve_for(c, r[0], "male", "ordinary")
            assert f"group:{grp}" in tags, tags
            shares[grp] = curve
        assert shares["black"][2] < shares["italian"][2] and shares["black"][0] > shares["italian"][0], shares
        c.close()


def test_kin_inside_an_organisation_share_a_surname():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        rows = c.execute("""SELECT a.name,b.name FROM kinship_links k JOIN actors a ON a.id=k.actor_a_id JOIN actors b ON b.id=k.actor_b_id
                            WHERE k.kin_kind='sibling' AND k.ended_day IS NULL""").fetchall()
        assert rows
        same = sum(1 for x, y in rows if x.split()[-1] == y.split()[-1])
        assert same >= 0.8 * len(rows), (same, len(rows))
        c.close()


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
