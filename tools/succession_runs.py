"""Measure the succession layers on a Saint Jude opening (task B12b): forced deaths and a long advance.

  python tools/succession_runs.py forced [--seeds 6] [--cause natural|insider|outsider|all]
      Each seed: a fresh copy of the opening; each family's head dies once in turn (a natural death, or killed by one of his own
      men, or by the head of another family); the weekly lifecycle runs until the contest (or the war it became) is over. Prints one
      line per death and a summary by outcome.
  python tools/succession_runs.py five [--days 1825] [--seed N]
      One advance of N days on a copy of the opening; counts the plots, coups, heirs, contests, wars and splits that arose.

It builds on copies in a temporary folder and never touches data/*.db.
"""
from __future__ import annotations

import argparse
import json
import os
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
    return conn


def _meta(row):
    return json.loads(row["metadata_json"] or "{}")


def _families(conn):
    return [int(r[0]) for r in conn.execute("SELECT org_actor_id FROM org_profiles WHERE package_key IN ('sabatini','pellegrino','ferrante','vannucci') ORDER BY org_actor_id")]


def forced(seeds: int, causes: list[str]) -> None:
    from engine import org_lifecycle, orgs, org_succession as su, outfit_choices
    tally: Counter = Counter()
    heir_named = Counter()
    by_role: Counter = Counter()
    contested_n: Counter = Counter()
    for cause in causes:
        for seed in range(seeds):
            conn = _open(5000 + seed)
            day = int(conn.execute("SELECT current_day FROM world_state WHERE id=1").fetchone()[0]) + 5
            for org in _families(conn):
                head = orgs.head_of(conn, org)
                roles_before = {int(r["actor_id"]): r["role_key"] for r in orgs.members(conn, org)}
                name = conn.execute("SELECT name FROM actors WHERE id=?", (org,)).fetchone()[0]
                # the head's own succession preference, as the weekly pass would have formed it by now (forced draw)
                from engine import org_motives
                old = org_motives._roll
                org_motives._roll = lambda c, a, d, s: 0.0 if s in ("heir_form", "heir_show") else old(c, a, d, s)
                try:
                    su._heirs(conn, day)
                finally:
                    org_motives._roll = old
                heir = su.heir_of(conn, org, head)
                backers = su.backers(conn, org)
                if cause == "natural":
                    conn.execute("UPDATE actors SET status='dead' WHERE id=?", (head,))
                elif cause == "insider":
                    killer = max((b for b in backers), key=lambda b: (su.drive(conn, b, "ambition"), -b))
                    outfit_choices.kill(conn, killer, head, day, sanctioned=False)
                else:
                    other = next(o for o in _families(conn) if o != org)
                    outfit_choices.kill(conn, orgs.head_of(conn, other), head, day, sanctioned=False)
                d, out = day, None
                for week in range(1, 80):
                    org_lifecycle.process_due(conn, d)
                    d += 7
                    open_rows = conn.execute("SELECT 1 FROM org_agenda WHERE kind IN ('contest','civil_war') AND status='open' AND (actor_id=?)", (org,)).fetchone()
                    if not open_rows and week >= 1:
                        break
                contest = conn.execute("SELECT * FROM org_agenda WHERE kind='contest' AND actor_id=? ORDER BY id DESC LIMIT 1", (org,)).fetchone()
                war = conn.execute("SELECT * FROM org_agenda WHERE kind='civil_war' AND actor_id=? ORDER BY id DESC LIMIT 1", (org,)).fetchone()
                m = _meta(contest) if contest is not None else {}
                outcome = m.get("outcome", "?")
                detail = ""
                if war is not None:
                    wm = _meta(war)
                    detail = f" war:{wm.get('how', 'open')}" + (f" split->{wm.get('new_org')}" if wm.get("new_org") else "")
                    outcome = f"{outcome}>{wm.get('how', 'open')}"
                new = orgs.head_of(conn, org)
                role_before = roles_before.get(new)
                won_heir = heir is not None and m.get("winner") == heir
                tally[(cause, outcome)] += 1
                heir_named[(cause, heir is not None, won_heir)] += 1
                by_role[(cause, role_before if not won_heir else "heir")] += 1
                contested = outcome not in ("agreed", "coup") or int(m.get("weeks") or 0) > 3
                contested_n[(cause, contested)] += 1
                print(f"{cause:9} seed {seed} {name:20} heir={'yes' if heir else 'no '} weeks={m.get('weeks', '-'):>3} outcome={outcome:22}{detail} winner was {role_before} won_by_heir={won_heir}")
            conn.close()
    print("\nSUMMARY by cause and outcome")
    for (cause, out), n in sorted(tally.items()):
        print(f"  {cause:9} {out:24} {n}")
    print("heir named / heir won (cause, named, heir_won): ", dict(heir_named))
    print("winner by role before (heir counted apart): ", dict(by_role))
    print("contested (more than three weeks, or anything but agreed): ", dict(contested_n))


def five(days: int, seed: int | None) -> None:
    from engine.simulation import advance_connection
    conn = _open(seed)
    t0 = time.time()
    for y in range(0, days, 365):
        advance_connection(conn, min(365, days - y))
    secs = time.time() - t0
    kinds = ("heir", "plot", "plot_found", "contest", "civil_war", "acting_head", "fill_unit_leader_seat", "killed_by")
    print(f"advanced {days} days in {secs:.0f}s")
    for k in kinds:
        rows = conn.execute("SELECT status,COUNT(*) FROM org_agenda WHERE kind=? GROUP BY status", (k,)).fetchall()
        print(f"  {k:24}", {r[0]: r[1] for r in rows})
    print("  heirs shown:", conn.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='heir' AND json_extract(metadata_json,'$.shown')=1").fetchone()[0])
    print("  plots by ending:", dict(conn.execute("SELECT COALESCE(json_extract(metadata_json,'$.found'),json_extract(metadata_json,'$.ended'),CASE WHEN json_extract(metadata_json,'$.struck') THEN 'struck' END,'open'),COUNT(*) FROM org_agenda WHERE kind='plot' GROUP BY 1").fetchall()))
    print("  contests:", [(_meta(r).get("cause"), _meta(r).get("outcome"), _meta(r).get("weeks")) for r in conn.execute("SELECT * FROM org_agenda WHERE kind='contest'")])
    print("  wars:", [(_meta(r).get("cause"), _meta(r).get("how")) for r in conn.execute("SELECT * FROM org_agenda WHERE kind='civil_war'")])
    print("  appointments made (unit leaders named):", conn.execute("SELECT COUNT(*) FROM org_agenda WHERE kind='history' AND json_extract(metadata_json,'$.reason')='rose to lead a unit'").fetchone()[0])
    print("  organisations now:", conn.execute("SELECT COUNT(*) FROM org_profiles WHERE package_key LIKE '%~split%'").fetchone()[0], "split off;",
          conn.execute("SELECT COUNT(*) FROM org_profiles").fetchone()[0], "in all")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["forced", "five"])
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--cause", default="all")
    ap.add_argument("--days", type=int, default=1825)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    if a.mode == "forced":
        forced(a.seeds, ["natural", "insider", "outsider"] if a.cause == "all" else [a.cause])
    else:
        five(a.days, a.seed)
