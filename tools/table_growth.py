"""Estimate per-table data growth between two databases.  Usage: python tools/table_growth.py LATE.db BASE.db [N]"""
import sqlite3, sys
late = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True); base = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)
n_top = int(sys.argv[3]) if len(sys.argv) > 3 else 20
out = []
for (t,) in late.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall():
    cols = [r[1] for r in late.execute(f'pragma table_info("{t}")')]
    expr = '+'.join(f'coalesce(length(quote("{c}")),0)' for c in cols)
    b = late.execute(f'select count(*),sum({expr}) from "{t}"').fetchone()
    try: b0 = base.execute(f'select count(*),sum({expr}) from "{t}"').fetchone()
    except Exception: b0 = (0, 0)
    out.append(((b[1] or 0) - (b0[1] or 0), t, b0[0], b[0]))
out.sort(reverse=True)
for d, t, n0, n in out[:n_top]:
    print(f"{d/1e6:7.1f} MB  {t:38} rows {n0:>7} -> {n:>8}")
