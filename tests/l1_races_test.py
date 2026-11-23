"""L1 task 5: the opening year's races exist, with the candidates the run's own filing driver would already have, and the clock carries on."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def _conn(tmp):
    return connect(build_saintjude(Path(tmp)))


def test_every_race_in_the_window_exists_and_is_open():
    from engine import offices, races
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        window = int(races._f(c, "race_open_days", 330))
        want = set()
        for o in c.execute("SELECT * FROM offices WHERE filled_by='elected'"):
            nd = offices.next_dates(c, o["office_key"], -1)
            if nd and int(nd["election_day"]) <= window:
                want.add((o["id"], int(nd["election_day"])))
        assert want, "the package has an election in the opening year"
        got = {(r["office_id"], r["election_day"]) for r in c.execute("SELECT office_id,election_day FROM races")}
        assert got == want, (got, want)
        for r in c.execute("SELECT * FROM races"):
            assert r["stage"] == "filing" and r["status"] == "open" and r["election_day"] > 0
        c.close()


def test_candidates_are_eligible_and_not_the_protagonist():
    from engine import offices, races
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        n = 0
        for r in c.execute("SELECT * FROM race_candidates"):
            n += 1
            key = races.office_key(c, r["race_id"])
            ok, why = offices.eligible(c, int(r["actor_id"]), key, 0)
            assert ok, (key, r["actor_id"], why)
            assert r["filed_day"] == 0 and r["dropped_day"] is None
            assert not races._is_player(c, int(r["actor_id"]))
        assert n >= 1
        # a filed race has its venture, as the civic clock would make it
        assert c.execute("SELECT COUNT(*) FROM races WHERE venture_id IS NULL AND id IN (SELECT race_id FROM race_candidates)").fetchone()[0] == 0
        c.close()


def test_the_clock_carries_on_without_a_second_race():
    from engine.simulation import advance_connection
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        c = _conn(t)
        before = c.execute("SELECT COUNT(*) FROM races").fetchone()[0]
        advance_connection(c, 30)
        assert c.execute("SELECT COUNT(*) FROM races").fetchone()[0] == before
        assert c.execute("SELECT COUNT(*) FROM races WHERE status IN ('decided','void')").fetchone()[0] == 0
        dup = c.execute("SELECT office_id,election_day FROM races GROUP BY 1,2 HAVING COUNT(*)>1").fetchall()
        assert not dup
        c.close()


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
