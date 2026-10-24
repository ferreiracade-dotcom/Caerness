"""E-005 to E-008: Design figures are drawn once per run from the run seed, held, logged, derived and range-bound."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _build(path: Path) -> None:
    from tools.build_opening import build_opening
    build_opening(path, package="saintjude")


def run():
    from engine import design
    from engine.db import connect
    tmp = Path(tempfile.mkdtemp())
    a, b = tmp / "a.db", tmp / "b.db"
    _build(a)
    os.environ["CAERNESS_DB_PATH"] = str(a)
    with connect() as conn:
        figs = design.package_figures(conn)
        n = conn.execute("SELECT COUNT(*) FROM design_figures").fetchone()[0]
        assert n == len(figs), (n, len(figs))
        rate = design.figure(conn, "population_decline_pct")
        assert 0.4 <= rate <= 1.5, rate
        assert design.figure(conn, "population_city_1975_m") == 1.1  # fixed
        row = conn.execute("SELECT seed,cause FROM design_figures WHERE key='population_decline_pct'").fetchone()
        assert row[0] is not None and "draw" in row[1]
        assert conn.execute("SELECT COUNT(*) FROM design_figure_log WHERE key='population_decline_pct'").fetchone()[0] == 1
        # every draw lies inside its range
        for k, v, lo, hi in conn.execute("SELECT key,value,lo,hi FROM design_figures WHERE kind='draw' AND lo IS NOT NULL"):
            assert lo - 1e-9 <= v <= hi + 1e-9, (k, v, lo, hi)
        # derived follows its inputs
        p80 = design.figure(conn, "population_1980_m")
        assert abs(p80 - 1.1 * (1 - rate / 100) ** 5) < 1e-9, p80
        # held: drawing again changes nothing
        design.draw_all(conn)
        assert design.figure(conn, "population_decline_pct") == rate
        # range enforced, cause required, derived recomputed
        got = design.set_figure(conn, "population_decline_pct", 3.0, cause="test: asked past the range")
        assert got == 1.5
        assert abs(design.figure(conn, "population_1980_m") - 1.1 * (1 - 1.5 / 100) ** 5) < 1e-9
        try:
            design.set_figure(conn, "population_decline_pct", 1.0, cause="")
            raise AssertionError("a change without a cause was accepted")
        except design.DesignError:
            pass
        assert design.set_figure(conn, "population_decline_pct", 2.0, cause="test: dated cause", exception=True) == 2.0
        assert design.figure(conn, "no_such_figure", "x") == "x"
        first = {k: v for k, v in conn.execute("SELECT key,value FROM design_figures WHERE kind='draw'")}
        conn.commit()
    # same seed -> same draws
    _build(b)
    os.environ["CAERNESS_DB_PATH"] = str(b)
    with connect() as conn:
        second = {k: v for k, v in conn.execute("SELECT key,value FROM design_figures WHERE kind='draw'")}
    first["population_decline_pct"] = second["population_decline_pct"]  # moved in the first run only
    assert first == second
    print("design_figures_runtime_test PASS")


if __name__ == "__main__":
    run()
