"""How the law response reads against 1975 (task B13b). One advance on a copy of the Saint Jude opening, then reports by crime kind:
reports, offender known, arrests (at filing or later), buried, never solved, dispositions, sentences. Reports; enforces nothing.

  python tools/law_stats.py [--days 1095] [--seed 7]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def law_figures(conn) -> dict:
    """Reports, arrests, dispositions and sentences by crime kind on a database that has been run (no simulation here)."""
    held_reports = {int(r[0]) for r in conn.execute(
        """SELECT DISTINCT json_extract(l.metadata_json,'$.crime_report_id') FROM custody c JOIN law_enforcement_cases l ON l.id=c.case_id
           WHERE json_extract(l.metadata_json,'$.crime_report_id') IS NOT NULL""")}
    rows = [(r[0], r[1], r[2], r[3], r[4], 1 if int(r[0]) in held_reports else 0, r[5]) for r in conn.execute(
        "SELECT id,crime_kind,offender_actor_id,status,case_id,COALESCE(json_extract(metadata_json,'$.identified'),1) FROM crime_reports")]
    by = defaultdict(Counter)
    for rid, kind, off, status, cid, held, ident in rows:
        b = by[kind]
        b["reports"] += 1
        b["named"] += 1 if (off is not None and ident) else 0
        b["arrested"] += 1 if held else 0
        b["buried"] += 1 if status == "buried" else 0
    out: dict = {"by_kind": {k: dict(v) for k, v in sorted(by.items())}}
    tot = sum(b["reports"] for b in by.values()); ar = sum(b["arrested"] for b in by.values())
    out["all"] = {"reports": tot, "arrested": ar, "arrested_pct": round(100 * ar / max(1, tot), 1)}
    d = Counter(r[0] for r in conn.execute("SELECT kind FROM case_dispositions"))
    n = max(1, sum(d.values()))
    out["dispositions"] = {k: f"{v} ({100 * v / n:.0f}%)" for k, v in d.items()}
    dk = conn.execute("SELECT r.crime_kind,d.kind,COUNT(*) FROM case_dispositions d JOIN crime_reports r ON r.id=d.report_id GROUP BY 1,2").fetchall()
    tab = defaultdict(dict)
    for k, dd, c in dk:
        tab[k][dd] = c
    out["dispositions_by_kind"] = dict(tab)
    s_ = sorted(r[0] for r in conn.execute("SELECT term_days FROM sentences"))
    if s_:
        out["sentences"] = {"n": len(s_), "median_years": round(s_[len(s_) // 2] / 365, 1), "p10": round(s_[len(s_) // 10] / 365, 1), "p90": round(s_[9 * len(s_) // 10] / 365, 1)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1095)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    from tools.lethality_runs import _open
    from engine.simulation import advance_connection
    conn = _open(a.seed)
    done = 0
    while done < a.days:
        advance_connection(conn, min(30, a.days - done))
        done += 30
    conn.commit()
    import json
    print(json.dumps({"seed": a.seed, "days": a.days, **law_figures(conn)}, indent=1))


if __name__ == "__main__":
    main()
