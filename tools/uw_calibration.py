"""Gap 4b calibration report: run N days of the packaged world on a COPY and report what the underworld did,
by outfit type and by city. A plausibility check, not a target.

    python tools/uw_calibration.py --days 365 [--db data/caerness.db] [--out report.json]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def classify(conn, oid):
    from engine.temperament import outfit_class
    return outfit_class(conn, oid)


def report(conn, start_day, org0):
    ops = conn.execute("SELECT * FROM underworld_operations WHERE day>=?", (start_day,)).fetchall()
    cls_cache, city_cache = {}, {}

    def cls(o):
        if o not in cls_cache:
            cls_cache[o] = classify(conn, o)
        return cls_cache[o]

    def city(o):
        if o not in city_cache:
            r = conn.execute("SELECT l.name FROM underworld_organizations o LEFT JOIN locations l ON l.id=o.primary_location_id WHERE o.id=?", (o,)).fetchone()
            city_cache[o] = r[0] if r and r[0] else "?"
        return city_cache[o]

    out = {"operations": Counter(), "by_class": defaultdict(Counter), "by_city": defaultdict(Counter), "styles": Counter(), "styles_by_class": defaultdict(Counter)}
    for o in ops:
        k = o["operation_kind"]
        out["operations"][k] += 1
        out["by_class"][cls(o["organization_id"])][k] += 1
        out["by_city"][city(o["organization_id"])][k] += 1
        if k == "hostile_move":
            st = json.loads(o["metadata_json"] or "{}").get("style")
            out["styles"][st] += 1
            out["styles_by_class"][cls(o["organization_id"])][st] += 1
    n_org = Counter(cls(int(r[0])) for r in conn.execute("SELECT id FROM underworld_organizations WHERE id IN (%s)" % ",".join(str(i) for i in org0)))
    out["outfits_by_class"] = dict(n_org)
    out["hostile_moves_per_outfit"] = {c: round(sum(v[k] for k in ("hostile_move", "targeted_hit", "territorial_attack", "challenge_zone", "poach_protection")) / max(1, n_org[c]), 3)
                                       for c, v in out["by_class"].items()}
    out["deaths_by_harm"] = conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE day>=? AND fatal=1 AND source_kind LIKE 'underworld_%'", (start_day,)).fetchone()[0]
    out["hit_kills"] = conn.execute("SELECT COUNT(*) FROM underworld_operations WHERE day>=? AND operation_kind='targeted_hit' AND result='killed'", (start_day,)).fetchone()[0]
    out["people_events"] = {r[0]: r[1] for r in conn.execute(
        "SELECT event_type,COUNT(*) FROM events WHERE day>=? AND event_type IN ('underworld_desertion','underworld_defection','underworld_informant','underworld_theft','household_service_quit') GROUP BY 1", (start_day,))}
    out["in_arrears_at_end"] = {r[0]: r[1] for r in conn.execute("SELECT holder_kind,COUNT(*) FROM payroll_arrears WHERE months_behind>=1 GROUP BY 1")}
    out["wages_paid_flows"] = conn.execute("SELECT COUNT(*) FROM economic_flows WHERE flow_kind='wage' AND day>=?", (start_day,)).fetchone()[0]
    out["challenges_and_occupations"] = out["operations"].get("challenge_zone", 0) + out["operations"].get("occupy_vacant_turf", 0) + out["operations"].get("hostile_move", 0) + out["operations"].get("poach_protection", 0)
    out["collapsed"] = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='underworld_outfit_collapsed' AND day>=?", (start_day,)).fetchone()[0]
    out["new_gangs"] = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='underworld_new_gang' AND day>=?", (start_day,)).fetchone()[0]
    out["crackdowns"] = conn.execute("SELECT COUNT(*) FROM underworld_enforcement_actions WHERE action_kind='city_crackdown' AND day>=?", (start_day,)).fetchone()[0]
    out["enforcement_actions"] = conn.execute("SELECT action_kind,COUNT(*) FROM underworld_enforcement_actions WHERE day>=? GROUP BY 1", (start_day,)).fetchall()
    out["enforcement_actions"] = {r[0]: r[1] for r in out["enforcement_actions"]}
    out["max_hostile_moves_one_outfit"] = max([sum(1 for o in ops if o["organization_id"] == i and o["operation_kind"] in ("hostile_move", "territorial_attack", "targeted_hit")) for i in org0] or [0])
    out["incidents"] = {r[0]: r[1] for r in conn.execute("SELECT incident_kind,COUNT(*) FROM underworld_incidents WHERE day>=? GROUP BY 1", (start_day,))}
    return json.loads(json.dumps(out, default=dict))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--db", default=str(ROOT / "data" / "caerness.db"))
    ap.add_argument("--out")
    ap.add_argument("--keep", help="copy the finished database here")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "cal.db"
        shutil.copy2(a.db, db)
        os.environ["CAERNESS_DB_PATH"] = str(db)
        from engine.db import connect, init_db
        from engine.simulation import advance_connection
        init_db()
        conn = connect()
        start = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0])
        org0 = [int(r[0]) for r in conn.execute("SELECT id FROM underworld_organizations WHERE status IN ('active','strained','fragmented')")]
        t = time.time()
        advance_connection(conn, a.days)
        conn.commit()
        rep = report(conn, start, org0)
        rep["seconds"] = round(time.time() - t, 1)
        rep["days"] = a.days
        txt = json.dumps(rep, indent=1, sort_keys=True)
        if a.out:
            Path(a.out).write_text(txt, encoding="utf-8")
        if a.keep:
            conn.close()
            shutil.copy2(db, a.keep)
        print(txt)


if __name__ == "__main__":
    main()
