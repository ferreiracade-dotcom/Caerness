"""PERF-01: an actor's evidence for one claim is found from the claim side, not by scanning everything
the actor has ever heard.  The actor-first plan made each lookup grow with a person's whole history."""
from __future__ import annotations
import os, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import belief


def run():
    path = Path(tempfile.gettempdir()) / f"caerness_perf01_{os.getpid()}.db"
    for s in ("", "-wal", "-shm"):
        Path(str(path) + s).unlink(missing_ok=True)
    c = sqlite3.connect(path)
    schema = (ROOT / "engine" / "schema.sql").read_text(encoding="utf-8")
    c.executescript(schema)
    for sql in (belief.ACTOR_CLAIM_EVIDENCE_SQL, belief.ACTOR_CLAIM_EVIDENCE_DETAIL_SQL):
        plan = [r[3] for r in c.execute("EXPLAIN QUERY PLAN " + sql, (1, 1)).fetchall()]
        first = next(p for p in plan if p.startswith("SEARCH") or p.startswith("SCAN"))
        assert first.startswith("SEARCH ce USING INDEX idx_claim_evidence_claim"), plan
        assert any("aea" in p and "actor_id=? AND evidence_id=?" in p for p in plan), plan
    c.close()
    path.unlink(missing_ok=True)
    print("PERF-01 belief query plan PASS")


if __name__ == "__main__":
    run()
