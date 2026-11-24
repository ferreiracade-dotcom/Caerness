"""Prison J1.7: the whole chain on the lived opening. Arrest, trial, sentence, stay, hearings and release hold together for a run of days; the same seed gives the same stays.

Slow (several runs of 120 to 400 days). Run: PYTHONPATH=. python tests/j1_chain_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lethality_runs import _open  # noqa: E402
from tools.prison_year import read  # noqa: E402

from engine import prison  # noqa: E402
from engine.player import set_player  # noqa: E402
from engine.simulation import advance_connection  # noqa: E402


def _run(days: int, seed: int = 7, protagonist: bool = False):
    conn = _open(seed)
    held = conn.execute("SELECT actor_id FROM custody WHERE kind='held' ORDER BY id LIMIT 1").fetchone()
    man = int(held[0]) if held else None
    if protagonist and man is not None:
        set_player(conn, man)
    for _ in range(days // 30):
        advance_connection(conn, 30)
    return conn, man


def _stays(conn):
    return [tuple(r) for r in conn.execute("SELECT actor_id,facility_id,group_id,sentence_id,since_day,until_day,status FROM inmate_stays ORDER BY id")]


def test_chain_holds_together_over_400_days():
    conn, man = _run(390)
    assert prison.enabled(conn)
    res = read(conn)
    assert res["stays_total"] >= 1 and man is not None
    assert not any(res["inconsistent"].values()), res["inconsistent"]  # no man in two stays; a serving sentence has a stay; a stay has a sentence or a hold; inside seats are for men inside
    assert res["integrity"] == "ok" and res["fk_violations"] == 0
    assert conn.execute("SELECT COUNT(*) FROM inmate_stays WHERE actor_id=?", (man,)).fetchone()[0] >= 1  # the man the lived opening already holds is placed


def test_protagonist_held_at_the_start_is_under_the_same_rules():
    conn, man = _run(120, protagonist=True)
    res = read(conn)
    assert not any(res["inconsistent"].values()), res["inconsistent"]
    assert conn.execute("SELECT COUNT(*) FROM inmate_stays WHERE actor_id=?", (man,)).fetchone()[0] == 1
    st = conn.execute("SELECT * FROM inmate_stays WHERE actor_id=?", (man,)).fetchone()
    assert st["status"] == "inside" and st["facility_id"] is not None


def test_same_seed_same_stays():
    a, _ = _run(120)
    b, _ = _run(120)
    assert _stays(a) == _stays(b) and _stays(a)


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in tests:
        f()
        print("ok", n, flush=True)
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
