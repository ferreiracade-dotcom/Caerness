"""PERF-01: hearing a rumour stores what is new for the hearer, not a fresh copy of the shared evidence.

Twenty people who hear the same rumour at the same place share one evidence row; each has their own access
and belief.  A first acquisition is not a belief *revision*; a later change of stance is.  The write-only
rumour->knowledge link is not written (knowledge_provenance already records the source)."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run():
    db = Path(tempfile.gettempdir()) / f"caerness_perf01_rows_{os.getpid()}.db"
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    os.environ["CAERNESS_DB_PATH"] = str(db); os.environ["CAERNESS_TEST_MODE"] = "1"
    from engine.db import reset_db, init_db, connect
    from engine.information import expose_actor_to_rumour
    from engine.belief import add_claim_evidence, observe_claim
    reset_db(force=True, backup=False); init_db(); c = connect()
    loc = int(c.execute("INSERT INTO locations(name,kind) VALUES ('Perf Market','town')").lastrowid)
    ev = int(c.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id) VALUES (0,'test','A cart overturns','A cart overturns in the market.',1,?)", (loc,)).lastrowid)
    rid = int(c.execute("INSERT INTO rumours(created_day,origin_location_id,text,truth_event_id,distortion,reach) VALUES (0,?,'A cart overturned in the market.',?,0.2,0.5)", (loc, ev)).lastrowid)
    c.execute("INSERT INTO rumour_locations(rumour_id,location_id,first_arrived_day,last_updated_day,prevalence,fidelity) VALUES (?,?,0,0,1.0,0.8)", (rid, loc))
    people = [int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)", (f"Perf Hearer {i}", loc, loc)).lastrowid) for i in range(20)]
    for p in people:
        assert expose_actor_to_rumour(c, rid, p, 0, loc, force=True) is not None
    claim = int(c.execute("SELECT id FROM information_claims WHERE claim_key=?", (f"rumour:{rid}",)).fetchone()[0])
    assert c.execute("SELECT COUNT(*) FROM claim_evidence WHERE claim_id=?", (claim,)).fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM actor_evidence_access aea JOIN claim_evidence ce ON ce.id=aea.evidence_id WHERE ce.claim_id=?", (claim,)).fetchone()[0] == 20
    assert c.execute("SELECT COUNT(*) FROM actor_beliefs WHERE claim_id=?", (claim,)).fetchone()[0] == 20
    assert c.execute("SELECT COUNT(*) FROM belief_revisions WHERE claim_id=?", (claim,)).fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM information_links WHERE source_kind='rumour' AND source_id=? AND target_kind='knowledge'", (rid,)).fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM knowledge_provenance kp JOIN knowledge k ON k.id=kp.knowledge_id WHERE k.fact_key=? AND kp.source_kind='rumour' AND kp.source_id=?", (f"rumour:{rid}", rid)).fetchone()[0] == 20
    # A strong contradiction reaches five of them: only their beliefs are revised.
    contra = add_claim_evidence(c, claim, evidence_kind="eyewitness", summary="No cart overturned; a stall collapsed.",
                                polarity="contradicts", reliability=0.95, location_id=loc, available_from_day=1)
    for p in people[:5]:
        observe_claim(c, p, claim, contra, received_day=1)
    revised = {int(r[0]) for r in c.execute("SELECT DISTINCT actor_id FROM belief_revisions WHERE claim_id=?", (claim,))}
    assert revised == set(people[:5]), revised
    c.close()
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    print("PERF-01 storage rows PASS")


if __name__ == "__main__":
    run()
