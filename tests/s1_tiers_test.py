"""S1: who is rising is read from live state, never from distance to anyone; a new signal puts a quiet man on the daily clock at once."""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CAERNESS_TEST_MODE", "1")
os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
from tests.sj_fixture import build_saintjude, connect  # noqa: E402


def _open(tmp):
    path = build_saintjude(Path(tmp))
    os.environ["CAERNESS_DB_PATH"] = str(path)
    from engine import tiers
    return connect(path), tiers


def test_module_never_looks_at_place_or_player():
    src = (ROOT / "engine" / "tiers.py").read_text()
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith(("#", '"""')))
    body = re.sub(r'""".*?"""', "", src, flags=re.S)
    for word in ("location", "player", "protagonist", "distance", "route"):
        assert word not in body.lower().replace("module never", ""), word


def test_signals_ignore_distance_and_new_signals_count_next_day():
    tmp = tempfile.mkdtemp()
    try:
        conn, tiers = _open(tmp)
        day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        rising = tiers.rising_actor_ids(conn, day)
        seated = {r[0] for r in conn.execute("SELECT actor_id FROM simulation_profiles WHERE cadence_days<=1")}
        assert seated and seated <= rising
        quiet = [r[0] for r in conn.execute("SELECT id FROM actors WHERE actor_type='character' AND status='active' ORDER BY id") if r[0] not in rising]
        assert len(quiet) > 1000, "most of the city is quiet"
        # moving everybody somewhere else changes nothing: no signal is a place
        locs = [r[0] for r in conn.execute("SELECT id FROM locations ORDER BY id")]
        conn.execute("UPDATE actors SET current_location_id=?", (locs[-1],))
        assert tiers.rising_actor_ids(conn, day) == rising
        # a quiet man far from anything is given a debt he cannot meet, an office, and a faster tier: each puts him on the daily clock
        a, b, c = quiet[0], quiet[1], quiet[2]
        conn.execute("""INSERT INTO agreement_terms(ref_kind,ref_id,debtor_ref,creditor_ref,amount_usd,every_days,next_due_day,breach_word,purpose,missed_count,owed_usd,status,created_day)
                        VALUES ('test',1,?,?,100,30,?,'late','test',1,100,'active',?)""", (f"person:{a}", f"person:{b}", day, day))
        off = conn.execute("SELECT id FROM offices LIMIT 1").fetchone()
        if off:
            conn.execute("INSERT INTO office_terms(office_id,actor_id,seat_no,start_day,how) VALUES (?,?,99,?,'special')", (off[0], b, day))
        conn.execute("UPDATE simulation_profiles SET forced_tier='ACTIVE',forced_until_day=? WHERE actor_id=?", (day + 5, c))
        now = tiers.rising_actor_ids(conn, day + 1)
        assert a in now and c in now and (b in now or not off)
        # with tiers off everyone is rising
        os.environ["CAERNESS_TIERS"] = "off"
        try:
            assert tiers.is_rising(conn, quiet[500], day) and not tiers.batching(conn)
        finally:
            os.environ.pop("CAERNESS_TIERS")
        conn.close()
    finally:
        import gc
        gc.collect()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_module_never_looks_at_place_or_player()
    test_signals_ignore_distance_and_new_signals_count_next_day()
    print("ok s1_tiers_test")
