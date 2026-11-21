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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1095)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--keep", default="")
    a = ap.parse_args()
    from tools.lethality_runs import _open
    from engine.simulation import advance_connection
    conn = _open(a.seed)
    done = 0
    while done < a.days:
        advance_connection(conn, min(30, a.days - done))
        done += 30
    conn.commit()
    rows = conn.execute("SELECT r.id,r.crime_kind,r.offender_actor_id,r.status,r.case_id,"
                        "(SELECT COUNT(*) FROM custody c WHERE c.case_id IN (SELECT id FROM law_enforcement_cases WHERE json_extract(metadata_json,'$.crime_report_id')=r.id)) FROM crime_reports r").fetchall()
    by = defaultdict(Counter)
    for rid, kind, off, status, cid, held in rows:
        b = by[kind]
        b["reports"] += 1
        b["offender_known"] += 1 if off is not None else 0
        b["arrested"] += 1 if held else 0
        b["buried"] += 1 if status == "buried" else 0
    print(f"seed {a.seed} days {a.days}")
    for kind, b in sorted(by.items()):
        n = b["reports"]
        print(f"  {kind:10s} reports {n:5d} known {b['offender_known']:5d} ({100*b['offender_known']/n:.0f}%) arrested {b['arrested']:4d} ({100*b['arrested']/n:.1f}% of reports, {100*b['arrested']/max(1,b['offender_known']):.0f}% of known) buried {b['buried']}")
    tot = sum(b["reports"] for b in by.values()); ar = sum(b["arrested"] for b in by.values())
    print(f"  all        reports {tot} arrested {ar} ({100*ar/max(1,tot):.1f}%)")
    d = Counter(r[0] for r in conn.execute("SELECT kind FROM case_dispositions"))
    n = sum(d.values())
    print("  dispositions", {k: f"{v} ({100*v/n:.0f}%)" for k, v in d.items()}, "total", n)
    dk = conn.execute("SELECT r.crime_kind,d.kind,COUNT(*) FROM case_dispositions d JOIN crime_reports r ON r.id=d.report_id GROUP BY 1,2").fetchall()
    tab = defaultdict(dict)
    for k, dd, c in dk:
        tab[k][dd] = c
    for k, v in sorted(tab.items()):
        print("   ", k, v)
    s = [r[0] for r in conn.execute("SELECT term_days FROM sentences")]
    if s:
        s.sort()
        print(f"  sentences {len(s)} median {s[len(s)//2]/365:.1f}y p10 {s[len(s)//10]/365:.1f} p90 {s[9*len(s)//10]/365:.1f}")
    # homicide: killings of mob-sphere vs ordinary
    h = conn.execute("SELECT COUNT(*),SUM(offender_actor_id IS NOT NULL) FROM crime_reports WHERE crime_kind='homicide'").fetchone()
    print("  homicide reports", h[0], "offender known", h[1])


if __name__ == "__main__":
    main()
