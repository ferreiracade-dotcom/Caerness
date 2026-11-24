"""L1b: every canon-anchored count has a band from package data, and a count outside it leans back unless a run cause works against it."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def _org(c, key):
    return int(c.execute("SELECT org_actor_id FROM org_profiles WHERE package_key=?", (key,)).fetchone()[0])


def test_every_made_men_figure_has_a_band_around_it():
    from engine import org_membership as om
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = connect(build_saintjude(Path(t)))
        n = 0
        for org, sp in om._orgs(c):
            lo, hi = om.band(c, org)
            fig = om.preferred(c, org)
            assert lo < fig < hi or lo <= fig <= hi, (sp["key"], lo, fig, hi)
            assert hi - lo >= 4 or (hi - lo) >= 2, (sp["key"], lo, hi)
            assert lo <= om.made_count(c, org) <= hi, (sp["key"], lo, om.made_count(c, org), hi)  # the opening starts inside its band
            n += 1
        assert n >= 9
        lo, hi = om.band(c, _org(c, "decavalcante"))
        assert lo <= 17 and hi >= 23, (lo, hi)  # 20 give or take the share, at least the minimum width
        c.close()


def test_outside_the_band_leans_back_unless_a_cause_works_against_it():
    from engine import org_membership as om
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = connect(build_saintjude(Path(t)))
        org = _org(c, "decavalcante")
        day = int(c.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        assert om.band_lean(c, org, day) == 0.0
        lo, hi = om.band(c, org)
        made = [int(r[0]) for r in c.execute("SELECT actor_id FROM org_seats WHERE org_actor_id=? AND inducted_day IS NOT NULL AND status='active' ORDER BY actor_id", (org,))]
        for a in made[: len(made) - int(lo) + 3]:
            c.execute("UPDATE org_seats SET status='dead' WHERE actor_id=? AND org_actor_id=?", (a, org))
        assert om.made_count(c, org) < lo
        lean = om.band_lean(c, org, day)
        assert lean > 0.0, lean
        for i in range(3):  # a war: killings that reached the family in the last half year
            c.execute("INSERT INTO org_incidents(day,kind,offender_actor_id,victim_actor_id,matters,raised_to_org_actor_id,status) VALUES (?,?,?,?,1,?,'open')",
                      (day - 10, "killing", made[0], made[1], org))
        assert om.band_lean(c, org, day) < lean, "a cause from the run damps the lean back"
        c.close()


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
