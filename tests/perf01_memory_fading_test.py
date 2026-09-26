"""PERF-01 memory fading: people forget low-importance rumours nobody repeats; the world does not.

A bystander forgets a minor rumour after its retention time and can hear it again.  The event's target, the
target's kin and the player keep it.  A severity-5 event is kept by everyone.  Shared evidence is removed
only once nobody holds it; claims, rumours and events are never removed.  The rule depends only on the day,
so a monthly cadence and a single late pass give the same result."""
from __future__ import annotations
import os, shutil, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _world(path: Path):
    os.environ["CAERNESS_DB_PATH"] = str(path); os.environ["CAERNESS_TEST_MODE"] = "1"
    from engine.db import reset_db, init_db, connect
    from engine.information import expose_actor_to_rumour
    reset_db(force=True, backup=False); init_db(); c = connect()
    loc = int(c.execute("INSERT INTO locations(name,kind) VALUES ('Fade Market','town')").lastrowid)
    person = lambda n: int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES (?,'character',?,?)", (n, loc, loc)).lastrowid)
    ids = {n: person(n) for n in ("bystander", "target", "kin", "player", "loner")}
    c.execute("INSERT INTO kinship_links(actor_a_id,actor_b_id,kin_kind,started_day) VALUES (?,?,'sibling',0)", (ids["target"], ids["kin"]))
    c.execute("INSERT OR REPLACE INTO player_state(id,player_actor_id,current_location_id,updated_day) VALUES (1,?,?,0)", (ids["player"], loc))

    def rumour(title, severity, target=None):
        ev = int(c.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id) VALUES (0,'test',?,?,?,?)", (title, title, severity, loc)).lastrowid)
        if target:
            c.execute("INSERT INTO event_targets(event_id,actor_id) VALUES (?,?)", (ev, target))
        rid = int(c.execute("INSERT INTO rumours(created_day,origin_location_id,text,truth_event_id) VALUES (0,?,?,?)", (loc, title, ev)).lastrowid)
        c.execute("INSERT INTO rumour_locations(rumour_id,location_id,first_arrived_day,last_updated_day,prevalence,fidelity) VALUES (?,?,0,0,1.0,0.8)", (rid, loc))
        return rid

    minor = rumour("A quarrel over a mule", 1, target=ids["target"])
    great = rumour("A new Sixth is acknowledged", 5)
    lonely = rumour("A hat blew into the river", 1)
    for who in ("bystander", "target", "kin", "player"):
        for rid in (minor, great):
            assert expose_actor_to_rumour(c, rid, ids[who], 0, loc, force=True) is not None
    expose_actor_to_rumour(c, lonely, ids["loner"], 0, loc, force=True)
    c.commit()
    return c, ids, {"minor": minor, "great": great, "lonely": lonely}, loc


def _knows(c, actor, rid):
    return c.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND fact_key=?", (actor, f"rumour:{rid}")).fetchone() is not None


def _state(c):
    return sorted(tuple(r) for r in c.execute("SELECT knower_actor_id,fact_key FROM knowledge ORDER BY 1,2"))


def run():
    from engine.memory import process_due_memory, next_memory_due_day
    tmp = Path(tempfile.mkdtemp(prefix="caerness_fade_"))
    c, ids, r, loc = _world(tmp / "a.db")
    assert next_memory_due_day(c, 0, 100) == 30 and next_memory_due_day(c, 30, 45) is None
    # Nothing fades early.
    process_due_memory(c, 240)
    assert _knows(c, ids["bystander"], r["minor"])
    # Monthly cadence to day 600 (> 1.3 x the severity-1 retention of 365 days).
    for day in range(30, 601, 30):
        process_due_memory(c, day)
    assert not _knows(c, ids["bystander"], r["minor"])
    assert not c.execute("SELECT 1 FROM rumour_exposures WHERE rumour_id=? AND actor_id=?", (r["minor"], ids["bystander"])).fetchone()
    for who in ("target", "kin", "player"):
        assert _knows(c, ids[who], r["minor"]), who
    for who in ("bystander", "target", "kin", "player"):
        assert _knows(c, ids[who], r["great"]), who
    minor_claims = [int(x[0]) for x in c.execute("SELECT id FROM information_claims WHERE claim_key LIKE ?", (f"rumour:{r['minor']}%",))]
    assert minor_claims and not c.execute(f"SELECT 1 FROM actor_beliefs WHERE actor_id=? AND claim_id IN ({','.join('?'*len(minor_claims))})", (ids["bystander"], *minor_claims)).fetchone()
    # Evidence nobody holds is collected; claims, rumours and events stay.
    lonely_claim = int(c.execute("SELECT id FROM information_claims WHERE claim_key=?", (f"rumour:{r['lonely']}",)).fetchone()[0])
    assert not c.execute("SELECT 1 FROM claim_evidence WHERE claim_id=?", (lonely_claim,)).fetchone()
    assert c.execute("SELECT 1 FROM rumours WHERE id=?", (r["lonely"],)).fetchone()
    assert c.execute("SELECT 1 FROM claim_evidence WHERE claim_id IN (%s)" % ",".join("?" * len(minor_claims)), minor_claims).fetchone()
    # A forgotten rumour can be heard again.
    from engine.information import expose_actor_to_rumour
    assert expose_actor_to_rumour(c, r["minor"], ids["bystander"], 601, loc, force=True) is not None
    monthly = _state(c)
    c.close()

    # One late pass gives the same memories as the monthly cadence (before the re-hearing).
    c2, ids2, r2, loc2 = _world(tmp / "b.db")
    process_due_memory(c2, 600)
    assert not _knows(c2, ids2["bystander"], r2["minor"]) and _knows(c2, ids2["target"], r2["minor"])
    expose_actor_to_rumour(c2, r2["minor"], ids2["bystander"], 601, loc2, force=True)
    assert _state(c2) == monthly
    c2.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("PERF-01 memory fading PASS")


if __name__ == "__main__":
    run()
