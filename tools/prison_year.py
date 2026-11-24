"""One-year (or shorter) prison measurement on a copy of the Saint Jude opening (J1). Reports; enforces nothing.

  python tools/prison_year.py [--days 365] [--seed 7] [--off] [--out runs/x.json]

Advances in 30-day steps and prints the wall time of each; at the end reads the prison population, the inside groups, events, channels and
reviews, and the consistency of stays against sentences and custody. --off turns the prison layer off (no package prison data) for the cost comparison.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _count(conn, sql, *a):
    return [tuple(r) for r in conn.execute(sql, a).fetchall()]


def read(conn) -> dict:
    from engine import prison
    out: dict = {}
    if not prison.enabled(conn):
        return out
    out["stays_total"] = conn.execute("SELECT COUNT(*) FROM inmate_stays").fetchone()[0]
    out["inside_now"] = conn.execute("SELECT COUNT(*) FROM inmate_stays WHERE status='inside'").fetchone()[0]
    out["stays_by_status"] = dict(_count(conn, "SELECT status,COUNT(*) FROM inmate_stays GROUP BY 1"))
    out["by_facility_inside"] = dict(_count(conn, "SELECT f.name,COUNT(*) FROM inmate_stays s JOIN facilities f ON f.id=s.facility_id WHERE s.status='inside' GROUP BY 1"))
    out["by_group_inside"] = dict(_count(conn, "SELECT g.group_key,COUNT(*) FROM inmate_stays s JOIN facility_groups g ON g.id=s.group_id WHERE s.status='inside' GROUP BY 1"))
    out["events"] = dict(_count(conn, "SELECT kind,COUNT(*) FROM prison_events GROUP BY 1"))
    out["channels"] = dict(_count(conn, "SELECT kind||'/'||status,COUNT(*) FROM prison_channels GROUP BY 1"))
    out["contacts"] = conn.execute("SELECT COUNT(*) FROM prison_contacts").fetchone()[0]
    out["reviews"] = dict(_count(conn, "SELECT kind||'/'||status||'/'||COALESCE(outcome,''),COUNT(*) FROM law_reviews GROUP BY 1"))
    out["sentences"] = dict(_count(conn, "SELECT status,COUNT(*) FROM sentences GROUP BY 1"))
    out["held_custody"] = conn.execute("SELECT COUNT(*) FROM custody WHERE kind='held'").fetchone()[0]
    # consistency
    bad: dict = {}
    bad["two_inside_stays"] = conn.execute("SELECT COUNT(*) FROM (SELECT actor_id FROM inmate_stays WHERE status='inside' GROUP BY 1 HAVING COUNT(*)>1)").fetchone()[0]
    bad["serving_without_stay"] = conn.execute("""SELECT COUNT(*) FROM sentences s WHERE s.status='serving'
        AND NOT EXISTS (SELECT 1 FROM inmate_stays t WHERE t.actor_id=s.actor_id AND t.status='inside')""").fetchone()[0]
    bad["inside_without_sentence_or_held"] = conn.execute("""SELECT COUNT(*) FROM inmate_stays t WHERE t.status='inside'
        AND NOT EXISTS (SELECT 1 FROM sentences s WHERE s.actor_id=t.actor_id AND s.status='serving')
        AND NOT EXISTS (SELECT 1 FROM custody c WHERE c.actor_id=t.actor_id AND c.kind='held')""").fetchone()[0]
    bad["inside_seat_not_inside"] = conn.execute("""SELECT COUNT(*) FROM org_seats o JOIN facility_groups g ON g.org_actor_id=o.org_actor_id
        WHERE o.status='active' AND NOT EXISTS (SELECT 1 FROM inmate_stays t WHERE t.actor_id=o.actor_id AND t.status='inside' AND t.group_id=g.id)""").fetchone()[0]
    out["inconsistent"] = bad
    out["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    out["fk_violations"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--off", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    from tools.lethality_runs import _open
    from engine.simulation import advance_connection
    from engine import prison
    t_open = time.time()
    conn = _open(a.seed)
    if a.off:
        prison.rules = lambda c: {}  # a package with no prison data
    open_s = time.time() - t_open
    steps, done = [], 0
    t0 = time.time()
    while done < a.days:
        step = min(30, a.days - done)
        t1 = time.time()
        advance_connection(conn, step)
        steps.append(round(time.time() - t1, 1))
        done += step
        print(f"seed {a.seed} off={a.off}: {done}/{a.days} days, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    res = {"seed": a.seed, "days": a.days, "off": a.off, "open_s": round(open_s, 1), "wall_s": round(time.time() - t0, 1), "step_s": steps}
    res.update(read(conn))
    txt = json.dumps(res, indent=1, default=str)
    print(txt)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
