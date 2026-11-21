"""Measure the understanding between the families on a Saint Jude opening (task B12e). Reports; clamps and enforces nothing.

  python tools/balance_runs.py [--days 1825] [--seed 7] [--out runs/x.json]

One advance on a copy of the opening (built in a temporary folder; never touches data/*.db), read at each year end: killings and deaths by
cause, victims by rank, made men lost against inductions, organisation sizes, tension between each pair (level, peak, what moved it),
first strikes and what came before them, how far the wars widened, attacks with several dead, which families fell apart, wall-clock.
Real-world figures in the notes are approximate and from memory. It runs on any tree that has tests/sj_fixture.py.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MOB_SOURCES = ("org_action", "org_incident", "org_incident_bystander")


def _opening(seed):
    sys.path.insert(0, str(ROOT))
    from tools.lethality_runs import _open
    return _open(seed)


def _names(conn):
    return {int(r[0]): (r[2] or r[1]) for r in conn.execute("SELECT p.org_actor_id,a.name,p.package_key FROM org_profiles p JOIN actors a ON a.id=p.org_actor_id")}


def _sizes(conn):
    out = {}
    for r in conn.execute("SELECT org_actor_id,COUNT(*),SUM(inducted_day IS NOT NULL) FROM org_seats WHERE status IN ('active','held') GROUP BY 1"):
        out[int(r[0])] = (int(r[1]), int(r[2] or 0))
    return out


def report(days: int, seed: int | None) -> dict:
    from engine.simulation import advance_connection
    conn = _opening(seed)
    callers: Counter = Counter()
    import engine.outfit_choices as _oc
    _real = _oc.kill

    def _wrapped(conn_, killer, victim, day, **kw):  # counts what asked for each killing and how it ended, by the calling function
        res = _real(conn_, killer, victim, day, **kw)
        callers[(sys._getframe(1).f_code.co_name, str(res)[:6])] += 1
        return res
    _oc.kill = _wrapped
    for mod in list(sys.modules.values()):
        if getattr(mod, "kill", None) is _real:
            mod.kill = _wrapped
    names = _names(conn)
    start_sizes = _sizes(conn)
    sizes_by_year = {0: start_sizes}
    t0 = time.time()
    done = 0
    while done < days:
        step = min(30, days - done)
        advance_connection(conn, step)
        done += step
        if done % 365 == 0 or done == days:
            sizes_by_year[done // 365 if done % 365 == 0 else (done + 364) // 365] = _sizes(conn)
    wall = time.time() - t0
    years = max(1, round(days / 365))
    out: dict = {"days": days, "seed": seed, "wall_s": round(wall, 1)}

    # deaths and killings
    fatal = conn.execute(
        "SELECT h.id,h.day,h.actor_id,h.source_kind,json_extract(h.metadata_json,'$.method') FROM harm_incidents h WHERE h.fatal=1").fetchall()
    out["deaths_by_cause"] = dict(Counter(r[3] for r in fatal))
    out["all_deceased_actors"] = conn.execute("SELECT COUNT(*) FROM actor_life_profiles WHERE life_status='deceased'").fetchone()[0]
    mob = [r for r in fatal if r[3] in MOB_SOURCES]
    out["mob_deaths_total"] = len(mob)
    out["mob_deaths_by_year"] = dict(sorted(Counter(int(r[1]) // 365 for r in mob).items()))

    def seat_of(actor):
        return conn.execute("SELECT s.role_key,s.org_actor_id,s.inducted_day FROM org_seats s WHERE s.actor_id=? ORDER BY (s.status='dead') DESC,s.id LIMIT 1", (int(actor),)).fetchone()
    mix = Counter()
    heads = {"boss", "underboss", "consigliere", "president", "elder", "banker", "senior", "principal"}
    for r in mob:
        s = seat_of(r[2])
        if s is None:
            mix["outsider (no seat)"] += 1
        elif s["role_key"] in heads:
            mix["head or executive"] += 1
        elif s["role_key"] in ("capo", "officer", "middle", "controller"):
            mix["officer (unit leader)"] += 1
        elif s["inducted_day"] is not None:
            mix["made man"] += 1
        else:
            mix["associate or other seated man"] += 1
    out["victim_mix_by_rank"] = dict(mix)

    # churn: made men lost (dead with an induction) against inductions, by year
    lost, inducted, joined = Counter(), Counter(), Counter()
    for r in conn.execute("SELECT left_day,status FROM org_seats WHERE inducted_day IS NOT NULL AND status IN ('dead','out','retired') AND left_day IS NOT NULL"):
        lost[(int(r[0]) // 365, r[1])] += 1
    for r in conn.execute("SELECT inducted_day FROM org_seats WHERE inducted_day>0"):
        inducted[int(r[0]) // 365] += 1
    for r in conn.execute("SELECT joined_day FROM org_seats WHERE joined_day>0 AND inducted_day IS NULL"):
        joined[int(r[0]) // 365] += 1
    out["made_men_lost_by_year_and_how"] = {f"{k[0]}:{k[1]}": v for k, v in sorted(lost.items())}
    out["inductions_by_year"] = dict(sorted(inducted.items()))
    out["new_associates_by_year"] = dict(sorted(joined.items()))
    out["sizes_by_year"] = {y: {names[o]: s for o, s in sorted(sz.items(), key=lambda kv: names[kv[0]])} for y, sz in sizes_by_year.items()}
    fell = []
    for o, (n0, m0) in start_sizes.items():
        n1 = sizes_by_year[max(sizes_by_year)].get(o, (0, 0))
        if m0 >= 15 and n1[1] < 0.6 * m0:
            fell.append(names[o])
    out["families_that_fell_apart"] = fell

    # tension
    out["tension_end"] = [(names[int(r[0])], names[int(r[1])], round(r[2], 1), round(r[3], 1)) for r in
                          conn.execute("SELECT from_org,to_org,level,peak FROM org_tension ORDER BY peak DESC LIMIT 20")]
    acts = Counter(r[0] for r in conn.execute("SELECT kind FROM org_tension_acts WHERE kind NOT IN ('history','wake')"))
    out["tension_acts"] = dict(acts.most_common())
    # first strike of each pair: the first killing of one side's man by the other, and what was moving the pair just before
    firsts = []
    seen = set()
    for r in conn.execute("SELECT day,from_org,to_org,actor_id,victim_id,note FROM org_tension_acts WHERE kind='killing' ORDER BY id"):
        pair = frozenset((int(r[1]), int(r[2])))
        if pair in seen:
            continue
        seen.add(pair)
        before = [(x[0], x[1], round(x[2], 1)) for x in conn.execute(
            "SELECT day,kind,delta FROM org_tension_acts WHERE ((from_org=? AND to_org=?) OR (from_org=? AND to_org=?)) AND day<=? AND kind NOT IN ('history','wake','strike') ORDER BY id DESC LIMIT 4",
            (r[1], r[2], r[2], r[1], r[0]))]
        firsts.append({"day": int(r[0]), "dead_man_org": names[int(r[1])], "killer_org": names[int(r[2])], "killing_preceded_by": before})
    out["first_killings_by_pair"] = firsts
    rungs = Counter()
    multi = []
    for r in conn.execute("SELECT day,from_org,to_org,note FROM org_tension_acts WHERE kind='strike' ORDER BY id"):
        rung, method, dead = (r[3] or "//").split("/")[:3] if r[3] else ("", "", "dead=0")
        rungs[f"{rung}/{method}"] += 1
        n = int(dead.split("=")[1]) if "=" in dead else 0
        if n >= 2:
            multi.append({"day": int(r[0]), "by": names[int(r[1])], "against": names[int(r[2])], "how": f"{rung}/{method}", "dead": n})
    out["strikes_by_rung_and_method"] = dict(rungs.most_common())
    out["multi_victim_attacks"] = multi
    out["killings_across_outfits"] = conn.execute("SELECT COUNT(*) FROM org_incidents WHERE kind='killing'").fetchone()[0]
    out["killings_across_by_year"] = dict(sorted(Counter(int(r[0]) // 365 for r in conn.execute("SELECT day FROM org_incidents WHERE kind='killing'")).items()))
    out["answers_to_killings"] = dict(conn.execute("SELECT status,COUNT(*) FROM org_incidents WHERE kind='killing' GROUP BY 1").fetchall())
    # how the independents and the outer ring took part: acts they were on either side of
    kinds_of = {int(r[0]): r[1] for r in conn.execute("SELECT org_actor_id,org_kind FROM org_profiles")}
    keys = {int(r[0]): r[1] for r in conn.execute("SELECT org_actor_id,package_key FROM org_profiles")}
    part = defaultdict(Counter)
    for r in conn.execute("SELECT from_org,to_org,kind FROM org_tension_acts WHERE kind NOT IN ('history','wake','strike','slight_own')"):
        for o in (int(r[0]), int(r[1])):
            if kinds_of.get(o) == "independent" or keys.get(o, "") in ("decavalcante", "genovesenj", "lucchesenj", "philadelphia", "gambino"):
                part[names[o]][r[2]] += 1
    out["independents_and_outer_ring_acts"] = {k: dict(v.most_common(8)) for k, v in sorted(part.items())}
    out["hired_jobs"] = conn.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='hit' AND json_extract(metadata_json,'$.hired')=1").fetchone()[0]
    out["heat_end"] = [(names[int(r[0])], round(r[1], 1), round(r[2], 1)) for r in conn.execute("SELECT org_actor_id,public_heat,violence_heat FROM org_heat ORDER BY public_heat DESC LIMIT 6")]
    out["kill_calls_by_caller_and_result"] = {f"{k[0]}:{k[1]}": v for k, v in sorted(callers.items(), key=lambda kv: -kv[1])}
    out["calibration"] = {"mob_killings_per_year": round(len(mob) / years, 1), "killings_across_per_year": round(out["killings_across_outfits"] / years, 1)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1825)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    res = report(a.days, a.seed)
    txt = json.dumps(res, indent=1, default=str)
    print(txt)
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
