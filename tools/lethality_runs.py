"""Measure lethality on a Saint Jude opening (task B12c). Reports; clamps nothing.

  python tools/lethality_runs.py shares
      Fatal share of a landed planned hit by chance of success, and of a wound by intent, method and severity (fresh actors).
  python tools/lethality_runs.py years [--days 1825] [--seed N] [--timing-only]
      One advance of N days on a copy of the opening: wall-clock, deaths by cause and method (harm_incidents), weekly incidents
      that killed, the answers to killings (respond_killing items and the hits sent) and how the hits went.

It builds in a temporary folder and never touches data/*.db. It runs on any tree that has `tests/sj_fixture.py` (point PYTHONPATH
at the tree), so BASE and the new code are measured by the same script; `method` is passed only where harm.py takes it.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import random
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _open(seed: int | None):
    from tests.sj_fixture import build_saintjude, connect
    tmp = Path(tempfile.mkdtemp())
    path = build_saintjude(tmp)
    os.environ["CAERNESS_DB_PATH"] = str(path)
    os.environ["CAERNESS_WORLD_PACKAGE"] = "saintjude"
    import engine.simulation  # noqa: F401
    conn = connect(path)
    if seed is not None:
        conn.execute("UPDATE world_state SET rng_seed=?", (seed,))
        conn.commit()
    return conn


def _victim(conn):
    from engine.health import ensure_health_profile
    from engine.household_life import set_life_profile
    aid = int(conn.execute("INSERT INTO actors(name,actor_type,status) VALUES (?,'character','active')", (f"[probe] {random.random()}",)).lastrowid)
    set_life_profile(conn, aid, birth_day=-30 * 365, demographic_sex="male", family_formation_eligible=True)
    ensure_health_profile(conn, aid, baseline_health=80)
    return aid


def shares() -> None:
    from engine import underworld_aggression as ag
    from engine.harm import record_harm
    conn = _open(1)
    n = 2000
    print("PLANNED HIT: share of attempts by band, and of landed hits that kill (style hired_killing, lethal intent)")
    new_sig = "conn" in inspect.signature(ag.hit_band).parameters
    for p in (0.15, 0.3, 0.5, 0.7, 0.9):
        c = Counter()
        rng = random.Random(7)
        for _ in range(n):
            c[ag.hit_band(p, rng, True, conn, style="hired_killing") if new_sig else ag.hit_band(p, rng, True)] += 1
        landed = n - c["failed"]
        print(f"  p={p:.2f} failed {c['failed']/n:.2f} wounded {c['wounded']/n:.2f} maimed {c['maimed']/n:.2f} killed {c['killed']/n:.2f}  killed|landed {c['killed']/max(1, landed):.2f}")
    print("BEATING (not lethal intent): killed|landed")
    for p in (0.5, 0.9):
        c = Counter()
        rng = random.Random(7)
        for _ in range(n):
            c[ag.hit_band(p, rng, False, conn) if new_sig else ag.hit_band(p, rng, False)] += 1
        print(f"  p={p:.2f} killed|landed {c['killed']/max(1, n - c['failed']):.3f}")
    takes_method = "method" in inspect.signature(record_harm).parameters
    print("WOUND: fatal share by intent, method and raw severity (record_harm, 600 fresh men each)")
    methods = [None, "fists", "blunt", "blade", "handgun_range", "handgun_point_blank", "execution"] if takes_method else [None]
    k = 0
    for intent in ("hostile", "lethal"):
        for m in methods:
            row = []
            for sev in (30, 60, 100):
                dead = 0
                for i in range(600):
                    k += 1
                    kw = {"method": m} if takes_method else {}
                    r = record_harm(conn, _victim(conn), source_kind="probe", source_ref_id=k, severity=sev, intent_class=intent, **kw)
                    dead += int(r["outcome"] == "fatal")
                row.append(f"sev{sev} {dead/600:.3f}")
            print(f"  {intent:8} {str(m):20} " + "  ".join(row))


def years(days: int, seed: int | None, timing_only: bool) -> None:
    from engine.simulation import advance_connection
    conn = _open(seed)
    t0 = time.time()
    done = 0
    while done < days:
        step = min(30, days - done)
        advance_connection(conn, step)
        done += step
    wall = time.time() - t0
    print(f"ADVANCE {days} days in {wall:.1f} s")
    if timing_only:
        return
    print("DEATHS BY CAUSE (harm_incidents fatal, by source_kind)")
    for r in conn.execute("SELECT source_kind,COUNT(*) FROM harm_incidents WHERE fatal=1 GROUP BY source_kind ORDER BY 2 DESC"):
        print(f"  {r[0]:34} {r[1]}")
    print("HARM INCIDENTS (all, by source_kind and outcome)")
    for r in conn.execute("SELECT source_kind,outcome,COUNT(*) FROM harm_incidents GROUP BY 1,2 ORDER BY 1,2"):
        print(f"  {r[0]:34} {r[1]:11} {r[2]}")
    meths = Counter()
    for r in conn.execute("SELECT metadata_json,fatal FROM harm_incidents"):
        m = json.loads(r[0] or "{}").get("method")
        if m:
            meths[(m, int(r[1]))] += 1
    if meths:
        print("BY METHOD (fatal 0/1)", dict(sorted(meths.items())))
    print("OTHER DEATHS (actors deceased, all causes)", conn.execute("SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='deceased'").fetchone()[0])
    try:
        print("RESPOND_KILLING items by status:", dict(conn.execute("SELECT status,COUNT(*) FROM org_agenda WHERE kind='respond_killing' GROUP BY 1").fetchall()))
        outs = Counter(json.loads(r[0] or "{}").get("outcome") or r[1] for r in conn.execute("SELECT metadata_json,status FROM org_agenda WHERE kind='respond_killing'"))
        print("  answers:", dict(outs))
        print("  killings across outfits, by how the dead man's head answered (org_incidents status):",
              dict(conn.execute("SELECT status,COUNT(*) FROM org_incidents WHERE kind='killing' GROUP BY 1").fetchall()))
        pairs = conn.execute("""SELECT json_extract(metadata_json,'$.killer_org'),raised_to_org_actor_id,COUNT(*),MIN(day),MAX(day) FROM org_incidents
                                WHERE kind='killing' GROUP BY 1,2 ORDER BY 3 DESC""").fetchall()
        print("  killings across outfits by (killer outfit, dead man's outfit): count, first day, last day:",
              [tuple(r) for r in pairs])
        print("  by year:", dict(Counter(int(r[0]) // 365 for r in conn.execute("SELECT day FROM org_incidents WHERE kind='killing'"))))
        team = Counter()
        for r in conn.execute("SELECT subject_id,created_day,status FROM org_agenda WHERE kind='hit' AND json_extract(metadata_json,'$.retaliation')=1"):
            team[(int(r[0]), int(r[1]))] += 1
        if team:
            sizes = Counter(team.values())
            print("  retaliation teams by size (men sent at one killer on one day):", dict(sorted(sizes.items())))
            dead = sum(1 for (k, _d) in team if not conn.execute("SELECT 1 FROM actor_life_profiles WHERE actor_id=? AND life_status<>'deceased'", (k,)).fetchone())
            print(f"  retaliation targets: {len(team)}, dead at the end of the run: {dead}")
        print("HIT items by status:", dict(conn.execute("SELECT status,COUNT(*) FROM org_agenda WHERE kind='hit' GROUP BY 1").fetchall()))
        print("  hits sent as retaliation:", conn.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='hit' AND json_extract(metadata_json,'$.retaliation')=1").fetchone()[0])
        print("KILLED_BY rows:", conn.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='killed_by'").fetchone()[0])
        print("INCIDENTS by kind:", dict(conn.execute("SELECT kind,COUNT(*) FROM org_incidents GROUP BY 1").fetchall()))
        print("  incidents that went too far:", conn.execute("SELECT COUNT(*) FROM harm_incidents WHERE source_kind='org_incident' AND json_extract(metadata_json,'$.went_too_far')=1").fetchone()[0])
        pair = {}
        for r in conn.execute("SELECT day,raised_to_org_actor_id,json_extract(metadata_json,'$.killer_org') FROM org_incidents WHERE kind='killing' ORDER BY day"):
            pair.setdefault(tuple(sorted((int(r[1]), int(r[2] if r[2] is not None else -1)))), []).append(int(r[0]))
        feuds = sorted(((len(v), min(v), max(v)) for v in pair.values()), reverse=True)
        print("  FEUDS (killings, first day, last day), longest first:", feuds[:6])
        print("  answers to a killing (incident status):", dict(conn.execute("SELECT status,COUNT(*) FROM org_incidents WHERE kind='killing' GROUP BY 1").fetchall()))
        inner = Counter()
        for r in conn.execute("""SELECT h.outcome FROM harm_incidents h WHERE h.source_kind='org_action' AND h.intent_class='lethal'
              AND EXISTS (SELECT 1 FROM org_seats a JOIN org_seats b ON a.org_actor_id=b.org_actor_id WHERE a.actor_id=json_extract(h.metadata_json,'$.offender_actor_id') AND b.actor_id=h.actor_id)"""):
            inner[r[0]] += 1
        print("  INTERNAL planned killings (lethal intent; offender and victim share an outfit), by outcome:", dict(inner))
        total = conn.execute("SELECT COUNT(*) FROM org_incidents WHERE kind='killing'").fetchone()[0]
        reply = conn.execute("""SELECT COUNT(*) FROM org_incidents i WHERE i.kind='killing' AND EXISTS (SELECT 1 FROM org_agenda a WHERE a.kind='hit'
              AND a.actor_id=i.offender_actor_id AND a.subject_id=i.victim_actor_id AND json_extract(a.metadata_json,'$.retaliation')=1)""").fetchone()[0]
        print(f"  FIRST STRIKES vs REPLIES: killings across outfits {total}, replies to an earlier killing {reply}, first strikes {total - reply}")
        print("  org_money to heads, total:", conn.execute("SELECT COALESCE(SUM(amount),0) FROM org_money").fetchone()[0])
    except Exception as e:  # noqa: BLE001  (BASE has no retaliation metadata)
        print("  (agenda summary unavailable:", repr(e)[:120], ")")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["shares", "years"])
    ap.add_argument("--days", type=int, default=1825)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--timing-only", action="store_true")
    a = ap.parse_args()
    shares() if a.what == "shares" else years(a.days, a.seed, a.timing_only)


if __name__ == "__main__":
    main()
