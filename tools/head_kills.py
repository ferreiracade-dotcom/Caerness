"""Who killed the heads, and why (task B13b). Runs N days on a copy of the Saint Jude opening and lists every landed killing of a man
holding a head's seat: killer and his seat, the function that asked for it, the day. Reports; enforces nothing.

  python tools/head_kills.py [--days 1095] [--seed 7]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1095)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--nopass", action="store_true", help="no package memo during a skip (for comparison)")
    ap.add_argument("--nocover", action="store_true", help="switch the B13b guard and cover terms off (for comparison)")
    a = ap.parse_args()
    from tools.lethality_runs import _open
    from engine.simulation import advance_connection
    import engine.outfit_choices as oc
    conn = _open(a.seed)
    if a.nopass:
        import contextlib
        import engine.world_package as wp
        wp.package_pass = contextlib.nullcontext
    real = oc.kill
    log: list = []
    if a.nocover:
        import engine.org_tension as ot
        ot.protection = lambda conn_, man: (0.0, 0.0)
        conn.execute("UPDATE design_figures SET value=0 WHERE key GLOB 'ten_*' AND key<>'ten_guard_half'")
        conn.commit()

    def seat(actor):
        r = conn.execute("SELECT s.role_key,a.name FROM org_seats s JOIN actors a ON a.id=s.org_actor_id WHERE s.actor_id=? AND s.status='active' ORDER BY s.id LIMIT 1", (int(actor),)).fetchone()
        return None if r is None else (r[0], r[1])

    def wrapped(c, killer, victim, day, **kw):
        vs, ks = seat(victim), seat(killer)
        res = real(c, killer, victim, day, **kw)
        dead = not conn.execute("SELECT 1 FROM actors WHERE id=? AND status='active'", (int(victim),)).fetchone()
        fr = sys._getframe(1)
        pl = fr.f_locals.get("payload") or fr.f_locals.get("plan") or {}
        why = {k: pl.get(k) for k in ("tension", "retaliation", "hired", "ordered_by", "sanctioned", "rung", "method") if isinstance(pl, dict) and pl.get(k) is not None}
        # who asked: the orderer's seat and whether the dead head's own man is the killer
        ob = why.get("ordered_by")
        why["orderer_seat"] = seat(ob) if ob else None
        log.append((int(day), fr.f_code.co_name, ks, vs, int(killer), int(victim), dead, why))
        return res
    oc.kill = wrapped
    for m in list(sys.modules.values()):
        if getattr(m, "kill", None) is real:
            m.kill = wrapped
    done = 0
    while done < a.days:
        advance_connection(conn, min(30, a.days - done))
        done += 30
    roles = Counter()
    heads = []
    for d, fn, ks, vs, k, v, dead, sanc in log:
        if dead:
            roles[(vs or ("outsider", ""))[0]] += 1
        if dead and vs and vs[0] == "boss":
            heads.append((d, fn, ks, vs, k, v, sanc))
    print("landed by function", dict(Counter(fn for d, fn, ks, vs, k, v, dead, why in log if dead)))
    print("landed by year", dict(sorted(Counter(d // 365 for d, fn, ks, vs, k, v, dead, why in log if dead).items())))
    acts = [r[0] for r in conn.execute("SELECT note FROM org_tension_acts WHERE kind='strike'")]
    print("strikes by rung", dict(Counter(n.split('/')[0] for n in acts)), "by method", dict(Counter(n.split('/')[1] for n in acts)))
    print(f"seed {a.seed} days {a.days}: landed killings by victim role {dict(roles)}; total landed {sum(roles.values())}")
    print(f"heads killed: {len(heads)}")
    for h in heads:
        print("  day %d by %s: killer %s seat %s -> head of %s why=%s" % (h[0], h[1], h[4], h[2], h[3], h[6]))
    print("heads: by function", dict(Counter(h[1] for h in heads)))


if __name__ == "__main__":
    main()
