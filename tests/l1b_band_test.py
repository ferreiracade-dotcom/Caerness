"""L1b: each canon made-men count lands somewhere inside a small band at the opening (a different place in each playthrough), and nothing
pulls it back to the band once play starts."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def test_every_made_men_figure_is_a_draw_inside_a_band_and_varies_with_the_seed():
    from engine import design, org_membership as om
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = connect(build_saintjude(Path(t)))
        figs = design.package_figures(c)
        keys = [sp["figure"] for _o, sp in om._orgs(c)]
        assert len(keys) >= 9
        for k in keys:
            f = figs[k]
            assert f["kind"] == "draw" and isinstance(f["range"], list), k
            lo, hi = f["range"]
            assert lo < f["default"] < hi or lo <= f["default"] <= hi
            assert int(lo) <= om.preferred(c, [o for o, sp in om._orgs(c) if sp["figure"] == k][0]) <= int(hi), k
            draws = {round(design._draw(seed, k, f)) for seed in range(1, 40)}
            assert len(draws) > 1, (k, draws)  # it differs between playthroughs
        c.close()


def test_nothing_pulls_a_count_back_to_its_band_in_play():
    src = (ROOT / "engine" / "org_membership.py").read_text(encoding="utf-8")
    assert "band_lean" not in src and "def band" not in src


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
