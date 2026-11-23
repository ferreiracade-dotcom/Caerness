"""P1 Task 11: five simulated years of Saint Jude politics, measured and written to runs/p1_measures/.

Slow. Asserts only time (the civic tick's own cost over five years under 10 minutes, a 30-day step under 10 s);
the other figures are reported, not asserted: the owner reads them.

Run: PYTHONPATH=. python tests/p1_measures_test.py"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.outfit_choice_fixture import open_world as _open_world

OUT = ROOT / "runs" / "p1_measures"
SEEDS = (3, 7, 11)
STEP = 30
YEARS = 5


def _one(seed: int) -> dict:
    from engine import simulation
    w = _open_world()
    c = w.conn
    c.execute("UPDATE world_state SET rng_seed=? WHERE id=1", (seed,))
    civic = {"t": 0.0, "slowest": 0.0}
    real = simulation.process_due_civic

    def timed(conn, day, **kw):
        t0 = time.perf_counter()
        try:
            return real(conn, day, **kw)
        finally:
            dt = time.perf_counter() - t0
            civic["t"] += dt
            civic["slowest"] = max(civic["slowest"], dt)
    simulation.process_due_civic = timed
    step_worst = 0.0
    try:
        for _ in range(YEARS * 365 // STEP):
            t0 = time.perf_counter()
            simulation.advance_connection(c, STEP)
            step_worst = max(step_worst, time.perf_counter() - t0)
    finally:
        simulation.process_due_civic = real
    c.commit()
    races = c.execute("SELECT * FROM races WHERE status='decided' AND COALESCE(special,0)=0 ORDER BY election_day,id").fetchall()
    inc_won = inc_total = reform_won = reform_total = 0
    turnout = []
    for r in races:
        res = json.loads(r["result_json"] or "{}")
        win = res.get("winner")
        if win is None:
            continue
        why = (res.get("why") or {}).get(str(win)) or {}
        if "incumbent" in why and any(float((res.get("why") or {}).get(k, {}).get("incumbent", 0) or 0) > 0 for k in (res.get("why") or {})):
            inc_total += 1
            inc_won += 1 if float(why["incumbent"]) > 0 else 0
        votes = res.get("votes") or {}
        if votes:
            turnout.append(sum(float(x) for x in votes.values()))
        pr = c.execute("SELECT o.package_key FROM race_candidates rc JOIN org_profiles o ON o.org_actor_id=rc.party_org_id WHERE rc.race_id=? AND rc.actor_id=?", (int(r["id"]), int(win))).fetchone()
        reform_total += 1
        reform_won += 1 if pr and pr[0] == "reform_clubs" else 0
    n = lambda sql: int(c.execute(sql).fetchone()[0])  # noqa: E731
    women = n("""SELECT COUNT(DISTINCT t.actor_id) FROM office_terms t JOIN actor_life_profiles p ON p.actor_id=t.actor_id
                 WHERE p.demographic_sex='female'""")
    stakes = n("SELECT COUNT(*) FROM field_holdings WHERE ended_day IS NULL")
    holders = max(1, n("SELECT COUNT(DISTINCT holder_kind||':'||holder_id) FROM field_holdings WHERE ended_day IS NULL"))
    return {
        "seed": seed, "civic_seconds": round(civic["t"], 1), "civic_slowest_call": round(civic["slowest"], 2), "slowest_30_day_step": round(step_worst, 1),
        "races_decided": len(races), "incumbent_races": inc_total, "incumbent_reelected": inc_won,
        "reform_wins": reform_won, "races_with_winner": reform_total, "mean_votes_per_race": round(sum(turnout) / len(turnout), 1) if turnout else None,
        "fraud_reports": n("SELECT COUNT(*) FROM crime_reports WHERE crime_kind='election_fraud'"),
        "bribery_reports": n("SELECT COUNT(*) FROM crime_reports WHERE crime_kind='bribery'"),
        "terms_ended_convicted": n("SELECT COUNT(*) FROM office_terms WHERE ended_how='convicted'"),
        "women_ever_in_office": women, "stakes_live": stakes, "stakes_per_holder": round(stakes / holders, 2),
        "payments_started": n("SELECT COUNT(*) FROM org_arrangements WHERE position_key LIKE 'political:%'"),
        "payments_by_org": n("SELECT COUNT(*) FROM org_arrangements WHERE position_key LIKE 'political:%' AND payer_kind='org'"),
        "fraud_acts": sum(len((json.loads(r[0] or "{}")).get("fraud") or []) for r in c.execute("SELECT result_json FROM races")),
        "fraud_caught": sum(1 for r in c.execute("SELECT result_json FROM races") for x in (json.loads(r[0] or "{}")).get("fraud") or [] if x.get("exposed")),
        "bribery_sentences": n("SELECT COUNT(*) FROM sentences WHERE crime_kind='bribery'"),
        "seats_filled": n("SELECT COUNT(*) FROM office_terms WHERE end_day IS NULL"),
    }


def _has(c, table, col) -> bool:
    return any(r[1] == col for r in c.execute(f"PRAGMA table_info({table})"))


def test_five_years_measures():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [_one(s) for s in SEEDS]
    (OUT / "measures.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for r in rows:
        print(json.dumps(r))
    for r in rows:
        assert r["civic_seconds"] < 600, r
        assert r["civic_slowest_call"] < 10, r


if __name__ == "__main__":
    try:
        test_five_years_measures()
        print("PASS test_five_years_measures")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
