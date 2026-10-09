"""PERF-01 audit retention: diagnostic trails keep about a year; history is never pruned.

Decision evaluations (and their candidate audits), mortality audits, growth snapshots and routine cultivation
practice reviews older than a year go.  Each entity's latest resolution review is always kept (the controller
reads it).  Breakthroughs, decisions themselves and events are history and stay."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run():
    db = Path(tempfile.gettempdir()) / f"caerness_audit_ret_{os.getpid()}.db"
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    os.environ["CAERNESS_DB_PATH"] = str(db); os.environ["CAERNESS_TEST_MODE"] = "1"
    from engine.db import reset_db, init_db, connect
    from engine.memory import prune_audit_logs
    reset_db(force=True, backup=False); init_db(); c = connect()
    loc = int(c.execute("INSERT INTO locations(name,kind) VALUES ('Audit Town','town')").lastrowid)
    a = int(c.execute("INSERT INTO actors(name,actor_type,current_location_id) VALUES ('Audited','character',?)", (loc,)).lastrowid)

    def cols(t):
        return {r[1]: r for r in c.execute(f"PRAGMA table_info({t})")}

    def insert(t, values):
        # Fill NOT NULL columns without defaults generically so the test follows the schema.
        info = cols(t); row = dict(values)
        for name, r in info.items():
            if name not in row and r[3] and r[4] is None and not r[5]:
                row[name] = 1 if "INT" in str(r[2]).upper() or "REAL" in str(r[2]).upper() else "x"
        keys = list(row)
        return int(c.execute(f"INSERT INTO {t}({','.join(keys)}) VALUES ({','.join('?' * len(keys))})", [row[k] for k in keys]).lastrowid)

    old_eval = insert("decision_evaluations", {"actor_id": a, "day": 10, "tier": "DORMANT"})
    new_eval = insert("decision_evaluations", {"actor_id": a, "day": 700, "tier": "DORMANT"})
    insert("decision_candidate_audit", {"evaluation_id": old_eval})
    insert("decision_candidate_audit", {"evaluation_id": new_eval})
    insert("mortality_audit", {"actor_id": a, "day": 10}); insert("mortality_audit", {"actor_id": a, "day": 700})
    insert("cultivation_history", {"actor_id": a, "day": 10, "history_kind": "practice_review", "summary": "old practice"})
    insert("cultivation_history", {"actor_id": a, "day": 10, "history_kind": "breakthrough_success", "summary": "old breakthrough"})
    insert("cultivation_history", {"actor_id": a, "day": 700, "history_kind": "practice_review", "summary": "new practice"})
    insert("resolution_reviews", {"entity_kind": "actor", "entity_id": a, "day": 10, "action": "none"})
    insert("resolution_reviews", {"entity_kind": "actor", "entity_id": a, "day": 20, "action": "none"})
    lone = int(c.execute("INSERT INTO actors(name,actor_type,current_location_id) VALUES ('Lone Reviewed','character',?)", (loc,)).lastrowid)
    insert("resolution_reviews", {"entity_kind": "actor", "entity_id": lone, "day": 5, "action": "none"})

    r = prune_audit_logs(c, 720)
    q = lambda sql, *p: c.execute(sql, p).fetchone()[0]
    assert q("SELECT COUNT(*) FROM decision_evaluations") == 1 and q("SELECT COUNT(*) FROM decision_candidate_audit") == 1
    assert q("SELECT COUNT(*) FROM mortality_audit") == 1
    assert q("SELECT COUNT(*) FROM cultivation_history WHERE history_kind='practice_review'") == 1
    assert q("SELECT COUNT(*) FROM cultivation_history WHERE history_kind='breakthrough_success'") == 1
    assert q("SELECT COUNT(*) FROM resolution_reviews WHERE entity_id=?", a) == 1
    assert q("SELECT day FROM resolution_reviews WHERE entity_id=?", a) == 20
    assert q("SELECT COUNT(*) FROM resolution_reviews WHERE entity_id=?", lone) == 1
    assert r["audit_rows_pruned"] >= 4, r
    c.close()
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    print("PERF-01 audit retention PASS", r)


if __name__ == "__main__":
    run()
