"""S1: careers on the batch clock integrate the same days, open their time gate on the exact day, and a rising man's career is daily."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CAERNESS_TEST_MODE", "1")
os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def _run(tmp, tiers_on: bool):
    if tiers_on:
        os.environ.pop("CAERNESS_TIERS", None)
    else:
        os.environ["CAERNESS_TIERS"] = "off"
    path = build_saintjude(Path(tmp))
    os.environ["CAERNESS_DB_PATH"] = str(path)
    from engine import civilian, tiers
    conn = connect(path)
    conn.execute("DELETE FROM actor_careers")
    rising = tiers.rising_actor_ids(conn, 0)
    quiet = [r[0] for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id") if r[0] not in rising][:3]
    civilian.ensure_career_track(conn, "s1_gate", "S1 gate", "civic", stages=[{"key": "a"}, {"key": "b", "requirements": {"min_days_in_stage": 20, "auto_advance": True}}])
    civilian.ensure_career_track(conn, "s1_flat", "S1 flat", "civic", stages=[{"key": "only"}])
    gate = civilian.start_career(conn, quiet[0], int(conn.execute("SELECT id FROM career_tracks WHERE key='s1_gate'").fetchone()[0]))
    flat = civilian.start_career(conn, quiet[1], int(conn.execute("SELECT id FROM career_tracks WHERE key='s1_flat'").fetchone()[0]))
    fast = civilian.start_career(conn, quiet[2], int(conn.execute("SELECT id FROM career_tracks WHERE key='s1_flat'").fetchone()[0]))
    conn.execute("UPDATE simulation_profiles SET forced_tier='ACTIVE',forced_until_day=100 WHERE actor_id=?", (quiet[2],))
    stage_b = int(conn.execute("SELECT id FROM career_stages WHERE stage_key='b'").fetchone()[0])
    advanced_on = None
    for day in range(1, 41):
        civilian.review_careers(conn, day)
        if advanced_on is None and int(conn.execute("SELECT current_stage_id FROM actor_careers WHERE id=?", (gate,)).fetchone()[0]) == stage_b:
            advanced_on = day
    exp = lambda cid: json.loads(conn.execute("SELECT experience_json FROM actor_careers WHERE id=?", (cid,)).fetchone()[0])
    out = {"advanced_on": advanced_on, "flat": exp(flat), "fast": exp(fast)}
    conn.close()
    return out


def test_batched_careers_match_daily_ones():
    tmp = tempfile.mkdtemp()
    try:
        base = _run(tmp, tiers_on=False)
        tier = _run(tmp, tiers_on=True)
        import gc
        gc.collect()
        assert base["advanced_on"] == tier["advanced_on"] == 20, (base["advanced_on"], tier["advanced_on"])
        assert base["flat"]["days_in_career"] == 40
        # batched: integrates every day up to its last review, which is within a week of today
        last = tier["flat"]["last_review_day"]
        assert 33 <= last <= 40 and tier["flat"]["days_in_career"] == last
        # a man with a faster tier is reviewed daily
        assert tier["fast"]["days_in_career"] == 40
    finally:
        os.environ.pop("CAERNESS_TIERS", None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_batched_careers_match_daily_ones()
    print("ok s1_careers_test")
