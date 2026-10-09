"""PERF-01 news fading: rumours stop circulating once they stop moving; old spread records are pruned.

A minor rumour that has not reached anywhere new for its staleness time fades: it is no longer heard as local
news, and its per-place spread rows and transmissions are dropped.  The rumour and its event remain (world
history), and people's memories of it follow memory fading, not news fading.  A great event stays news
longer.  Delivered transmissions of circulating rumours are pruned after 90 days."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run():
    db = Path(tempfile.gettempdir()) / f"caerness_news_fade_{os.getpid()}.db"
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    os.environ["CAERNESS_DB_PATH"] = str(db); os.environ["CAERNESS_TEST_MODE"] = "1"
    from engine.db import reset_db, init_db, connect
    from engine.information import hear_local_rumours, expose_actor_to_rumour
    from engine.memory import process_due_memory
    reset_db(force=True, backup=False); init_db(); c = connect()
    loc = int(c.execute("INSERT INTO locations(name,kind) VALUES ('News Square','town')").lastrowid)
    other = int(c.execute("INSERT INTO locations(name,kind) VALUES ('News Road','village')").lastrowid)

    def rumour(title, severity):
        ev = int(c.execute("INSERT INTO events(day,event_type,title,summary,severity,location_id) VALUES (0,'test',?,?,?,?)", (title, title, severity, loc)).lastrowid)
        rid = int(c.execute("INSERT INTO rumours(created_day,origin_location_id,text,truth_event_id) VALUES (0,?,?,?)", (loc, title, ev)).lastrowid)
        c.execute("INSERT INTO rumour_locations(rumour_id,location_id,first_arrived_day,last_updated_day,prevalence,fidelity) VALUES (?,?,0,0,0.9,0.8)", (rid, loc))
        c.execute("INSERT INTO rumour_transmissions(rumour_id,from_location_id,to_location_id,due_day,fidelity,prevalence,hop_count,status) VALUES (?,?,?,5,0.7,0.5,1,'delivered')", (rid, loc, other))
        return rid, ev

    minor, minor_ev = rumour("A goat escaped", 1)
    great, great_ev = rumour("The Emperor fell ill", 5)
    listener = int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES ('News Listener','character',?,?)", (loc, loc)).lastrowid)
    keeper = int(c.execute("INSERT INTO actors(name,actor_type,current_location_id,home_location_id) VALUES ('News Keeper','character',?,?)", (loc, loc)).lastrowid)
    expose_actor_to_rumour(c, minor, keeper, 0, loc, force=True)

    process_due_memory(c, 120)
    # Still news at day 120; the delivered transmission (day 5) is older than 90 days and is pruned.
    assert c.execute("SELECT status FROM rumours WHERE id=?", (minor,)).fetchone()[0] == "circulating"
    assert not c.execute("SELECT 1 FROM rumour_transmissions WHERE rumour_id=?", (minor,)).fetchone()

    process_due_memory(c, 210)
    assert c.execute("SELECT status FROM rumours WHERE id=?", (minor,)).fetchone()[0] == "faded"
    assert not c.execute("SELECT 1 FROM rumour_locations WHERE rumour_id=?", (minor,)).fetchone()
    assert c.execute("SELECT 1 FROM events WHERE id=?", (minor_ev,)).fetchone()
    assert c.execute("SELECT status FROM rumours WHERE id=?", (great,)).fetchone()[0] == "circulating"
    assert c.execute("SELECT 1 FROM rumour_locations WHERE rumour_id=?", (great,)).fetchone()
    # A newcomer hears the great event as local news, not the stale goat; the keeper still remembers the goat.
    assert hear_local_rumours(c, listener, loc, 210, limit=8, force_top=8) == 1
    assert c.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND fact_key=?", (listener, f"rumour:{great}")).fetchone()
    assert c.execute("SELECT 1 FROM knowledge WHERE knower_actor_id=? AND fact_key=?", (keeper, f"rumour:{minor}")).fetchone()
    # No write-only spread links.
    assert not c.execute("SELECT 1 FROM information_links WHERE relation='spread_via'").fetchone()
    c.close()
    for s in ("", "-wal", "-shm"):
        Path(str(db) + s).unlink(missing_ok=True)
    print("PERF-01 news fading PASS")


if __name__ == "__main__":
    run()
